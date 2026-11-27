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
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hbt.core.models import HbtCoreSegment, SegmentVoiceTiming
from hbt.pipeline.text import RAW_TOKEN_RE, TOKEN_RE
from hbt.postv.voice import DEFAULT_NARRATOR as DEFAULT_VOICE
from hbt.postv.voice import SynthItem, VoiceProvider
from hbt.shared.audio_utils import write_fallback_speech_wav_atomic
from hbt.shared.tts_client import resolve_voice_id as _resolve_voice_id

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
LEAD_PAD_US = 150_000  # 0.15 giây đệm đầu trước phân đoạn 1
SEGMENT_GAP_US = 450_000  # 0.45 giây khoảng nghỉ tự nhiên giữa các phân đoạn
TAIL_PAD_US = 1_000_000  # 1.00 giây đuôi cuối để không bao giờ cắt cụt âm tiết cuối
_TARGET_SEG_RMS = 0.14  # ~ -17 dBFS trước khi loudnorm tổng -14 LUFS


def _normalize_pcm_rms(pcm: bytes) -> bytes:
    """Cân đều độ lớn giữa các đoạn giọng VieNeu trước khi ghép tổng (giữ đỉnh <= 0.95)."""
    if len(pcm) < 4:
        return pcm
    import array

    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    n = len(samples)
    if n == 0:
        return pcm
    peak = max(abs(min(samples)), abs(max(samples)))
    if peak < 150:
        return pcm
    sq_sum = sum(s * s for s in samples)
    rms = math.sqrt(sq_sum / n) / 32768.0
    if rms <= 1e-4:
        return pcm
    gain = min(_TARGET_SEG_RMS / rms, (0.95 * 32767.0) / peak, 3.0)
    if 0.92 <= gain <= 1.08:
        return pcm
    out = array.array("h", (max(-32767, min(32767, int(round(s * gain)))) for s in samples))
    return out.tobytes()


def spoken_text_for_segment(raw_text: str) -> str:
    """Chuyển lời thoại có thể chứa `{cách đọc}` hoặc `|` sang văn bản đọc cho VieNeu-TTS."""
    raw = (raw_text or "").strip()
    if not raw:
        return ""
    parts: list[str] = []
    pending_break = False
    for token in RAW_TOKEN_RE.findall(raw):
        if token == "|":
            pending_break = True
            continue
        m = TOKEN_RE.match(token)
        if m:
            spoken = (m.group("spoken") or "").strip() or (m.group("disp") or "").strip()
            word = f"{spoken}{m.group('punct') or ''}".strip()
        else:
            word = token.strip()
        if not word:
            continue
        if pending_break and parts and not parts[-1].endswith((",", ".", "!", "?", ";", ":", "…")):
            parts[-1] = parts[-1] + ","
        parts.append(word)
        pending_break = False
    return " ".join(parts).strip()


def _segment_hash(voice_id: str, spoken: str) -> str:
    payload = f"hbt_core_v1|{voice_id}|{spoken.strip()}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def create_fallback_speech_wav(dest: Path, text: str, sample_rate: int = SAMPLE_RATE) -> None:
    """Tạo file WAV giọng giả lập có nhịp âm tiết (khi CI/test chưa cài .venv-tts)."""
    write_fallback_speech_wav_atomic(dest, text, sample_rate=sample_rate, audible=True)


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


