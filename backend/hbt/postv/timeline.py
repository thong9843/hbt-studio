"""Thuật toán Ngân sách thời gian (Time Budgeting) & Timeline Meme Cut-in độc lập cho PostV."""

from __future__ import annotations

import re
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.postv.models import PostvComment, PostvSegment

VIENEU_WORDS_PER_SEC = 3.2
SENTENCE_PAD_SEC = 0.4
MEME_CUTIN_MIN_SEC = 2.5
MEME_CUTIN_MAX_SEC = 3.5
DEFAULT_MEME_CUTIN_SEC = 3.0
MEME_TRAIL_SILENCE_SEC = 0.3
SENTENCE_SPLIT_RE = re.compile(r"[.!?\n…]+")


@dataclass(frozen=True)
class TimeBudgetSummary:
    t_post: float
    t_comments_replies: float
    t_memes: float
    total_seconds: float
    target_seconds: float


@dataclass(frozen=True)
class MemeCutinWindow:
    seg_index: int
    start: float
    duration: float
    end: float


def estimate_tts_seconds(text: str) -> float:
    """Ước tính thời lượng đọc VieNeu-TTS: ~3.2 từ/giây + 0.4s nghỉ đệm mỗi câu."""
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    if not clean:
        return 0.0
    words = len(clean.split(" "))
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(clean) if s.strip()]
    n_sentences = max(1, len(sentences))
    return round(words / VIENEU_WORDS_PER_SEC + n_sentences * SENTENCE_PAD_SEC, 2)


def clamp_meme_cutin_duration(raw_seconds: float | None) -> float:
    """Ép thời lượng mỗi cut-in meme về khung chuẩn 2.5s - 3.5s."""
    if raw_seconds is None or raw_seconds <= 0:
        return DEFAULT_MEME_CUTIN_SEC
    return round(min(MEME_CUTIN_MAX_SEC, max(MEME_CUTIN_MIN_SEC, float(raw_seconds))), 2)


def resolve_meme_cutin_duration(library_dir: Path | None, meme_id: str | None) -> float:
    """Đọc thời lượng cut-in meme từ `library/memes/index.json`, luôn kẹp trong [2.5, 3.5] giây."""
    if not meme_id:
        return 0.0
    if library_dir is not None:
        try:
            from hbt.chatting.stickers import get_meme_metadata
            from hbt.postv.memes import resolve_meme_file

            resolved = resolve_meme_file(library_dir, meme_id)
            lookup_key = resolved.name if resolved is not None else meme_id
            meta = get_meme_metadata(library_dir, lookup_key)
            return clamp_meme_cutin_duration(float(meta.get("duration", DEFAULT_MEME_CUTIN_SEC)))
        except Exception:
            pass
    return DEFAULT_MEME_CUTIN_SEC


def pad_voice_wav_for_memes(
    wav_in: Path,
    wav_out: Path,
    times: Sequence[tuple[float, float]],
    scene_of: Sequence[int],
    n_scenes: int,
    meme_durations: dict[int, float],
    min_trail_silence: float = MEME_TRAIL_SILENCE_SEC,
) -> tuple[Path, list[tuple[float, float]], bool]:
    """Chèn khoảng lặng PCM đúng chuẩn `Duration(Meme) + 0.3s` khi người dùng gắn meme thủ công
    sau bước sinh giọng mà file voice.wav chưa đủ chỗ trống giữa 2 đoạn."""
    if not meme_durations or n_scenes <= 1:
        return wav_in, list(times), False

    first_start = [0.0] * n_scenes
    last_end = [0.0] * n_scenes
    for si in range(n_scenes):
        idx = [i for i, s in enumerate(scene_of) if s == si]
        if idx:
            first_start[si], last_end[si] = times[idx[0]][0], times[idx[-1]][1]

    insert_after: list[tuple[int, float, float]] = []
    for k, m_dur in sorted(meme_durations.items()):
        if not 0 <= k < n_scenes - 1:
            continue
        cur_gap = max(0.0, first_start[k + 1] - last_end[k])
        needed = float(m_dur) + float(min_trail_silence)
        extra = needed - cur_gap
        if extra > 0.05:
            insert_after.append((k, last_end[k], extra))

    if not insert_after:
        return wav_in, list(times), False

    with wave.open(str(wav_in), "rb") as src:
        params = src.getparams()
        sr = src.getframerate()
        frame_width = src.getsampwidth() * src.getnchannels()
        pcm = src.readframes(src.getnframes())

    chunks: list[bytes] = []
    cursor_byte = 0
    for _k, cut_sec, extra_sec in insert_after:
        cut_frame = min(len(pcm) // frame_width, max(0, int(round(cut_sec * sr))))
        cut_byte = cut_frame * frame_width
        if cut_byte > cursor_byte:
            chunks.append(pcm[cursor_byte:cut_byte])
            cursor_byte = cut_byte
        pad_frames = max(1, int(round(extra_sec * sr)))
        chunks.append(b"\x00" * (pad_frames * frame_width))
    if cursor_byte < len(pcm):
        chunks.append(pcm[cursor_byte:])

    wav_out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_out), "wb") as dst:
        dst.setparams(params)
        dst.writeframes(b"".join(chunks))

    adjusted_times: list[tuple[float, float]] = []
    for i, (t0, t1) in enumerate(times):
        si = scene_of[i]
        shift = sum(extra for k, _cut, extra in insert_after if si > k)
        adjusted_times.append((round(t0 + shift, 4), round(t1 + shift, 4)))
    return wav_out, adjusted_times, True


