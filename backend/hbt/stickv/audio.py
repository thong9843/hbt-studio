"""Âm thanh StickV: VieNeu-TTS batch (Audio Anchoring), lip-sync RMS, karaoke & -14 LUFS."""

from __future__ import annotations

import logging
import wave
from pathlib import Path

import numpy as np

from hbt.core.audio import build_topic_bgm_playlist
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.postv.voice import SynthItem, VoiceProvider
from hbt.shared.ffmpeg_utils import (
    FFMPEG_RESOURCE_CLAMP,
    build_acrossfade_filter_graph,
    measure_audio_duration,
)
from hbt.shared.tts_client import DEFAULT_VIENEU_VOICE, resolve_voice_id
from hbt.stickv.models import StickvBeat

logger = logging.getLogger(__name__)

SFX_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "whoosh": ("swoosh", "whoosh", "swipe"),
    "pop": ("pop", "bubble", "click"),
    "vine_boom": ("bass-drop", "boom", "drop", "hit", "punch", "slam"),
    "ding": ("retrieve", "ding", "bell", "chime", "ping"),
}

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def _write_fallback_wav(dest: Path, text: str) -> None:
    """Tạo file WAV ước lượng theo độ dài chữ khi chạy unit test không có VieNeuProvider."""
    dur_s = max(1.4, min(12.0, len(text.split()) * 0.38))
    sr = 24000
    n_frames = int(dur_s * sr)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * n_frames)


def resolve_sfx_file(
    sfx_tag: str, library_dir: Path, assets_dir: Path | None = None
) -> Path | None:
    """Tìm file SFX khớp `sfx_tag` trong `library/sfx/` hoặc `assets/sfx/`."""
    tag = (sfx_tag or "none").strip().lower()
    if tag == "none":
        return None
    keywords = SFX_TAG_KEYWORDS.get(tag, (tag,))
    dirs = [library_dir / "sfx"]
    if assets_dir is not None:
        dirs.insert(0, assets_dir / "sfx")

    for d in dirs:
        if not d.is_dir():
            continue
        files = sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTS)
        for kw in keywords:
            for f in files:
                if kw in f.stem.lower():
                    return f
    return None


def extract_wav_rms_envelope(wav_path: Path, fps: int, duration_sec: float) -> list[float]:
    """Trích biên độ RMS theo từng khung hình (0.0..1.0) để đồng bộ nhép miệng (Lip-sync)."""
    n_frames = max(1, int(round(duration_sec * fps)))
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
        win = max(1, int(sr / fps))
        out: list[float] = []
        peak_ref = max(0.05, float(np.percentile(np.abs(samples), 95))) if len(samples) else 0.1
        for f_idx in range(n_frames):
            s0 = f_idx * win
            s1 = s0 + win
            if s0 >= len(samples):
                out.append(0.0)
            else:
                rms = float(np.sqrt(np.mean(samples[s0:s1] ** 2)))
                out.append(min(1.0, round(rms / peak_ref, 3)))
        return out
    except Exception:
        return [0.0] * n_frames


def compute_word_timings(
    narration: str, speech_duration_sec: float
) -> list[tuple[str, float, float]]:
    """Chia mốc thời gian tương đối cho từng từ để tô sáng phụ đề Karaoke."""
    words = [w for w in (narration or "").split() if w]
    if not words:
        return []
    dur = max(0.5, float(speech_duration_sec))
    weights = [max(1, len(w)) for w in words]
    total_w = sum(weights)
    timings: list[tuple[str, float, float]] = []
    cur = 0.0
    for w, wt in zip(words, weights, strict=True):
        span = dur * (wt / total_w)
        timings.append((w, cur, cur + span))
        cur += span
    return timings


