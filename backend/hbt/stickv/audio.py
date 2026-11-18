"""Âm thanh StickV: VieNeu-TTS có nhịp ngắt tự nhiên, Karaoke khóa tiếng nói & -14 LUFS."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import wave
from pathlib import Path

import numpy as np

from hbt.app_settings import resolve_online_api_key
from hbt.core.audio import build_topic_bgm_playlist
from hbt.pipeline.align import align_silence
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.postv.voice import SynthItem, VoiceProvider
from hbt.shared.ffmpeg_utils import (
    FFMPEG_RESOURCE_CLAMP,
    build_acrossfade_filter_graph,
    measure_audio_duration,
)
from hbt.shared.online_sources.jamendo_music import import_jamendo_music, search_jamendo_music
from hbt.shared.tts_client import DEFAULT_VIENEU_VOICE, resolve_voice_id
from hbt.stickv.models import StickvBeat

logger = logging.getLogger(__name__)

LEAD_IN_SILENCE_S = 0.10
SENTENCE_GAP_S = 0.30
PAUSE_END_SENTENCE_S = 0.45
PAUSE_MID_CLAUSE_S = 0.25

SFX_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "whoosh": ("swoosh", "whoosh", "swipe"),
    "pop": ("pop", "bubble", "click"),
    "vine_boom": ("bass-drop", "boom", "drop", "hit", "punch", "slam"),
    "ding": ("retrieve", "ding", "bell", "chime", "ping"),
}

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def split_beat_sentences(text: str) -> list[str]:
    """Tách các câu trong cùng 1 beat theo dấu ngắt câu (. ? ! …) để VieNeu đọc có nhịp nghỉ."""
    clean = (text or "").strip()
    if not clean:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", clean) if p.strip()]
    return parts or [clean]


def compute_pause_after(text: str, *, pause_scale: float = 1.0) -> float:
    """Tính khoảng nghỉ cuối beat: 0.45s cho kết câu (.?!…), 0.25s cho ngắt ý (,;:)."""
    stripped = (text or "").rstrip()
    base = PAUSE_END_SENTENCE_S if stripped.endswith((".", "?", "!", "…")) else PAUSE_MID_CLAUSE_S
    return round(base * max(0.5, min(2.0, float(pause_scale))), 3)


def _write_fallback_wav(dest: Path, text: str) -> None:
    """Tạo file WAV ước lượng theo độ dài chữ khi chạy unit test không có VieNeuProvider."""
    dur_s = max(1.0, min(12.0, len(text.split()) * 0.36))
    sr = 24000
    n_frames = int(dur_s * sr)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00\x00" * n_frames)


def _assemble_padded_beat_wav(
    sub_wavs: list[Path],
    out_wav: Path,
    *,
    lead_s: float,
    gap_s: float,
    tail_s: float,
    sentences: list[str] | None = None,
) -> tuple[float, list[tuple[float, float, str]]]:
    """Ghép các câu con kèm khoảng lặng đầu/giữa/cuối và trả về `(total_dur, spoken_segments)`."""
    chunks: list[bytes] = []
    sr = 24000
    ch = 1
    sw = 2

    valid_pairs: list[tuple[Path, str]] = []
    sent_list = sentences or []
    for idx, p in enumerate(sub_wavs):
        if p.is_file() and p.stat().st_size > 44:
            txt = sent_list[idx] if idx < len(sent_list) else ""
            valid_pairs.append((p, txt))

    if valid_pairs:
        try:
            with wave.open(str(valid_pairs[0][0]), "rb") as wf0:
                sr = wf0.getframerate()
                ch = wf0.getnchannels()
                sw = wf0.getsampwidth()
        except (wave.Error, EOFError):
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            out_wav.write_bytes(valid_pairs[0][0].read_bytes())
            dur = round(lead_s + tail_s + 0.5, 3)
            txt = valid_pairs[0][1]
            segs = [(round(lead_s, 4), round(lead_s + 0.5, 4), txt)] if txt else []
            return dur, segs

    bytes_per_sec = max(1, sr * ch * sw)
    acc_bytes = 0
    spoken_segments: list[tuple[float, float, str]] = []

    def _silence_bytes(sec: float) -> bytes:
        n_samples = max(0, int(round(sec * sr)))
        return b"\x00" * (n_samples * ch * sw)

    lead_b = _silence_bytes(lead_s)
    chunks.append(lead_b)
    acc_bytes += len(lead_b)

    for i, (wp, sent_txt) in enumerate(valid_pairs):
        with wave.open(str(wp), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        seg_start = round(acc_bytes / bytes_per_sec, 4)
        chunks.append(frames)
        acc_bytes += len(frames)
        seg_end = round(acc_bytes / bytes_per_sec, 4)
        if sent_txt:
            spoken_segments.append((seg_start, seg_end, sent_txt))
        if i < len(valid_pairs) - 1:
            gap_b = _silence_bytes(gap_s)
            chunks.append(gap_b)
            acc_bytes += len(gap_b)

    tail_b = _silence_bytes(tail_s)
    chunks.append(tail_b)
    acc_bytes += len(tail_b)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join(chunks)
    with wave.open(str(out_wav), "wb") as out_wf:
        out_wf.setnchannels(ch)
        out_wf.setsampwidth(sw)
        out_wf.setframerate(sr)
        out_wf.writeframes(payload)
    return round(len(payload) / bytes_per_sec, 3), spoken_segments


def _segments_sidecar_path(wav_path: Path) -> Path:
    return wav_path.with_suffix(".segments.json")


def load_beat_spoken_segments(wav_path: Path) -> list[tuple[float, float, str]]:
    """Đọc danh sách các đoạn nói thật `(start_s, end_s, text)` đã ghi cạnh file WAV."""
    sc = _segments_sidecar_path(wav_path)
    if not sc.is_file():
        return []
    try:
        raw = json.loads(sc.read_text(encoding="utf-8"))
        out: list[tuple[float, float, str]] = []
        if isinstance(raw, list):
            for it in raw:
                if isinstance(it, dict) and str(it.get("text") or "").strip():
                    st = float(it.get("start_s") or 0.0)
                    et = float(it.get("end_s") or st)
                    if et > st:
                        out.append((round(st, 4), round(et, 4), str(it["text"]).strip()))
        return out
    except Exception:
        return []


def build_global_spoken_segments(
    beat_wavs: list[tuple[Path, float]],
) -> list[tuple[float, float, str]]:
    """Chuyển `spoken_segments` của từng beat sang trục thời gian toàn cục của video."""
    global_segs: list[tuple[float, float, str]] = []
    cur_t = 0.0
    for wav_p, dur in beat_wavs:
        for st, et, txt in load_beat_spoken_segments(wav_p):
            global_segs.append((round(cur_t + st, 4), round(cur_t + et, 4), txt))
        cur_t += float(dur)
    return global_segs


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
    narration: str,
    speech_duration_sec: float,
    *,
    start_offset_s: float = 0.0,
) -> list[tuple[str, float, float]]:
    """Chia mốc thời gian cho từng từ trong [start_offset_s, start_offset_s + dur]."""
    words = [w for w in (narration or "").split() if w]
    if not words:
        return []
    dur = max(0.3, float(speech_duration_sec))
    weights = [max(1, len(w)) for w in words]
    total_w = sum(weights)
    timings: list[tuple[str, float, float]] = []
    cur = max(0.0, float(start_offset_s))
    for w, wt in zip(words, weights, strict=True):
        span = dur * (wt / total_w)
        timings.append((w, round(cur, 3), round(cur + span, 3)))
        cur += span
    return timings


def align_beat_karaoke(
    narration: str,
    wav_path: Path,
    total_dur: float,
    *,
    lead_in_s: float = LEAD_IN_SILENCE_S,
    pause_after_s: float = PAUSE_END_SENTENCE_S,
    spoken_segments: list[tuple[float, float, str]] | None = None,
) -> list[tuple[str, float, float]]:
    """Khóa mốc Karaoke chặt vào từng câu trong `spoken_segments` (không lấn khoảng lặng)."""
    segs = spoken_segments if spoken_segments is not None else load_beat_spoken_segments(wav_path)
    if segs:
        timings: list[tuple[str, float, float]] = []
        for seg_start, seg_end, seg_text in segs:
            seg_dur = max(0.15, float(seg_end) - float(seg_start))
            timings.extend(compute_word_timings(seg_text, seg_dur, start_offset_s=float(seg_start)))
        if timings:
            return timings

    words = [w for w in (narration or "").split() if w]
    if not words:
        return []
    max_speech_end = max(lead_in_s + 0.3, float(total_dur) - max(0.0, pause_after_s))
    if wav_path.is_file():
        try:
            spans = align_silence(words, wav_path, total_dur)
            if spans and len(spans) == len(words) and all(s is not None for s in spans):
                return [
                    (w, round(float(s[0]), 3), round(min(max_speech_end, float(s[1])), 3))
                    for w, s in zip(words, spans, strict=True)
                ]
        except Exception:
            pass
    speech_span = max(0.3, max_speech_end - lead_in_s)
    return compute_word_timings(narration, speech_span, start_offset_s=lead_in_s)


def synth_stickv_beats_audio(
    beats: list[StickvBeat],
    audio_dir: Path,
    *,
    voice_provider: VoiceProvider | None,
    voice_id: str,
    default_voice: str = DEFAULT_VIENEU_VOICE,
    pause_scale: float = 1.0,
) -> list[tuple[Path, float]]:
    """Sinh giọng từng câu con trong beat, chèn khoảng nghỉ tự nhiên & đo duration."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    scale = max(0.5, min(2.0, float(pause_scale)))
    lead_s = round(LEAD_IN_SILENCE_S * scale, 3)
    gap_s = round(SENTENCE_GAP_S * scale, 3)

    beat_sub_wavs: list[tuple[list[Path], list[str]]] = []
    synth_items: list[SynthItem] = []

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
        for beat in beats:
            sents = split_beat_sentences(beat.narration)
            sub_paths: list[Path] = []
            for s_idx, sent in enumerate(sents, start=1):
                sp = audio_dir / f"{beat.id}_s{s_idx}.wav"
                sub_paths.append(sp)
                synth_items.append(SynthItem(text=sent, voice_id=chosen_voice, out=sp))
            beat_sub_wavs.append((sub_paths, sents))
        if synth_items:
            voice_provider.synthesize_many(synth_items)
    else:
        for beat in beats:
            sents = split_beat_sentences(beat.narration) or ["stickv"]
            sub_paths = []
            for s_idx, sent in enumerate(sents, start=1):
                sp = audio_dir / f"{beat.id}_s{s_idx}.wav"
                _write_fallback_wav(sp, sent)
                sub_paths.append(sp)
            beat_sub_wavs.append((sub_paths, sents))

    results: list[tuple[Path, float]] = []
    for beat, (sub_paths, sents) in zip(beats, beat_sub_wavs, strict=True):
        if voice_provider is not None and sub_paths:
            for sp in sub_paths:
                if not sp.is_file() or sp.stat().st_size <= 44:
                    raise RuntimeError(f"VieNeu-TTS không tạo được file giọng cho beat {beat.id}")
        wav_p = audio_dir / f"{beat.id}.wav"
        tail_s = compute_pause_after(beat.narration, pause_scale=scale)
        assembled_dur, spoken_segs = _assemble_padded_beat_wav(
            sub_paths,
            wav_p,
            lead_s=lead_s,
            gap_s=gap_s,
            tail_s=tail_s,
            sentences=sents,
        )
        for sp in sub_paths:
            sp.unlink(missing_ok=True)
        _segments_sidecar_path(wav_p).write_text(
            json.dumps(
                [{"start_s": st, "end_s": et, "text": tx} for st, et, tx in spoken_segs],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        probed_dur = measure_audio_duration(wav_p)
        anchored_dur = round(max(1.2, probed_dur if probed_dur > 0 else assembled_dur), 3)
        beat.duration_sec = anchored_dur
        results.append((wav_p, anchored_dur))
    return results


def auto_resolve_mood_bgm(
    library_dir: Path,
    total_dur: float,
    music_mood: str,
    *,
    workspace_dir: Path | None = None,
) -> list[Path]:
    """Ưu tiên nhạc trong `library/music/` khớp `music_mood`; thiếu thì tự tải từ Jamendo."""
    tracks = build_topic_bgm_playlist(library_dir, total_dur, topic=music_mood)
    if tracks:
        return tracks
    cid = resolve_online_api_key("JAMENDO_CLIENT_ID", workspace_dir)
    if not cid:
        return []
    try:

        async def _fetch() -> list[Path]:
            hits = await search_jamendo_music(mood=music_mood, client_id=cid, limit=5)
            if not hits:
                return []
            first = hits[0]
            res = await import_jamendo_music(
                item_id=str(first.get("id") or ""),
                title=str(first.get("title") or "Jamendo BGM"),
                artist=str(first.get("artist") or "Jamendo Artist"),
                download_url=str(first.get("download_url") or first.get("preview_url") or ""),
                tags=list(first.get("tags") or []),
                moods=[music_mood] if music_mood else [],
                license_url=str(first.get("license") or ""),
                library_dir=library_dir,
            )
            p = Path(str(res.get("path") or ""))
            return [p] if p.is_file() else []

        return asyncio.run(_fetch())
    except Exception:
        return []


def mix_stickv_audio(
    *,
    beats: list[StickvBeat],
    beat_wavs: list[tuple[Path, float]],
    topic: str,
    library_dir: Path,
    assets_dir: Path,
    out_wav: Path,
    bgm_volume: float = 0.16,
    music_mood: str = "",
    workspace_dir: Path | None = None,
) -> Path:
    """Ghép giọng đọc + SFX (-16 LUFS) + nhạc nền (-27 LUFS) + master -14 LUFS."""
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
            f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[sfx_bus];"
            "[voice_bus][sfx_bus]amix=inputs=2:normalize=0[fg_bus]"
        )
    else:
        filter_parts.append("[voice_bus]acopy[fg_bus]")

    bgm_tracks = auto_resolve_mood_bgm(
        library_dir, total_dur, music_mood or topic, workspace_dir=workspace_dir
    )
    if bgm_tracks:
        bgm_start_idx = next_idx
        for t in bgm_tracks:
            inputs.extend(["-i", str(t)])
        bgm_fc, bgm_lbl = build_acrossfade_filter_graph(len(bgm_tracks), total_dur)
        for k in range(len(bgm_tracks) - 1, -1, -1):
            bgm_fc = bgm_fc.replace(f"[{k}:a]", f"[{bgm_start_idx + k}:a]")
        filter_parts.append(bgm_fc)
        filter_parts.append(
            f"{bgm_lbl}aresample=44100,loudnorm=I=-27:TP=-2.0:LRA=11,"
            f"volume={bgm_volume:.2f}[bgm_low];"
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
