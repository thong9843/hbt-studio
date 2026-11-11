"""Sinh giọng đọc tự động VieNeu-TTS cho HBT Core (Nhiệm vụ 1.1).

- Thay thế hoàn toàn quy trình tải file âm thanh thủ công từ Vbee.
- Tích hợp engine VieNeu-TTS nội bộ (.venv-tts, HF_HUB_OFFLINE=1) tự động sinh file giọng đọc
  từng phân đoạn (segment).
- Tính mốc micro-giây chính xác (start_us, end_us, duration_us) kèm giây (start_s, end_s).
- Bắn sự kiện tiến trình SSE `{step: "voice", current, total, percent}`.
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hbt.core.models import HbtCoreSegment, SegmentVoiceTiming
from hbt.pipeline.text import parse_voice
from hbt.postv.voice import DEFAULT_NARRATOR as DEFAULT_VOICE
from hbt.postv.voice import SynthItem, VoiceProvider

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
SEGMENT_GAP_US = 220_000  # 0.22 giây khoảng nghỉ tự nhiên giữa các phân đoạn
TAIL_PAD_US = 300_000  # 0.30 giây đuôi cuối file giọng


def spoken_text_for_segment(raw_text: str) -> str:
    """Chuyển lời thoại có thể chứa `{cách đọc}` hoặc `|` sang văn bản đọc cho VieNeu-TTS."""
    tokens = parse_voice(raw_text or "")
    if not tokens:
        return (raw_text or "").replace("|", " ").strip()
    parts: list[str] = []
    for i, tok in enumerate(tokens):
        if (
            i > 0
            and tok.get("chunk_start")
            and parts
            and not parts[-1].endswith((",", ".", "!", "?", ";", ":"))
        ):
            parts[-1] = parts[-1] + ","
        parts.append(str(tok.get("spoken", "")).strip())
    return " ".join(p for p in parts if p).strip()


def _segment_hash(voice_id: str, spoken: str) -> str:
    payload = f"hbt_core_v1|{voice_id}|{spoken.strip()}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def create_fallback_speech_wav(dest: Path, text: str, sample_rate: int = SAMPLE_RATE) -> None:
    """Tạo file WAV giọng giả lập có nhịp âm tiết (dùng khi môi trường test/CI chưa cài .venv-tts).

    Tạo cụm xung âm thanh theo từng từ và khoảng lặng giữa các phân đoạn để bộ căn chữ
    (align_scenes / silence) và bộ trộn FFmpeg luôn hoạt động mượt 100% offline.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    words = [w for w in (text or "").split() if w.strip()]
    word_count = max(2, len(words))
    # Mỗi từ ~0.24s phát âm + 0.05s nghỉ nhẹ, tổng tối thiểu 1.2s
    dur_s = max(1.2, min(12.0, word_count * 0.28 + 0.25))
    total_frames = int(round(dur_s * sample_rate))

    buf = bytearray(total_frames * 2)
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

    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(buf))


def wav_frames_and_rate(wav_path: Path) -> tuple[int, int]:
    """Đọc chính xác số frame và sample rate của file WAV."""
    with wave.open(str(wav_path), "rb") as wf:
        return wf.getnframes(), wf.getframerate()


def wav_duration_us(wav_path: Path) -> int:
    """Tính thời lượng chính xác của file WAV bằng micro-giây (1s = 1_000_000 us)."""
    frames, rate = wav_frames_and_rate(wav_path)
    if rate <= 0:
        return 1_000_000
    return int(round((frames * 1_000_000) / rate))


def _read_mono_16bit_pcm(wav_path: Path, target_rate: int = SAMPLE_RATE) -> bytes:
    """Đọc dữ liệu PCM 16-bit mono từ file WAV để ghép nối thành voice.wav tổng."""
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if channels == 1 and sampwidth == 2 and rate == target_rate:
        return raw

    # Chuyển đổi đơn giản nếu khác kênh hoặc tần số lấy mẫu
    import audioop

    data = raw
    if sampwidth != 2:
        data = audioop.lin2lin(data, sampwidth, 2)
    if channels > 1:
        data = audioop.tomono(data, 2, 0.5, 0.5)
    if rate != target_rate:
        data, _ = audioop.ratecv(data, 2, 1, rate, target_rate, None)
    return data


