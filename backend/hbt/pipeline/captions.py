"""Phụ đề karaoke (IMPLEMENT.md mục 5.3): chia cụm, tính thời điểm, vẽ trạng thái, ffconcat, SRT.

Vẽ từng trạng thái bằng `visual.render_caption` (Pillow, font Be Vietnam Pro): mỗi trạng thái là
một PNG 1080×1920 trong suốt; FFmpeg phủ chúng lên video bằng `overlay` qua file concat.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .visual import H, W, render_caption

MAX_TOKENS = 7  # cụm dài hơn thì tự tách đôi
LEAD = 0.05  # hiện cụm sớm hơn chữ đầu
JOIN_GAP = 0.6  # khoảng cách tới cụm sau nhỏ hơn mức này thì giữ cụm đến lúc cụm sau xuất hiện
HOLD = 0.25  # giữ cụm sau chữ cuối nếu cụm sau còn xa
DEFAULT_Y = 1420
HIGH_CARD_Y = 230
HIGH_CARD_BOTTOM = 1100
MIN_STATE = 0.001


@dataclass
class Phrase:
    scene: int
    token_ids: list[int]
    words: list[str]  # chữ hiển thị (disp) từng token
    word_starts: list[float]
    first_start: float  # đầu chữ đầu
    last_end: float  # cuối chữ cuối
    start: float = 0.0  # lúc cụm hiện
    end: float = 0.0  # lúc cụm biến mất
    states: list[tuple[float, float, int]] = field(default_factory=list)  # (từ, đến, chữ sáng)


def caption_y_for(caption_y: int | None, card_bottom: int | None) -> int:
    """null → 1420; nếu đáy thẻ chữ > 1100 thì 230; số cụ thể thì giữ nguyên."""
    if caption_y is not None:
        return caption_y
    if card_bottom is not None and card_bottom > HIGH_CARD_BOTTOM:
        return HIGH_CARD_Y
    return DEFAULT_Y


def split_phrases(tokens: Sequence[dict], scene_of: Sequence[int]) -> list[list[int]]:
    """Gom token thành cụm: theo `|` và dấu câu (`chunk_start`), không vượt ranh giới cảnh;
    cụm hơn MAX_TOKENS token thì tách đôi (lặp lại cho đến khi đủ ngắn)."""
    groups: list[list[int]] = []
    for i, tok in enumerate(tokens):
        if not groups or tok["chunk_start"] or scene_of[i] != scene_of[groups[-1][0]]:
            groups.append([])
        groups[-1].append(i)

    def halve(ids: list[int]) -> list[list[int]]:
        if len(ids) <= MAX_TOKENS:
            return [ids]
        mid = (len(ids) + 1) // 2
        return halve(ids[:mid]) + halve(ids[mid:])

    return [part for g in groups for part in halve(g)]


def build_phrases(
    tokens: Sequence[dict],
    times: Sequence[tuple[float, float]],
    scene_of: Sequence[int],
) -> list[Phrase]:
    """Tính thời điểm hiện/biến mất của cụm và khoảng sáng của từng chữ."""
    phrases = []
    for ids in split_phrases(tokens, scene_of):
        starts, prev = [], 0.0
        for i in ids:  # đảm bảo mốc không lùi
            prev = max(prev, times[i][0])
            starts.append(prev)
        phrases.append(
            Phrase(
                scene=scene_of[ids[0]],
                token_ids=ids,
                words=[tokens[i]["disp"] for i in ids],
                word_starts=starts,
                first_start=starts[0],
                last_end=max(times[ids[-1]][1], starts[-1]),
            )
        )
    for k, p in enumerate(phrases):
        p.start = max(p.first_start - LEAD, 0.0)
        nxt = phrases[k + 1] if k + 1 < len(phrases) else None
        if nxt is not None and nxt.first_start - p.last_end < JOIN_GAP:
            # nối sang cụm sau nhưng không chồng lúc cụm sau hiện (tránh hai cụm cùng lúc)
            p.end = max(nxt.first_start - LEAD, p.last_end)
        else:
            p.end = p.last_end + HOLD
        bounds = [p.start, *p.word_starts, p.end]
        bounds = [max(bounds[0], 0.0)] + [max(b, bounds[0]) for b in bounds[1:]]
        for j in range(len(bounds) - 1):
            lo, hi = bounds[j], bounds[j + 1]
            if hi - lo >= MIN_STATE:
                p.states.append((lo, hi, j - 1))  # j=0: chưa chữ nào sáng (act = -1)
    return phrases


def _state_path(out_dir: Path, words: Sequence[str], act: int, yc: int) -> Path:
    key = hashlib.sha1(f"{list(words)}|{act}|{yc}".encode()).hexdigest()[:16]
    return out_dir / f"cap_{key}.png"


def render_states(
    phrases: Sequence[Phrase],
    caption_ys: Sequence[int],
    out_dir: Path,
    total: float,
) -> list[tuple[Path, float]]:
    """Vẽ PNG từng trạng thái (bỏ qua file đã có) và trả về dòng thời gian [(png, giây)] phủ kín
    từ 0 đến `total`; chỗ không có phụ đề dùng PNG trong suốt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    blank = out_dir / "blank.png"
    if not blank.exists():
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)

    spans: list[tuple[float, float, Path]] = []
    for p in phrases:
        yc = caption_ys[p.scene]
        for lo, hi, act in p.states:
            path = _state_path(out_dir, p.words, act, yc)
            if not path.exists():
                render_caption(p.words, act, str(path), yc)
            spans.append((lo, hi, path))
    spans.sort(key=lambda s: s[0])

    timeline: list[tuple[Path, float]] = []
    cursor = 0.0
    for lo, hi, path in spans:
        lo = max(lo, cursor)  # không chồng
        if hi <= lo:
            continue
        if lo > cursor:
            timeline.append((blank, lo - cursor))
        timeline.append((path, hi - lo))
        cursor = hi
    if total > cursor:
        timeline.append((blank, total - cursor))
    return timeline


def write_ffconcat(timeline: Sequence[tuple[Path, float]], path: Path) -> None:
    """File ffconcat (đường dẫn tuyệt đối, dấu `/`). File cuối được lặp lại vì demuxer bỏ qua
    `duration` của mục cuối."""

    def q(p: Path) -> str:
        return "file '" + p.resolve().as_posix().replace("'", "'\\''") + "'"

    lines = ["ffconcat version 1.0"]
    for png, dur in timeline:
        lines += [q(png), f"duration {dur:.6f}"]
    if timeline:
        lines.append(q(timeline[-1][0]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _srt_time(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(phrases: Sequence[Phrase], path: Path) -> None:
    """captions.srt theo cụm (để tải lên YouTube nếu muốn)."""
    blocks = []
    for n, p in enumerate(phrases, 1):
        blocks.append(f"{n}\n{_srt_time(p.start)} --> {_srt_time(p.end)}\n{' '.join(p.words)}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
