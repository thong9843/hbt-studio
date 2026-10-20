"""GET /api/health — kiểm tra môi trường: FFmpeg, faster-whisper, GPU CUDA."""

from __future__ import annotations

import importlib
import shutil
import subprocess

from fastapi import APIRouter

router = APIRouter()


def check_ffmpeg() -> bool:
    exe = shutil.which("ffmpeg")
    if exe is None:
        return False
    try:
        result = subprocess.run([exe, "-version"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


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
def health() -> dict[str, bool]:
    ffmpeg = check_ffmpeg()
    # Chỉ FFmpeg là bắt buộc để dựng; Whisper và GPU có đường dự phòng (mục 5.2).
    return {"ok": ffmpeg, "ffmpeg": ffmpeg, "whisper": check_whisper(), "gpu": check_gpu()}
