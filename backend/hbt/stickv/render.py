"""Bộ dựng video StickV v6.1: stream khung hình lip-sync/karaoke trực tiếp vào FFmpeg (nhẹ RAM)."""

from __future__ import annotations

import gc
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from hbt.pipeline.audio import build_outro_audio
from hbt.pipeline.cancel import CancelToken
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe, run_ffmpeg
from hbt.postv.voice import VoiceProvider
from hbt.shared.ffmpeg_utils import (
    FFMPEG_ENCODE_CLAMP,
    FFMPEG_RESOURCE_CLAMP,
    measure_audio_duration,
)
from hbt.shared.online_sources.iconify_props import resolve_prop_png
from hbt.shared.pipeline.watermark import (
    WatermarkSettings,
    build_watermark_overlay_filter,
    render_watermark_png,
)
from hbt.stickv.animator import StickmanAnimator
from hbt.stickv.audio import (
    GLOBAL_LEAD_SILENCE_S,
    LEAD_IN_SILENCE_S,
    align_beat_karaoke,
    compute_pause_after,
    extract_wav_rms_envelope,
    load_beat_spoken_segments,
    mix_stickv_audio,
    synth_stickv_beats_audio,
)
from hbt.stickv.backdrops import DOMAIN_PALETTES, BackdropRenderer, normalize_domain
from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvBeat, StickvProject, StickvTheme
from hbt.stickv.puppet import normalize_stickv_pose
from hbt.stickv.stage import (
    BeatStageState,
    compute_beat_character_target,
    compute_camera_state,
    compute_layered_camera_layout,
    infer_auto_prop_query,
    render_animated_beat_frame,
    render_beat_layers,
)

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
) -> Path:
    """Stream từng khung hình RGB (backdrop liên tục + tween + animator + karaoke) vào FFmpeg."""
    dur = max(1.0, float(beat.duration_sec or 2.0))
    n_frames = n_frames_override if n_frames_override is not None else max(1, int(round(dur * fps)))
    rms_env = extract_wav_rms_envelope(wav_path, fps, dur)
    pause_after = compute_pause_after(beat.narration, pause_scale=pause_scale)
    lead_in = (
        GLOBAL_LEAD_SILENCE_S if global_frame_offset == 0 else (LEAD_IN_SILENCE_S * pause_scale)
    )
    speech_end = max(lead_in + 0.3, dur - pause_after)
    spoken_segs = load_beat_spoken_segments(wav_path)
    word_timings = align_beat_karaoke(
        beat.narration,
        wav_path,
        dur,
        lead_in_s=lead_in,
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
        speech_start=lead_in,
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
        wav_path=wav_path,
        prev_pose_state=prev_stage_state.pose_state if prev_stage_state is not None else None,
        global_t_offset=global_frame_offset / max(1, fps),
    )

    prop_img: Image.Image | None = None
    prop_query = (getattr(beat, "prop_query", None) or "").strip()
    if interaction == "hold_prop" and prop_query:
        accent = DOMAIN_PALETTES[norm_domain]["accent"]
        prop_path = resolve_prop_png(prop_query, library_dir, accent_color=accent)
        if prop_path.is_file():
            with Image.open(prop_path) as raw_prop:
                prop_img = raw_prop.convert("RGBA")

    last_char_size: tuple[int, int] | None = None
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
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
            bg_frame = backdrop.render_frame(global_t)
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
        _, stderr_b = proc.communicate(timeout=300.0)
        if proc.returncode != 0:
            raise FFmpegError(
                f"FFmpeg stream beat {beat.id} lỗi ({proc.returncode}): "
                f"{stderr_b.decode('utf-8', errors='replace')[-300:]}"
            )
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
                x=tx, y=ty, scale=tsc, pose_state=animator.last_pose_state
            )
    finally:
        for pipe in (proc.stdin, proc.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass
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
) -> tuple[int, float, BeatStageState | None]:
    """Stream liên tục nhiều beat trong 1 cụm chương qua cùng ống FFmpeg, giữ liền mạch 100%."""
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
    total_chapters = max((b.chapter for b in all_beats), default=1)
    accent = DOMAIN_PALETTES[norm_domain]["accent"]

    cur_frame_offset = global_frame_offset
    cur_audio_t = acc_audio_t
    cur_state = prev_stage_state

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None
        for g_idx, beat, wav_p, dur_b in chunk_items:
            if cancel is not None:
                cancel.check()
            target_total_frames = max(cur_frame_offset + 1, int(round((cur_audio_t + dur_b) * fps)))
            n_frames_beat = target_total_frames - cur_frame_offset

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

            char_img: Image.Image | None = None
            if char_png is not None and char_png.is_file():
                with Image.open(char_png) as raw_char:
                    char_img = raw_char.convert("RGBA")

            target_char_h = (
                char_img.height
                if char_img is not None
                else int(h * (0.48 if aspect == "9:16" else 0.64))
            )
            interaction = getattr(beat, "interaction", "none") or "none"
            rms_env = extract_wav_rms_envelope(wav_p, fps, dur_b)
            pause_after = compute_pause_after(beat.narration, pause_scale=pause_scale)
            lead_in = GLOBAL_LEAD_SILENCE_S if g_idx == 0 else (LEAD_IN_SILENCE_S * pause_scale)
            speech_end = max(lead_in + 0.3, dur_b - pause_after)
            spoken_segs = load_beat_spoken_segments(wav_p)
            word_timings = align_beat_karaoke(
                beat.narration,
                wav_p,
                dur_b,
                lead_in_s=lead_in,
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
                duration_sec=dur_b,
                speech_start=lead_in,
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
            )

            prop_img: Image.Image | None = None
            raw_prop_q = (getattr(beat, "prop_query", None) or "").strip()
            wants_card_icon = beat.board_type in (
                "none",
                "bullets",
                "list",
                "card",
                "recap_card",
            )
            if not raw_prop_q and wants_card_icon:
                raw_prop_q = infer_auto_prop_query(beat.narration)
            if (interaction == "hold_prop" or wants_card_icon) and raw_prop_q:
                try:
                    prop_path = resolve_prop_png(raw_prop_q, library_dir, accent_color=accent)
                    if prop_path.is_file():
                        with Image.open(prop_path) as raw_prop:
                            prop_img = raw_prop.convert("RGBA")
                except Exception:
                    prop_img = None

            next_beat = all_beats[g_idx + 1] if g_idx + 1 < len(all_beats) else None
            has_next_diff_title = next_beat is None or (
                (next_beat.board_title or "").strip() != (beat.board_title or "").strip()
                or next_beat.board_type != beat.board_type
                or not (beat.board_title or "").strip()
            )
            prev_ch = cur_state.last_chapter if cur_state is not None else None
            show_chapter_banner = bool((getattr(beat, "chapter_title", "") or "").strip()) and (
                g_idx == 0 or beat.chapter != prev_ch
            )

            last_char_size: tuple[int, int] | None = None
            last_cam = (1.0, 0.5, 0.5)
            try:
                for f_idx in range(n_frames_beat):
                    if cancel is not None and f_idx % 8 == 0:
                        cancel.check()
                    t_sec = f_idx / fps
                    global_t = (cur_frame_offset + f_idx) / fps
                    mouth = rms_env[f_idx] if f_idx < len(rms_env) else 0.0
                    if interaction == "versus_split":
                        animator.facing = "left" if t_sec < dur_b * 0.5 else "right"
                    bg_frame = backdrop_renderer.render_frame(global_t)
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
                            duration_sec=dur_b,
                            draw_board=True,
                            extra_dy=motion.dy if motion.used_fallback else 0.0,
                            prev_stage_state=cur_state,
                            spoken_segments=spoken_segs or None,
                            is_puppet=motion.phase == "puppet",
                            total_chapters=total_chapters,
                            has_next_diff_title=has_next_diff_title,
                            show_chapter_banner=show_chapter_banner,
                        )
                    finally:
                        bg_frame.close()
                        if anim_char is not None:
                            anim_char.close()
                    try:
                        proc.stdin.write(frame.tobytes())
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
                )
            finally:
                animator.close()
                if char_img is not None:
                    char_img.close()
                if prop_img is not None:
                    prop_img.close()
                bg_png.unlink(missing_ok=True)
                if char_png is not None:
                    char_png.unlink(missing_ok=True)

            cur_frame_offset += n_frames_beat
            cur_audio_t += dur_b
            gc.collect()

        if proc.stdin is not None:
            proc.stdin.flush()
            proc.stdin.close()
            proc.stdin = None
        _, stderr_b = proc.communicate(timeout=300.0)
        if proc.returncode != 0:
            raise FFmpegError(
                f"FFmpeg stream chunk lỗi ({proc.returncode}): "
                f"{stderr_b.decode('utf-8', errors='replace')[-300:]}"
            )
        os.replace(tmp_mp4, out_mp4)
    finally:
        for pipe in (proc.stdin, proc.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=2.0)
        except Exception:
            pass
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
        f"[v0][v1]xfade=transition=fade:duration=0.5:offset={offset:.3f}[vout];"
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
    fps = 24 if preview else min(30, project.fps)
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
        shared_backdrop = BackdropRenderer(norm_domain, w, h)
        global_frame_offset = 0
        acc_audio_t = 0.0
        prev_stage_state: BeatStageState | None = None
        try:
            for c_idx, (c_kind, c_items) in enumerate(chunks, start=1):
                check_cancel()
                pct = 35.0 + (c_idx / total_chunks) * 45.0
                first_b = c_items[0][1]
                emit(
                    pct,
                    f"Đang dựng cụm {c_idx}/{total_chunks} (Chương {first_b.chapter})...",
                )
                chunk_mp4 = chunks_dir / f"chunk_{c_idx:03d}.mp4"

                if c_kind == "video":
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
                        animation_mode=getattr(project, "animation_mode", "auto"),
                        pause_scale=pause_scale,
                        cancel=cancel,
                        global_frame_offset=global_frame_offset,
                        n_frames_override=n_frames_beat,
                        prev_stage_state=prev_stage_state,
                        stage_state_out=state_box,
                        backdrop_renderer=shared_backdrop,
                    )
                    global_frame_offset += n_frames_beat
                    acc_audio_t += float(dur_b)
                    if isinstance(state_box.get("state"), BeatStageState):
                        prev_stage_state = state_box["state"]
                    bg_png.unlink(missing_ok=True)
                    if char_png is not None:
                        char_png.unlink(missing_ok=True)
                else:
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
                            animation_mode=getattr(project, "animation_mode", "auto"),
                            pause_scale=pause_scale,
                            cancel=cancel,
                            global_frame_offset=global_frame_offset,
                            acc_audio_t=acc_audio_t,
                            prev_stage_state=prev_stage_state,
                            backdrop_renderer=shared_backdrop,
                        )
                    )
                chunk_clips.append(chunk_mp4)
                gc.collect()
        finally:
            shared_backdrop.close()

        emit(85.0, "Đang nối chương & gắn watermark HBT...")
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

        wm = watermark or WatermarkSettings()
        with_outro = bool(getattr(project, "outro", True)) and not preview
        body_mp4 = (chunks_dir / "body_muxed.mp4") if with_outro else out_mp4

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
            wm_fc = build_watermark_overlay_filter(
                input_video="0:v", input_wm="2:v", output_label="vout"
            )
            run_ffmpeg(
                [
                    *FFMPEG_RESOURCE_CLAMP,
                    "-i",
                    str(video_only),
                    "-i",
                    str(mixed_wav),
                    "-i",
                    str(wm_png),
                    "-filter_complex",
                    wm_fc,
                    "-map",
                    "[vout]",
                    "-map",
                    "1:a",
                    "-shortest",
                    *FFMPEG_ENCODE_CLAMP,
                    *STICKV_MP4_COMPAT_FLAGS,
                    str(body_mp4),
                ]
            )
        else:
            run_ffmpeg(
                [
                    *FFMPEG_RESOURCE_CLAMP,
                    "-i",
                    str(video_only),
                    "-i",
                    str(mixed_wav),
                    "-shortest",
                    *FFMPEG_ENCODE_CLAMP,
                    *STICKV_MP4_COMPAT_FLAGS,
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