def synthesize_core_segments(
    segments: list[HbtCoreSegment],
    project_dir: Path,
    voice_provider: VoiceProvider | None = None,
    *,
    voice_id: str | None = None,
    on_sse_event: Callable[[dict[str, Any]], None] | None = None,
    strict_tts: bool = False,
) -> tuple[Path, list[SegmentVoiceTiming]]:
    """Sinh giọng tự động VieNeu-TTS cho từng phân đoạn (segment), tính mốc micro-giây
    chính xác và bắn sự kiện tiến trình SSE `{step: "voice", current, total, percent}`.

    Trả về `(combined_voice_wav_path, list[SegmentVoiceTiming])`.
    """
    chosen_voice = (voice_id or DEFAULT_VOICE).strip() or DEFAULT_VOICE
    cache_dir = project_dir / "build" / "core_voice"
    cache_dir.mkdir(parents=True, exist_ok=True)

    total = len(segments)
    if total == 0:
        raise ValueError("Không có phân đoạn nào để sinh giọng đọc")

    tts_ok = False
    if voice_provider is not None and hasattr(voice_provider, "status"):
        try:
            st = voice_provider.status()
            tts_ok = bool(st and st.ok)
        except Exception:
            tts_ok = False

    if strict_tts and not tts_ok:
        raise RuntimeError("VieNeu-TTS (.venv-tts) chưa sẵn sàng trên máy")

    segment_wavs: list[tuple[HbtCoreSegment, Path, bool]] = []

    for idx, seg in enumerate(segments, start=1):
        spoken = spoken_text_for_segment(seg.text)
        h = _segment_hash(chosen_voice, spoken or f"empty_{idx}")
        seg_wav = cache_dir / f"seg_{idx:02d}_{h}.wav"
        was_cached = seg_wav.is_file() and seg_wav.stat().st_size > 44

        if not was_cached:
            if tts_ok and voice_provider is not None and spoken:
                try:
                    voice_provider.synthesize_many(
                        [SynthItem(text=spoken, voice_id=chosen_voice, out=seg_wav)]
                    )
                except Exception as exc:
                    if strict_tts:
                        raise
                    logger.warning(
                        "VieNeu-TTS lỗi ở phân đoạn %d (%s), dùng WAV dự phòng: %s",
                        idx,
                        chosen_voice,
                        exc,
                    )
                    create_fallback_speech_wav(seg_wav, spoken)
            else:
                create_fallback_speech_wav(seg_wav, spoken or "phân đoạn")

        segment_wavs.append((seg, seg_wav, was_cached))

        percent = int(round((idx / total) * 100))
        event_payload = {
            "step": "voice",
            "current": idx,
            "total": total,
            "percent": percent,
            "message": f"Đã sinh giọng đọc phân đoạn {idx}/{total} ({percent}%)",
        }
        if on_sse_event is not None:
            on_sse_event(event_payload)

    # Ghép nối tất cả segment WAV thành project_dir / "voice.wav" và tính mốc micro-giây chính xác
    combined_wav = project_dir / "voice.wav"
    tmp_wav = project_dir / "voice.wav.tmp"
    timings: list[SegmentVoiceTiming] = []

    cursor_us = 0
    gap_frames = int(round((SEGMENT_GAP_US / 1_000_000) * SAMPLE_RATE))
    tail_frames = int(round((TAIL_PAD_US / 1_000_000) * SAMPLE_RATE))
    silence_gap_bytes = b"\x00\x00" * gap_frames
    silence_tail_bytes = b"\x00\x00" * tail_frames

    with wave.open(str(tmp_wav), "wb") as out_wf:
        out_wf.setnchannels(1)
        out_wf.setsampwidth(2)
        out_wf.setframerate(SAMPLE_RATE)

        for i, (seg, seg_wav, was_cached) in enumerate(segment_wavs):
            pcm = _read_mono_16bit_pcm(seg_wav, SAMPLE_RATE)
            num_frames = len(pcm) // 2
            dur_us = int(round((num_frames * 1_000_000) / SAMPLE_RATE))
            start_us = cursor_us
            end_us = start_us + dur_us

            out_wf.writeframes(pcm)
            cursor_us = end_us

            if i < len(segment_wavs) - 1:
                out_wf.writeframes(silence_gap_bytes)
                cursor_us += int(round((gap_frames * 1_000_000) / SAMPLE_RATE))
            else:
                out_wf.writeframes(silence_tail_bytes)
                cursor_us += int(round((tail_frames * 1_000_000) / SAMPLE_RATE))

            timings.append(
                SegmentVoiceTiming(
                    order=seg.order,
                    text=seg.text,
                    voice_id=chosen_voice,
                    wav_path=str(seg_wav),
                    start_us=start_us,
                    end_us=end_us,
                    duration_us=dur_us,
                    start_s=round(start_us / 1_000_000, 6),
                    end_s=round(end_us / 1_000_000, 6),
                    duration_s=round(dur_us / 1_000_000, 6),
                    cached=was_cached,
                )
            )

    tmp_wav.replace(combined_wav)
    return combined_wav, timings
