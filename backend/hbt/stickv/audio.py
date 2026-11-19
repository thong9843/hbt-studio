"""Âm thanh StickV: VieNeu-TTS có nhịp ngắt tự nhiên, Karaoke khóa tiếng nói & -14 LUFS."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
from hbt.shared.online_sources.freesound_audio import (
    import_freesound_audio,
    search_freesound_audio,
)
from hbt.shared.tts_client import DEFAULT_VIENEU_VOICE, resolve_voice_id
from hbt.stickv.models import StickvBeat

logger = logging.getLogger(__name__)

# Chuẩn nhịp thở & chống AAC priming nuốt chữ đầu video (GĐ9)
GLOBAL_LEAD_SILENCE_S = 0.18
LEAD_IN_SILENCE_S = 0.04
SENTENCE_GAP_S = 0.20
PAUSE_END_SENTENCE_S = 0.24
PAUSE_MID_CLAUSE_S = 0.20

DEFAULT_PRE_ROLL_MS = 35
DEFAULT_POST_ROLL_MS = 75
DEFAULT_GHOST_MAX_MS = 80
DEFAULT_GHOST_GAP_MS = 220
DEFAULT_FADE_IN_MS = 18
DEFAULT_FADE_OUT_MS = 25

SFX_TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "whoosh": ("swoosh", "whoosh", "swipe"),
    "pop": ("pop", "bubble", "click"),
    "vine_boom": ("bass-drop", "boom", "drop", "hit", "punch", "slam"),
    "ding": ("retrieve", "ding", "bell", "chime", "ping"),
}

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_HEADING_RE = re.compile(r"(?m)^\s*#+\s*")
_MD_BULLET_RE = re.compile(r"(?m)^\s*[-•*]\s+")
_MD_SYNTAX_RE = re.compile(r"\*\*|__|~~|`|#")
_MULTI_SPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?…])")
_DUP_PUNCT_RE = re.compile(r"([.!?])\1+")


def _atomic_write_bytes(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _atomic_write_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _atomic_write_pcm_wav(dest: Path, pcm: np.ndarray, *, sr: int, ch: int = 1) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    arr = np.asarray(pcm, dtype=np.int16)
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(ch)
            wf.setsampwidth(2)
            wf.setframerate(int(sr))
            wf.writeframes(arr.tobytes())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def sanitize_tts_text(text: str, *, ensure_terminal: bool = True) -> str:
    """Làm sạch markdown & chuẩn hóa dấu câu tiếng Việt trước khi gửi vào VieNeu-TTS."""
    raw = str(text or "")
    if not raw.strip():
        return ""
    s = _MD_LINK_RE.sub(r"\1", raw)
    s = _MD_HEADING_RE.sub("", s)
    s = _MD_BULLET_RE.sub("", s)
    s = _MD_SYNTAX_RE.sub("", s)
    s = s.replace("*", "")
    s = s.replace("...", "…")
    s = _MULTI_SPACE_RE.sub(" ", s).strip()
    s = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", s)
    s = _DUP_PUNCT_RE.sub(r"\1", s)
    s = s.strip(" \t\r\n\"'“”")
    if not s:
        return ""
    if ensure_terminal and not s.endswith((".", "?", "!", "…")):
        s = s.rstrip(",;:-–— ")
        if s and not s.endswith((".", "?", "!", "…")):
            s = f"{s}."
    return s


def split_beat_sentences(text: str, *, min_words: int = 5) -> list[str]:
    """Tách câu theo dấu ngắt câu (. ? ! …) và gộp mảnh < 5 từ để giữ mạch ngữ điệu tự nhiên."""
    clean = sanitize_tts_text(text, ensure_terminal=True)
    if not clean:
        return []
    raw_parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", clean) if p.strip()]
    if len(raw_parts) <= 1:
        return raw_parts or [clean]

    threshold = max(1, int(min_words))
    merged: list[str] = []
    idx = 0
    while idx < len(raw_parts):
        part = raw_parts[idx]
        words_n = len(part.split())
        if words_n < threshold:
            if merged:
                merged[-1] = f"{merged[-1]} {part}"
            elif idx + 1 < len(raw_parts):
                raw_parts[idx + 1] = f"{part} {raw_parts[idx + 1]}"
            else:
                merged.append(part)
        else:
            merged.append(part)
        idx += 1

    return [sanitize_tts_text(p, ensure_terminal=True) for p in merged if p.strip()] or [clean]


def compute_pause_after(text: str, *, pause_scale: float = 1.0) -> float:
    """Tính khoảng nghỉ cuối beat: 0.24s cho kết câu (.?!…), 0.20s cho ngắt ý (,;:)."""
    stripped = (text or "").rstrip()
    base = PAUSE_END_SENTENCE_S if stripped.endswith((".", "?", "!", "…")) else PAUSE_MID_CLAUSE_S
    return round(base * max(0.5, min(2.0, float(pause_scale))), 3)


def clean_tts_wav(
    wav_path: Path,
    out_path: Path | None = None,
    *,
    pre_roll_ms: int = DEFAULT_PRE_ROLL_MS,
    post_roll_ms: int = DEFAULT_POST_ROLL_MS,
    ghost_max_ms: int = DEFAULT_GHOST_MAX_MS,
    ghost_gap_ms: int = DEFAULT_GHOST_GAP_MS,
    fade_in_ms: int = DEFAULT_FADE_IN_MS,
    fade_out_ms: int = DEFAULT_FADE_OUT_MS,
    rms_thresh: float = 0.014,
) -> dict[str, Any]:
    """Làm sạch clip WAV từ VieNeu-TTS bằng Envelope + ZCR Gate & cosine fade chống click.

    - Bảo vệ âm đầu bằng `pre_roll >= 35ms` và âm đóng bằng `post_roll >= 75ms`.
    - Cắt sạch xung nhiễu đuôi tách biệt `< 80ms` sau khoảng lặng `>= 220ms` (tiếng ma `"Nếu..."`).
    - Áp cosine fade-in `18ms` và fade-out `25ms` chống bậc nhảy biên độ khi ghép câu.
    """
    src = Path(wav_path)
    dest = Path(out_path) if out_path is not None else src
    if not src.is_file() or src.stat().st_size <= 44:
        return {
            "file_path": str(dest),
            "cleaned": False,
            "ghosts_removed": 0,
            "pre_roll_ms": 0.0,
            "post_roll_ms": 0.0,
            "original_ms": 0.0,
            "cleaned_ms": 0.0,
        }

    try:
        with wave.open(str(src), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError):
        return {
            "file_path": str(dest),
            "cleaned": False,
            "ghosts_removed": 0,
            "pre_roll_ms": 0.0,
            "post_roll_ms": 0.0,
            "original_ms": 0.0,
            "cleaned_ms": 0.0,
        }

    if sw != 2 or not raw or sr <= 0:
        return {
            "file_path": str(dest),
            "cleaned": False,
            "ghosts_removed": 0,
            "pre_roll_ms": 0.0,
            "post_roll_ms": 0.0,
            "original_ms": 0.0,
            "cleaned_ms": 0.0,
        }

    pcm = np.frombuffer(raw, dtype=np.int16)
    if ch > 1:
        pcm = pcm.reshape(-1, ch)
        mono = pcm.astype(np.float32).mean(axis=1) / 32768.0
    else:
        mono = pcm.astype(np.float32) / 32768.0

    n_samples = len(mono)
    orig_ms = round((n_samples / sr) * 1000.0, 2)
    frame_ms = 10
    frame_samp = max(1, int(round(sr * frame_ms / 1000.0)))
    n_frames = max(1, (n_samples + frame_samp - 1) // frame_samp)

    rms_arr = np.zeros(n_frames, dtype=np.float32)
    zcr_arr = np.zeros(n_frames, dtype=np.float32)
    for fi in range(n_frames):
        s0 = fi * frame_samp
        s1 = min(n_samples, s0 + frame_samp)
        seg = mono[s0:s1]
        if len(seg) == 0:
            continue
        rms_arr[fi] = float(np.sqrt(np.mean(seg * seg)))
        if len(seg) > 1:
            zcr_arr[fi] = float(np.mean(np.abs(np.diff(np.signbit(seg).astype(np.int8)))))

    peak_rms = float(np.max(rms_arr)) if len(rms_arr) else 0.0
    if peak_rms < 1e-4:
        # Clip im lặng (fallback test) -> giữ nguyên độ dài, ghi nguyên tử nếu khác đích
        if dest != src:
            _atomic_write_pcm_wav(dest, pcm, sr=sr, ch=ch)
        return {
            "file_path": str(dest),
            "cleaned": True,
            "ghosts_removed": 0,
            "pre_roll_ms": 0.0,
            "post_roll_ms": 0.0,
            "original_ms": orig_ms,
            "cleaned_ms": orig_ms,
        }

    eff_thresh = max(float(rms_thresh), peak_rms * 0.06)
    zcr_rms_floor = max(0.005, eff_thresh * 0.45)
    active = (rms_arr >= eff_thresh) | ((rms_arr >= zcr_rms_floor) & (zcr_arr >= 0.12))

    # Gom thành các đảo tiếng nói (nối các khoảng đóng phụ âm tắc < 60ms)
    raw_islands: list[tuple[int, int]] = []
    fi = 0
    while fi < n_frames:
        if not active[fi]:
            fi += 1
            continue
        start_f = fi
        while fi < n_frames and active[fi]:
            fi += 1
        raw_islands.append((start_f, fi))

    if not raw_islands:
        if dest != src:
            _atomic_write_pcm_wav(dest, pcm, sr=sr, ch=ch)
        return {
            "file_path": str(dest),
            "cleaned": True,
            "ghosts_removed": 0,
            "pre_roll_ms": 0.0,
            "post_roll_ms": 0.0,
            "original_ms": orig_ms,
            "cleaned_ms": orig_ms,
        }

    bridge_frames = max(1, int(round(60 / frame_ms)))
    islands: list[tuple[int, int]] = [raw_islands[0]]
    for st_f, en_f in raw_islands[1:]:
        prev_st, prev_en = islands[-1]
        if st_f - prev_en < bridge_frames:
            islands[-1] = (prev_st, en_f)
        else:
            islands.append((st_f, en_f))

    # Triệt tiêu xung nhiễu đuôi tách biệt (< ghost_max_ms sau khoảng nghỉ >= ghost_gap_ms)
    ghosts_removed = 0
    ghost_cut_samp = n_samples
    while len(islands) >= 2:
        last_st, last_en = islands[-1]
        prev_st, prev_en = islands[-2]
        last_dur_ms = (last_en - last_st) * frame_ms
        gap_ms = (last_st - prev_en) * frame_ms
        if last_dur_ms <= max(10, int(ghost_max_ms)) and gap_ms >= max(80, int(ghost_gap_ms)):
            ghost_cut_samp = min(ghost_cut_samp, last_st * frame_samp)
            islands.pop()
            ghosts_removed += 1
        else:
            break

    speech_start_samp = islands[0][0] * frame_samp
    speech_end_samp = min(n_samples, islands[-1][1] * frame_samp)

    safe_pre_ms = max(DEFAULT_PRE_ROLL_MS, int(pre_roll_ms))
    safe_post_ms = max(DEFAULT_POST_ROLL_MS, int(post_roll_ms))
    pre_samp = int(round(sr * safe_pre_ms / 1000.0))
    post_samp = int(round(sr * safe_post_ms / 1000.0))

    trim_start = max(0, speech_start_samp - pre_samp)
    need_pre = max(0, pre_samp - speech_start_samp)

    max_end = min(n_samples, ghost_cut_samp)
    trim_end = min(max_end, speech_end_samp + post_samp)
    actual_post_avail = max(0, trim_end - speech_end_samp)
    need_post = max(0, post_samp - actual_post_avail)

    sliced = pcm[trim_start:trim_end].astype(np.float32)

    # Cosine De-Click Fade-In (18ms) & Fade-Out (25ms)
    fi_samp = min(len(sliced) // 2, max(1, int(round(sr * max(1, int(fade_in_ms)) / 1000.0))))
    fo_samp = min(len(sliced) // 2, max(1, int(round(sr * max(1, int(fade_out_ms)) / 1000.0))))
    if fi_samp > 1:
        ramp_in = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fi_samp, dtype=np.float32)))
        if ch > 1:
            ramp_in = ramp_in[:, None]
        sliced[:fi_samp] *= ramp_in
    if fo_samp > 1:
        ramp_out = 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fo_samp, dtype=np.float32)))
        if ch > 1:
            ramp_out = ramp_out[:, None]
        sliced[-fo_samp:] *= ramp_out

    parts: list[np.ndarray] = []
    if need_pre > 0:
        z_shape = (need_pre, ch) if ch > 1 else (need_pre,)
        parts.append(np.zeros(z_shape, dtype=np.float32))
    parts.append(sliced)
    if need_post > 0:
        z_shape = (need_post, ch) if ch > 1 else (need_post,)
        parts.append(np.zeros(z_shape, dtype=np.float32))

    final_f = np.concatenate(parts, axis=0) if len(parts) > 1 else sliced
    out_pcm = np.clip(np.round(final_f), -32768, 32767).astype(np.int16)
    _atomic_write_pcm_wav(dest, out_pcm, sr=sr, ch=ch)

    actual_pre_ms = round(((speech_start_samp - trim_start) + need_pre) / sr * 1000.0, 2)
    actual_post_ms = round((actual_post_avail + need_post) / sr * 1000.0, 2)
    cleaned_ms = round((len(out_pcm) / sr) * 1000.0, 2)
    return {
        "file_path": str(dest),
        "cleaned": True,
        "ghosts_removed": ghosts_removed,
        "pre_roll_ms": actual_pre_ms,
        "post_roll_ms": actual_post_ms,
        "original_ms": orig_ms,
        "cleaned_ms": cleaned_ms,
    }


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
    clean_clips: bool = True,
) -> tuple[float, list[tuple[float, float, str]]]:
    """Làm sạch từng clip TTS, ghép kèm khoảng lặng đầu/giữa/cuối & trả `(dur, spoken_segments)`."""
    chunks: list[bytes] = []
    sr = 24000
    ch = 1
    sw = 2

    valid_pairs: list[tuple[Path, str]] = []
    sent_list = sentences or []
    for idx, p in enumerate(sub_wavs):
        if p.is_file() and p.stat().st_size > 44:
            if clean_clips:
                clean_tts_wav(p)
            txt = sent_list[idx] if idx < len(sent_list) else ""
            valid_pairs.append((p, txt))

    if valid_pairs:
        try:
            with wave.open(str(valid_pairs[0][0]), "rb") as wf0:
                sr = wf0.getframerate()
                ch = wf0.getnchannels()
                sw = wf0.getsampwidth()
        except (wave.Error, EOFError):
            _atomic_write_bytes(out_wav, valid_pairs[0][0].read_bytes())
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
    tmp_wav = out_wav.with_name(f"{out_wav.name}.tmp")
    try:
        with wave.open(str(tmp_wav), "wb") as out_wf:
            out_wf.setnchannels(ch)
            out_wf.setsampwidth(sw)
            out_wf.setframerate(sr)
            out_wf.writeframes(payload)
        os.replace(tmp_wav, out_wav)
    finally:
        if tmp_wav.exists():
            tmp_wav.unlink(missing_ok=True)
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
    global_lead_s: float = GLOBAL_LEAD_SILENCE_S,
    on_progress: Callable[[float, str], None] | None = None,
    cancel: Any | None = None,
) -> list[tuple[Path, float]]:
    """Sinh giọng sạch từng câu, bảo vệ âm đầu + 180ms AAC priming guard & đo duration."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    scale = max(0.5, min(2.0, float(pause_scale)))
    lead_s = round(LEAD_IN_SILENCE_S * scale, 3)
    first_lead_s = round(max(float(global_lead_s), lead_s), 3)
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
            if cancel is not None and hasattr(cancel, "check"):
                cancel.check()
            voice_provider.synthesize_many(synth_items)
    else:
        for beat in beats:
            sents = split_beat_sentences(beat.narration) or ["stickv."]
            sub_paths = []
            for s_idx, sent in enumerate(sents, start=1):
                sp = audio_dir / f"{beat.id}_s{s_idx}.wav"
                _write_fallback_wav(sp, sent)
                sub_paths.append(sp)
            beat_sub_wavs.append((sub_paths, sents))

    results: list[tuple[Path, float]] = []
    total_beats_count = max(1, len(beats))
    for beat_idx, (beat, (sub_paths, sents)) in enumerate(zip(beats, beat_sub_wavs, strict=True)):
        if cancel is not None and hasattr(cancel, "check"):
            cancel.check()
        if voice_provider is not None and sub_paths:
            for sp in sub_paths:
                if not sp.is_file() or sp.stat().st_size <= 44:
                    raise RuntimeError(f"VieNeu-TTS không tạo được file giọng cho beat {beat.id}")
        wav_p = audio_dir / f"{beat.id}.wav"
        tail_s = compute_pause_after(beat.narration, pause_scale=scale)
        cur_lead_s = first_lead_s if beat_idx == 0 else lead_s
        assembled_dur, spoken_segs = _assemble_padded_beat_wav(
            sub_paths,
            wav_p,
            lead_s=cur_lead_s,
            gap_s=gap_s,
            tail_s=tail_s,
            sentences=sents,
            clean_clips=True,
        )
        for sp in sub_paths:
            sp.unlink(missing_ok=True)
        _atomic_write_text(
            _segments_sidecar_path(wav_p),
            json.dumps(
                [{"start_s": st, "end_s": et, "text": tx} for st, et, tx in spoken_segs],
                ensure_ascii=False,
                indent=2,
            ),
        )
        probed_dur = measure_audio_duration(wav_p)
        anchored_dur = round(max(1.2, probed_dur if probed_dur > 0 else assembled_dur), 3)
        beat.duration_sec = anchored_dur
        results.append((wav_p, anchored_dur))
        if on_progress is not None:
            pct = 8.0 + ((beat_idx + 1) / total_beats_count) * 18.0
            on_progress(
                round(pct, 1),
                f"Đã xử lý giọng đọc beat {beat_idx + 1}/{total_beats_count}...",
            )
    return results


