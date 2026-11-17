"""Bộ dựng video StickV v6.1: stream khung hình lip-sync/karaoke trực tiếp vào FFmpeg (nhẹ RAM)."""

from __future__ import annotations

import gc
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from hbt.pipeline.cancel import CancelToken
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe, run_ffmpeg
from hbt.postv.voice import VoiceProvider
from hbt.shared.ffmpeg_utils import (
    FFMPEG_ENCODE_CLAMP,
    FFMPEG_RESOURCE_CLAMP,
    measure_audio_duration,
)
from hbt.shared.pipeline.watermark import (
    WatermarkSettings,
    build_watermark_overlay_filter,
    render_watermark_png,
)
from hbt.stickv.audio import (
    compute_word_timings,
    extract_wav_rms_envelope,
    mix_stickv_audio,
    synth_stickv_beats_audio,
)
from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvBeat, StickvProject
from hbt.stickv.stage import render_animated_beat_frame, render_beat_layers


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
    cancel: CancelToken | None = None,
) -> Path:
    """Stream từng khung hình RGB (lip-sync + chớp mắt + karaoke) vào FFmpeg stdin, 0 PNG rác."""
    dur = max(1.0, float(beat.duration_sec or 2.0))
    n_frames = max(1, int(round(dur * fps)))
    rms_env = extract_wav_rms_envelope(wav_path, fps, dur)
    word_timings = compute_word_timings(beat.narration, max(0.5, dur - 0.25))

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
        str(out_mp4),
    ]

    with Image.open(bg_png) as raw_bg:
        bg_img = raw_bg.convert("RGB")
        char_img: Image.Image | None = None
        if char_png is not None and char_png.is_file():
            with Image.open(char_png) as raw_char:
                char_img = raw_char.convert("RGBA")

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
                mouth = rms_env[f_idx] if f_idx < len(rms_env) else 0.0
                frame = render_animated_beat_frame(
                    bg_img=bg_img,
                    char_img=char_img,
                    beat=beat,
                    aspect=aspect,  # type: ignore[arg-type]
                    t_sec=t_sec,
                    mouth_open=mouth,
                    word_timings=word_timings,
                )
                try:
                    proc.stdin.write(frame.tobytes())
                finally:
                    frame.close()
            proc.stdin.close()
            _, stderr_b = proc.communicate()
            if proc.returncode != 0:
                raise FFmpegError(
                    f"FFmpeg stream beat {beat.id} lỗi ({proc.returncode}): "
                    f"{stderr_b.decode('utf-8', errors='replace')[-300:]}"
                )
        finally:
            if proc.poll() is None:
                proc.kill()
            bg_img.close()
            if char_img is not None:
                char_img.close()
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
    cancel: CancelToken | None = None,
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
        cancel=cancel,
    )


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
        beat_wavs = synth_stickv_beats_audio(
            beats,
            audio_dir,
            voice_provider=voice_provider,
            voice_id=project.voice_id,
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
        )

        beat_clips: list[Path] = []
        total_b = len(beats)
        for idx, (beat, (wav_p, _dur)) in enumerate(zip(beats, beat_wavs, strict=True), start=1):
            check_cancel()
            pct = 35.0 + (idx / max(1, total_b)) * 45.0
            emit(pct, f"Đang dựng phân cảnh {idx}/{total_b} (Chương {beat.chapter})...")

            bg_png, char_png = render_beat_layers(
                beat,
                aspect=project.aspect,
                theme=project.theme,
                out_dir=chunks_dir,
                library_dir=library_dir,
                assets_dir=assets_dir,
                project_dir=project_dir,
            )
            clip_mp4 = chunks_dir / f"beat_{idx:03d}.mp4"
            _render_single_beat_clip(
                beat=beat,
                wav_path=wav_p,
                bg_png=bg_png,
                char_png=char_png,
                out_mp4=clip_mp4,
                w=w,
                h=h,
                fps=fps,
                aspect=project.aspect,
                project_dir=project_dir,
                library_dir=library_dir,
                assets_dir=assets_dir,
                cancel=cancel,
            )
            beat_clips.append(clip_mp4)

            bg_png.unlink(missing_ok=True)
            if char_png is not None:
                char_png.unlink(missing_ok=True)
            if idx % 3 == 0:
                gc.collect()

        emit(85.0, "Đang nối chương & gắn watermark HBT...")
        check_cancel()
        concat_txt = chunks_dir / "concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{p.resolve().as_posix()}'" for p in beat_clips),
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
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    *FFMPEG_ENCODE_CLAMP,
                    str(out_mp4),
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
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    str(out_mp4),
                ]
            )

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
