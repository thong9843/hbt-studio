"""Tiện ích FFmpeg dùng chung: đo thời lượng audio, kẹp tài nguyên, scale 9:16 và nhạc nền."""

from __future__ import annotations

from pathlib import Path

from hbt.pipeline.ffutil import media_duration

FFMPEG_RESOURCE_CLAMP: tuple[str, ...] = (
    "-threads",
    "2",
    "-filter_threads",
    "2",
)

FFMPEG_ENCODE_CLAMP: tuple[str, ...] = (
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "22",
    "-max_muxing_queue_size",
    "512",
)

ACROSSFADE_DURATION_S = 2.0


def measure_audio_duration(audio_path: Path, fallback_us_fn=None) -> float:
    """Đo thời lượng chính xác (giây) của file audio bằng `ffprobe`, fallback sang `wave`."""
    try:
        probed = media_duration(audio_path)
        if probed is not None and probed > 0:
            return round(float(probed), 6)
    except Exception:
        pass
    if fallback_us_fn is not None:
        return round(fallback_us_fn(audio_path) / 1_000_000.0, 6)
    return 0.0


def build_scale_9_16_filter(width: int = 1080, height: int = 1920) -> str:
    """Bộ lọc FFmpeg scale + crop khung dọc 9:16 chuẩn."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}"
    )


def build_acrossfade_filter_graph(
    num_tracks: int,
    target_duration_s: float,
    *,
    crossfade_s: float = ACROSSFADE_DURATION_S,
) -> tuple[str, str]:
    """Sinh chuỗi filter_complex nối các bài nhạc bằng `acrossfade=d=2.0` chuẩn FFmpeg."""
    fade_out_st = max(0.5, target_duration_s - 1.5)
    if num_tracks <= 1:
        fc = (
            f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"atrim=0:{target_duration_s:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_st:.3f}:d=1.5[bgm]"
        )
        return fc, "[bgm]"

    parts: list[str] = []
    for i in range(num_tracks):
        parts.append(
            f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS[a{i}]"
        )

    prev_label = "[a0]"
    for i in range(1, num_tracks):
        out_label = f"[xf{i}]"
        parts.append(f"{prev_label}[a{i}]acrossfade=d={crossfade_s:.1f}:c1=tri:c2=tri{out_label}")
        prev_label = out_label

    parts.append(
        f"{prev_label}atrim=0:{target_duration_s:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_st:.3f}:d=1.5[bgm]"
    )
    return ";".join(parts), "[bgm]"
