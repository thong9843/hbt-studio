"""Tiện ích dùng chung cho test: tạo âm thanh giả, bỏ qua test cần FFmpeg khi máy không có."""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np
import pytest

SR = 44100

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="cần FFmpeg trên PATH")


def write_wav(path: Path, parts: list[tuple[str, float]], freq: float = 440.0) -> float:
    """Ghi wav mono 44,1 kHz. `parts`: [("tone"|"gap", giây)]. Trả về tổng thời lượng."""
    chunks = []
    for kind, dur in parts:
        n = int(round(dur * SR))
        if kind == "tone":
            t = np.arange(n) / SR
            chunks.append(0.5 * np.sin(2 * np.pi * freq * t))
        else:
            chunks.append(np.zeros(n))
    data = np.concatenate(chunks)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return len(data) / SR
