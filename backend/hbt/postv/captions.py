"""Phụ đề PostV kiểu Hooked: 1–3 từ mỗi lần, từ đang đọc đổi màu (IMPLEMENT-POSTV.md mục 6, 6b).

Tách cụm và vẽ trạng thái là mã riêng của PostV (B5); chỉ dùng lại `Phrase`, các hằng thời gian và
`write_ffconcat` của HBT. Mỗi trạng thái là một PNG **dải** 1080×BAND (không phải cả khung) nên
vẽ và giải mã nhanh; ffmpeg đặt dải ở `band_y`. Từ bị che (mức chặn) vẽ rồi làm mờ, hoặc thay `***`.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from hbt.pipeline.cache import code_digest
from hbt.pipeline.captions import HOLD, JOIN_GAP, LEAD, MIN_STATE, Phrase, _srt_time
from hbt.pipeline.text import display
from hbt.pipeline.visual import W, font

MAX_WORDS = 3  # tối đa số từ hiện cùng lúc
BAND = 360  # chiều cao dải PNG (đủ 2 dòng cỡ 72)
MAX_TEXT_WIDTH = 940
STARS = "***"
BLUR_PER_SIZE = 12 / 70  # bán kính làm mờ theo cỡ chữ (mục 6b: ~12 px ở cỡ 70)
HOOKED_GREEN = "#38E178"
HBT_YELLOW = "#FFD43B"


@dataclass(frozen=True)
class Style:
    weight: str = "ExtraBold"
    size: int = 72
    color: tuple[int, int, int] = (255, 255, 255)
    active: tuple[int, int, int] = (255, 212, 59)
    stroke: int = 7
    stroke_color: tuple[int, int, int] = (15, 15, 25)
    upper: bool = False
    y: int = 1400  # tâm khối chữ trong khung 1080×1920 (vùng an toàn TikTok: đáy ≤ 1500)
    line_height: int = 100
    gap: int = 24


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def style_for(preset: str = "hbt", highlight: str | None = None) -> Style:
    """Kiểu phụ đề theo preset; `highlight` (hex) ghi đè màu từ đang đọc."""
    if preset == "sample":  # "Mẫu postv-thu-01": CHỮ HOA, trắng viền đen, từ đang đọc xanh lá
        base = Style(
            active=_rgb(HOOKED_GREEN), stroke=8, stroke_color=(0, 0, 0), upper=True, y=1459
        )
    else:
        base = Style(active=_rgb(HBT_YELLOW))
    if highlight:
        base = replace(base, active=_rgb(highlight))
    return base


@dataclass
class CapPhrase(Phrase):
    masked: list[bool] = field(default_factory=list)  # từ nào bị che (cùng thứ tự `words`)


def split_short(tokens: Sequence[dict], scene_of: Sequence[int]) -> list[list[int]]:
    """Gom token thành cụm ≤ MAX_WORDS từ: theo dấu câu (`chunk_start`), không vượt ranh giới
    đoạn; cụm dài thì chia đều (4 → 2+2, 5 → 3+2, 7 → 3+2+2)."""
    groups: list[list[int]] = []
    for i, tok in enumerate(tokens):
        if not groups or tok["chunk_start"] or scene_of[i] != scene_of[groups[-1][0]]:
            groups.append([])
        groups[-1].append(i)
    out: list[list[int]] = []
    for g in groups:
        parts = -(-len(g) // MAX_WORDS)
        base, extra = divmod(len(g), parts)
        at = 0
        for k in range(parts):
            size = base + (1 if k < extra else 0)
            out.append(g[at : at + size])
            at += size
    return out


def build_phrases(
    tokens: Sequence[dict],
    times: Sequence[tuple[float, float]],
    scene_of: Sequence[int],
    masked_tokens: Collection[int] = (),
) -> list[CapPhrase]:
    """Thời điểm hiện/biến mất của cụm và khoảng sáng từng từ (cùng cách tính với HBT)."""
    phrases: list[CapPhrase] = []
    for ids in split_short(tokens, scene_of):
        starts, prev = [], 0.0
        for i in ids:  # mốc không lùi
            prev = max(prev, times[i][0])
            starts.append(prev)
        phrases.append(
            CapPhrase(
                scene=scene_of[ids[0]],
                token_ids=ids,
                words=[tokens[i]["disp"] for i in ids],
                word_starts=starts,
                first_start=starts[0],
                last_end=max(times[ids[-1]][1], starts[-1]),
                masked=[i in masked_tokens for i in ids],
            )
        )
    for k, p in enumerate(phrases):
        p.start = max(p.first_start - LEAD, 0.0)
        nxt = phrases[k + 1] if k + 1 < len(phrases) else None
        if nxt is not None and nxt.first_start - p.last_end < JOIN_GAP:
            p.end = max(nxt.first_start - LEAD, p.last_end)
        else:
            p.end = p.last_end + HOLD
        bounds = [p.start, *p.word_starts, p.end]
        bounds = [max(bounds[0], 0.0)] + [max(b, bounds[0]) for b in bounds[1:]]
        for j in range(len(bounds) - 1):
            lo, hi = bounds[j], bounds[j + 1]
            if hi - lo >= MIN_STATE:
                p.states.append((lo, hi, j - 1))  # j = 0: chưa từ nào sáng (act = -1)
    return phrases


def _layout(words: Sequence[str], f, gap: int) -> list[list[int]]:
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines: list[list[int]] = [[]]
    used = 0.0
    for k, w in enumerate(words):
        wd = probe.textlength(w, font=f)
        extra = (gap if lines[-1] else 0) + wd
        if lines[-1] and used + extra > MAX_TEXT_WIDTH:
            lines.append([])
            used, extra = 0.0, wd
        lines[-1].append(k)
        used += extra
    return lines


def render_state(
    words: Sequence[str],
    act: int,
    masked: Sequence[bool],
    style: Style,
    mode: str,
    path: Path,
) -> None:
    """Một trạng thái: dải RGBA 1080×BAND, `act` là từ đang đọc (-1 = chưa từ nào)."""
    f = font(style.weight, style.size)
    texts = []
    for w, m in zip(words, masked, strict=True):
        t = display(w)
        t = t.upper() if style.upper else t
        texts.append(STARS if m and mode == "stars" else t)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [probe.textlength(t, font=f) for t in texts]
    lines = _layout(texts, f, style.gap)
    im = Image.new("RGBA", (W, BAND), (0, 0, 0, 0))
    top = BAND / 2 - style.line_height * len(lines) / 2
    blur = style.size * BLUR_PER_SIZE
    for li, ln in enumerate(lines):
        tw = sum(widths[k] for k in ln) + style.gap * (len(ln) - 1)
        x, y = (W - tw) / 2, top + li * style.line_height
        for k in ln:
            fill = style.active if k == act else style.color
            hidden = masked[k] and mode != "stars"
            target = Image.new("RGBA", (W, BAND), (0, 0, 0, 0)) if hidden else im
            d = ImageDraw.Draw(target)
            d.text((x + 3, y + 8), texts[k], font=f, fill=(0, 0, 0, 120))
            d.text(
                (x, y + 4), texts[k], font=f, fill=fill,
                stroke_width=style.stroke, stroke_fill=style.stroke_color,
            )  # fmt: skip
            if hidden:  # làm mờ đúng vùng chữ của từ đó
                im.alpha_composite(target.filter(ImageFilter.GaussianBlur(blur)))
            x += widths[k] + style.gap
    im.save(path)


_CODE = code_digest(sys.modules[__name__])  # đổi kiểu vẽ thì vẽ lại PNG


def _state_path(out_dir: Path, words, act: int, masked, style: Style, mode: str) -> Path:
    raw = f"{_CODE}|{list(words)}|{act}|{list(masked)}|{style}|{mode}"
    return out_dir / f"cap_{hashlib.sha1(raw.encode()).hexdigest()[:16]}.png"


def render_states(
    phrases: Sequence[CapPhrase],
    style: Style,
    mode: str,
    out_dir: Path,
    total: float,
) -> list[tuple[Path, float]]:
    """Vẽ PNG từng trạng thái (bỏ qua file đã có) và trả dòng thời gian [(png, giây)] phủ kín từ
    0 đến `total`; chỗ không có phụ đề dùng dải trong suốt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    blank = out_dir / "blank.png"
    if not blank.exists():
        Image.new("RGBA", (W, BAND), (0, 0, 0, 0)).save(blank)
    spans: list[tuple[float, float, Path]] = []
    for p in phrases:
        for lo, hi, act in p.states:
            path = _state_path(out_dir, p.words, act, p.masked, style, mode)
            if not path.exists():
                render_state(p.words, act, p.masked, style, mode, path)
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


def band_y(style: Style) -> int:
    """Toạ độ y của dải trong khung 1080×1920 (tâm khối chữ ở giữa dải)."""
    return int(style.y - BAND / 2)


def write_srt(phrases: Sequence[CapPhrase], path: Path) -> None:
    """captions.srt theo cụm; từ bị che luôn ghi `***` (mục 6b)."""
    blocks = []
    for n, p in enumerate(phrases, 1):
        words = [STARS if m else w for w, m in zip(p.words, p.masked, strict=True)]
        blocks.append(f"{n}\n{_srt_time(p.start)} --> {_srt_time(p.end)}\n{' '.join(words)}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
