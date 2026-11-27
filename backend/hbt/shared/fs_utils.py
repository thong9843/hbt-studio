"""Tiện ích hệ thống tệp & ghi nguyên tử (atomic write, safe slug) dùng chung toàn backend."""

from __future__ import annotations

import json
import os
import re
import wave
from pathlib import Path
from typing import Any

import numpy as np

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def safe_slug(
    raw: str, *, default: str = "item", max_len: int = 64, lowercase: bool = False
) -> str:
    """Chuẩn hóa chuỗi bất kỳ thành tên tệp / slug an toàn."""
    txt = (raw or "").strip()
    if lowercase:
        txt = txt.lower()
    cleaned = _SLUG_RE.sub("-", txt).strip("-")
    if not cleaned:
        return default
    return cleaned[:max_len].strip("-") or default


def atomic_write_bytes(dest: Path, data: bytes) -> Path:
    """Ghi bytes ra file tạm cùng thư mục rồi `os.replace` để không bao giờ để lại file dở."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return dest


def atomic_write_text(dest: Path, text: str, *, encoding: str = "utf-8") -> Path:
    """Ghi chuỗi UTF-8 nguyên tử (temp + os.replace)."""
    return atomic_write_bytes(dest, text.encode(encoding))


def atomic_write_json(dest: Path, obj: Any, *, indent: int = 2) -> Path:
    """Ghi JSON nguyên tử UTF-8."""
    return atomic_write_text(dest, json.dumps(obj, ensure_ascii=False, indent=indent))


def atomic_write_pcm_wav(dest: Path, pcm: np.ndarray, *, sr: int, ch: int = 1) -> Path:
    """Ghi mảng float32 [-1, 1] sang WAV PCM int16 theo kiểu nguyên tử (temp + os.replace)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    clipped = np.clip(pcm, -1.0, 1.0)
    pcm_i16 = np.round(clipped * 32767.0).astype(np.int16)
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(ch)
            wf.setsampwidth(2)
            wf.setframerate(int(sr))
            wf.writeframes(pcm_i16.tobytes())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return dest