def compute_time_budget(
    post_text: str,
    comments_and_replies: Sequence[PostvComment | str],
    meme_durations: Sequence[float] = (),
    target_seconds: float = 90.0,
) -> TimeBudgetSummary:
    """Target_Duration = T_post + Tổng(T_comments + T_replies) + Tổng(T_memes)."""
    t_post = estimate_tts_seconds(post_text)
    t_comm = sum(
        estimate_tts_seconds(c.text if isinstance(c, PostvComment) else str(c))
        for c in comments_and_replies
    )
    t_memes = sum(clamp_meme_cutin_duration(d) for d in meme_durations if d > 0)
    total = round(t_post + t_comm + t_memes, 2)
    return TimeBudgetSummary(
        t_post=round(t_post, 2),
        t_comments_replies=round(t_comm, 2),
        t_memes=round(t_memes, 2),
        total_seconds=total,
        target_seconds=float(target_seconds),
    )


def estimate_meme_pause_slots(
    segments: Sequence[PostvSegment],
    library_dir: Path | None,
    default_gap: float = 0.25,
) -> list[float]:
    """Trả về danh sách khoảng nghỉ (giây) ngay SAU từng đoạn trong `segments`.

    - Đoạn thường: nghỉ `default_gap` (0.25s).
    - Đoạn kích hoạt meme: Start_Time_Audio(sau) = End_Time(trước) + Duration(Meme) + 0.3s.
    """
    gaps: list[float] = []
    for seg in segments:
        if getattr(seg, "meme_id", None):
            m_dur = resolve_meme_cutin_duration(library_dir, seg.meme_id)
            gaps.append(round(m_dur + MEME_TRAIL_SILENCE_SEC, 3))
        else:
            gaps.append(default_gap)
    return gaps


def plan_meme_cutin_and_card_starts(
    segments: Sequence[PostvSegment],
    offsets: Sequence[float],
    first_start: Sequence[float],
    last_end: Sequence[float],
    base_starts: Sequence[float],
    meme_durations: dict[int, float],
    total: float,
) -> tuple[list[float], dict[int, MemeCutinWindow]]:
    """Điều phối mốc chuyển thẻ & cửa sổ Meme Cut-in Pause không đè lên TTS.

    Công thức bắt buộc:
    - Giây 0.00 luôn mở ngay Thẻ Bài Gốc (starts[0] == 0.0).
    - Meme chạy tại [last_end[k], last_end[k] + actual_dur] và TẮT HẲN ít nhất 0.3s trước
      khi câu bình luận tiếp theo cất tiếng (`next_voice - 0.3s`).
    - Thẻ kế tiếp (`starts[k + 1]`) chỉ chuyển sang sau khi meme đã tắt hẳn.
    """
    starts = list(base_starts)
    if starts:
        starts[0] = 0.0

    windows: dict[int, MemeCutinWindow] = {}
    for k, m_dur in meme_durations.items():
        if k >= len(segments) or k >= len(last_end):
            continue
        m_start = last_end[k]
        next_voice = first_start[k + 1] if k + 1 < len(first_start) else total
        # Chỉ phát tới tối đa next_voice - 0.3s để âm thanh gốc meme tắt hoàn toàn trước TTS sau
        max_avail = (
            max(0.0, next_voice - m_start - MEME_TRAIL_SILENCE_SEC)
            if k + 1 < len(first_start)
            else max(0.0, total - m_start)
        )
        if max_avail < 0.35:
            # Khoảng nghỉ quá ngắn (vd: file thu sẵn không chừa slot) → bỏ meme tránh đè tiếng
            continue
        actual_dur = min(m_dur, max_avail)
        m_end = m_start + actual_dur
        windows[k] = MemeCutinWindow(seg_index=k, start=m_start, duration=actual_dur, end=m_end)

        if k + 1 < len(starts):
            # Chuyển thẻ ngay giữa khoảng lặng 0.3s sau khi meme đã tắt hẳn hình & tiếng
            target_transition = min(next_voice - 0.04, m_end + 0.08)
            if target_transition > starts[k]:
                starts[k + 1] = max(starts[k + 1], target_transition)

    return starts, windows
