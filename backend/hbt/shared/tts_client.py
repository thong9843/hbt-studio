"""Giao thức gọi VieNeu-TTS dùng chung cho HBT Core, PostV và Chatting."""

from __future__ import annotations

import logging
from pathlib import Path

from hbt.postv.voice import SynthItem, VoiceProvider

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ALIAS = "vienneu_default"


def resolve_voice_id(voice_id: str | None, default_voice: str) -> str:
    """Chuẩn hóa `voice_id`: ánh xạ `vienneu_default` hoặc rỗng về giọng mặc định."""
    raw = (voice_id or DEFAULT_VOICE_ALIAS).strip()
    if not raw or raw == DEFAULT_VOICE_ALIAS:
        return default_voice
    return raw


def synthesize_single_segment_sync(
    *,
    spoken: str,
    chosen_voice: str,
    dest_wav: Path,
    voice_provider: VoiceProvider | None,
    tts_ok: bool,
    strict_tts: bool,
    index: int,
    fallback_fn,
) -> None:
    """Sinh giọng cho 1 phân đoạn bằng VieNeuProvider, tự rơi về `fallback_fn` nếu không strict."""
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
    fallback_fn(dest_wav, spoken or f"phân đoạn {index}")