def trim_wav_speech_bounds(wav_path: Path, frame_ms: int = 20) -> tuple[float, float]:
    """Đo ngưỡng RMS từng cửa sổ 20ms để tìm mốc bắt đầu/kết thúc tiếng nói thật `[lo, hi]`
    bên trong file WAV (loại bỏ khoảng lặng đầu/cuối của VieNeu-TTS)."""
    try:
        pcm = _read_mono_16bit_pcm(wav_path, SAMPLE_RATE)
    except Exception:
        dur = wav_duration_us(wav_path) / 1_000_000 if wav_path.is_file() else 1.0
        return 0.0, max(0.2, dur)

    import array

    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    n = len(samples)
    total_s = n / SAMPLE_RATE if n else 0.0
    if n == 0:
        return 0.0, 0.2

    peak = max(abs(min(samples)), abs(max(samples)))
    if peak < 150:
        return 0.0, max(0.2, total_s)

    step = max(1, int(SAMPLE_RATE * frame_ms / 1000))
    thresh = max(220.0, peak * 0.05)
    first_active: int | None = None
    last_active: int | None = None
    for i in range(0, n, step):
        chunk = samples[i : i + step]
        if not chunk:
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
        if rms >= thresh:
            if first_active is None:
                first_active = i
            last_active = min(n, i + step)

    if first_active is None or last_active is None:
        return 0.0, max(0.2, total_s)

    lo = max(0.0, (first_active / SAMPLE_RATE) - 0.02)
    hi = min(total_s, (last_active / SAMPLE_RATE) + 0.04)
    if hi - lo < 0.15:
        return 0.0, max(0.2, total_s)
    return round(lo, 4), round(hi, 4)


