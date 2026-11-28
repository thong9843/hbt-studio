"""Bộ dựng video StickV v6.1: stream khung hình lip-sync/karaoke trực tiếp vào FFmpeg (nhẹ RAM)."""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import math
import os
import queue
import shutil
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from hbt.app_settings import AppSettingsStore
from hbt.config import load_settings
from hbt.pipeline import whisper as _whisper
from hbt.pipeline.audio import build_outro_audio
from hbt.pipeline.cancel import CancelToken
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe
from hbt.pipeline.whisper import WhisperConfig
from hbt.postv.voice import VoiceProvider
from hbt.shared.ffmpeg_utils import (
    FFMPEG_ENCODE_CLAMP,
    FFMPEG_RESOURCE_CLAMP,
    WINDOWS_LOW_PRIO_FLAGS,
    measure_audio_duration,
)
from hbt.shared.ffmpeg_utils import (
    run_ffmpeg_low_prio as run_ffmpeg,
)
from hbt.shared.online_sources.reference_images import (
    DEFAULT_AI_IMAGE_BUDGET,
    REF_CACHE_VERSION,
    resolve_reference_image,
)
from hbt.shared.pipeline.watermark import (
    WatermarkSettings,
    render_watermark_png,
)
from hbt.stickv.animator import StickmanAnimator
from hbt.stickv.audio import (
    GLOBAL_LEAD_SILENCE_S,
    LEAD_IN_SILENCE_S,
    BeatTimelineEntry,
    align_beat_karaoke,
    align_stickv_master_karaoke,
    build_master_voice_wav,
    compute_pause_after,
    extract_wav_rms_envelope,
    load_beat_spoken_segments,
    mix_stickv_audio,
    synth_stickv_beats_audio,
    verify_zero_drift_timeline,
)
from hbt.stickv.backdrops import DOMAIN_PALETTES, BackdropRenderer, normalize_domain
from hbt.stickv.beat_cache import (
    StickvBeatCache,
    compute_beat_cache_key,
    hash_file_sha256,
)
from hbt.stickv.llm import classify_beat_visual_mode
from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvBeat, StickvProject, StickvTheme
from hbt.stickv.puppet import PuppetAssetCache, is_puppet_ready, normalize_stickv_pose
from hbt.stickv.stage import (
    BeatStageState,
    _pick_visual_first_title,
    close_stage_cache,
    compute_beat_character_target,
    compute_camera_state,
    compute_layered_camera_layout,
    infer_auto_prop_query,
    render_animated_beat_frame,
    render_beat_layers,
)

logger = logging.getLogger(__name__)


class _AsyncPipeWriter:
    """Đẩy raw RGB24 vào FFmpeg qua hàng đợi nhỏ (4 frame ≈ 25MB) để không nghẽn luồng Pillow."""

    def __init__(self, pipe: Any, max_buffered: int = 4) -> None:
        self._pipe = pipe
        self._q: queue.Queue[bytes | None] = queue.Queue(maxsize=max_buffered)
        self._err: BaseException | None = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="ffmpeg-pipe-writer", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while True:
                chunk = self._q.get()
                if chunk is None:
                    break
                self._pipe.write(chunk)
        except BaseException as exc:  # noqa: BLE001
            self._err = exc

    def write(self, data: bytes) -> None:
        if self._err is not None:
            raise self._err
        self._q.put(data)

    def finish(self) -> None:
        if not self._closed:
            self._closed = True
            self._q.put(None)
        self._thread.join(timeout=10.0)
        if self._err is not None:
            raise self._err

    def abort(self) -> None:
        if not self._closed:
            self._closed = True
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            try:
                self._q.put_nowait(None)
            except queue.Full:
                pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)


# Chuẩn mã hóa tương thích tuyệt đối với Windows Media Player & mọi thiết bị di động
STICKV_MP4_COMPAT_FLAGS: tuple[str, ...] = (
    "-pix_fmt",
    "yuv420p",
    "-profile:v",
    "high",
    "-level",
    "4.1",
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-ar",
    "48000",
    "-movflags",
    "+faststart",
)


def allocate_beat_frame_counts(
    beat_durations: Sequence[float],
    fps: int,
) -> list[int]:
    """Khóa đồng hồ tích lũy A/V: `end_frame_i = round(acc_audio * fps)` (lệch <= 1 frame)."""
    eff_fps = max(1, int(fps))
    counts: list[int] = []
    acc_frames = 0
    acc_audio_s = 0.0
    for dur in beat_durations:
        acc_audio_s += max(0.0, float(dur))
        end_frame = max(acc_frames + 1, int(round(acc_audio_s * eff_fps)))
        counts.append(end_frame - acc_frames)
        acc_frames = end_frame
    return counts


