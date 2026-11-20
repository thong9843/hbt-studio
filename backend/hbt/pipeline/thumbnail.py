"""Ảnh bìa (thumbnail) HBT, IMPLEMENT.md mục 4e. Tham số giữ nguyên theo
`reference/pipeline/thumbnail_reference.py`; chỉ đường dẫn font và logo là khác.

Khung 1080×1920 (9:16). Tiêu đề nằm trong y=600..1320 (cắt 3:2 của YouTube Shorts); nhãn series và
logo nằm trong y=240..1680 (cắt 3:4 của lưới hồ sơ TikTok). Chữ luôn vẽ bằng Pillow.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from hbt.config import BRAND_DIR

from .visual import FONT_DIR, hex2rgb

W, H = 1080, 1920
CROP_3X2 = (0, 600, W, 1320)
RED, CREAM, INK, DARK = (178, 34, 40), (247, 238, 218), (30, 24, 22), (18, 14, 26)
BRICOLAGE_FILE = "BricolageGrotesque-Variable.ttf"
BRICOLAGE_AXES = (96, 800, 78)  # opsz, wght 800, wdth 78 (thứ tự trục của file)
MAX_WIDTH = 950
MAX_BASE, MIN_BASE = 185, 60
LAST_SCALE, LAST_MAX = 1.12, 205
MAX_BLOCK_HEIGHT = 610
STROKE = 0.11
JPEG_QUALITY = 93
MAX_BYTES = 5 << 20
LOGO_FILE = "hbt-logo-mark.png"
LOGO_WIDTH, LOGO_Y = 300, 1385
PILL_Y, PILL_H = 330, 84

_measure = ImageDraw.Draw(Image.new("L", (1, 1)))


def title_lines(lines: list[str]) -> list[str]:
    """NFC rồi IN HOA ("đ" → "Đ", "ư" → "Ư", "ỷ" → "Ỷ")."""
    return [unicodedata.normalize("NFC", ln).strip().upper() for ln in lines]


def title_font(size: float, font_dir: Path | None = None):
    """Bricolage Grotesque 800 width 78; chưa có file thì dự phòng Be Vietnam Pro ExtraBold."""
    folder = font_dir or FONT_DIR
    path = folder / BRICOLAGE_FILE
    if path.is_file():
        try:
            f = ImageFont.truetype(str(path), int(size))
            f.set_variation_by_axes(list(BRICOLAGE_AXES))
            return f
        except (OSError, AttributeError):
            pass
    return ImageFont.truetype(str(folder / "BeVietnamPro-ExtraBold.ttf"), int(size))


def title_font_name(font_dir: Path | None = None) -> str:
    return (
        "Bricolage Grotesque"
        if ((font_dir or FONT_DIR) / BRICOLAGE_FILE).is_file()
        else "Be Vietnam Pro ExtraBold"
    )


def _width(text: str, font, stroke: float) -> float:
    return _measure.textlength(text, font=font) + 2 * stroke


@dataclass(frozen=True)
class TitleLine:
    text: str
    size: float
    x: float
    y: float
    stroke: int
    last: bool


def layout_title(lines: list[str], font_dir: Path | None = None) -> list[TitleLine]:
    """Cỡ chữ và vị trí từng dòng: dòng dài nhất vừa 950 px, dòng cuối lớn hơn ×1,12 nếu vẫn vừa,
    tổng cao ≤ 610 px, khối căn giữa quanh y=960."""
    lines = title_lines(lines)
    base = MAX_BASE
    while base > MIN_BASE and (
        max(_width(t, title_font(base, font_dir), base * STROKE) for t in lines) > MAX_WIDTH
    ):
        base -= 2
    sizes = [float(base)] * len(lines)
    last = min(base * LAST_SCALE, LAST_MAX)
    if _width(lines[-1], title_font(last, font_dir), last * STROKE) <= MAX_WIDTH:
        sizes[-1] = last
    while sum(s * 1.02 for s in sizes) > MAX_BLOCK_HEIGHT:
        sizes = [s * 0.96 for s in sizes]
    heights = [s * 1.02 for s in sizes]
    y = 960 - sum(heights) / 2
    out = []
    for i, (text, size) in enumerate(zip(lines, sizes, strict=True)):
        stroke = int(size * STROKE)
        w = _width(text, title_font(size, font_dir), stroke)
        out.append(TitleLine(text, size, (W - w) / 2 + stroke, y, stroke, i == len(lines) - 1))
        y += heights[i]
    return out


def title_ink_boxes(lines: list[str], font_dir: Path | None = None) -> list[tuple[int, ...]]:
    """Khung chứa nét chữ (kể cả dấu, viền và bóng) của từng dòng, để kiểm vùng an toàn."""
    boxes = []
    for ln in layout_title(lines, font_dir):
        f = title_font(ln.size, font_dir)
        x0, y0, x1, y1 = _measure.textbbox((ln.x, ln.y), ln.text, font=f, stroke_width=ln.stroke)
        boxes.append((int(x0), int(y0), int(x1) + 10, int(y1) + 12))  # cộng độ lệch bóng (10, 12)
    return boxes


def cover_background(thumb, scenes, project_dir: Path) -> tuple[Path, bool]:
    """Ảnh nền của bìa: `(đường dẫn, cần cắt giữa)`. Có `thumb.image` (ảnh tải lên) thì dùng ảnh đó
    và cắt giữa kiểu cover; không thì dùng ảnh của cảnh `thumb.scene` như cũ. Thiếu file ảnh bìa
    riêng thì ném `FileNotFoundError` (người gọi báo cảnh báo), không quay về ảnh cảnh."""
    if thumb.image:
        path = project_dir / thumb.image
        if not path.is_file():
            raise FileNotFoundError(f"Thiếu ảnh bìa {thumb.image}")
        return path, True
    return project_dir / scenes[thumb.scene - 1].image, False


def _background(bg_path: Path, fit: bool = False) -> Image.Image:
    if fit:  # ảnh tải lên: xoay theo EXIF rồi cắt giữa cho đúng 9:16, không kéo giãn
        with Image.open(bg_path) as src:
            bg = ImageOps.fit(
                ImageOps.exif_transpose(src).convert("RGB"),
                (W, H),
                Image.LANCZOS,
                centering=(0.5, 0.5),
            )
    else:
        bg = Image.open(bg_path).convert("RGB").resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg).enhance(0.82)
    bg = ImageEnhance.Color(bg).enhance(1.1)
    ys = np.arange(H)[:, None]
    alpha = np.clip(1 - np.abs(ys - 960) / 560, 0, 1) ** 1.3 * 0.50  # dải tối mềm sau chữ
    shade = np.zeros((H, W, 4), np.uint8)
    shade[..., :3] = (10, 8, 18)
    shade[..., 3] = (alpha * 255).astype(np.uint8).repeat(W, 1)
    im = bg.convert("RGBA")
    im.alpha_composite(Image.fromarray(shade, "RGBA"))
    return im


def render_cover(
    bg_path: Path,
    lines: list[str],
    series: str,
    accent: str = "#FFD43B",
    logo_path: Path | None = None,
    font_dir: Path | None = None,
    fit_background: bool = False,
) -> Image.Image:
    """Ảnh bìa 1080×1920 RGB. Thiếu logo hoặc nền hỏng thì ném lỗi (người gọi báo cảnh báo).
    `fit_background`: nền là ảnh tải lên (cắt giữa); mặc định kéo ảnh cảnh về 1080×1920 như cũ."""
    logo_path = logo_path or BRAND_DIR / LOGO_FILE
    logo = Image.open(logo_path).convert("RGBA")  # mở trước để lỗi sớm
    im = _background(bg_path, fit_background)
    d = ImageDraw.Draw(im)
    accent_rgb = hex2rgb(accent)
    for ln in layout_title(lines, font_dir):
        f = title_font(ln.size, font_dir)
        fill = accent_rgb if ln.last else (255, 255, 255)
        d.text(
            (ln.x + 10, ln.y + 12), ln.text, font=f, fill=(0, 0, 0, 150),
            stroke_width=ln.stroke, stroke_fill=(0, 0, 0, 150),
        )  # fmt: skip
        d.text((ln.x, ln.y), ln.text, font=f, fill=fill, stroke_width=ln.stroke, stroke_fill=DARK)
    series = series.strip()
    if series:  # nhãn series (trên, trong vùng 3:4)
        pf = ImageFont.truetype(str(FONT_DIR / "BeVietnamPro-ExtraBold.ttf"), 44)
        pw, ph = int(_measure.textlength(series, font=pf)) + 84, PILL_H
        px = (W - pw) // 2
        d.rounded_rectangle((px + 6, PILL_Y + 8, px + pw + 6, PILL_Y + ph + 8), ph // 2,
                            fill=(0, 0, 0, 130))  # fmt: skip
        d.rounded_rectangle((px, PILL_Y, px + pw, PILL_Y + ph), ph // 2, fill=CREAM,
                            outline=INK, width=5)  # fmt: skip
        d.text((px + 42, PILL_Y + ph / 2 - 27), series, font=pf, fill=RED)
    logo = logo.resize((LOGO_WIDTH, int(logo.height * LOGO_WIDTH / logo.width)), Image.LANCZOS)
    im.alpha_composite(logo, ((W - LOGO_WIDTH) // 2, LOGO_Y))  # logo HBT (dưới, trong vùng 3:4)
    return im.convert("RGB")


def save_covers(image: Image.Image, out_dir: Path) -> tuple[Path, Path]:
    """Ghi `cover_9x16.jpg` (1080×1920) và `youtube_3x2.jpg` (dải y=600..1320 của cùng ảnh)."""
    cover, youtube = out_dir / "cover_9x16.jpg", out_dir / "youtube_3x2.jpg"
    quality = JPEG_QUALITY
    while True:
        image.save(cover, quality=quality, subsampling=0)
        if cover.stat().st_size <= MAX_BYTES or quality <= 70:
            break
        quality -= 5  # hiếm: nền quá nhiều chi tiết, giữ dưới 5 MB
    image.crop(CROP_3X2).save(youtube, quality=quality, subsampling=0)
    return cover, youtube
