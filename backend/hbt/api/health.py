"""GET /api/health — kiểm tra môi trường: FFmpeg (kèm encoder/filter cần dùng), faster-whisper, GPU.

Định nghĩa (IMPLEMENT.md mục 9): `ok` = FFmpeg chạy được và đủ mọi encoder/filter trong
REQUIRED_ENCODERS + REQUIRED_FILTERS; `missing` liệt kê thứ còn thiếu. Whisper và GPU không
ảnh hưởng `ok` vì đã có đường dự phòng (mục 5.2).
"""

from __future__ import annotations

import importlib
import re
import shutil
import subprocess

from fastapi import APIRouter

router = APIRouter()

REQUIRED_ENCODERS = ("libx264",)
REQUIRED_FILTERS = ("zoompan", "xfade", "sidechaincompress", "loudnorm", "silencedetect")


def _ffmpeg_stdout(*args: str) -> str | None:
    """Chạy `ffmpeg -hide_banner <args>`; None nếu không có FFmpeg hoặc lỗi."""
    exe = shutil.which("ffmpeg")
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "-hide_banner", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


# Một dòng của bảng: cột cờ (2–6 ký tự gồm chữ, `.` hoặc `|`), rồi tên. Không dựa vào dòng phân cách
# `------` vì FFmpeg 6.1 không in nó cho `-filters` (bản 9.0 có), và số cờ mỗi bản một khác.
ENTRY = re.compile(r"^\s*[A-Za-z.|]{2,6}\s+(\S+)")


def parse_names(listing: str) -> set[str]:
    """Lấy tên từ bảng `ffmpeg -encoders` / `-filters`.

    Dòng chú thích ("T.. = Timeline support", "A = Audio input/output") có tên là `=` hoặc không có
    cột cờ, nên bị loại."""
    names: set[str] = set()
    for line in listing.splitlines():
        m = ENTRY.match(line)
        if m and m.group(1) != "=":
            names.add(m.group(1))
    return names


def check_ffmpeg() -> list[str] | None:
    """None nếu không chạy được FFmpeg; ngược lại là danh sách encoder/filter còn thiếu."""
    if _ffmpeg_stdout("-version") is None:
        return None
    encoders = _ffmpeg_stdout("-encoders")
    filters = _ffmpeg_stdout("-filters")
    have = parse_names(encoders or "") | parse_names(filters or "")
    return [n for n in (*REQUIRED_ENCODERS, *REQUIRED_FILTERS) if n not in have]


def check_whisper() -> bool:
    try:
        importlib.import_module("faster_whisper")
    except Exception:
        return False
    return True


def check_gpu() -> bool:
    # faster-whisper chạy trên CTranslate2 → hỏi thẳng CTranslate2, không cần torch.
    try:
        ctranslate2 = importlib.import_module("ctranslate2")
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


@router.get("/health")
def health() -> dict[str, bool | list[str]]:
    missing = check_ffmpeg()
    ffmpeg = missing is not None
    if missing is None:
        missing = ["ffmpeg"]
    return {
        "ok": not missing,
        "ffmpeg": ffmpeg,
        "whisper": check_whisper(),
        "gpu": check_gpu(),
        "missing": missing,
    }