def _stream_beat_frames_to_ffmpeg(
    *,
    beat: StickvBeat,
    wav_path: Path,
    bg_png: Path,
    char_png: Path | None,
    out_mp4: Path,
    w: int,
    h: int,
    fps: int,
    aspect: str,
    library_dir: Path,
    assets_dir: Path,
    domain: str = "paper_classic",
    theme: StickvTheme = "cream",
    animation_mode: str = "auto",
    pause_scale: float = 1.0,
    cancel: CancelToken | None = None,
    global_frame_offset: int = 0,
    n_frames_override: int | None = None,
    prev_stage_state: BeatStageState | None = None,
    stage_state_out: dict[str, Any] | None = None,
    backdrop_renderer: BackdropRenderer | None = None,
    asset_cache: PuppetAssetCache | None = None,
    watermark_img: Image.Image | None = None,
) -> Path:
    """Stream từng khung hình RGB (backdrop liên tục + tween + animator + karaoke) vào FFmpeg."""
    dur = max(1.0, float(beat.duration_sec or 2.0))
    n_frames = n_frames_override if n_frames_override is not None else max(1, int(round(dur * fps)))
    rms_env = extract_wav_rms_envelope(wav_path, fps, dur)
    pause_after = compute_pause_after(beat.narration, pause_scale=pause_scale)
    lead_in = (
        GLOBAL_LEAD_SILENCE_S if global_frame_offset == 0 else (LEAD_IN_SILENCE_S * pause_scale)
    )
    spoken_segs = load_beat_spoken_segments(wav_path)
    speech_start = spoken_segs[0][0] if spoken_segs else lead_in
    speech_end = (
        min(dur, spoken_segs[-1][1]) if spoken_segs else max(lead_in + 0.3, dur - pause_after)
    )
    word_timings = align_beat_karaoke(
        beat.narration,
        wav_path,
        dur,
        lead_in_s=speech_start,
        pause_after_s=pause_after,
        spoken_segments=spoken_segs,
    )

    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = out_mp4.with_name(f"{out_mp4.stem}.tmp.mp4")
    cmd = [
        ffmpeg_exe(),
        "-y",
        *FFMPEG_RESOURCE_CLAMP,
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        *FFMPEG_ENCODE_CLAMP,
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-video_track_timescale",
        "90000",
        str(tmp_mp4),
    ]

    norm_domain = normalize_domain(domain)
    owns_backdrop = backdrop_renderer is None
    backdrop = (
        backdrop_renderer if backdrop_renderer is not None else BackdropRenderer(norm_domain, w, h)
    )
    char_img: Image.Image | None = None
    if char_png is not None and char_png.is_file():
        with Image.open(char_png) as raw_char:
            char_img = raw_char.convert("RGBA")

    target_char_h = (
        char_img.height if char_img is not None else int(h * (0.48 if aspect == "9:16" else 0.56))
    )
    interaction = getattr(beat, "interaction", "none") or "none"
    animator = StickmanAnimator(
        pose=beat.pose,
        anim_oneshot=getattr(beat, "anim_oneshot", None),
        anim_loop=getattr(beat, "anim_loop", None),
        facing=beat.facing,
        duration_sec=dur,
        speech_start=speech_start,
        speech_end=speech_end,
        fps=fps,
        rms_env=rms_env,
        library_dir=library_dir,
        assets_dir=assets_dir,
        target_height=target_char_h,
        char_img_fallback=char_img,
        interaction=interaction,
        emotion=getattr(beat, "emotion", "auto"),
        face_mood=getattr(beat, "face_mood", None),
        narration=beat.narration,
        beat_id=beat.id,
        animation_mode=animation_mode,
        wav_path=wav_path,
        prev_pose_state=prev_stage_state.pose_state if prev_stage_state is not None else None,
        global_t_offset=global_frame_offset / max(1, fps),
        asset_cache=asset_cache,
    )

    prop_img, _ = _resolve_beat_visual_image(
        beat,
        project_dir=out_mp4.parents[2],
        library_dir=library_dir,
        accent=DOMAIN_PALETTES[norm_domain]["accent"],
    )

    last_char_size: tuple[int, int] | None = None
    beat_board_cache: dict[str, Any] = {}
    karaoke_cache: dict[str, Any] = {}
    err_log_path = out_mp4.with_name(f"{out_mp4.stem}.ffmpeg.err.log")
    err_file = open(err_log_path, "wb")  # noqa: SIM115
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=err_file,
        creationflags=WINDOWS_LOW_PRIO_FLAGS,
    )
    try:
        assert proc.stdin is not None
        for f_idx in range(n_frames):
            if cancel is not None and f_idx % 8 == 0:
                cancel.check()
            t_sec = f_idx / fps
            global_t = (global_frame_offset + f_idx) / fps
            mouth = rms_env[f_idx] if f_idx < len(rms_env) else 0.0
            if interaction == "versus_split":
                animator.facing = "left" if t_sec < dur * 0.5 else "right"
            bg_frame = backdrop.render_frame_rgba(global_t)
            anim_char, motion = animator.frame_at(f_idx, t_sec)
            if anim_char is not None:
                last_char_size = anim_char.size
            try:
                frame = render_animated_beat_frame(
                    bg_img=bg_frame,
                    char_img=anim_char,
                    beat=beat,
                    aspect=aspect,  # type: ignore[arg-type]
                    t_sec=t_sec,
                    mouth_open=0.0 if motion.phase == "puppet" else mouth,
                    word_timings=word_timings,
                    prop_img=prop_img,
                    domain=norm_domain,
                    theme=theme,
                    duration_sec=dur,
                    draw_board=True,
                    extra_dy=motion.dy if motion.used_fallback else 0.0,
                    prev_stage_state=prev_stage_state,
                    spoken_segments=spoken_segs or None,
                    is_puppet=motion.phase == "puppet",
                    board_cache=beat_board_cache,
                    mutate_bg=True,
                    karaoke_cache=karaoke_cache,
                    watermark_img=watermark_img,
                )
            finally:
                bg_frame.close()
                if anim_char is not None:
                    anim_char.close()
            try:
                proc.stdin.write(frame.tobytes())
            finally:
                frame.close()
        if proc.stdin is not None:
            proc.stdin.flush()
            proc.stdin.close()
            proc.stdin = None
        proc.wait(timeout=300.0)
        err_file.close()
        if proc.returncode != 0:
            err_tail = (
                err_log_path.read_text(encoding="utf-8", errors="replace")[-300:]
                if err_log_path.is_file()
                else ""
            )
            raise FFmpegError(f"FFmpeg stream beat {beat.id} lỗi ({proc.returncode}): {err_tail}")
        os.replace(tmp_mp4, out_mp4)
        if stage_state_out is not None:
            cw, ch_h = last_char_size or (
                (char_img.width, char_img.height) if char_img is not None else (240, target_char_h)
            )
            tx, ty, tsc = compute_beat_character_target(
                w,
                h,
                cw,
                ch_h,
                interaction=interaction,
                aspect=aspect,  # type: ignore[arg-type]
            )
            stage_state_out["state"] = BeatStageState(
                x=tx,
                y=ty,
                scale=tsc,
                pose_state=animator.last_pose_state,
                last_board_title=(beat.board_title or "").strip(),
                last_board_type=beat.board_type,
                last_chapter=beat.chapter,
                last_visual_title=_pick_visual_first_title(beat),
            )
    finally:
        close_stage_cache(beat_board_cache)
        close_stage_cache(karaoke_cache)
        try:
            err_file.close()
        except Exception:
            pass
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass
        err_log_path.unlink(missing_ok=True)
        if tmp_mp4.exists():
            tmp_mp4.unlink(missing_ok=True)
        if owns_backdrop:
            backdrop.close()
        animator.close()
        if char_img is not None:
            char_img.close()
        if prop_img is not None:
            prop_img.close()
    return out_mp4


def _resolve_beat_video_clip(
    beat: StickvBeat,
    *,
    project_dir: Path,
    library_dir: Path,
    assets_dir: Path,
) -> Path | None:
    """Tìm file Video Pose (.mp4/.mov/.webm) từ clip_path hoặc media_path."""
    raw = (beat.clip_path or beat.media_path or "").strip()
    if not raw:
        return None
    name = Path(raw.split("?")[0]).name
    candidates = [
        project_dir / raw,
        assets_dir / "stickman" / name,
        library_dir / "stickman" / name,
        library_dir / "stickman" / "poses" / name,
    ]
    for c in candidates:
        if c.is_file() and c.suffix.lower() in {".mp4", ".mov", ".webm"}:
            return c
    return None


def _render_single_beat_clip(
    *,
    beat: StickvBeat,
    wav_path: Path,
    bg_png: Path,
    char_png: Path | None,
    out_mp4: Path,
    w: int,
    h: int,
    fps: int,
    aspect: str,
    project_dir: Path,
    library_dir: Path,
    assets_dir: Path,
    domain: str = "paper_classic",
    theme: StickvTheme = "cream",
    animation_mode: str = "auto",
    pause_scale: float = 1.0,
    cancel: CancelToken | None = None,
    global_frame_offset: int = 0,
    n_frames_override: int | None = None,
    prev_stage_state: BeatStageState | None = None,
    stage_state_out: dict[str, Any] | None = None,
    backdrop_renderer: BackdropRenderer | None = None,
    asset_cache: PuppetAssetCache | None = None,
    watermark_img: Image.Image | None = None,
    watermark_png: Path | None = None,
) -> Path:
    dur = max(1.0, float(beat.duration_sec or 2.0))
    media_file = _resolve_beat_video_clip(
        beat, project_dir=project_dir, library_dir=library_dir, assets_dir=assets_dir
    )

    if media_file is not None:
        clip_dur = measure_audio_duration(media_file)
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps},format=yuv420p"
        )
        loop_args = ["-stream_loop", "-1"] if (clip_dur <= 0 or clip_dur < dur) else []
        if watermark_png is not None and watermark_png.is_file():
            cmd = [
                *FFMPEG_RESOURCE_CLAMP,
                *loop_args,
                "-i",
                str(media_file),
                "-i",
                str(watermark_png),
                "-t",
                f"{dur:.3f}",
                "-an",
                "-filter_complex",
                f"[0:v]{vf}[vbase];[vbase][1:v]overlay=0:0:format=auto[vout]",
                "-map",
                "[vout]",
                *FFMPEG_ENCODE_CLAMP,
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "high",
                "-level",
                "4.1",
                str(out_mp4),
            ]
        else:
            cmd = [
                *FFMPEG_RESOURCE_CLAMP,
                *loop_args,
                "-i",
                str(media_file),
                "-t",
                f"{dur:.3f}",
                "-an",
                "-vf",
                vf,
                *FFMPEG_ENCODE_CLAMP,
                str(out_mp4),
            ]
        run_ffmpeg(cmd)
        return out_mp4

    return _stream_beat_frames_to_ffmpeg(
        beat=beat,
        wav_path=wav_path,
        bg_png=bg_png,
        char_png=char_png,
        out_mp4=out_mp4,
        w=w,
        h=h,
        fps=fps,
        aspect=aspect,
        library_dir=library_dir,
        assets_dir=assets_dir,
        domain=domain,
        theme=theme,
        animation_mode=animation_mode,
        pause_scale=pause_scale,
        cancel=cancel,
        global_frame_offset=global_frame_offset,
        n_frames_override=n_frames_override,
        prev_stage_state=prev_stage_state,
        stage_state_out=stage_state_out,
        backdrop_renderer=backdrop_renderer,
        asset_cache=asset_cache,
        watermark_img=watermark_img,
    )


