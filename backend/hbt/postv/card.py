"""Vẽ thẻ bài của PostV bằng Pillow (IMPLEMENT-POSTV.md mục 6).

Chữ trên video luôn vẽ bằng Pillow với font trong `backend/hbt/fonts/` để đúng dấu tiếng Việt
(CLAUDE.md). Thẻ là tấm trắng bo góc kiểu mạng xã hội chung chung: avatar hình người xám trơn,
không logo hay giao diện của nền tảng nào. Mọi số đo nằm ở `templates/story_cards.json`.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from hbt.postv.censor import CensorMatcher, find_censor_hits
from hbt.postv.counts import format_count

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
CardKind = Literal["hook", "post", "comment"]
CensorMode = Literal["blur", "stars"]
VIEWS_LABEL = "lượt xem"


def load_template(name: str = "story_cards") -> dict:
    return json.loads((TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


@dataclass
class Word:
    text: str
    start: int  # vị trí trong chữ gốc (đã chuẩn hoá NFC)
    end: int
    width: float = 0.0
    censored: bool = False
    accent: bool = False


def _words(text: str) -> list[Word]:
    return [Word(m.group(), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _mark(words: list[Word], spans: list[tuple[int, int]], attr: str) -> None:
    for w in words:
        if any(w.start < e and s < w.end for s, e in spans):
            setattr(w, attr, True)


def _wrap(words: list[Word], font: ImageFont.FreeTypeFont, max_width: float) -> list[list[Word]]:
    space = font.getlength(" ")
    lines: list[list[Word]] = [[]]
    used = 0.0
    for w in words:
        w.width = font.getlength(w.text)
        extra = (space if lines[-1] else 0) + w.width
        if lines[-1] and used + extra > max_width:
            lines.append([])
            used, extra = 0.0, w.width
        lines[-1].append(w)
        used += extra
    return [ln for ln in lines if ln]


def _ellipsize(
    lines: list[list[Word]], max_lines: int, font: ImageFont.FreeTypeFont, max_width: float
) -> list[list[Word]]:
    """Quá `max_lines` thì cắt và thêm `…` vào cuối dòng cuối (vừa khít chiều rộng)."""
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    space = font.getlength(" ")
    dots = Word("…", -1, -1, width=font.getlength("…"))
    while last and sum(w.width for w in last) + space * len(last) + dots.width > max_width:
        last.pop()
    last.append(dots)
    return kept


def _normalise(text: str) -> str:
    return re.sub(r"[ \t]+", " ", unicodedata.normalize("NFC", text or "")).strip()


def _censor_spans(text: str, censor: list[CensorMatcher] | None) -> list[tuple[int, int]]:
    # vị trí chỉ dùng được khi chữ thường hoá giữ nguyên độ dài (đúng với tiếng Việt)
    if not censor or len(text.casefold()) != len(text):
        return []
    return [(h.start, h.end) for h in find_censor_hits(text, censor)]


def _draw_word(
    img: Image.Image, xy: tuple[float, float], word: Word, font, fill, mode: CensorMode, tpl: dict
) -> None:
    if not word.censored:
        ImageDraw.Draw(img).text(xy, word.text, font=font, fill=fill)
        return
    cfg = tpl["censor"]
    if mode == "stars":
        ImageDraw.Draw(img).text(xy, cfg["stars"], font=font, fill=fill)
        return
    pad = int(cfg["blur_radius"] * 3)
    box = (
        int(xy[0]) - pad,
        int(xy[1]) - pad,
        int(xy[0] + word.width) + pad,
        int(xy[1] + font.size * 1.5) + pad,
    )
    patch = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0))
    ImageDraw.Draw(patch).text((xy[0] - box[0], xy[1] - box[1]), word.text, font=font, fill=fill)
    patch = patch.filter(ImageFilter.GaussianBlur(cfg["blur_radius"]))
    img.alpha_composite(patch, (max(box[0], 0), max(box[1], 0)))


def _avatar(size: int, bg: str, fg: str) -> Image.Image:
    """Hình người xám trơn trong vòng tròn (không ảnh đại diện thật, không biểu tượng nền tảng)."""
    s = size * 4  # vẽ lớn rồi thu nhỏ cho mịn
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, s - 1, s - 1), fill=_rgb(bg))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, s - 1, s - 1), fill=255)
    person = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    p = ImageDraw.Draw(person)
    p.ellipse((s * 0.34, s * 0.2, s * 0.66, s * 0.52), fill=_rgb(fg))
    p.ellipse((s * 0.16, s * 0.6, s * 0.84, s * 1.25), fill=_rgb(fg))
    im.paste(
        person, (0, 0), Image.composite(person.getchannel("A"), Image.new("L", (s, s), 0), mask)
    )
    return im.resize((size, size), Image.LANCZOS)


def _icon(kind: str, size: int, color: tuple[int, int, int]) -> Image.Image:
    s = size * 4
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(int(s * 0.09), 2)
    if kind == "like":  # trái tim
        heart = [(0.5, 0.88), (0.1, 0.46), (0.1, 0.3), (0.5, 0.55), (0.9, 0.3), (0.9, 0.46)]
        d.polygon([(s * x, s * y) for x, y in heart], outline=color, width=w)
        d.arc((s * 0.1, s * 0.12, s * 0.5, s * 0.52), 180, 360, fill=color, width=w)
        d.arc((s * 0.5, s * 0.12, s * 0.9, s * 0.52), 180, 360, fill=color, width=w)
    elif kind == "reply":  # khung chat
        d.rounded_rectangle(
            (s * 0.1, s * 0.12, s * 0.9, s * 0.7), radius=int(s * 0.18), outline=color, width=w
        )
        d.polygon(
            [(s * 0.3, s * 0.68), (s * 0.3, s * 0.9), (s * 0.5, s * 0.7)], outline=color, width=w
        )
    elif kind == "repost":  # hai mũi tên vòng
        d.line([(s * 0.2, s * 0.4), (s * 0.2, s * 0.3), (s * 0.8, s * 0.3)], fill=color, width=w)
        d.line(
            [(s * 0.65, s * 0.15), (s * 0.82, s * 0.3), (s * 0.65, s * 0.45)], fill=color, width=w
        )
        d.line([(s * 0.8, s * 0.6), (s * 0.8, s * 0.7), (s * 0.2, s * 0.7)], fill=color, width=w)
        d.line(
            [(s * 0.35, s * 0.55), (s * 0.18, s * 0.7), (s * 0.35, s * 0.85)], fill=color, width=w
        )
    else:  # chia sẻ: máy bay giấy
        plane = [(0.1, 0.5), (0.9, 0.12), (0.62, 0.88), (0.48, 0.58)]
        d.polygon([(s * x, s * y) for x, y in plane], outline=color, width=w)
        d.line([(s * 0.48, s * 0.58), (s * 0.9, s * 0.12)], fill=color, width=w)
    return im.resize((size, size), Image.LANCZOS)


def _round_rect(size: tuple[int, int], radius: int, fill: tuple[int, int, int]) -> Image.Image:
    s = 4
    big = Image.new("RGBA", (size[0] * s, size[1] * s), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, size[0] * s - 1, size[1] * s - 1), radius=radius * s, fill=fill
    )
    return big.resize(size, Image.LANCZOS)


def _canvas(tpl: dict) -> Image.Image:
    return Image.new("RGBA", (tpl["canvas"]["w"], tpl["canvas"]["h"]), (0, 0, 0, 0))


def render_hook(
    text: str,
    accent: str = "",
    tpl: dict | None = None,
    censor: list[CensorMatcher] | None = None,
    censor_mode: CensorMode = "blur",
) -> tuple[Image.Image, int]:
    """Thẻ tiêu đề: chữ đen to căn giữa, cụm nhấn có ô màu bo góc. Trả về (lớp RGBA, đáy thẻ)."""
    tpl = tpl or load_template()
    c, h = tpl["card"], tpl["hook"]
    text = _normalise(text)
    font = _font(h["font"], h["size"])
    inner = c["w"] - 2 * h["pad"]
    words = _words(text)
    if accent.strip():
        needle = _normalise(accent).casefold()
        low = text.casefold()
        spans = (
            [(m.start(), m.end()) for m in re.finditer(re.escape(needle), low)]
            if len(low) == len(text)
            else []
        )
        _mark(words, spans, "accent")
    _mark(words, _censor_spans(text, censor), "censored")
    lines = _ellipsize(_wrap(words, font, inner), h["max_lines"], font, inner)
    lh = int(h["size"] * h["line_height"])
    height = int(2 * h["pad"] * 0.8 + lh * max(len(lines), 1))
    img = _canvas(tpl)
    img.alpha_composite(
        _round_rect((c["w"], height), c["radius"], _rgb(c["bg"])), (c["x"], h["top"])
    )
    space = font.getlength(" ")
    y = h["top"] + int(h["pad"] * 0.8)
    for line in lines:
        total = sum(w.width for w in line) + space * (len(line) - 1)
        x = c["x"] + (c["w"] - total) / 2
        i = 0
        while i < len(line):
            w = line[i]
            if w.accent:  # gom các từ nhấn liền nhau vào một ô
                j = i
                while j + 1 < len(line) and line[j + 1].accent:
                    j += 1
                run = line[i : j + 1]
                run_w = sum(r.width for r in run) + space * (len(run) - 1)
                pad = h["accent_pad"]
                box_w, box_h = int(run_w + 2 * pad), int(lh * 0.98)
                img.alpha_composite(
                    _round_rect((box_w, box_h), h["accent_radius"], _rgb(h["accent_bg"])),
                    (int(x - pad), int(y + lh * 0.02)),
                )
                for r in run:
                    _draw_word(img, (x, y), r, font, _rgb(h["accent_fg"]), censor_mode, tpl)
                    x += r.width + space
                i = j + 1
                continue
            _draw_word(img, (x, y), w, font, _rgb(h["color"]), censor_mode, tpl)
            x += w.width + space
            i += 1
        y += lh
    return img, h["top"] + height


def render_card(
    handle: str,
    age: str,
    text: str,
    *,
    likes: int | None = None,
    replies: int | None = None,
    reposts: int | None = None,
    shares: int | None = None,
    views: int | None = None,
    tpl: dict | None = None,
    censor: list[CensorMatcher] | None = None,
    censor_mode: CensorMode = "blur",
    top: int | None = None,
) -> tuple[Image.Image, int]:
    """Thẻ bài gốc hoặc bình luận: avatar, tên, thời gian, chữ, số liệu. Trả (lớp RGBA, đáy)."""
    tpl = tpl or load_template()
    c, hd, b, st = tpl["card"], tpl["header"], tpl["body"], tpl["stats"]
    top = c["top"] if top is None else top
    text = _normalise(text)
    font = _font(b["font"], b["size"])
    inner = c["w"] - 2 * c["pad"]
    words = _words(text)
    _mark(words, _censor_spans(text, censor), "censored")
    lines = _ellipsize(_wrap(words, font, inner), b["max_lines"], font, inner)
    lh = int(b["size"] * b["line_height"])

    stat_items = [
        (k, v)
        for k, v in (("like", likes), ("reply", replies), ("repost", reposts), ("share", shares))
        if v is not None
    ]
    stats_h = (st["icon"] if stat_items else 0) + (
        int(st["size"] * 1.4) if views is not None else 0
    )
    gaps = (b["gap"] if lines else 0) + (st["top_gap"] if stats_h else 0)
    height = c["pad"] * 2 + hd["avatar"] + gaps + lh * len(lines) + stats_h

    img = _canvas(tpl)
    img.alpha_composite(_round_rect((c["w"], height), c["radius"], _rgb(c["bg"])), (c["x"], top))
    x0, y0 = c["x"] + c["pad"], top + c["pad"]
    img.alpha_composite(_avatar(hd["avatar"], hd["avatar_bg"], hd["avatar_fg"]), (x0, y0))
    tx = x0 + hd["avatar"] + hd["gap"]
    d = ImageDraw.Draw(img)
    name_font, age_font = (
        _font(hd["handle_font"], hd["handle_size"]),
        _font(hd["age_font"], hd["age_size"]),
    )
    d.text((tx, y0 - 2), handle or "—", font=name_font, fill=_rgb(hd["handle_color"]))
    if age:
        d.text((tx, y0 + hd["handle_size"] + 2), age, font=age_font, fill=_rgb(hd["age_color"]))

    y = y0 + hd["avatar"] + (b["gap"] if lines else 0)
    for line in lines:
        x = float(x0)
        space = font.getlength(" ")
        for w in line:
            _draw_word(img, (x, y), w, font, _rgb(b["color"]), censor_mode, tpl)
            x += w.width + space
        y += lh
    y += st["top_gap"] if stats_h else 0
    if stat_items:
        sfont = _font(st["font"], st["size"])
        x = float(x0)
        color = _rgb(st["color"])
        for kind, value in stat_items:
            img.alpha_composite(_icon(kind, st["icon"], color), (int(x), int(y)))
            label = format_count(value)
            d.text(
                (x + st["icon"] + 10, y + (st["icon"] - st["size"]) / 2 - 2),
                label,
                font=sfont,
                fill=color,
            )
            x += st["icon"] + 10 + sfont.getlength(label) + st["gap"]
        y += st["icon"]
    if views is not None:
        sfont = _font(st["font"], int(st["size"] * 0.95))
        d.text(
            (x0, y + 8),
            f"{format_count(views)} {VIEWS_LABEL}",
            font=sfont,
            fill=_rgb(st["views_color"]),
        )
    return img, top + height


def hook_text_from_post(text: str, limit: int = 60) -> str:
    """Chữ thẻ tiêu đề khi chưa nhập: câu đầu của bài, cắt ở từ nếu dài quá `limit`."""
    s = _normalise(text).replace(chr(10), " ")
    first = re.split(r"(?<=[.!?…])\s", s, maxsplit=1)[0]
    if len(first) <= limit:
        return first
    cut = first[:limit]
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…" if " " in cut else cut + "…"


def composite_preview(
    layer: Image.Image, background: Image.Image | None, flat: str = "#6DB33F"
) -> Image.Image:
    """Lớp thẻ đặt trên khung nền (ảnh clip) hoặc một màu phẳng, để xem trước trên giao diện."""
    base = Image.new("RGBA", layer.size, _rgb(flat) + (255,))
    if background is not None:
        bg = background.convert("RGB")
        scale = max(layer.width / bg.width, layer.height / bg.height)
        bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.LANCZOS)
        left, top = (bg.width - layer.width) // 2, (bg.height - layer.height) // 2
        base = bg.crop((left, top, left + layer.width, top + layer.height)).convert("RGBA")
    base.alpha_composite(layer)
    return base.convert("RGB")