def synth_stickv_beats_audio(
    beats: list[StickvBeat],
    audio_dir: Path,
    *,
    voice_provider: VoiceProvider | None,
    voice_id: str,
    default_voice: str = DEFAULT_VIENEU_VOICE,
) -> list[tuple[Path, float]]:
    """Sinh giọng từng beat bằng VieNeu-TTS theo lô (1 lần nạp model) & đo duration_sec."""
    audio_dir.mkdir(parents=True, exist_ok=True)

    if voice_provider is not None:
        status = voice_provider.status()
        if not status.ok:
            raise RuntimeError(
                status.note
                or "VieNeu-TTS (.venv-tts hoặc models/hf_vieneu) chưa sẵn sàng để đọc lời thoại."
            )
        available_ids: list[str] = []
        try:
            available_ids = [v.id for v in voice_provider.list_voices()]
        except Exception:
            available_ids = []
        chosen_voice = resolve_voice_id(
            voice_id, default_voice, available_voices=available_ids or None
        )
        synth_items: list[SynthItem] = []
        wav_paths: list[Path] = []
        for beat in beats:
            wav_p = audio_dir / f"{beat.id}.wav"
            wav_paths.append(wav_p)
            spoken = (beat.narration or "").strip()
            if spoken:
                synth_items.append(SynthItem(text=spoken, voice_id=chosen_voice, out=wav_p))
        if synth_items:
            voice_provider.synthesize_many(synth_items)
    else:
        wav_paths = []
        for beat in beats:
            wav_p = audio_dir / f"{beat.id}.wav"
            _write_fallback_wav(wav_p, beat.narration or "stickv")
            wav_paths.append(wav_p)

    results: list[tuple[Path, float]] = []
    for beat, wav_p in zip(beats, wav_paths, strict=True):
        if not wav_p.is_file() or wav_p.stat().st_size <= 44:
            if voice_provider is not None:
                raise RuntimeError(f"VieNeu-TTS không tạo được file giọng cho beat {beat.id}")
            _write_fallback_wav(wav_p, beat.narration or "stickv")
        raw_dur = measure_audio_duration(wav_p)
        anchored_dur = round(max(1.2, raw_dur + 0.25), 3)
        beat.duration_sec = anchored_dur
        results.append((wav_p, anchored_dur))
    return results


def mix_stickv_audio(
    *,
    beats: list[StickvBeat],
    beat_wavs: list[tuple[Path, float]],
    topic: str,
    library_dir: Path,
    assets_dir: Path,
    out_wav: Path,
    bgm_volume: float = 0.16,
) -> Path:
    """Ghép giọng đọc theo neo thời gian + SFX + nhạc nền ducking + chuẩn hoá -14 LUFS."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    total_dur = round(sum(d for _, d in beat_wavs), 3)
    if total_dur <= 0:
        _write_fallback_wav(out_wav, "empty")
        return out_wav

    inputs: list[str] = []
    filter_parts: list[str] = []

    cur_t = 0.0
    voice_labels: list[str] = []
    sfx_events: list[tuple[float, Path]] = []

    for i, (beat, (wav_p, dur)) in enumerate(zip(beats, beat_wavs, strict=False)):
        inputs.extend(["-i", str(wav_p)])
        delay_ms = int(round(cur_t * 1000))
        lbl = f"[v{i}]"
        filter_parts.append(
            f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}{lbl}"
        )
        voice_labels.append(lbl)
        sfx_path = resolve_sfx_file(beat.sfx_tag, library_dir, assets_dir)
        if sfx_path is not None:
            sfx_events.append((cur_t, sfx_path))
        cur_t += dur

    filter_parts.append(
        f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:normalize=0,"
        f"apad=whole_dur={total_dur:.3f}[voice_bus]"
    )

    next_idx = len(beat_wavs)
    sfx_labels: list[str] = []
    for s_i, (s_t, s_path) in enumerate(sfx_events[:40]):
        inputs.extend(["-i", str(s_path)])
        delay_ms = int(round(s_t * 1000))
        lbl = f"[sfx{s_i}]"
        filter_parts.append(
            f"[{next_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume=0.35,adelay={delay_ms}|{delay_ms}{lbl}"
        )
        sfx_labels.append(lbl)
        next_idx += 1

    if sfx_labels:
        filter_parts.append(
            f"[voice_bus]{''.join(sfx_labels)}amix=inputs={1 + len(sfx_labels)}:normalize=0[fg_bus]"
        )
    else:
        filter_parts.append("[voice_bus]acopy[fg_bus]")

    bgm_tracks = build_topic_bgm_playlist(library_dir, total_dur, topic=topic)
    if bgm_tracks:
        bgm_start_idx = next_idx
        for t in bgm_tracks:
            inputs.extend(["-i", str(t)])
        bgm_fc, bgm_lbl = build_acrossfade_filter_graph(len(bgm_tracks), total_dur)
        for k in range(len(bgm_tracks) - 1, -1, -1):
            bgm_fc = bgm_fc.replace(f"[{k}:a]", f"[{bgm_start_idx + k}:a]")
        filter_parts.append(bgm_fc)
        filter_parts.append(
            f"{bgm_lbl}aresample=44100,volume={bgm_volume:.2f}[bgm_low];"
            "[fg_bus]asplit=2[fg_sc][fg_mix];"
            "[bgm_low][fg_sc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=250[bgm_duck];"
            "[fg_mix][bgm_duck]amix=inputs=2:normalize=0,"
            "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
        )
    else:
        filter_parts.append("[fg_bus]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    cmd = [
        *FFMPEG_RESOURCE_CLAMP,
        *inputs,
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[aout]",
        "-t",
        f"{total_dur:.3f}",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "44100",
        str(out_wav),
    ]
    run_ffmpeg(cmd)
    return out_wav
