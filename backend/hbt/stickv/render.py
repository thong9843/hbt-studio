"""Bộ dựng video StickV FFmpeg theo chương (Chunked Chapters) tối ưu CPU & RAM."""

from __future__ import annotations

import gc
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hbt.pipeline.cancel import CancelToken
from hbt.pipeline.ffutil import run_ffmpeg
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
from hbt.stickv.audio import mix_stickv_audio, synth_stickv_beats_audio
from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvBeat, StickvProject
from hbt.stickv.stage import render_beat_layers


def _overlay_expr(beat: StickvBeat, w: int, h: int, aspect: str) -> tuple[str, str]:
    """Biểu thức chuyển động mượt FFmpeg (0 khung hình Pillow thừa -> tiết kiệm RAM)."""
    if aspect == "9:16":
        base_x = "(W-w)/2"
        base_y = "H-h-240"
    else:
        base_x = "120"
        base_y = "(H-h)/2+40"

    m = beat.motion
    if m == "slide_left":
        return f"if(lt(t,0.35), W-(W-({base_x}))*(t/0.35), {base_x})", base_y
    if m == "slide_right":
        return f"if(lt(t,0.35), -w+(({base_x})+w)*(t/0.35), {base_x})", base_y
    if m == "shake":
        return f"({base_x})+sin(t*38)*10", base_y
    if m == "float":
        return base_x, f"({base_y})+sin(t*3.2)*14"
    if m == "bounce":
        return base_x, f"({base_y})-abs(sin(t*6.5))*18"
    return base_x, base_y


def _render_single_beat_clip(
    *,
    beat: StickvBeat,
    bg_png: Path,
    char_png: Path | None,
    out_mp4: Path,
    w: int,
    h: int,
    fps: int,
    aspect: str,
    project_dir: Path,
) -> Path:
    dur = max(1.0, float(beat.duration_sec or 2.0))
    media_file = (project_dir / beat.media_path) if beat.media_path else None

    if media_file and media_file.is_file() and media_file.suffix.lower() in {".mp4", ".mov", ".webm"}:
        # Chèn clip chuyển động điểm nhấn (.mp4 từ Google Flow / Veo)
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps},format=yuv420p"
        )
        cmd = [
            *FFMPEG_RESOURCE_CLAMP,
            "-stream_loop",
            "-1",
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

    if char_png is not None and char_png.is_file():
        ox, oy = _overlay_expr(beat, w, h, aspect)
        fc = f"[0:v][1:v]overlay=x='{ox}':y='{oy}':shortest=1,fps={fps},format=yuv420p[v]"
        cmd = [
            *FFMPEG_RESOURCE_CLAMP,
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(bg_png),
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(char_png),
            "-filter_complex",
            fc,
            "-map",
            "[v]",
            "-an",
            *FFMPEG_ENCODE_CLAMP,
            str(out_mp4),
        ]
    else:
        cmd = [
            *FFMPEG_RESOURCE_CLAMP,
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(bg_png),
            "-vf",
            f"fps={fps},format=yuv420p",
            "-an",
            *FFMPEG_ENCODE_CLAMP,
            str(out_mp4),
        ]
    run_ffmpeg(cmd)
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
    fps = 24 if preview else project.fps
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

        # Render từng beat & gom theo chương (2-3 phút) để nhẹ RAM
        beat_clips: list[Path] = []
        total_b = len(beats)
        for idx, beat in enumerate(beats, start=1):
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
                bg_png=bg_png,
                char_png=char_png,
                out_mp4=clip_mp4,
                w=w,
                h=h,
                fps=fps,
                aspect=project.aspect,
                project_dir=project_dir,
            )
            beat_clips.append(clip_mp4)

            # Giải phóng file ảnh tạm & thu gom rác bộ nhớ ngay sau mỗi beat
            bg_png.unlink(missing_ok=True)
            if char_png is not None:
                char_png.unlink(missing_ok=True)
            if idx % 4 == 0:
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
            wm_fc = build_watermark_overlay_filter(video_label="0:v", wm_label="2:v", out_label="vout")
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
        # Luôn giải phóng build/chunks/ để bảo vệ ổ đĩa & RAM máy cũ
        shutil.rmtree(chunks_dir, ignore_errors=True)
        gc.collect()
