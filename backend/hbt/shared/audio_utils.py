"""Tiện ích xử lý âm thanh dùng chung: chuẩn hóa LUFS, trích biên độ RMS và tạo WAV dự phòng."""

from __future__ import annotations

import math
import os
import struct
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import numpy as np

from hbt.pipeline.ffutil import run_ffmpeg
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP

DEFAULT_SAMPLE_RATE = 24000


def normalize_audio_lufs(
    src_file: Path,
    target_lufs: float = -16.0,
    dst_file: Path | None = None,
    *,
    run_fn: Callable[[list[str]], Any] | None = None,
) -> Path:
    """Chuẩn hóa âm lượng MP3 bằng `loudnorm` (giữ nguyên file gốc nếu FFmpeg lỗi)."""
    target = dst_file or src_file
    tmp = target.with_name(f"{target.stem}.norm{target.suffix or '.mp3'}")
    runner = run_fn or run_ffmpeg
    try:
        runner(
            [
                *FFMPEG_RESOURCE_CLAMP,
                "-i",
                str(src_file),
                "-af",
                f"loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=11",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(tmp),
            ]
        )
        if tmp.is_file() and tmp.stat().st_size > 0:
            os.replace(tmp, target)
            return target
    except Exception:
        tmp.unlink(missing_ok=True)
    if dst_file is not None and src_file.is_file() and src_file != target and not target.is_file():
        os.replace(src_file, target)
    return target


def write_fallback_speech_wav_atomic(
    dest: Path,
    text: str,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    audible: bool = True,
) -> Path:
    """Tạo file WAV 24kHz mono 16-bit dự phòng khi chạy offline/CI không có VieNeu-TTS."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    words = [w for w in (text or "").split() if w.strip()]
    word_count = max(2 if audible else 1, len(words))
    if audible:
        dur_s = max(1.2, word_count * 0.28 + 0.25)
    else:
        dur_s = max(0.8, min(12.0, word_count * 0.34))
    total_frames = int(round(dur_s * sample_rate))
    buf = bytearray(total_frames * 2)

    if audible:
        frames_per_word = max(1, int(0.21 * sample_rate))
        gap_frames = max(1, int(0.05 * sample_rate))
        stride = frames_per_word + gap_frames
        for w_idx in range(word_count):
            start_f = int(0.08 * sample_rate) + w_idx * stride
            end_f = min(total_frames - int(0.08 * sample_rate), start_f + frames_per_word)
            if start_f >= total_frames or end_f <= start_f:
                break
            freq = 185.0 + (w_idx % 4) * 25.0
            for f in range(start_f, end_f):
                env = math.sin(math.pi * (f - start_f) / max(1, end_f - start_f))
                val = int(7500.0 * env * math.sin(2.0 * math.pi * freq * (f / sample_rate)))
                struct.pack_into("<h", buf, f * 2, val)

    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(buf))
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return dest


def extract_wav_rms_frames(
    wav_path: Path,
    fps: int,
    duration_sec: float,
    *,
    norm_mode: Literal["sample_p95", "frame_p92"] = "sample_p95",
) -> list[float]:
    """Đọc WAV PCM16 một lượt duy nhất và trả biên độ RMS chuẩn hóa theo từng frame."""
    safe_fps = max(1, int(fps))
    n_frames = max(1, int(round(max(0.1, float(duration_sec)) * safe_fps)))
    if not wav_path.is_file():
        return [0.0] * n_frames
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if not raw or sw != 2:
            return [0.0] * n_frames
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if ch > 1:
            samples = samples.reshape(-1, ch).mean(axis=1)
        samples /= 32768.0
        win = max(1, int(sr / safe_fps))

        raw_rms: list[float] = []
        for idx in range(n_frames):
            s0 = idx * win
            s1 = s0 + win
            if s0 >= len(samples):
                raw_rms.append(0.0)
            else:
                seg = samples[s0:s1]
                raw_rms.append(float(np.sqrt(np.mean(seg * seg))))

        if norm_mode == "frame_p92":
            p92 = float(np.percentile(raw_rms, 92)) if raw_rms else 0.1
            peak_ref = max(0.02, p92)
            return [min(1.0, r / peak_ref) for r in raw_rms]

        peak_ref = max(0.05, float(np.percentile(np.abs(samples), 95))) if len(samples) else 0.1
        return [min(1.0, round(r / peak_ref, 3)) for r in raw_rms]
    except Exception:
        return [0.0] * n_frames
