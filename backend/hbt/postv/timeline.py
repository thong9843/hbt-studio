"""Thuật toán Ngân sách thời gian (Time Budgeting) & Timeline Meme Cut-in độc lập cho PostV."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.postv.models import PostvComment, PostvSegment

VIENEU_WORDS_PER_SEC = 3.2
SENTENCE_PAD_SEC = 0.4
MEME_CUTIN_MIN_SEC = 2.5
MEME_CUTIN_MAX_SEC = 3.5
DEFAULT_MEME_CUTIN_SEC = 3.0
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

            meta = get_meme_metadata(library_dir, meme_id)
            return clamp_meme_cutin_duration(float(meta.get("duration", DEFAULT_MEME_CUTIN_SEC)))
        except Exception:
            pass
    return DEFAULT_MEME_CUTIN_SEC


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
    - Đoạn kích hoạt meme: dừng đọc TTS hoàn toàn trong `meme_dur + 0.35s` (trọn 2.5s-3.5s meme).
    """
    gaps: list[float] = []
    for seg in segments:
        if getattr(seg, "meme_id", None):
            m_dur = resolve_meme_cutin_duration(library_dir, seg.meme_id)
            gaps.append(round(m_dur + 0.35, 3))
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

    - Giây 0.00 luôn mở ngay Thẻ Bài Gốc (starts[0] == 0.0).
    - Khi đoạn `k` kích hoạt meme:
      + TTS ngừng ở `last_end[k]`.
      + Meme chạy độc lập tại `[last_end[k] + 0.12, m_end]` (2.5s–3.5s).
      + Chỉ sau khi meme kết thúc (`m_end`) thẻ tiếp theo (`starts[k + 1]`) mới cuộn tới.
    """
    starts = list(base_starts)
    if starts:
        starts[0] = 0.0

    windows: dict[int, MemeCutinWindow] = {}
    for k, m_dur in meme_durations.items():
        if k >= len(segments) or k >= len(last_end):
            continue
        m_start = last_end[k] + 0.12
        next_voice = first_start[k + 1] if k + 1 < len(first_start) else total
        # Đảm bảo không cắt lẹm vào giọng đọc đoạn kế tiếp nếu thiếu khoảng trống
        max_avail = (
            max(0.5, next_voice - m_start - 0.05)
            if k + 1 < len(first_start)
            else max(0.5, total - m_start)
        )
        actual_dur = min(m_dur, max_avail)
        m_end = m_start + actual_dur
        windows[k] = MemeCutinWindow(seg_index=k, start=m_start, duration=actual_dur, end=m_end)

        if k + 1 < len(starts):
            target_transition = min(next_voice - 0.04, m_end + 0.06)
            if target_transition > starts[k]:
                starts[k + 1] = max(starts[k + 1], target_transition)

    return starts, windows
