"""Tiện ích FFmpeg dùng chung: đo thời lượng audio, kẹp tài nguyên, scale 9:16 và nhạc nền."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from hbt.pipeline import cancel as _cancel
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe, media_duration

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
    "-threads",
    "2",
    "-x264-params",
    "threads=2:lookahead_threads=1",
    "-max_muxing_queue_size",
    "512",
)

WINDOWS_LOW_PRIO_FLAGS: int = (
    getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000) if os.name == "nt" else 0
)


def run_ffmpeg_low_prio(
    args: Sequence[str | Path],
    *,
    timeout: float | None = None,
) -> None:
    """Chạy `ffmpeg -y -v error` ở mức ưu tiên thấp (Windows) để không chiếm nghẹt CPU máy."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-v", "error", "-y", *map(str, args)]
    token = _cancel.current()
    if token is not None:
        token.check()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=WINDOWS_LOW_PRIO_FLAGS,
    )
    if token is not None:
        token.track(proc)
    try:
        _, stderr = proc.communicate(timeout=timeout)
    finally:
        if token is not None:
            token.untrack(proc)
    if token is not None:
        token.check()
    if proc.returncode != 0:
        tail = "\n".join((stderr or "").strip().splitlines()[-12:])
        raise FFmpegError(f"ffmpeg lỗi (mã {proc.returncode}):\n{tail}")


ACROSSFADE_DURATION_S = 2.0

_SCRIPT_FLAG_LOCK = threading.Lock()
_CACHED_SCRIPT_FLAG: str | None = None


class MediaInfo(NamedTuple):
    """Thông số cơ bản từ `ffprobe`: `(duration_s, width, height)`."""

    duration_s: float
    width: int
    height: int


def probe_media_info(path: Path, *, timeout: float = 5.0) -> MediaInfo:
    """Đo `duration_s`, `width`, `height` bằng `ffprobe` JSON (trả 0 nếu không khả dụng)."""
    exe = shutil.which("ffprobe") or "ffprobe"
    try:
        pr = subprocess.run(
            [
                exe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if pr.returncode == 0 and pr.stdout.strip():
            info = json.loads(pr.stdout)
            streams = info.get("streams") or []
            w = int(streams[0].get("width") or 0) if streams else 0
            h = int(streams[0].get("height") or 0) if streams else 0
            dur = round(max(0.0, float((info.get("format") or {}).get("duration") or 0.0)), 3)
            return MediaInfo(duration_s=dur, width=w, height=h)
    except Exception:
        pass
    return MediaInfo(duration_s=0.0, width=0, height=0)


def resolve_filter_complex_script_flag(
    *,
    ffmpeg_bin: str | None = None,
    help_output: str | None = None,
) -> str:
    """Chọn cờ filtergraph theo FFmpeg (`-/filter_complex` 7+ vs `-filter_complex_script` 6)."""
    global _CACHED_SCRIPT_FLAG

    if help_output is not None:
        return (
            "-filter_complex_script"
            if "-filter_complex_script" in help_output
            else "-/filter_complex"
        )

    if ffmpeg_bin is None:
        with _SCRIPT_FLAG_LOCK:
            if _CACHED_SCRIPT_FLAG is not None:
                return _CACHED_SCRIPT_FLAG

    exe = ffmpeg_bin or shutil.which("ffmpeg")
    if exe is None:
        return "-filter_complex_script"

    try:
        pr = subprocess.run(
            [exe, "-hide_banner", "-h", "long"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
            check=False,
        )
        out = (pr.stderr or pr.stdout or "").strip()
        flag = (
            "-filter_complex_script"
            if (pr.returncode == 0 and "-filter_complex_script" in out)
            else "-/filter_complex"
        )
    except OSError:
        return "-filter_complex_script"

    if ffmpeg_bin is None:
        with _SCRIPT_FLAG_LOCK:
            _CACHED_SCRIPT_FLAG = flag
    return flag


def reset_script_flag_cache() -> None:
    """Xóa cache cờ filter_complex (dùng trong unit test)."""
    global _CACHED_SCRIPT_FLAG
    with _SCRIPT_FLAG_LOCK:
        _CACHED_SCRIPT_FLAG = None


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