def auto_resolve_mood_bgm(
    library_dir: Path,
    total_dur: float,
    music_mood: str,
    *,
    workspace_dir: Path | None = None,
) -> list[Path]:
    """Ưu tiên nhạc trong `library/music/` khớp `music_mood`; thiếu thì tự tải từ Freesound."""
    tracks = build_topic_bgm_playlist(library_dir, total_dur, topic=music_mood)
    if tracks:
        return tracks
    fkey = resolve_online_api_key("FREESOUND_API_KEY", workspace_dir)
    if not fkey:
        return []
    try:

        async def _fetch() -> list[Path]:
            hits = await search_freesound_audio(
                kind="music", mood=music_mood, api_key=fkey, page_size=5
            )
            if not hits:
                return []
            first = hits[0]
            res = await import_freesound_audio(
                item_id=str(first.get("id") or ""),
                title=str(first.get("title") or "Freesound BGM"),
                artist=str(first.get("artist") or "Freesound Creator"),
                download_url=str(first.get("download_url") or first.get("preview_url") or ""),
                kind="music",
                tags=list(dict.fromkeys([*(first.get("tags") or []), music_mood]))
                if music_mood
                else list(first.get("tags") or []),
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
    """Ghép giọng đọc + SFX (-16 LUFS) + BGM liên tục (-27 LUFS, duck 25/220ms) + -14 LUFS."""
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
        delay_part = f",adelay={delay_ms}|{delay_ms}" if delay_ms > 0 else ""
        filter_parts.append(
            f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            f"{delay_part}{lbl}"
        )
        voice_labels.append(lbl)
        sfx_path = resolve_sfx_file(beat.sfx_tag, library_dir, assets_dir)
        if sfx_path is not None:
            sfx_events.append((cur_t, sfx_path))
        cur_t += dur

    if len(voice_labels) == 1:
        filter_parts.append(
            f"{voice_labels[0]}apad=whole_dur={total_dur:.3f},atrim=0:{total_dur:.3f}[voice_bus]"
        )
    else:
        filter_parts.append(
            f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:duration=longest:"
            f"dropout_transition=0:normalize=0,"
            f"apad=whole_dur={total_dur:.3f},atrim=0:{total_dur:.3f}[voice_bus]"
        )

    next_idx = len(beat_wavs)
    sfx_labels: list[str] = []
    for s_i, (s_t, s_path) in enumerate(sfx_events[:40]):
        inputs.extend(["-i", str(s_path)])
        delay_ms = int(round(s_t * 1000))
        lbl = f"[sfx{s_i}]"
        delay_part = f",adelay={delay_ms}|{delay_ms}" if delay_ms > 0 else ""
        filter_parts.append(
            f"[{next_idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume=0.35{delay_part}{lbl}"
        )
        sfx_labels.append(lbl)
        next_idx += 1

    if sfx_labels:
        if len(sfx_labels) == 1:
            filter_parts.append(
                f"{sfx_labels[0]}loudnorm=I=-16:TP=-1.5:LRA=11[sfx_bus];"
                "[voice_bus][sfx_bus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[fg_bus]"
            )
        else:
            filter_parts.append(
                f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:duration=longest:"
                "dropout_transition=0:normalize=0,"
                "loudnorm=I=-16:TP=-1.5:LRA=11[sfx_bus];"
                "[voice_bus][sfx_bus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[fg_bus]"
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
            f"{bgm_lbl}aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"apad=whole_dur={total_dur:.3f},atrim=0:{total_dur:.3f},asetpts=PTS-STARTPTS,"
            f"loudnorm=I=-27:TP=-2.0:LRA=11,volume={bgm_volume:.2f}[bgm_low];"
            "[fg_bus]asplit=2[fg_sc][fg_mix];"
            "[bgm_low][fg_sc]sidechaincompress=threshold=0.02:ratio=6:attack=25:release=220[bgm_duck];"
            "[fg_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total_dur:.3f}[aout]"
        )
    else:
        filter_parts.append(f"[fg_bus]loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total_dur:.3f}[aout]")

    fc_text = ";\n".join(filter_parts) + "\n"
    script_path = out_wav.with_name(f"{out_wav.stem}_filtergraph.txt")
    _atomic_write_text(script_path, fc_text)

    from hbt.cinema.hardware import resolve_filter_complex_script_flag

    tmp_wav = out_wav.with_name(f"{out_wav.stem}.tmp.wav")
    script_flag = resolve_filter_complex_script_flag()
    cmd = [
        *FFMPEG_RESOURCE_CLAMP,
        *inputs,
        script_flag,
        str(script_path),
        "-map",
        "[aout]",
        "-t",
        f"{total_dur:.3f}",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        str(tmp_wav),
    ]
    try:
        run_ffmpeg(cmd)
        os.replace(tmp_wav, out_wav)
    finally:
        if tmp_wav.exists():
            tmp_wav.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
    return out_wav