def build_core_voice_full_wav(
    timings: list[SegmentVoiceTiming],
    scene_starts: list[float],
    total_duration_s: float,
    dest_wav: Path,
    *,
    lead_pad_s: float = LEAD_PAD_US / 1_000_000,
) -> Path:
    """Ghép toàn bộ giọng từng cảnh đúng theo mốc `scene_starts` của trục video `xfade` thành
    `core_voice_full.wav` (16-bit mono 24kHz) để Whisper căn chữ và bộ trộn dùng chung 1 trục."""
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    total_frames = max(1, int(round(max(total_duration_s, 0.5) * SAMPLE_RATE)))
    buf = bytearray(total_frames * 2)

    for idx, (timing, start_s) in enumerate(zip(timings, scene_starts, strict=False)):
        seg_wav = Path(timing.wav_path)
        if not seg_wav.is_file():
            continue
        pcm = _normalize_pcm_rms(_read_mono_16bit_pcm(seg_wav, SAMPLE_RATE))
        place_s = max(0.0, float(start_s) + (lead_pad_s if idx == 0 else 0.0))
        start_f = int(round(place_s * SAMPLE_RATE))
        if start_f >= total_frames:
            continue
        max_bytes = (total_frames - start_f) * 2
        chunk = pcm[:max_bytes]
        byte_off = start_f * 2
        buf[byte_off : byte_off + len(chunk)] = chunk

    tmp_wav = dest_wav.with_name(dest_wav.name + ".tmp")
    with wave.open(str(tmp_wav), "wb") as out_wf:
        out_wf.setnchannels(1)
        out_wf.setsampwidth(2)
        out_wf.setframerate(SAMPLE_RATE)
        out_wf.writeframes(bytes(buf))
    tmp_wav.replace(dest_wav)
    return dest_wav


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
    available_voice_ids: list[str] | None = None
    if voice_provider is not None and hasattr(voice_provider, "status"):
        try:
            st = voice_provider.status()
            tts_ok = bool(st and st.ok)
            if tts_ok and hasattr(voice_provider, "list_voices"):
                available_voice_ids = [v.id for v in voice_provider.list_voices()]
        except Exception:
            tts_ok = False

    if tts_ok and available_voice_ids:
        chosen_voice = _resolve_voice_id(
            chosen_voice, DEFAULT_VOICE, available_voices=available_voice_ids
        )

    if strict_tts and not tts_ok:
        raise RuntimeError("VieNeu-TTS (.venv-tts) chưa sẵn sàng trên máy")

    segment_entries: list[tuple[int, HbtCoreSegment, str, Path, bool]] = []
    pending_items: list[tuple[int, SynthItem]] = []
    for idx, seg in enumerate(segments, start=1):
        spoken = spoken_text_for_segment(seg.text)
        h = _segment_hash(chosen_voice, spoken or f"empty_{idx}")
        seg_wav = cache_dir / f"seg_{idx:02d}_{h}.wav"
        was_cached = (
            seg_wav.is_file()
            and seg_wav.stat().st_size > 44
            and wav_duration_us(seg_wav) >= 100_000
        )
        segment_entries.append((idx, seg, spoken, seg_wav, was_cached))
        if not was_cached and tts_ok and voice_provider is not None and spoken:
            pending_items.append((idx, SynthItem(text=spoken, voice_id=chosen_voice, out=seg_wav)))

    # Gọi VieNeu-TTS theo 1 lô duy nhất (nạp mô hình 1 lần thay vì lặp lại từng phân đoạn)
    if pending_items and voice_provider is not None:
        batch_items = [item for _, item in pending_items]
        done_count = sum(1 for _, _, _, _, c in segment_entries if c)

        def _on_item(batch_idx: int, state: str) -> None:
            nonlocal done_count
            if state != "done" or on_sse_event is None:
                return
            done_count = min(total, done_count + 1)
            pct = int(round((done_count / total) * 100))
            on_sse_event(
                {
                    "step": "voice",
                    "current": done_count,
                    "total": total,
                    "percent": pct,
                    "message": f"Đã sinh giọng đọc phân đoạn {done_count}/{total} ({pct}%)",
                }
            )

        try:
            try:
                voice_provider.synthesize_many(batch_items, on_item=_on_item)
            except TypeError:
                voice_provider.synthesize_many(batch_items)
        except Exception as exc:
            if strict_tts:
                raise
            logger.warning(
                "VieNeu-TTS lỗi khi sinh lô giọng (%s), rơi về WAV dự phòng: %s",
                chosen_voice,
                exc,
            )

    segment_wavs: list[tuple[HbtCoreSegment, Path, bool]] = []
    for idx, seg, spoken, seg_wav, was_cached in segment_entries:
        valid_wav = (
            seg_wav.is_file()
            and seg_wav.stat().st_size > 44
            and wav_duration_us(seg_wav) >= 100_000
        )
        if not valid_wav:
            if tts_ok and spoken:
                logger.warning(
                    "VieNeu-TTS không tạo WAV hợp lệ phân đoạn %d (size=%s), dùng WAV dự phòng",
                    idx,
                    seg_wav.stat().st_size if seg_wav.is_file() else 0,
                )
            create_fallback_speech_wav(seg_wav, spoken or "phân đoạn")

        segment_wavs.append((seg, seg_wav, was_cached))

        if not pending_items or was_cached:
            percent = int(round((idx / total) * 100))
            if on_sse_event is not None:
                on_sse_event(
                    {
                        "step": "voice",
                        "current": idx,
                        "total": total,
                        "percent": percent,
                        "message": f"Đã sinh giọng đọc phân đoạn {idx}/{total} ({percent}%)",
                    }
                )

    # Ghép nối tất cả segment WAV thành project_dir / "voice.wav" và tính mốc micro-giây chính xác
    combined_wav = project_dir / "voice.wav"
    tmp_wav = project_dir / "voice.wav.tmp"
    timings: list[SegmentVoiceTiming] = []

    cursor_us = 0
    lead_frames = int(round((LEAD_PAD_US / 1_000_000) * SAMPLE_RATE))
    gap_frames = int(round((SEGMENT_GAP_US / 1_000_000) * SAMPLE_RATE))
    tail_frames = int(round((TAIL_PAD_US / 1_000_000) * SAMPLE_RATE))
    silence_lead_bytes = b"\x00\x00" * lead_frames
    silence_gap_bytes = b"\x00\x00" * gap_frames
    silence_tail_bytes = b"\x00\x00" * tail_frames

    with wave.open(str(tmp_wav), "wb") as out_wf:
        out_wf.setnchannels(1)
        out_wf.setsampwidth(2)
        out_wf.setframerate(SAMPLE_RATE)

        if lead_frames > 0:
            out_wf.writeframes(silence_lead_bytes)
            cursor_us += int(round((lead_frames * 1_000_000) / SAMPLE_RATE))

        for i, (seg, seg_wav, was_cached) in enumerate(segment_wavs):
            pcm = _normalize_pcm_rms(_read_mono_16bit_pcm(seg_wav, SAMPLE_RATE))
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
