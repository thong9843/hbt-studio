"""Gọi FFmpeg/ffprobe: chạy lệnh, đọc thông số, đo độ lớn (LUFS)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

LUFS_RE = re.compile(r"I:\s+(-?inf|-?\d+(?:\.\d+)?)\s+LUFS")


class FFmpegError(RuntimeError):
    """Lệnh FFmpeg/ffprobe lỗi; thông báo chứa phần cuối stderr."""


def _exe(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FFmpegError(f"Không tìm thấy {name} trên PATH. Hãy cài FFmpeg (xem README.md).")
    return path


def ffmpeg_exe() -> str:
    return _exe("ffmpeg")


def _tail(text: str, lines: int = 12) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def run_ffmpeg(args: Sequence[str | Path]) -> None:
    """Chạy `ffmpeg -y -v error <args>`; lỗi thì ném FFmpegError kèm stderr."""
    cmd = [_exe("ffmpeg"), "-hide_banner", "-v", "error", "-y", *map(str, args)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg lỗi (mã {result.returncode}):\n{_tail(result.stderr)}")


def probe(path: str | Path) -> dict:
    """ffprobe -show_streams -show_format → dict."""
    cmd = [
        _exe("ffprobe"),
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe lỗi với {path}:\n{_tail(result.stderr)}")
    return json.loads(result.stdout)


def media_duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


def measure_lufs(path: str | Path) -> float:
    """Độ lớn tích hợp (EBU R128, LUFS) của cả file. Im lặng hoàn toàn → -inf."""
    cmd = [
        _exe("ffmpeg"),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        "ebur128=peak=true",
        "-vn",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise FFmpegError(f"Không đo được độ lớn của {path}:\n{_tail(result.stderr)}")
    found = LUFS_RE.findall(result.stderr)
    if not found:
        raise FFmpegError(f"ffmpeg không in kết quả ebur128 cho {path}")
    return float(found[-1])