def _resolve_outro_clip(brand_dir: Path, fps: int) -> Path | None:
    outro_dir = Path(brand_dir) / "outro"
    candidates = (
        [outro_dir / "outro_4s_60fps.mp4", outro_dir / "outro_4s_50fps.mp4"]
        if fps >= 50
        else [outro_dir / "outro_4s_50fps.mp4", outro_dir / "outro_4s_60fps.mp4"]
    )
    for c in candidates:
        if c.is_file():
            return c
    return None


def group_beats_into_chunks(
    beats: list[StickvBeat],
    beat_wavs: list[tuple[Path, float]],
    *,
    project_dir: Path,
    library_dir: Path,
    assets_dir: Path,
    max_chunk_sec: float = 48.0,
    min_chapter_split_sec: float = 24.0,
) -> list[tuple[str, list[tuple[int, StickvBeat, Path, float]]]]:
    """Gom các beat thành cụm theo chương (~30–60s/cụm) để render dài không tràn RAM."""
    chunks: list[tuple[str, list[tuple[int, StickvBeat, Path, float]]]] = []
    cur_items: list[tuple[int, StickvBeat, Path, float]] = []
    cur_dur = 0.0
    cur_chapter: int | None = None

    for g_idx, (beat, (wav_p, dur_b)) in enumerate(zip(beats, beat_wavs, strict=True)):
        dur_val = max(1.0, float(dur_b or 2.0))
        media_clip = _resolve_beat_video_clip(
            beat, project_dir=project_dir, library_dir=library_dir, assets_dir=assets_dir
        )
        if media_clip is not None:
            if cur_items:
                chunks.append(("stream", cur_items))
                cur_items = []
                cur_dur = 0.0
                cur_chapter = None
            chunks.append(("video", [(g_idx, beat, wav_p, dur_val)]))
            continue

        crossed_chapter = cur_chapter is not None and beat.chapter != cur_chapter
        if cur_items and (
            (cur_dur + dur_val > max_chunk_sec)
            or (crossed_chapter and cur_dur >= min_chapter_split_sec)
        ):
            chunks.append(("stream", cur_items))
            cur_items = []
            cur_dur = 0.0

        cur_items.append((g_idx, beat, wav_p, dur_val))
        cur_dur += dur_val
        cur_chapter = beat.chapter

    if cur_items:
        chunks.append(("stream", cur_items))
    return chunks


_SCENE_QUERY_HINTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("kiến trúc sư", "cố tình", "lầm tưởng", "ý đồ"),
        "medieval architecture tilted tower blueprint",
        "2D editorial illustration of an astonished medieval architect inspecting a tilting "
        "stone tower blueprint, no text, no labels, no arrows, no watermark",
    ),
    (
        ("cát mịn", "bùn non", "địa chất", "mềm yếu", "thổ nhưỡng", "nền móng"),
        "soft clay soil foundation geology layers",
        "2D cross-section editorial illustration of a heavy marble tower base sinking "
        "into soft sandy clay soil strata, no text, no labels, no arrows, no watermark",
    ),
    (
        ("chiến tranh", "gián đoạn", "ngừng nghỉ", "thế kỷ"),
        "medieval war history fortification italy",
        "2D editorial storybook scene of an unfinished stone tower standing quietly in "
        "medieval Italy during wartime pause, no text, no labels, no arrows, no watermark",
    ),
    (
        ("nén chặt", "ổn định", "cân bằng", "nghỉ"),
        "ground settlement equilibrium structure",
        "2D editorial illustration showing compacted soil beneath a stabilized historic "
        "monument at golden hour, no text, no labels, no arrows, no watermark",
    ),
    (
        ("kỹ sư", "bẻ cong", "bù lại", "độ lệch"),
        "structural engineering correction architecture",
        "2D editorial illustration of engineers inspecting subtle structural alignment on a "
        "historic monument, no text, no labels, no arrows, no watermark",
    ),
    (
        ("gia cố", "cáp", "sụp đổ", "bảo tồn"),
        "steel cable stabilization monument engineering",
        "2D editorial illustration of counterweights and tension cables gently stabilizing a "
        "historic structure, no text, no labels, no arrows, no watermark",
    ),
    (
        ("kỳ quan", "biểu tượng", "đăng ký", "khám phá", "hấp dẫn"),
        "historic plaza aerial view editorial",
        "Clean 2D editorial sunset panorama illustrating discovery and wonder, "
        "no text, no labels, no arrows, no watermark",
    ),
)


def _infer_visual_scene_hint(narration: str, entity_anchor: str) -> tuple[str, str]:
    """Tạo truy vấn ảnh & prompt 2D không chữ cho beat cũ chưa có `prop_query`/`image_prompt`."""
    low = (narration or "").strip().lower()
    scene_q = ""
    scene_prompt = ""
    for kws, q_en, p_en in _SCENE_QUERY_HINTS:
        if any(kw in low for kw in kws):
            scene_q = q_en
            scene_prompt = p_en
            break
    if not scene_q:
        scene_q = infer_auto_prop_query(narration)
    query = f"{entity_anchor} {scene_q}".strip() if entity_anchor else scene_q
    if not scene_prompt:
        subj = entity_anchor or "historical science concept"
        scene_prompt = (
            f"Clean 2D flat editorial illustration representing {subj} ({scene_q}), "
            "no text, no labels, no arrows, no watermark"
        )
    return query[:80].strip(), scene_prompt[:320]


def _resolve_beat_visual_image(
    beat: StickvBeat,
    *,
    project_dir: Path,
    library_dir: Path,
    accent: tuple[int, int, int, int],
    primary_entity_en: str = "",
    ai_photo_budget: list[int] | None = None,
    visual_sources_log: list[dict[str, Any]] | None = None,
    prev_image_path: str = "",
    out_meta: dict[str, str] | None = None,
) -> tuple[Image.Image | None, str]:
    """Giải quyết ảnh minh họa cho 100% beat (Wikimedia -> Pixabay -> Cloudflare Flux 2D)."""
    photo_path: Path | None = None
    photo_src = "none"
    ref_q = ""

    prev_p = Path(prev_image_path) if prev_image_path else None
    prev_norm = str(prev_p.resolve()).lower() if prev_p and prev_p.is_file() else ""
    prev_sha = (
        hashlib.sha1(prev_p.read_bytes(), usedforsecurity=False).hexdigest()
        if prev_p and prev_p.is_file()
        else ""
    )

    def _is_dup(cand: Path | None) -> bool:
        if cand is None or not cand.is_file() or not prev_norm:
            return False
        if str(cand.resolve()).lower() == prev_norm:
            return True
        if prev_sha:
            try:
                return (
                    hashlib.sha1(cand.read_bytes(), usedforsecurity=False).hexdigest() == prev_sha
                )
            except OSError:
                return False
        return False

    if beat.media_path:
        cand_m = project_dir / beat.media_path
        if cand_m.is_file() and cand_m.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            photo_path = cand_m
            photo_src = "media_path"
            ref_q = beat.media_path

    eff_visual_mode = classify_beat_visual_mode(beat, primary_entity_en=primary_entity_en)
    if photo_path is None:
        raw_prop_q = (getattr(beat, "prop_query", None) or "").strip()
        entity_anchor = (getattr(beat, "beat_entity_en", "") or primary_entity_en or "").strip()
        raw_prompt = (getattr(beat, "image_prompt", None) or "").strip()
        inferred_q, inferred_prompt = _infer_visual_scene_hint(beat.narration, entity_anchor)
        ref_q = raw_prop_q or inferred_q
        ill_prompt = raw_prompt or inferred_prompt
        try:
            cand_p, cand_src = resolve_reference_image(
                ref_q,
                library_dir,
                workspace_dir=project_dir.parent.parent,
                accent_color=accent,
                illustration_prompt=ill_prompt,
                primary_entity_en=entity_anchor,
                visual_mode=eff_visual_mode,
                allow_ai_fallback=True,
                ai_budget=ai_photo_budget,
            )
            photo_src = cand_src
            if cand_src != "iconify" and cand_p.is_file():
                photo_path = cand_p
        except Exception:
            photo_path = None
            photo_src = "fallback_icon"

        if _is_dup(photo_path):
            base_ent = entity_anchor or ref_q
            scene_ctx = beat.board_title or beat.narration[:60]
            no_text = "no text, no labels, no arrows, no watermark"
            alt_specs = (
                (
                    f"{base_ent} detail closeup",
                    f"Clean 2D flat editorial illustration showing a fresh angle of "
                    f"{base_ent} ({scene_ctx}), {no_text}",
                    "real_photo",
                ),
                (
                    f"alternate editorial scene {beat.id} {base_ent}",
                    f"Clean 2D flat editorial illustration illustrating: "
                    f"{beat.narration[:140]} ({base_ent}, {beat.id}), {no_text}",
                    "editorial_illustration",
                ),
            )
            for alt_q, alt_prompt, alt_vmode in alt_specs:
                try:
                    # Tắt pass 1b (`primary_entity_en=""`) để không tải lại đúng ảnh #1 của thực thể
                    alt_p, alt_src = resolve_reference_image(
                        alt_q,
                        library_dir,
                        workspace_dir=project_dir.parent.parent,
                        accent_color=accent,
                        illustration_prompt=alt_prompt,
                        primary_entity_en="",
                        visual_mode=alt_vmode,
                        allow_ai_fallback=True,
                        ai_budget=ai_photo_budget,
                    )
                    if alt_src != "iconify" and alt_p.is_file() and not _is_dup(alt_p):
                        photo_path = alt_p
                        photo_src = alt_src
                        ref_q = alt_q
                        if alt_vmode == "editorial_illustration":
                            eff_visual_mode = "editorial_illustration"
                        break
                except Exception:
                    continue

    prop_img: Image.Image | None = None
    if photo_path is not None and photo_path.is_file():
        with Image.open(photo_path) as raw_photo:
            prop_img = raw_photo.convert("RGBA")

    resolved_path_str = str(photo_path) if photo_path else ""
    if out_meta is not None:
        out_meta["path"] = resolved_path_str
        out_meta["visual_mode"] = eff_visual_mode
        out_meta["query"] = ref_q

    logger.info(
        "[StickV Visual-First] beat=%s mode=%s source=%s query=%r",
        beat.id,
        eff_visual_mode,
        photo_src,
        ref_q,
    )
    if visual_sources_log is not None:
        visual_sources_log.append(
            {
                "beat_id": beat.id,
                "visual_mode": eff_visual_mode,
                "source": photo_src,
                "query": ref_q,
                "board_title": beat.board_title,
                "path": resolved_path_str,
            }
        )
    return prop_img, photo_src


