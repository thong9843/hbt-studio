"""Vẽ thẻ chữ, nhãn, phụ đề karaoke bằng Pillow (chữ tiếng Việt luôn chuẩn dấu)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .text import display

W, H = 1080, 1920
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
INK = (40, 22, 18)
CREAM = (246, 238, 222)
SIZES = {"s": 50, "m": 62, "l": 84, "xl": 100}
CARD_Y = {"top": 110, "upper": 560, "middle": 760, "lower": 1300}
_fonts = {}


def font(weight: str, size: int):
    key = (weight, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(str(FONT_DIR / f"BeVietnamPro-{weight}.ttf"), size)
    return _fonts[key]


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def color_of(name, theme):
    if not name or name == "ink":
        return INK
    if name in theme:
        return hex2rgb(theme[name])
    if name.startswith("#"):
        return hex2rgb(name)
    return INK


def fit_image(src, dst):
    im = Image.open(src).convert("RGB")
    ImageOps.fit(im, (W, H), Image.LANCZOS).save(dst)


def _wrap(draw, text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def draw_card(layer, lines, y, theme, maxw=960, pad=36):
    """lines: [{'text','size','color'}]. Thẻ giấy kem, viền màu chủ đạo, căn giữa ngang."""
    tmp = ImageDraw.Draw(layer)
    rows = []
    for ln in lines:
        if not ln.get("text"):
            continue
        size = SIZES.get(ln.get("size", "m"), 62)
        f = font("ExtraBold" if size >= 70 else "Bold", size)
        col = color_of(ln.get("color", "ink"), theme)
        for t in _wrap(tmp, ln["text"], f, maxw - 2 * pad):
            rows.append((t, f, col, int(size * 1.28)))
    if not rows:
        return
    bw = max(tmp.textlength(r[0], font=r[1]) for r in rows) + 2 * pad
    bh = sum(r[3] for r in rows) + 2 * pad - 8
    border = color_of("primary", theme)
    c = Image.new("RGBA", (int(bw) + 30, int(bh) + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle((12, 14, bw + 12, bh + 14), 18, fill=(0, 0, 0, 110))
    d.rounded_rectangle((0, 0, bw, bh), 18, fill=CREAM + (255,), outline=border + (255,), width=5)
    yy = pad - 6
    for t, f, col, lh in rows:
        d.text(((bw - d.textlength(t, font=f)) / 2, yy), t, font=f, fill=col)
        yy += lh
    layer.alpha_composite(c, (int((W - c.width) / 2), int(y)))
    return int(y) + c.height


def draw_label(layer, lb, theme):
    f = font("ExtraBold", int(lb.get("size", 80)))
    col = color_of(lb.get("color", "ink"), theme)
    d0 = ImageDraw.Draw(layer)
    tw = d0.textlength(lb["text"], font=f)
    size = int(lb.get("size", 80))
    c = Image.new("RGBA", (int(tw) + 40, int(size * 1.5)), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.text((20, 5), lb["text"], font=f, fill=col)
    if lb.get("rot"):
        c = c.rotate(float(lb["rot"]), expand=True, resample=Image.BICUBIC)
    layer.alpha_composite(c, (int(lb["x"] - c.width / 2), int(lb["y"] - c.height / 2)))


def build_scene_layers(scene, img_src, base_out, card_out, theme):
    """Ảnh nền (đã gắn nhãn cố định) + lớp thẻ chữ trong suốt. Trả về toạ độ đáy thẻ."""
    fit_image(img_src, base_out)
    if scene.get("labels"):
        b = Image.open(base_out).convert("RGBA")
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for lb in scene["labels"]:
            draw_label(lay, lb, theme)
        b.alpha_composite(lay)
        b.convert("RGB").save(base_out)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    card = scene.get("card") or {}
    y = card.get("y", "top")
    y = CARD_Y.get(y, y) if isinstance(y, str) else int(y)
    bottom = draw_card(lay, card.get("lines", []), y, theme) if card.get("lines") else None
    lay.save(card_out)
    return y, bottom


# ---------------------------------------------------------------- karaoke captions
CAP_FONT = ("ExtraBold", 70)
HIGHLIGHT = (255, 212, 59)


def render_caption(words, act, path, yc):
    f = font(*CAP_FONT)
    toks = [display(w) for w in words]
    d0 = ImageDraw.Draw(Image.new("L", (1, 1)))
    ws = [d0.textlength(t, font=f) for t in toks]
    sp, maxw, lh = 22, 900, 96
    lines, lw = [[]], 0
    for k, wd in enumerate(ws):
        if lines[-1] and lw + sp + wd > maxw:
            lines.append([])
            lw = 0
        lw += (sp if lines[-1] else 0) + wd
        lines[-1].append(k)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    y0 = yc - lh * len(lines) / 2
    for li, ln in enumerate(lines):
        tw = sum(ws[k] for k in ln) + sp * (len(ln) - 1)
        x, y = (W - tw) / 2, y0 + li * lh
        for k in ln:
            if k == act:
                d.rounded_rectangle(
                    (x - 12, y + 2, x + ws[k] + 12, y + lh - 4), 18, fill=HIGHLIGHT + (255,)
                )
                d.text((x, y + 4), toks[k], font=f, fill=(20, 20, 20))
            else:
                d.text((x + 3, y + 8), toks[k], font=f, fill=(0, 0, 0, 120))
                d.text(
                    (x, y + 4),
                    toks[k],
                    font=f,
                    fill=(255, 255, 255),
                    stroke_width=7,
                    stroke_fill=(15, 15, 25),
                )
            x += ws[k] + sp
    im.save(path)
