"""Âm thanh StickV: VieNeu-TTS có nhịp ngắt tự nhiên, Karaoke khóa tiếng nói & -14 LUFS."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from hbt.app_settings import resolve_online_api_key
from hbt.core.audio import build_topic_bgm_playlist
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.pipeline.render import whisper_alignment
from hbt.pipeline.text import parse_voice
from hbt.pipeline.whisper import WhisperConfig, WhisperFailed
from hbt.postv.voice import SynthItem, VoiceProvider
from hbt.shared.audio_utils import extract_wav_rms_frames, write_fallback_speech_wav_atomic
from hbt.shared.ffmpeg_utils import (
    FFMPEG_RESOURCE_CLAMP,
    build_acrossfade_filter_graph,
    measure_audio_duration,
    resolve_filter_complex_script_flag,
)
from hbt.shared.fs_utils import atomic_write_bytes as _atomic_write_bytes
from hbt.shared.fs_utils import atomic_write_text as _atomic_write_text
from hbt.shared.online_sources.freesound_audio import (
    import_freesound_audio,
    search_freesound_audio,
)
from hbt.shared.tts_client import DEFAULT_VIENEU_VOICE, resolve_voice_id
from hbt.stickv.models import StickvBeat

logger = logging.getLogger(__name__)

# Chuẩn nhịp thở & chống AAC priming nuốt chữ đầu video (GĐ9-v10)
MASTER_SAMPLE_RATE = 48000
KARAOKE_LEAD_OFFSET_S = -0.025
GLOBAL_LEAD_SILENCE_S = 0.18
LEAD_IN_SILENCE_S = 0.04
SENTENCE_GAP_S = 0.20
PAUSE_END_SENTENCE_S = 0.24
PAUSE_MID_CLAUSE_S = 0.20


@dataclass(frozen=True)
class BeatTimelineEntry:
    """Mốc thời gian tuyệt đối theo mẫu PCM của từng beat trên `stickv_voice_full.wav`."""

    beat_idx: int
    beat_start_s: float
    beat_end_s: float
    speech_start_s: float
    speech_end_s: float

    @property
    def duration_s(self) -> float:
        return max(0.0, self.beat_end_s - self.beat_start_s)


DEFAULT_PRE_ROLL_MS = 35
DEFAULT_POST_ROLL_MS = 75
DEFAULT_GHOST_MAX_MS = 140
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
    write_fallback_speech_wav_atomic(dest, text, sample_rate=24000, audible=False)


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
    return extract_wav_rms_frames(wav_path, fps, duration_sec, norm_mode="sample_p95")


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


def _active_speech_bounds(
    wav_path: Path,
    start_s: float,
    end_s: float,
    *,
    rms_thresh: float = 0.012,
) -> tuple[float, float]:
    """Thu hẹp `[start_s, end_s]` về đúng vùng có năng lượng giọng nói thật trong WAV."""
    lo = max(0.0, float(start_s))
    hi = max(lo, float(end_s))
    if hi - lo <= 0.12 or not wav_path.is_file():
        return lo, hi
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            n_total = wf.getnframes()
            if sw != 2 or sr <= 0 or n_total <= 0:
                return lo, hi
            s0 = min(n_total, max(0, int(round(lo * sr))))
            s1 = min(n_total, max(s0, int(round(hi * sr))))
            if s1 - s0 < int(sr * 0.05):
                return lo, hi
            wf.setpos(s0)
            raw = wf.readframes(s1 - s0)
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            pcm = pcm.reshape(-1, ch).mean(axis=1)
        win = max(1, int(round(sr * 0.01)))  # 10ms
        n_win = len(pcm) // win
        if n_win < 2:
            return lo, hi
        frames = pcm[: n_win * win].reshape(n_win, win)
        rms = np.sqrt(np.mean(frames * frames, axis=1))
        peak = float(np.max(rms)) if len(rms) else 0.0
        if peak < 1e-4:
            return lo, hi
        active_idx = np.flatnonzero(rms >= max(rms_thresh, peak * 0.08))
        if len(active_idx) == 0:
            return lo, hi
        act_lo = lo + (int(active_idx[0]) * win) / sr
        act_hi = lo + ((int(active_idx[-1]) + 1) * win) / sr
        if act_hi - act_lo < 0.12:
            return lo, hi
        return round(max(lo, act_lo), 4), round(min(hi, act_hi), 4)
    except Exception:
        return lo, hi


def align_beat_karaoke(
    narration: str,
    wav_path: Path,
    total_dur: float,
    *,
    lead_in_s: float = LEAD_IN_SILENCE_S,
    pause_after_s: float = PAUSE_END_SENTENCE_S,
    spoken_segments: list[tuple[float, float, str]] | None = None,
) -> list[tuple[str, float, float]]:
    """Khóa mốc Karaoke chặt vào tiếng nói thật trong `spoken_segments` (không lấn khoảng lặng)."""
    segs = spoken_segments if spoken_segments is not None else load_beat_spoken_segments(wav_path)
    if segs:
        timings: list[tuple[str, float, float]] = []
        for seg_start, seg_end, seg_text in segs:
            act_st, act_en = _active_speech_bounds(wav_path, float(seg_start), float(seg_end))
            seg_dur = max(0.15, act_en - act_st)
            timings.extend(compute_word_timings(seg_text, seg_dur, start_offset_s=act_st))
        if timings:
            return timings

    words = [w for w in (narration or "").split() if w]
    if not words:
        return []
    max_speech_end = max(lead_in_s + 0.3, float(total_dur) - max(0.0, pause_after_s))
    act_st, act_en = _active_speech_bounds(wav_path, lead_in_s, max_speech_end)
    speech_span = max(0.3, act_en - act_st)
    return compute_word_timings(narration, speech_span, start_offset_s=act_st)


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


def _vn_word_weight(word: str) -> float:
    """Trọng số phát âm âm tiết tiếng Việt (từ dài/số/ngắt câu chiếm thời lượng lâu hơn)."""
    clean = re.sub(r"[^\w\d]", "", (word or "").strip())
    if not clean:
        return 0.6
    if any(ch.isdigit() for ch in clean):
        return max(1.6, 0.7 * len(clean))
    base = 1.0 + 0.14 * max(0, len(clean) - 2)
    if (word or "").rstrip().endswith((".", "?", "!", "…")):
        base += 0.35
    elif (word or "").rstrip().endswith((",", ";", ":")):
        base += 0.18
    return base


def _resample_mono_pcm(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Chuyển tần số lấy mẫu PCM mono bằng nội suy tuyến tính chuẩn xác số mẫu."""
    if src_sr <= 0 or dst_sr <= 0 or len(samples) == 0 or src_sr == dst_sr:
        return samples.astype(np.float32, copy=False)
    n_out = max(1, int(round(len(samples) * (dst_sr / float(src_sr)))))
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False, dtype=np.float64)
    return np.interp(x_new, x_old, samples.astype(np.float32)).astype(np.float32)


