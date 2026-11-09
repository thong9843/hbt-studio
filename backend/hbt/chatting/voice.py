"""Tạo giọng VieNeu cho từng tin nhắn Chatting theo §9 (dùng lại voice_worker của PostV)."""

from __future__ import annotations

import hashlib
import logging
import wave
from pathlib import Path

from hbt.chatting.models import ChatDoc
from hbt.pipeline.ffutil import media_duration
from hbt.postv.censor import CensorStore, compile_censor, find_censor_hits
from hbt.postv.voice import SynthItem, VoiceProvider

logger = logging.getLogger(__name__)

DEFAULT_CHAR_VOICES = {
    "me": "Adam bựa",
    "left_1": "Trúc Ly",
    "left_2": "Thiện Minh",
    "left_3": "Mai Anh",
}


def get_voice_cache_dir(project_dir: Path) -> Path:
    d = project_dir / "build" / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def text_hash(voice_id: str, text: str) -> str:
    s = f"{voice_id}:{text.strip()}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:16]


def create_placeholder_wav(dest: Path, duration_s: float, sample_rate: int = 24000) -> None:
    """Tạo file wav giữ chỗ (âm thanh mẫu/yên lặng) khi TTS chưa sẵn sàng."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    num_frames = int(duration_s * sample_rate)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Ghi các sample 0 (yên lặng)
        wf.writeframes(b"\x00\x00" * num_frames)


def get_wav_duration(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return round(frames / float(rate), 3)
    except Exception:
        dur = media_duration(wav_path)
        return dur if dur is not None else 1.0


def check_censor_text(workspace_dir: Path, text: str) -> bool:
    """Kiểm tra có từ che K-41 trong text không."""
    try:
        store = CensorStore(workspace_dir)
        matchers = compile_censor(store.load().words)
        hits = find_censor_hits(text, matchers)
        return len(hits) > 0
    except Exception:
        return False


def synthesize_chat_voices(
    workspace_dir: Path,
    slug: str,
    doc: ChatDoc,
    voice_provider: VoiceProvider,
) -> list[tuple[int, Path, float]]:
    """Sinh giọng cho toàn bộ tin nhắn trong doc.
    Trả về danh sách: [(message_index, wav_path, duration_s), ...]
    """
    project_dir = workspace_dir / "chatting" / slug
    cache_dir = get_voice_cache_dir(project_dir)

    char_map = {c.id: c for c in doc.characters}
    results: list[tuple[int, Path, float]] = []
    items_to_synth: list[tuple[int, SynthItem]] = []

    # Kiểm tra trạng thái TTS
    status = voice_provider.status() if hasattr(voice_provider, "status") else None
    tts_ready = status.ok if status else False

    for idx, msg in enumerate(doc.messages):
        char = char_map.get(msg.from_)
        voice_id = char.voice if char and char.voice else DEFAULT_CHAR_VOICES.get("me", "Adam bựa")
        h = text_hash(voice_id, msg.text)
        out_file = cache_dir / f"{h}.wav"

        if out_file.is_file() and out_file.stat().st_size > 44:
            results.append((idx, out_file, get_wav_duration(out_file)))
        else:
            items_to_synth.append((idx, SynthItem(text=msg.text, voice_id=voice_id, out=out_file)))

    if items_to_synth:
        if tts_ready:
            try:
                synth_list = [item for _, item in items_to_synth]
                voice_provider.synthesize_many(synth_list)
                for idx, item in items_to_synth:
                    dur = get_wav_duration(item.out)
                    results.append((idx, item.out, dur))
            except Exception as e:
                logger.warning("VieNeu synthesize_many thất bại: %s, dùng âm thanh giữ chỗ", e)
                for idx, item in items_to_synth:
                    dur = max(1.0, round(len(item.text) / 14.0, 2))
                    create_placeholder_wav(item.out, dur)
                    results.append((idx, item.out, dur))
        else:
            # Fallback tạo placeholder wav nếu chưa cài hoặc thiếu weights
            for idx, item in items_to_synth:
                dur = max(1.0, round(len(item.text) / 14.0, 2))
                create_placeholder_wav(item.out, dur)
                results.append((idx, item.out, dur))

    results.sort(key=lambda r: r[0])
    return results