def _stream_chunk_frames_to_ffmpeg(
    *,
    chunk_items: list[tuple[int, StickvBeat, Path, float]],
    all_beats: list[StickvBeat],
    out_mp4: Path,
    w: int,
    h: int,
    fps: int,
    aspect: str,
    project_dir: Path,
    library_dir: Path,
    assets_dir: Path,
    chunks_dir: Path,
    domain: str,
    theme: StickvTheme,
    animation_mode: str,
    pause_scale: float,
    cancel: CancelToken | None,
    global_frame_offset: int,
    acc_audio_t: float,
    prev_stage_state: BeatStageState | None,
    backdrop_renderer: BackdropRenderer,
    on_progress: Callable[[float, str], None] | None = None,
    master_word_timings: dict[int, list[tuple[str, float, float]]] | None = None,
    beat_timeline: list[BeatTimelineEntry] | None = None,
    ai_photo_budget: list[int] | None = None,
    board_carry: dict[str, Any] | None = None,
    primary_entity_en: str = "",
    asset_cache: PuppetAssetCache | None = None,
    watermark_img: Image.Image | None = None,
    watermark_patch: tuple[Image.Image, int, int] | None = None,
    visual_sources_log: list[dict[str, Any]] | None = None,
    pre_resolved_visual: tuple[Image.Image | None, str, dict[str, str]] | None = None,
) -> tuple[int, float, BeatStageState | None]:
    """Stream liên tục nhiều beat trong 1 cụm chương qua cùng ống FFmpeg, giữ liền mạch 100%."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp4 = out_mp4.with_name(f"{out_mp4.stem}.tmp.mp4")
    cmd = [
        ffmpeg_exe(),
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-y",
        *FFMPEG_RESOURCE_CLAMP,
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        *FFMPEG_ENCODE_CLAMP,
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-video_track_timescale",
        "90000",
        str(tmp_mp4),
    ]

    norm_domain = normalize_domain(domain)
    total_chapters = max((b.chapter for b in all_beats), default=1)
    total_beats_count = max(1, len(all_beats))
    accent = DOMAIN_PALETTES[norm_domain]["accent"]

    cur_frame_offset = global_frame_offset
    cur_audio_t = acc_audio_t
    cur_state = prev_stage_state

    err_log_path = out_mp4.with_name(f"{out_mp4.stem}.ffmpeg.err.log")
    err_file = open(err_log_path, "wb")  # noqa: SIM115
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=err_file,
        creationflags=WINDOWS_LOW_PRIO_FLAGS,
    )
    if cancel is not None and hasattr(cancel, "_lock") and hasattr(cancel, "_procs"):
        with cancel._lock:
            cancel._procs.add(proc)
    assert proc.stdin is not None
    pipe_writer = _AsyncPipeWriter(proc.stdin)
    try:
        for g_idx, beat, wav_p, dur_b in chunk_items:
            if cancel is not None:
                cancel.check()
            if on_progress is not None:
                beat_pct = 35.0 + (g_idx / total_beats_count) * 48.0
                on_progress(
                    round(beat_pct, 1),
                    (
                        f"Đang dựng khung hình beat {g_idx + 1}/{total_beats_count} "
                        f"(Chương {beat.chapter})..."
                    ),
                )
            tl_entry = (
                beat_timeline[g_idx]
                if (beat_timeline is not None and 0 <= g_idx < len(beat_timeline))
                else None
            )
            eff_dur_b = tl_entry.duration_s if tl_entry is not None else dur_b
            target_end_s = (
                tl_entry.beat_end_s if tl_entry is not None else (cur_audio_t + eff_dur_b)
            )
            target_total_frames = max(cur_frame_offset + 1, int(round(target_end_s * fps)))
            n_frames_beat = target_total_frames - cur_frame_offset

            bg_png: Path | None = None
            char_png: Path | None = None
            char_img: Image.Image | None = None
            puppet_mode = animation_mode != "static" and is_puppet_ready(library_dir, assets_dir)
            if not puppet_mode:
                bg_png, char_png = render_beat_layers(
                    beat,
                    aspect=aspect,  # type: ignore[arg-type]
                    theme=theme,
                    out_dir=chunks_dir,
                    library_dir=library_dir,
                    assets_dir=assets_dir,
                    project_dir=project_dir,
                    domain=norm_domain,
                )
                if char_png is not None and char_png.is_file():
                    with Image.open(char_png) as raw_char:
                        char_img = raw_char.convert("RGBA")

            target_char_h = (
                char_img.height if char_img is not None else (620 if aspect == "9:16" else 660)
            )
            interaction = getattr(beat, "interaction", "none") or "none"
            rms_env = extract_wav_rms_envelope(wav_p, fps, eff_dur_b)
            pause_after = compute_pause_after(beat.narration, pause_scale=pause_scale)
            lead_in = GLOBAL_LEAD_SILENCE_S if g_idx == 0 else (LEAD_IN_SILENCE_S * pause_scale)
            spoken_segs = load_beat_spoken_segments(wav_p)
            speech_start = (
                max(0.0, tl_entry.speech_start_s - tl_entry.beat_start_s)
                if tl_entry is not None
                else (spoken_segs[0][0] if spoken_segs else lead_in)
            )
            speech_end = (
                min(eff_dur_b, max(speech_start, tl_entry.speech_end_s - tl_entry.beat_start_s))
                if tl_entry is not None
                else (
                    min(eff_dur_b, spoken_segs[-1][1])
                    if spoken_segs
                    else max(lead_in + 0.3, eff_dur_b - pause_after)
                )
            )
            if master_word_timings is not None and g_idx in master_word_timings:
                word_timings = master_word_timings[g_idx]
            else:
                word_timings = align_beat_karaoke(
                    beat.narration,
                    wav_p,
                    eff_dur_b,
                    lead_in_s=speech_start,
                    pause_after_s=pause_after,
                    spoken_segments=spoken_segs,
                )

            camera_shot = getattr(beat, "camera_shot", "wide_stage") or "wide_stage"
            eff_pose = beat.pose
            if camera_shot == "focus_board" and normalize_stickv_pose(beat.pose) in (
                "idle_breathe",
                "present_board",
            ):
                eff_pose = "point_board_high"

            animator = StickmanAnimator(
                pose=eff_pose,
                emotion=getattr(beat, "emotion", "auto"),
                narration=beat.narration,
                anim_oneshot=getattr(beat, "anim_oneshot", None),
                anim_loop=getattr(beat, "anim_loop", None),
                facing=beat.facing,
                duration_sec=eff_dur_b,
                speech_start=speech_start,
                speech_end=speech_end,
                fps=fps,
                rms_env=rms_env,
                library_dir=library_dir,
                assets_dir=assets_dir,
                target_height=target_char_h,
                char_img_fallback=char_img,
                interaction=interaction,
                beat_id=beat.id,
                animation_mode=animation_mode,
                wav_path=wav_p,
                prev_pose_state=cur_state.pose_state if cur_state is not None else None,
                global_t_offset=cur_frame_offset / max(1, fps),
                board_type=beat.board_type,
                asset_cache=asset_cache,
            )

            if pre_resolved_visual is not None and len(chunk_items) == 1:
                prop_img, _photo_src, resolved_meta = pre_resolved_visual
            else:
                prev_img_path = (
                    str(board_carry.get("last_image_path") or "") if board_carry is not None else ""
                )
                resolved_meta = {}
                prop_img, _photo_src = _resolve_beat_visual_image(
                    beat,
                    project_dir=project_dir,
                    library_dir=library_dir,
                    accent=accent,
                    primary_entity_en=primary_entity_en,
                    ai_photo_budget=ai_photo_budget,
                    visual_sources_log=visual_sources_log,
                    prev_image_path=prev_img_path,
                    out_meta=resolved_meta,
                )
            if board_carry is not None and resolved_meta.get("path"):
                board_carry["last_image_path"] = resolved_meta["path"]

            next_beat = all_beats[g_idx + 1] if g_idx + 1 < len(all_beats) else None
            has_next_diff_title = next_beat is None or (
                (next_beat.board_title or "").strip() != (beat.board_title or "").strip()
                or next_beat.board_type != beat.board_type
                or not (beat.board_title or "").strip()
            )
            prev_ch = cur_state.last_chapter if cur_state is not None else None
            show_chapter_banner = (
                total_chapters > 1
                and bool((getattr(beat, "chapter_title", "") or "").strip())
                and (g_idx == 0 or beat.chapter != prev_ch)
            )

            last_char_size: tuple[int, int] | None = None
            last_cam = (1.0, 0.5, 0.5)
            beat_board_cache: dict[str, Any] = {}
            karaoke_cache: dict[str, Any] = {}
            prev_board_img = board_carry.get("img") if board_carry is not None else None
            puppet_unscaled = (
                animator.puppet_rig.canvas_size if animator.puppet_rig is not None else None
            )
            puppet_target_scale = 1.0
            if puppet_unscaled is not None:
                _, _, puppet_target_scale = compute_beat_character_target(
                    w,
                    h,
                    puppet_unscaled[0],
                    puppet_unscaled[1],
                    interaction=interaction,
                    aspect=aspect,  # type: ignore[arg-type]
                    camera_shot=camera_shot,
                )
                last_char_size = puppet_unscaled
            try:
                for f_idx in range(n_frames_beat):
                    if cancel is not None and f_idx % 8 == 0:
                        cancel.check()
                    t_sec = f_idx / fps
                    global_t = (cur_frame_offset + f_idx) / fps
                    mouth = rms_env[f_idx] if f_idx < len(rms_env) else 0.0
                    if interaction == "versus_split":
                        animator.facing = "left" if t_sec < eff_dur_b * 0.5 else "right"
                    bg_frame = backdrop_renderer.render_frame_rgba(global_t)
                    out_char_scale = 1.0
                    if puppet_unscaled is not None:
                        if cur_state is not None and t_sec < 0.55:
                            u_sc = max(0.0, min(1.0, t_sec / 0.55))
                            p_sc = 0.5 * (1.0 - math.cos(math.pi * u_sc))
                            out_char_scale = (
                                cur_state.scale + (puppet_target_scale - cur_state.scale) * p_sc
                            )
                        else:
                            out_char_scale = puppet_target_scale
                    anim_char, motion = animator.frame_at(f_idx, t_sec, output_scale=out_char_scale)
                    if anim_char is not None and puppet_unscaled is None:
                        last_char_size = anim_char.size
                    try:
                        frame = render_animated_beat_frame(
                            bg_img=bg_frame,
                            char_img=anim_char,
                            beat=beat,
                            aspect=aspect,  # type: ignore[arg-type]
                            t_sec=t_sec,
                            mouth_open=0.0 if motion.phase == "puppet" else mouth,
                            word_timings=word_timings,
                            prop_img=prop_img,
                            domain=norm_domain,
                            theme=theme,
                            duration_sec=eff_dur_b,
                            draw_board=True,
                            extra_dy=motion.dy if motion.used_fallback else 0.0,
                            prev_stage_state=cur_state,
                            spoken_segments=spoken_segs or None,
                            is_puppet=motion.phase == "puppet",
                            total_chapters=total_chapters,
                            has_next_diff_title=has_next_diff_title,
                            show_chapter_banner=show_chapter_banner,
                            board_cache=beat_board_cache,
                            prev_board_img=prev_board_img,
                            mutate_bg=True,
                            karaoke_cache=karaoke_cache,
                            watermark_img=watermark_img,
                            watermark_patch=watermark_patch,
                            char_unscaled_size=puppet_unscaled,
                        )
                    finally:
                        bg_frame.close()
                        if anim_char is not None:
                            anim_char.close()
                    try:
                        pipe_writer.write(frame.tobytes())
                    finally:
                        frame.close()

                end_t_b = max(0.0, (n_frames_beat - 1) / max(1, fps))
                last_cam = compute_camera_state(
                    camera_shot,
                    aspect=aspect,  # type: ignore[arg-type]
                    t_sec=end_t_b,
                    prev_stage_state=cur_state,
                )
                end_layout = compute_layered_camera_layout(
                    camera_shot,
                    aspect=aspect,  # type: ignore[arg-type]
                    w=w,
                    h=h,
                    t_sec=end_t_b,
                    prev_stage_state=cur_state,
                )
                cw, ch_h = last_char_size or (
                    (char_img.width, char_img.height)
                    if char_img is not None
                    else (240, target_char_h)
                )
                tx, ty, tsc = compute_beat_character_target(
                    w,
                    h,
                    cw,
                    ch_h,
                    interaction=interaction,
                    aspect=aspect,  # type: ignore[arg-type]
                    camera_shot=camera_shot,
                )
                cur_state = BeatStageState(
                    x=tx,
                    y=ty,
                    scale=tsc,
                    pose_state=animator.last_pose_state,
                    camera_zoom=last_cam[0],
                    camera_pan_x=last_cam[1],
                    camera_pan_y=last_cam[2],
                    board_alpha=end_layout.board_alpha,
                    camera_shot=camera_shot,
                    last_board_title=(beat.board_title or "").strip(),
                    last_board_type=beat.board_type,
                    last_chapter=beat.chapter,
                    last_visual_title=_pick_visual_first_title(beat),
                )
                if board_carry is not None:
                    old_carried = board_carry.get("img")
                    raw_static = beat_board_cache.pop("static_board", None)
                    next_board: Image.Image | None = None
                    if isinstance(raw_static, tuple) and isinstance(raw_static[0], Image.Image):
                        next_board = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                        next_board.paste(raw_static[0], (raw_static[1], raw_static[2]))
                        raw_static[0].close()
                    elif isinstance(raw_static, Image.Image):
                        next_board = raw_static
                    if next_board is None and end_layout.board_alpha > 0.05:
                        from hbt.stickv.stage import (
                            _composite_transitioned_board,
                            resolve_stage_palette,
                        )

                        next_board = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                        _composite_transitioned_board(
                            next_board,
                            beat,
                            end_layout.board_box,
                            resolve_stage_palette(norm_domain, theme),
                            t_sec=max(1.0, end_t_b),
                            duration_sec=eff_dur_b,
                            progress=1.0,
                            prop_img=prop_img,
                            prev_stage_state=cur_state,
                            total_chapters=total_chapters,
                            has_next_diff_title=has_next_diff_title,
                            cam_board_scale=end_layout.board_scale,
                            cam_board_alpha=end_layout.board_alpha,
                            clamp_bounds=end_layout.clamp_bounds,
                            anchor_top_center=end_layout.anchor_top_center,
                        )
                    board_carry["img"] = next_board
                    if old_carried is not None and old_carried is not next_board:
                        old_carried.close()
            finally:
                close_stage_cache(karaoke_cache)
                close_stage_cache(beat_board_cache)
                animator.close()
                if char_img is not None:
                    char_img.close()
                if prop_img is not None:
                    prop_img.close()
                if bg_png is not None:
                    bg_png.unlink(missing_ok=True)
                if char_png is not None:
                    char_png.unlink(missing_ok=True)

            cur_frame_offset += n_frames_beat
            cur_audio_t = target_end_s
            gc.collect()

        pipe_writer.finish()
        if proc.stdin is not None:
            proc.stdin.flush()
            proc.stdin.close()
            proc.stdin = None
        proc.wait(timeout=300.0)
        err_file.close()
        if proc.returncode != 0:
            err_tail = (
                err_log_path.read_text(encoding="utf-8", errors="replace")[-400:]
                if err_log_path.is_file()
                else ""
            )
            raise FFmpegError(f"FFmpeg stream chunk lỗi ({proc.returncode}): {err_tail}")
        os.replace(tmp_mp4, out_mp4)
    finally:
        pipe_writer.abort()
        if cancel is not None and hasattr(cancel, "_lock") and hasattr(cancel, "_procs"):
            with cancel._lock:
                cancel._procs.discard(proc)
        try:
            err_file.close()
        except Exception:
            pass
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass
        err_log_path.unlink(missing_ok=True)
        if tmp_mp4.exists():
            tmp_mp4.unlink(missing_ok=True)

    return cur_frame_offset, cur_audio_t, cur_state


def _append_outro(
    *,
    main_mp4: Path,
    main_wav: Path,
    out_mp4: Path,
    w: int,
    h: int,
    fps: int,
    aspect: str,
    brand_dir: Path,
    library_dir: Path,
    chunks_dir: Path,
) -> Path:
    """Ghép Outro 4s thương hiệu HBT Studio bằng xfade 0.5s + acrossfade 0.5s (-14 LUFS)."""
    outro_clip = _resolve_outro_clip(brand_dir, fps)
    if outro_clip is None:
        return main_mp4

    outro_voice = Path(library_dir) / "outro" / "voice.wav"
    outro_wav = chunks_dir / "outro_audio.wav"
    build_outro_audio(outro_voice if outro_voice.is_file() else None, outro_wav, chunks_dir)

    main_dur = measure_audio_duration(main_mp4) or measure_audio_duration(main_wav) or 4.0
    offset = max(0.0, main_dur - 0.5)

    if aspect == "16:9":
        # Mở rộng nền đỏ HBT #B22228 ra 1920x1080 và căn giữa clip outro sắc nét
        outro_vf = (
            f"color=c=#B22228:s={w}x{h}:r={fps}:d=4.0[obg];"
            f"[1:v]scale=-2:{h}:flags=lanczos,fps={fps},format=yuv420p[ofg];"
            f"[obg][ofg]overlay=(W-w)/2:0:shortest=1,settb=AVTB[v1];"
        )
    else:
        outro_vf = f"[1:v]scale={w}:{h}:flags=lanczos,fps={fps},format=yuv420p,settb=AVTB[v1];"

    fc = (
        f"[0:v]fps={fps},format=yuv420p,settb=AVTB[v0];"
        f"{outro_vf}"
        f"[v0][v1]xfade=transition=fade:duration=0.5:offset={offset:.3f},fps={fps}[vout];"
        "[2:a][3:a]acrossfade=d=0.5:c1=tri:c2=tri[aout]"
    )

    run_ffmpeg(
        [
            *FFMPEG_RESOURCE_CLAMP,
            "-i",
            str(main_mp4),
            "-i",
            str(outro_clip),
            "-i",
            str(main_wav),
            "-i",
            str(outro_wav),
            "-filter_complex",
            fc,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            *FFMPEG_ENCODE_CLAMP,
            *STICKV_MP4_COMPAT_FLAGS,
            str(out_mp4),
        ]
    )
    return out_mp4


def render_stickv(
    project: StickvProject,
    project_dir: Path,
    *,
    library_dir: Path,
    assets_dir: Path,
    brand_dir: Path,
    voice_provider: VoiceProvider | None = None,
    watermark: WatermarkSettings | None = None,
    preview: bool = False,
    cancel: CancelToken | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    whisper_cfg: WhisperConfig | None = None,
) -> dict[str, Any]:
    """Dựng video StickV hoàn chỉnh theo từng chương và dọn sạch tệp tạm sau khi nối."""
    if not project.beats:
        raise ValueError("Kịch bản StickV chưa có beat nào")

    def emit(pct: float, msg: str) -> None:
        if on_progress is not None:
            on_progress(pct, msg)

    def check_cancel() -> None:
        if cancel is not None:
            cancel.check()

    beats = project.beats[:3] if preview else project.beats
    fps = 30 if preview else 60
    w, h = STICKV_ASPECT_SIZES[project.aspect]

    audio_dir = project_dir / "audio"
    chunks_dir = project_dir / "build" / "chunks"
    renders_dir = project_dir / "renders"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    renders_dir.mkdir(parents=True, exist_ok=True)

    out_name = "preview.mp4" if preview else "final.mp4"
    out_mp4 = renders_dir / out_name

    try:
        emit(8.0, "Đang tạo giọng đọc VieNeu-TTS theo từng beat...")
        check_cancel()
        pause_scale = float(getattr(project, "pause_scale", 1.0) or 1.0)
        beat_wavs = synth_stickv_beats_audio(
            beats,
            audio_dir,
            voice_provider=voice_provider,
            voice_id=project.voice_id,
            pause_scale=pause_scale,
            on_progress=on_progress,
            cancel=cancel,
        )
        try:
            from hbt.api.cinema import evict_all_tts_pools

            evict_all_tts_pools()
        except Exception:
            pass

        emit(24.0, "Đang chốt trục âm thanh chủ (48kHz) & căn mốc Karaoke Whisper...")
        check_cancel()
        build_dir = project_dir / "build"
        voice_full_wav, beat_timeline, voice_full_dur = build_master_voice_wav(
            beat_wavs, build_dir / "stickv_voice_full.wav"
        )
        anchored_beat_wavs: list[tuple[Path, float]] = []
        for beat, (wav_p, _), entry in zip(beats, beat_wavs, beat_timeline, strict=True):
            beat.duration_sec = round(entry.duration_s, 4)
            anchored_beat_wavs.append((wav_p, entry.duration_s))
        beat_wavs = anchored_beat_wavs

        eff_whisper_cfg = whisper_cfg
        whisper_init_err = ""
        if eff_whisper_cfg is None and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                app_cfg = AppSettingsStore(project_dir.parent.parent).load()
                s = load_settings()
                eff_whisper_cfg = WhisperConfig(
                    model=_whisper.effective_model(app_cfg.whisper_model, s.whisper_model),
                    device=s.whisper_device,
                    timeout=app_cfg.whisper_timeout_seconds or _whisper.DEFAULT_TIMEOUT,
                    models_dir=s.models_dir,
                )
            except Exception as exc:
                whisper_init_err = f"Khởi tạo AppSettings/Settings lỗi ({exc}); thử mặc định auto"
                logger.warning("StickV WhisperConfig init warning: %s", exc)
                try:
                    s_fb = load_settings()
                    eff_whisper_cfg = WhisperConfig(
                        model=_whisper.effective_model("auto", s_fb.whisper_model),
                        device=s_fb.whisper_device,
                        timeout=_whisper.DEFAULT_TIMEOUT,
                        models_dir=s_fb.models_dir,
                    )
                    whisper_init_err = ""
                except Exception as exc2:
                    whisper_init_err = f"Không tạo được WhisperConfig: {exc2}"
                    logger.warning("StickV WhisperConfig fallback failed: %s", exc2)
                    eff_whisper_cfg = None

        master_word_timings, _align_meta = align_stickv_master_karaoke(
            beats,
            beat_timeline,
            voice_full_wav,
            cache_file=build_dir / "stickv_timing.json",
            whisper_cfg=eff_whisper_cfg,
            whisper_init_error=whisper_init_err,
            cancel=cancel,
            beat_wavs=beat_wavs,
        )
        planned_frames = sum(allocate_beat_frame_counts([e.duration_s for e in beat_timeline], fps))
        verify_zero_drift_timeline(
            beat_timeline,
            planned_frames / float(fps),
            voice_full_dur,
            master_word_timings,
        )

        emit(28.0, "Đang trộn SFX & nhạc nền (-14 LUFS)...")
        check_cancel()
        mixed_wav = chunks_dir / "mixed.wav"
        mix_stickv_audio(
            beats=beats,
            beat_wavs=beat_wavs,
            topic=project.topic,
            library_dir=library_dir,
            assets_dir=assets_dir,
            out_wav=mixed_wav,
            music_mood=project.music_mood,
            workspace_dir=project_dir.parent.parent,
            voice_full_wav=voice_full_wav,
            beat_timeline=beat_timeline,
        )

        chunks = group_beats_into_chunks(
            beats,
            beat_wavs,
            project_dir=project_dir,
            library_dir=library_dir,
            assets_dir=assets_dir,
        )
        chunk_clips: list[Path] = []
        total_chunks = max(1, len(chunks))
        norm_domain = normalize_domain(getattr(project, "domain", "paper_classic"))
        wm = watermark or WatermarkSettings()
        wm_png: Path | None = None
        wm_img: Image.Image | None = None
        wm_patch: tuple[Image.Image, int, int] | None = None
        if wm.enabled:
            wm_png = chunks_dir / "watermark.png"
            render_watermark_png(
                wm_png,
                wm,
                width=w,
                height=h,
                brand_dir=brand_dir,
                assets_dir=assets_dir,
            )
            with Image.open(wm_png) as raw_wm:
                wm_rgba = raw_wm.convert("RGBA")
                wb = wm_rgba.getbbox()
                if wb is not None:
                    wm_patch = (wm_rgba.crop(wb), int(wb[0]), int(wb[1]))
                    wm_rgba.close()
                else:
                    wm_img = wm_rgba

        shared_backdrop = BackdropRenderer(norm_domain, w, h)
        shared_puppet_assets = PuppetAssetCache()
        beat_cache = StickvBeatCache(build_dir / "beat_cache")
        total_beats_count = max(1, len(beats))
        total_chapters = max((b.chapter for b in beats), default=1)
        anim_mode = getattr(project, "animation_mode", "auto")
        prim_ent = getattr(project, "primary_entity_en", "") or ""
        global_frame_offset = 0
        acc_audio_t = 0.0
        prev_stage_state: BeatStageState | None = None
        ai_photo_budget = [DEFAULT_AI_IMAGE_BUDGET]
        board_carry: dict[str, Any] = {"img": None}
        visual_sources_log: list[dict[str, Any]] = []
        try:
            for c_idx, (c_kind, c_items) in enumerate(chunks, start=1):
                check_cancel()
                pct = 35.0 + ((c_idx - 1) / total_chunks) * 45.0
                first_b = c_items[0][1]
                emit(
                    pct,
                    f"Đang dựng cụm {c_idx}/{total_chunks} (Chương {first_b.chapter})...",
                )

                if c_kind == "video":
                    chunk_mp4 = chunks_dir / f"chunk_{c_idx:03d}.mp4"
                    _g_idx, beat, wav_p, dur_b = c_items[0]
                    bg_png, char_png = render_beat_layers(
                        beat,
                        aspect=project.aspect,
                        theme=project.theme,
                        out_dir=chunks_dir,
                        library_dir=library_dir,
                        assets_dir=assets_dir,
                        project_dir=project_dir,
                        domain=norm_domain,
                    )
                    target_total_frames = max(
                        global_frame_offset + 1, int(round((acc_audio_t + dur_b) * fps))
                    )
                    n_frames_beat = target_total_frames - global_frame_offset
                    state_box: dict[str, Any] = {}
                    _render_single_beat_clip(
                        beat=beat,
                        wav_path=wav_p,
                        bg_png=bg_png,
                        char_png=char_png,
                        out_mp4=chunk_mp4,
                        w=w,
                        h=h,
                        fps=fps,
                        aspect=project.aspect,
                        project_dir=project_dir,
                        library_dir=library_dir,
                        assets_dir=assets_dir,
                        domain=norm_domain,
                        theme=project.theme,
                        animation_mode=anim_mode,
                        pause_scale=pause_scale,
                        cancel=cancel,
                        global_frame_offset=global_frame_offset,
                        n_frames_override=n_frames_beat,
                        prev_stage_state=prev_stage_state,
                        stage_state_out=state_box,
                        backdrop_renderer=shared_backdrop,
                        asset_cache=shared_puppet_assets,
                        watermark_img=wm_img,
                        watermark_png=wm_png,
                    )
                    global_frame_offset += n_frames_beat
                    acc_audio_t += float(dur_b)
                    if isinstance(state_box.get("state"), BeatStageState):
                        prev_stage_state = state_box["state"]
                    bg_png.unlink(missing_ok=True)
                    if char_png is not None:
                        char_png.unlink(missing_ok=True)
                    chunk_clips.append(chunk_mp4)
                elif beat_cache.enabled:
                    for g_idx, beat, wav_p, dur_b in c_items:
                        check_cancel()
                        tl_entry = beat_timeline[g_idx] if 0 <= g_idx < len(beat_timeline) else None
                        eff_dur_b = tl_entry.duration_s if tl_entry is not None else dur_b
                        target_end_s = (
                            tl_entry.beat_end_s
                            if tl_entry is not None
                            else (acc_audio_t + eff_dur_b)
                        )
                        target_total_frames = max(
                            global_frame_offset + 1, int(round(target_end_s * fps))
                        )
                        n_frames_beat = target_total_frames - global_frame_offset
                        pause_after = compute_pause_after(beat.narration, pause_scale=pause_scale)
                        lead_in = (
                            GLOBAL_LEAD_SILENCE_S
                            if g_idx == 0
                            else (LEAD_IN_SILENCE_S * pause_scale)
                        )
                        spoken_segs = load_beat_spoken_segments(wav_p)
                        speech_start = (
                            max(0.0, tl_entry.speech_start_s - tl_entry.beat_start_s)
                            if tl_entry is not None
                            else (spoken_segs[0][0] if spoken_segs else lead_in)
                        )
                        speech_end = (
                            min(
                                eff_dur_b,
                                max(speech_start, tl_entry.speech_end_s - tl_entry.beat_start_s),
                            )
                            if tl_entry is not None
                            else (
                                min(eff_dur_b, spoken_segs[-1][1])
                                if spoken_segs
                                else max(lead_in + 0.3, eff_dur_b - pause_after)
                            )
                        )
                        if master_word_timings is not None and g_idx in master_word_timings:
                            w_timings = master_word_timings[g_idx]
                        else:
                            w_timings = align_beat_karaoke(
                                beat.narration,
                                wav_p,
                                eff_dur_b,
                                lead_in_s=speech_start,
                                pause_after_s=pause_after,
                                spoken_segments=spoken_segs,
                            )
                        next_b = beats[g_idx + 1] if g_idx + 1 < len(beats) else None
                        has_next_diff = next_b is None or (
                            (next_b.board_title or "").strip() != (beat.board_title or "").strip()
                            or next_b.board_type != beat.board_type
                            or not (beat.board_title or "").strip()
                        )
                        prev_ch = (
                            prev_stage_state.last_chapter if prev_stage_state is not None else None
                        )
                        show_banner = (
                            total_chapters > 1
                            and bool((getattr(beat, "chapter_title", "") or "").strip())
                            and (g_idx == 0 or beat.chapter != prev_ch)
                        )
                        wav_sha = hash_file_sha256(wav_p) if wav_p.is_file() else ""
                        pre_meta: dict[str, str] = {}
                        pre_prop_img, pre_photo_src = _resolve_beat_visual_image(
                            beat,
                            project_dir=project_dir,
                            library_dir=library_dir,
                            accent=DOMAIN_PALETTES[norm_domain]["accent"],
                            primary_entity_en=prim_ent,
                            ai_photo_budget=ai_photo_budget,
                            visual_sources_log=visual_sources_log,
                            prev_image_path=str(board_carry.get("last_image_path") or ""),
                            out_meta=pre_meta,
                        )
                        res_p_str = pre_meta.get("path", "")
                        res_sha = (
                            hash_file_sha256(Path(res_p_str))[:16]
                            if (res_p_str and Path(res_p_str).is_file())
                            else "none"
                        )
                        cache_prim_ent = (
                            f"{prim_ent}|{REF_CACHE_VERSION}"
                            f"|{pre_meta.get('visual_mode', 'real_photo')}|{res_sha}"
                        )
                        cache_key = compute_beat_cache_key(
                            beat=beat,
                            aspect=project.aspect,
                            w=w,
                            h=h,
                            fps=fps,
                            domain=norm_domain,
                            theme=project.theme,
                            animation_mode=anim_mode,
                            pause_scale=pause_scale,
                            primary_entity_en=cache_prim_ent,
                            total_chapters=total_chapters,
                            has_next_diff_title=has_next_diff,
                            show_chapter_banner=show_banner,
                            watermark=wm,
                            n_frames_beat=n_frames_beat,
                            eff_dur_b=eff_dur_b,
                            speech_start=speech_start,
                            speech_end=speech_end,
                            word_timings=w_timings,
                            spoken_segs=spoken_segs,
                            wav_sha256=wav_sha,
                            global_frame_offset=global_frame_offset,
                            prev_stage_state=prev_stage_state,
                            prev_board_img=board_carry.get("img"),
                        )
                        hit = beat_cache.lookup(cache_key)
                        if hit is not None:
                            if pre_prop_img is not None:
                                pre_prop_img.close()
                            if res_p_str:
                                board_carry["last_image_path"] = res_p_str
                            cached_mp4, next_state, next_board = hit
                            old_carried = board_carry.get("img")
                            board_carry["img"] = next_board
                            if old_carried is not None and old_carried is not next_board:
                                old_carried.close()
                            prev_stage_state = next_state
                            global_frame_offset += n_frames_beat
                            acc_audio_t = target_end_s
                            chunk_clips.append(cached_mp4)
                            emit(
                                round(35.0 + ((g_idx + 1) / total_beats_count) * 48.0, 1),
                                f"Dùng cache beat {g_idx + 1}/{total_beats_count}"
                                f" (Chương {beat.chapter})...",
                            )
                        else:
                            beat_mp4 = chunks_dir / f"beat_{g_idx:04d}.mp4"
                            global_frame_offset, acc_audio_t, prev_stage_state = (
                                _stream_chunk_frames_to_ffmpeg(
                                    chunk_items=[(g_idx, beat, wav_p, dur_b)],
                                    all_beats=beats,
                                    out_mp4=beat_mp4,
                                    w=w,
                                    h=h,
                                    fps=fps,
                                    aspect=project.aspect,
                                    project_dir=project_dir,
                                    library_dir=library_dir,
                                    assets_dir=assets_dir,
                                    chunks_dir=chunks_dir,
                                    domain=norm_domain,
                                    theme=project.theme,
                                    animation_mode=anim_mode,
                                    pause_scale=pause_scale,
                                    cancel=cancel,
                                    global_frame_offset=global_frame_offset,
                                    acc_audio_t=acc_audio_t,
                                    prev_stage_state=prev_stage_state,
                                    backdrop_renderer=shared_backdrop,
                                    on_progress=on_progress,
                                    master_word_timings=master_word_timings,
                                    beat_timeline=beat_timeline,
                                    ai_photo_budget=ai_photo_budget,
                                    board_carry=board_carry,
                                    primary_entity_en=prim_ent,
                                    asset_cache=shared_puppet_assets,
                                    watermark_img=wm_img,
                                    watermark_patch=wm_patch,
                                    visual_sources_log=visual_sources_log,
                                    pre_resolved_visual=(pre_prop_img, pre_photo_src, pre_meta),
                                )
                            )
                            if beat_mp4.is_file() and beat_mp4.stat().st_size > 128:
                                beat_cache.store(
                                    cache_key,
                                    beat_mp4,
                                    prev_stage_state,
                                    board_carry.get("img"),
                                )
                            chunk_clips.append(beat_mp4)
                else:
                    chunk_mp4 = chunks_dir / f"chunk_{c_idx:03d}.mp4"
                    global_frame_offset, acc_audio_t, prev_stage_state = (
                        _stream_chunk_frames_to_ffmpeg(
                            chunk_items=c_items,
                            all_beats=beats,
                            out_mp4=chunk_mp4,
                            w=w,
                            h=h,
                            fps=fps,
                            aspect=project.aspect,
                            project_dir=project_dir,
                            library_dir=library_dir,
                            assets_dir=assets_dir,
                            chunks_dir=chunks_dir,
                            domain=norm_domain,
                            theme=project.theme,
                            animation_mode=anim_mode,
                            pause_scale=pause_scale,
                            cancel=cancel,
                            global_frame_offset=global_frame_offset,
                            acc_audio_t=acc_audio_t,
                            prev_stage_state=prev_stage_state,
                            backdrop_renderer=shared_backdrop,
                            on_progress=on_progress,
                            master_word_timings=master_word_timings,
                            beat_timeline=beat_timeline,
                            ai_photo_budget=ai_photo_budget,
                            board_carry=board_carry,
                            primary_entity_en=prim_ent,
                            asset_cache=shared_puppet_assets,
                            watermark_img=wm_img,
                            watermark_patch=wm_patch,
                            visual_sources_log=visual_sources_log,
                        )
                    )
                    chunk_clips.append(chunk_mp4)
                gc.collect()
        finally:
            if visual_sources_log:
                try:
                    (build_dir / "visual_sources.json").write_text(
                        json.dumps(visual_sources_log, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
            if wm_patch is not None:
                wm_patch[0].close()
            if wm_img is not None:
                wm_img.close()
            carried = board_carry.get("img")
            if carried is not None:
                carried.close()
                board_carry["img"] = None
            shared_puppet_assets.close()
            shared_backdrop.close()

        emit(85.0, "Đang nối chương & ghép âm thanh hoàn chỉnh...")
        check_cancel()
        concat_txt = chunks_dir / "concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in chunk_clips),
            encoding="utf-8",
        )
        video_only = chunks_dir / "video_only.mp4"
        run_ffmpeg(
            [
                *FFMPEG_RESOURCE_CLAMP,
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_txt),
                "-c",
                "copy",
                str(video_only),
            ]
        )

        with_outro = bool(getattr(project, "outro", True)) and not preview
        body_mp4 = (chunks_dir / "body_muxed.mp4") if with_outro else out_mp4

        # Watermark đã được ghép trực tiếp ở Pass 1 -> Pass 3 chỉ copy luồng video (0% re-encode)
        run_ffmpeg(
            [
                *FFMPEG_RESOURCE_CLAMP,
                "-i",
                str(video_only),
                "-i",
                str(mixed_wav),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(body_mp4),
            ]
        )

        if with_outro:
            emit(92.0, "Đang ghép Outro 4 giây HBT Studio...")
            check_cancel()
            joined = _append_outro(
                main_mp4=body_mp4,
                main_wav=mixed_wav,
                out_mp4=out_mp4,
                w=w,
                h=h,
                fps=fps,
                aspect=project.aspect,
                brand_dir=brand_dir,
                library_dir=library_dir,
                chunks_dir=chunks_dir,
            )
            if joined != out_mp4 and body_mp4.is_file():
                body_mp4.replace(out_mp4)

        emit(98.0, "Đang dọn tệp tạm & hoàn tất...")
        dur_s = measure_audio_duration(out_mp4) or round(sum(b.duration_sec for b in beats), 2)
        size_mb = round(out_mp4.stat().st_size / (1024 * 1024), 2) if out_mp4.is_file() else 0.0
        return {
            "file_path": str(out_mp4),
            "duration_sec": dur_s,
            "size_mb": size_mb,
            "aspect": project.aspect,
            "fps": fps,
            "preview": preview,
        }
    finally:
        shutil.rmtree(chunks_dir, ignore_errors=True)
        gc.collect()