def _read_wav_mono_float(wav_path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if sw != 2 or sr <= 0 or not raw:
        return 0, np.zeros(0, dtype=np.float32)
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        pcm = pcm.reshape(-1, ch).mean(axis=1)
    return sr, pcm


def build_master_voice_wav(
    beat_wavs: list[tuple[Path, float]],
    out_wav: Path,
    *,
    target_sr: int = MASTER_SAMPLE_RATE,
) -> tuple[Path, list[BeatTimelineEntry], float]:
    """Ghép chuẩn từng mẫu PCM (48kHz) thành `stickv_voice_full.wav` bất biến & bảng mốc beat."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sr = max(8000, int(target_sr))
    chunks: list[np.ndarray] = []
    timeline: list[BeatTimelineEntry] = []
    acc_samples = 0

    for idx, (wav_p, fallback_dur) in enumerate(beat_wavs):
        pcm = np.zeros(0, dtype=np.float32)
        src_sr = 0
        if wav_p.is_file() and wav_p.stat().st_size > 44:
            try:
                src_sr, pcm = _read_wav_mono_float(wav_p)
            except (wave.Error, EOFError, OSError):
                pcm = np.zeros(0, dtype=np.float32)

        if len(pcm) > 0 and src_sr > 0:
            beat_pcm = _resample_mono_pcm(pcm, src_sr, sr)
        else:
            n_fb = max(1, int(round(max(0.5, float(fallback_dur or 1.0)) * sr)))
            beat_pcm = np.zeros(n_fb, dtype=np.float32)

        beat_start_s = acc_samples / float(sr)
        n_beat = len(beat_pcm)
        beat_end_s = (acc_samples + n_beat) / float(sr)
        beat_dur = beat_end_s - beat_start_s

        spoken_segs = load_beat_spoken_segments(wav_p)
        if spoken_segs:
            sp_lo = max(0.0, min(beat_dur, float(spoken_segs[0][0])))
            sp_hi = max(sp_lo, min(beat_dur, float(spoken_segs[-1][1])))
        else:
            sp_lo, sp_hi = _active_speech_bounds(wav_p, 0.0, beat_dur)
            sp_lo = max(0.0, min(beat_dur, sp_lo))
            sp_hi = max(sp_lo, min(beat_dur, sp_hi))

        timeline.append(
            BeatTimelineEntry(
                beat_idx=idx,
                beat_start_s=round(beat_start_s, 6),
                beat_end_s=round(beat_end_s, 6),
                speech_start_s=round(beat_start_s + sp_lo, 6),
                speech_end_s=round(beat_start_s + sp_hi, 6),
            )
        )
        chunks.append(beat_pcm)
        acc_samples += n_beat

    if chunks:
        full_f = np.concatenate(chunks, axis=0)
    else:
        full_f = np.zeros(sr, dtype=np.float32)
        acc_samples = sr

    full_pcm = np.clip(np.round(full_f * 32767.0), -32768, 32767).astype(np.int16)
    _atomic_write_pcm_wav(out_wav, full_pcm, sr=sr, ch=1)
    total_dur = round(acc_samples / float(sr), 6)
    return out_wav, timeline, total_dur


def _clamp_monotonic_beat_timings(
    raw_items: list[tuple[str, float, float]],
    *,
    beat_start_s: float,
    beat_end_s: float,
    lead_offset_s: float = KARAOKE_LEAD_OFFSET_S,
) -> list[tuple[str, float, float]]:
    """Áp bù trễ `lead_offset_s`, quy về thời gian cục bộ `[0, beat_dur]` đơn điệu không chồng."""
    beat_dur = max(0.05, float(beat_end_s) - float(beat_start_s))
    out: list[tuple[str, float, float]] = []
    prev_end = 0.0
    for word, g_st, g_en in raw_items:
        loc_st = max(0.0, min(beat_dur - 0.01, (float(g_st) + lead_offset_s) - beat_start_s))
        if loc_st < prev_end:
            loc_st = min(beat_dur - 0.01, prev_end)
        loc_en = max(loc_st + 0.01, min(beat_dur, (float(g_en) + lead_offset_s) - beat_start_s))
        out.append((word, round(loc_st, 4), round(loc_en, 4)))
        prev_end = loc_en
    return out


def _rms_20ms_speech_bounds(
    wav_path: Path,
    start_s: float,
    end_s: float,
    *,
    rms_thresh: float = 0.012,
) -> tuple[float, float]:
    """Thu hẹp `[start_s, end_s]` trên file WAV tổng bằng cửa sổ năng lượng RMS 20ms."""
    lo = max(0.0, float(start_s))
    hi = max(lo, float(end_s))
    if hi - lo <= 0.12 or not wav_path.is_file():
        return lo, hi
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            n_total = wf.getnframes()
            if sw != 2 or sr <= 0 or n_total <= 0:
                return lo, hi
            s0 = min(n_total, max(0, int(round(lo * sr))))
            s1 = min(n_total, max(s0, int(round(hi * sr))))
            if s1 - s0 < int(sr * 0.04):
                return lo, hi
            wf.setpos(s0)
            raw = wf.readframes(s1 - s0)
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if ch > 1:
            pcm = pcm.reshape(-1, ch).mean(axis=1)
        win = max(1, int(round(sr * 0.02)))  # 20ms
        n_win = len(pcm) // win
        if n_win < 2:
            return lo, hi
        frames = pcm[: n_win * win].reshape(n_win, win)
        rms = np.sqrt(np.mean(frames * frames, axis=1))
        peak = float(np.max(rms)) if len(rms) else 0.0
        if peak < 1e-4:
            return lo, hi
        active_idx = np.flatnonzero(rms >= max(rms_thresh, peak * 0.08))
        if len(active_idx) == 0:
            return lo, hi
        act_lo = lo + (int(active_idx[0]) * win) / sr
        act_hi = lo + ((int(active_idx[-1]) + 1) * win) / sr
        if act_hi - act_lo < 0.10:
            return lo, hi
        return round(max(lo, act_lo), 4), round(min(hi, act_hi), 4)
    except Exception:
        return lo, hi


def _fallback_rms_beat_karaoke(
    beat: StickvBeat,
    entry: BeatTimelineEntry,
    voice_full_wav: Path,
    *,
    beat_wav_path: Path | None = None,
    lead_offset_s: float = KARAOKE_LEAD_OFFSET_S,
) -> list[tuple[str, float, float]]:
    """Fallback căn chữ RMS 20ms + trọng số âm tiết tiếng Việt trong vùng tiếng nói."""
    segs = load_beat_spoken_segments(beat_wav_path) if beat_wav_path is not None else []
    raw_global: list[tuple[str, float, float]] = []
    if segs:
        for seg_st, seg_en, seg_txt in segs:
            words = [w for w in seg_txt.split() if w]
            if not words:
                continue
            g_lo = entry.beat_start_s + float(seg_st)
            g_hi = min(entry.beat_end_s, entry.beat_start_s + float(seg_en))
            act_lo, act_hi = _rms_20ms_speech_bounds(voice_full_wav, g_lo, g_hi)
            span = max(0.12, act_hi - act_lo)
            weights = [_vn_word_weight(w) for w in words]
            total_w = sum(weights) or 1.0
            cur = act_lo
            for w, wt in zip(words, weights, strict=True):
                d = span * (wt / total_w)
                raw_global.append((w, cur, min(act_hi, cur + d)))
                cur += d
    if not raw_global:
        words = [w for w in (beat.narration or "").split() if w]
        if not words:
            return []
        act_lo, act_hi = _rms_20ms_speech_bounds(
            voice_full_wav, entry.speech_start_s, entry.speech_end_s
        )
        if act_hi - act_lo < 0.10:
            act_lo, act_hi = entry.beat_start_s, entry.beat_end_s
        span = max(0.12, act_hi - act_lo)
        weights = [_vn_word_weight(w) for w in words]
        total_w = sum(weights) or 1.0
        cur = act_lo
        for w, wt in zip(words, weights, strict=True):
            d = span * (wt / total_w)
            raw_global.append((w, cur, min(act_hi, cur + d)))
            cur += d

    return _clamp_monotonic_beat_timings(
        raw_global,
        beat_start_s=entry.beat_start_s,
        beat_end_s=entry.beat_end_s,
        lead_offset_s=lead_offset_s,
    )


def _extract_token_display(tok: Any) -> str:
    """Bóc đúng chuỗi hiển thị tiếng Việt (`disp`) từ token `parse_voice` (cấm in dict thô)."""
    if isinstance(tok, dict):
        raw = tok.get("disp") or tok.get("text") or tok.get("word") or ""
        return str(raw).strip()
    if hasattr(tok, "disp"):
        return str(tok.disp or "").strip()
    if hasattr(tok, "text"):
        return str(tok.text or "").strip()
    return str(tok or "").strip()


def _is_corrupted_karaoke_word(word: str) -> bool:
    w = str(word or "")
    return "{" in w or "}" in w or "'disp'" in w or '"disp"' in w or "'syl'" in w or len(w) > 30


def _compute_timing_cache_key(
    voice_full_wav: Path,
    beats: list[StickvBeat],
    whisper_cfg: WhisperConfig | None,
    lead_offset_s: float,
) -> str:
    h = hashlib.sha256()
    if voice_full_wav.is_file():
        with voice_full_wav.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    for b in beats:
        h.update(f"|{b.id}:{b.narration}".encode())
    cfg_sig = (
        f"whisper_v2:{whisper_cfg.model}:{whisper_cfg.device}:{whisper_cfg.timeout}"
        if whisper_cfg is not None
        else "rms20_vn_v2"
    )
    h.update(f"|{cfg_sig}|{lead_offset_s:.4f}".encode())
    return h.hexdigest()


def align_stickv_master_karaoke(
    beats: list[StickvBeat],
    beat_timeline: list[BeatTimelineEntry],
    voice_full_wav: Path,
    *,
    cache_file: Path | None = None,
    whisper_cfg: WhisperConfig | None = None,
    whisper_init_error: str = "",
    lead_offset_s: float = KARAOKE_LEAD_OFFSET_S,
    cancel: Any | None = None,
    beat_wavs: list[tuple[Path, float]] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[dict[int, list[tuple[str, float, float]]], dict[str, Any]]:
    """Căn mốc từng từ trên `stickv_voice_full.wav` (Whisper ưu tiên + cache + RMS 20ms)."""
    cache_key = _compute_timing_cache_key(voice_full_wav, beats, whisper_cfg, lead_offset_s)
    if cache_file is not None and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
                raw_beats = cached.get("beats") or {}
                loaded: dict[int, list[tuple[str, float, float]]] = {}
                corrupted = False
                for idx in range(len(beats)):
                    rows = raw_beats.get(str(idx), [])
                    parsed_rows = [(str(w), float(st), float(et)) for w, st, et in rows]
                    if any(_is_corrupted_karaoke_word(w) for w, _, _ in parsed_rows):
                        corrupted = True
                        break
                    loaded[idx] = parsed_rows
                if not corrupted:
                    meta = dict(cached.get("meta") or {})
                    meta["cache_hit"] = True
                    return loaded, meta
        except Exception:
            pass

    if cancel is not None and hasattr(cancel, "check"):
        cancel.check()

    method = "rms20_vn"
    info: dict[str, Any] = {}
    if whisper_init_error:
        info["whisper_fallback_reason"] = whisper_init_error
    timings_by_beat: dict[int, list[tuple[str, float, float]]] = {}

    # 1. Ưu tiên Whisper thật (tiến trình con hbt.pipeline.whisper_worker, KHÔNG initial_prompt)
    if whisper_cfg is not None and voice_full_wav.is_file():
        all_tokens: list[Any] = []
        all_beat_idxs: list[int] = []
        for idx, beat in enumerate(beats):
            toks = parse_voice(beat.narration or "")
            if not toks:
                continue
            all_tokens.extend(toks)
            all_beat_idxs.extend([idx] * len(toks))

        if all_tokens:
            try:
                aligned = whisper_alignment(
                    all_tokens,
                    all_beat_idxs,
                    voice_full_wav,
                    whisper_cfg,
                    log or (lambda _m: None),
                )
                if len(aligned.times) == len(all_tokens):
                    per_beat_raw: dict[int, list[tuple[str, float, float]]] = {
                        i: [] for i in range(len(beats))
                    }
                    for tok, b_idx, (t_st, t_en) in zip(
                        all_tokens, all_beat_idxs, aligned.times, strict=True
                    ):
                        w_txt = _extract_token_display(tok)
                        if w_txt:
                            per_beat_raw[b_idx].append((w_txt, float(t_st), float(t_en)))
                    for idx, entry in enumerate(beat_timeline):
                        timings_by_beat[idx] = _clamp_monotonic_beat_timings(
                            per_beat_raw.get(idx, []),
                            beat_start_s=entry.beat_start_s,
                            beat_end_s=entry.beat_end_s,
                            lead_offset_s=lead_offset_s,
                        )
                    method = "whisper"
                    info = dict(aligned.info or {})
            except (WhisperFailed, RuntimeError, ImportError, OSError) as exc:
                logger.warning("Whisper StickV fallback sang RMS 20ms + âm tiết: %s", exc)
                info["whisper_fallback_reason"] = str(exc)

    # 2. Fallback an toàn: năng lượng RMS khung 20ms + trọng số âm tiết tiếng Việt
    if method != "whisper":
        for idx, (beat, entry) in enumerate(zip(beats, beat_timeline, strict=True)):
            bw_path = beat_wavs[idx][0] if (beat_wavs and idx < len(beat_wavs)) else None
            timings_by_beat[idx] = _fallback_rms_beat_karaoke(
                beat,
                entry,
                voice_full_wav,
                beat_wav_path=bw_path,
                lead_offset_s=lead_offset_s,
            )

    meta = {"method": method, "lead_offset_s": lead_offset_s, "cache_hit": False, **info}
    if cache_file is not None:
        payload = {
            "cache_key": cache_key,
            "meta": meta,
            "beats": {
                str(idx): [[w, st, et] for w, st, et in rows]
                for idx, rows in timings_by_beat.items()
            },
        }
        _atomic_write_text(cache_file, json.dumps(payload, ensure_ascii=False, indent=2))
    return timings_by_beat, meta


def verify_zero_drift_timeline(
    beat_timeline: list[BeatTimelineEntry],
    total_video_duration_s: float,
    voice_full_duration_s: float,
    word_timings_by_beat: dict[int, list[tuple[str, float, float]]],
    *,
    max_drift_s: float = 0.03,
) -> float:
    """Kiểm toán Zero-Drift: sai lệch hình-tiếng <= 0.03s & mốc từ đơn điệu, kẹp chặt trong beat."""
    drift = abs(float(total_video_duration_s) - float(voice_full_duration_s))
    if drift > max_drift_s:
        raise ValueError(
            f"Zero-Drift check thất bại: lệch {drift:.4f}s > {max_drift_s:.3f}s "
            f"(video={total_video_duration_s:.3f}s, voice={voice_full_duration_s:.3f}s)"
        )
    for entry in beat_timeline:
        rows = word_timings_by_beat.get(entry.beat_idx, [])
        beat_dur = entry.duration_s
        prev_st = -1e-6
        prev_en = 0.0
        for _w, st, et in rows:
            if st < -1e-4 or et > beat_dur + 0.005:
                raise ValueError(
                    f"Từ Karaoke beat {entry.beat_idx} vượt biên [0, {beat_dur:.3f}]: ({st}, {et})"
                )
            if st < prev_st - 1e-4 or st < prev_en - 1e-4 or et < st - 1e-4:
                raise ValueError(
                    f"Từ Karaoke beat {entry.beat_idx} không đơn điệu/chồng lấn: ({st}, {et})"
                )
            prev_st = st
            prev_en = et
    return round(drift, 5)


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
    voice_full_wav: Path | None = None,
    beat_timeline: list[BeatTimelineEntry] | None = None,
) -> Path:
    """Trộn song song `stickv_voice_full.wav` bất biến + SFX (-16 LUFS) + BGM (-27 LUFS)."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    own_master_wav: Path | None = None
    master_wav = voice_full_wav
    timeline = beat_timeline

    if master_wav is None or not master_wav.is_file() or timeline is None:
        own_master_wav = out_wav.with_name(f"{out_wav.stem}_master_voice.tmp.wav")
        master_wav, timeline, total_dur = build_master_voice_wav(beat_wavs, own_master_wav)
    else:
        total_dur = (
            round(timeline[-1].beat_end_s, 4)
            if timeline
            else round(sum(d for _, d in beat_wavs), 4)
        )

    if total_dur <= 0:
        if own_master_wav is not None:
            own_master_wav.unlink(missing_ok=True)
        _write_fallback_wav(out_wav, "empty")
        return out_wav

    inputs: list[str] = ["-i", str(master_wav)]
    filter_parts: list[str] = [
        f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
        f"apad=whole_dur={total_dur:.4f},atrim=0:{total_dur:.4f},asetpts=PTS-STARTPTS[voice_bus]"
    ]

    sfx_events: list[tuple[float, Path]] = []
    for i, beat in enumerate(beats):
        sfx_path = resolve_sfx_file(beat.sfx_tag, library_dir, assets_dir)
        if sfx_path is not None and i < len(timeline):
            sfx_events.append((timeline[i].beat_start_s, sfx_path))

    next_idx = 1
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
            f"apad=whole_dur={total_dur:.4f},atrim=0:{total_dur:.4f},asetpts=PTS-STARTPTS,"
            f"loudnorm=I=-27:TP=-2.0:LRA=11,volume={bgm_volume:.2f}[bgm_low];"
            "[fg_bus]asplit=2[fg_sc][fg_mix];"
            "[bgm_low][fg_sc]sidechaincompress=threshold=0.02:ratio=6:attack=25:release=220[bgm_duck];"
            "[fg_mix][bgm_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={total_dur:.4f},atrim=0:{total_dur:.4f}[aout]"
        )
    else:
        filter_parts.append(
            "[fg_bus]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={total_dur:.4f},atrim=0:{total_dur:.4f}[aout]"
        )

    fc_text = ";\n".join(filter_parts) + "\n"
    script_path = out_wav.with_name(f"{out_wav.stem}_filtergraph.txt")
    _atomic_write_text(script_path, fc_text)

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
        f"{total_dur:.4f}",
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
        # Khoá cứng độ dài mẫu PCM 48kHz khớp tuyệt đối `total_dur` (bù 40ms lookahead của loudnorm)
        target_pcm_frames = max(1, int(round(total_dur * 48000)))
        pad_wav: Path | None = None
        try:
            with wave.open(str(tmp_wav), "rb") as rf:
                ch = rf.getnchannels()
                sw = rf.getsampwidth()
                sr = rf.getframerate()
                cur_frames = rf.getnframes()
                if sr == 48000 and ch > 0 and sw > 0 and abs(cur_frames - target_pcm_frames) > 0:
                    pcm_raw = rf.readframes(min(cur_frames, target_pcm_frames))
                    pad_wav = tmp_wav.with_name(f"{tmp_wav.stem}.pad.wav")
                    with wave.open(str(pad_wav), "wb") as wf:
                        wf.setnchannels(ch)
                        wf.setsampwidth(sw)
                        wf.setframerate(sr)
                        wf.writeframes(pcm_raw)
                        if cur_frames < target_pcm_frames:
                            wf.writeframes(b"\x00" * ((target_pcm_frames - cur_frames) * ch * sw))
            if pad_wav is not None and pad_wav.is_file():
                os.replace(pad_wav, out_wav)
                return out_wav
        except (wave.Error, EOFError):
            pass
        finally:
            if pad_wav is not None and pad_wav.exists():
                pad_wav.unlink(missing_ok=True)
        os.replace(tmp_wav, out_wav)
    finally:
        if tmp_wav.exists():
            tmp_wav.unlink(missing_ok=True)
        if own_master_wav is not None and own_master_wav.exists():
            own_master_wav.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
    return out_wav
