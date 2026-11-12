"""Pipeline sinh giọng tự động VieNeu-TTS cho từng phân đoạn kịch bản HBT Core.

- Thay thế hoàn toàn quy trình tải file âm thanh thủ công từ Vbee.
- Không giới hạn số từ (loại bỏ hoàn toàn giới hạn 750 từ / 3000 ký tự).
- Gửi từng câu `text` qua VieNeu-TTS, lưu vào `audio/segment_X.wav`, đo thời lượng chính xác
  bằng `ffprobe` (hoặc `wave`), tính mốc `start_time` / `end_time` để FFmpeg Timeline hiển thị
  từng ảnh và thẻ kem khớp 100% độ dài câu đọc.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from hbt.config import load_settings
from hbt.core.models import HbtCoreSegment
from hbt.core.voice import (
    DEFAULT_VOICE,
    SEGMENT_GAP_US,
    create_fallback_speech_wav,
    spoken_text_for_segment,
    wav_duration_us,
)
from hbt.pipeline.ffutil import media_duration
from hbt.postv.voice import SynthItem, VieNeuProvider, VoiceProvider

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ALIAS = "vienneu_default"


def resolve_voice_id(voice_id: str | None) -> str:
    """Chuẩn hóa `voice_id`: ánh xạ `vienneu_default` về giọng mặc định VieNeu."""
    raw = (voice_id or DEFAULT_VOICE_ALIAS).strip()
    if not raw or raw == DEFAULT_VOICE_ALIAS:
        return DEFAULT_VOICE
    return raw


def measure_audio_duration(audio_path: Path) -> float:
    """Đo thời lượng chính xác (giây) của file WAV bằng `ffprobe`, fallback sang `wave`."""
    try:
        probed = media_duration(audio_path)
        if probed is not None and probed > 0:
            return round(float(probed), 6)
    except Exception:
        pass
    dur_us = wav_duration_us(audio_path)
    return round(dur_us / 1_000_000.0, 6)


def _segment_to_dict(seg: HbtCoreSegment | dict[str, Any], index: int) -> dict[str, Any]:
    if isinstance(seg, HbtCoreSegment):
        d = seg.model_dump(mode="json")
    else:
        d = dict(seg)
    d.setdefault("id", index)
    d.setdefault("order", d["id"])
    return d


def _synthesize_single_segment_sync(
    *,
    spoken: str,
    chosen_voice: str,
    dest_wav: Path,
    voice_provider: VoiceProvider | None,
    tts_ok: bool,
    strict_tts: bool,
    index: int,
) -> None:
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    if tts_ok and voice_provider is not None and spoken:
        try:
            voice_provider.synthesize_many(
                [SynthItem(text=spoken, voice_id=chosen_voice, out=dest_wav)]
            )
            if dest_wav.is_file() and dest_wav.stat().st_size > 44:
                return
        except Exception as exc:
            if strict_tts:
                raise
            logger.warning(
                "VieNeu-TTS lỗi ở phân đoạn %d (%s), dùng WAV dự phòng: %s",
                index,
                chosen_voice,
                exc,
            )
    if strict_tts and not tts_ok:
        raise RuntimeError("VieNeu-TTS (.venv-tts) chưa sẵn sàng trên máy")
    create_fallback_speech_wav(dest_wav, spoken or f"phân đoạn {index}")


async def synthesize_script_segments(
    segments: Sequence[HbtCoreSegment | dict[str, Any]],
    voice_id: str = DEFAULT_VOICE_ALIAS,
    *,
    output_dir: Path | None = None,
    voice_provider: VoiceProvider | None = None,
    on_sse_event: Callable[[dict[str, Any]], None] | None = None,
    strict_tts: bool = False,
    gap_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Tự động sinh file giọng `audio/segment_X.wav` bằng VieNeu-TTS cho từng phân đoạn,
    đo `duration` chính xác bằng ffprobe/wave và tính mốc `start_time`, `end_time`.

    Trả về danh sách các phân đoạn kèm `duration`, `audio_path`, `start_time`, `end_time`.
    """
    seg_list = list(segments)
    total = len(seg_list)
    if total == 0:
        return []

    settings = load_settings()
    base_dir = Path(output_dir) if output_dir is not None else settings.workspace_dir / "core_tts"
    audio_dir = base_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    provider = voice_provider
    if provider is None:
        try:
            cache_file = settings.workspace_dir / "cache" / "vieneu_voices.json"
            provider = VieNeuProvider(settings.models_dir, cache_file=cache_file)
        except Exception:
            provider = None

    tts_ok = False
    if provider is not None and hasattr(provider, "status"):
        try:
            st = await asyncio.to_thread(provider.status)
            tts_ok = bool(st and st.ok)
        except Exception:
            tts_ok = False

    if strict_tts and not tts_ok:
        raise RuntimeError("VieNeu-TTS (.venv-tts) chưa sẵn sàng trên máy")

    chosen_voice = resolve_voice_id(voice_id)
    gap_s = (SEGMENT_GAP_US / 1_000_000.0) if gap_seconds is None else max(0.0, float(gap_seconds))

    enriched: list[dict[str, Any]] = []
    cursor_s = 0.0

    for idx, raw_seg in enumerate(seg_list, start=1):
        seg_dict = _segment_to_dict(raw_seg, idx)
        seg_id = int(seg_dict.get("id") or idx)
        seg_wav = audio_dir / f"segment_{seg_id}.wav"
        spoken = spoken_text_for_segment(str(seg_dict.get("text") or ""))

        await asyncio.to_thread(
            _synthesize_single_segment_sync,
            spoken=spoken,
            chosen_voice=chosen_voice,
            dest_wav=seg_wav,
            voice_provider=provider,
            tts_ok=tts_ok,
            strict_tts=strict_tts,
            index=idx,
        )

        duration_s = await asyncio.to_thread(measure_audio_duration, seg_wav)
        start_time = round(cursor_s, 6)
        end_time = round(start_time + duration_s, 6)
        cursor_s = end_time + (gap_s if idx < total else 0.0)

        seg_out = {
            **seg_dict,
            "id": seg_id,
            "order": idx,
            "voice_id": chosen_voice,
            "duration": duration_s,
            "audio_path": str(seg_wav),
            "start_time": start_time,
            "end_time": end_time,
        }
        enriched.append(seg_out)

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

    return enriched


def sync_wavs_to_audio_folder(
    timings_paths: Sequence[tuple[int, Path]],
    project_dir: Path,
) -> list[Path]:
    """Sao chép các file giọng phân đoạn vào `project_dir/audio/segment_X.wav`."""
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for seg_id, src in timings_paths:
        dest = audio_dir / f"segment_{seg_id}.wav"
        if src.is_file() and src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        out.append(dest)
    return out
