"""Bộ tạo và phủ lớp Watermark bản quyền (PNG trong suốt 1080x1920 + FFmpeg overlay) dùng chung."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import BaseModel, Field

from hbt.config import BRAND_DIR, REPO_ROOT

WatermarkMode = Literal["text", "logo", "both"]
WatermarkPosition = Literal["top-left", "top-right", "center-subtle"]

FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"


class WatermarkSettings(BaseModel):
    """Cấu hình Watermark bản quyền lưu trong workspace/settings/app.json."""

    enabled: bool = True
    mode: WatermarkMode = "both"
    text: str = Field(default="@HayBietTuot", max_length=64)
    logo_path: str = "brand/hbt-logo-mark.png"
    position: WatermarkPosition = "top-right"
    opacity: float = Field(default=0.35, ge=0.15, le=0.80)


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        if FONT_BOLD.is_file():
            return ImageFont.truetype(str(FONT_BOLD), size=max(10, size))
    except Exception:
        pass
    return ImageFont.load_default()


def resolve_watermark_logo(
    logo_path: str | None,
    *,
    brand_dir: Path | None = None,
    assets_dir: Path | None = None,
) -> Path | None:
    """Tìm file PNG logo watermark từ cấu hình, thư mục assets/watermarks hoặc brand/."""
    bdir = brand_dir or BRAND_DIR
    candidates: list[Path] = []
    if logo_path:
        raw = Path(logo_path)
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.append(REPO_ROOT / raw)
            if assets_dir is not None:
                candidates.append(Path(assets_dir) / "watermarks" / raw.name)
            candidates.append(bdir / raw.name)
    candidates.append(bdir / "hbt-logo-mark.png")
    candidates.append(bdir / "hbt-avatar-192.png")

    for c in candidates:
        if c.is_file():
            return c
    return None


def render_watermark_png(
    out_png: Path,
    cfg: WatermarkSettings | None = None,
    *,
    width: int = 1080,
    height: int = 1920,
    brand_dir: Path | None = None,
    assets_dir: Path | None = None,
) -> Path:
    """Vẽ lớp PNG trong suốt (width x height) chứa logo và/hoặc chữ bản quyền có đổ bóng mềm."""
    settings = cfg or WatermarkSettings()
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not settings.enabled:
        canvas.save(out_png, format="PNG")
        canvas.close()
        return out_png

    scale = width / 1080.0
    use_logo = settings.mode in ("logo", "both")
    use_text = settings.mode in ("text", "both") and bool(settings.text.strip())

    logo_im: Image.Image | None = None
    if use_logo:
        logo_file = resolve_watermark_logo(
            settings.logo_path, brand_dir=brand_dir, assets_dir=assets_dir
        )
        if logo_file is not None:
            try:
                with Image.open(logo_file) as raw_logo:
                    rgba = raw_logo.convert("RGBA")
                    target_h = max(20, int(round(46 * scale)))
                    aspect = rgba.width / max(1, rgba.height)
                    target_w = max(20, int(round(target_h * aspect)))
                    logo_im = rgba.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    rgba.close()
            except Exception:
                logo_im = None

    font_px = max(14, int(round(30 * scale)))
    font = _load_bold_font(font_px)
    label = settings.text.strip() if use_text else ""

    dummy_draw = ImageDraw.Draw(canvas)
    text_w, text_h = 0, 0
    if label:
        bbox = dummy_draw.textbbox((0, 0), label, font=font)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

    gap = int(round(12 * scale)) if (logo_im is not None and label) else 0
    logo_w = logo_im.width if logo_im is not None else 0
    logo_h = logo_im.height if logo_im is not None else 0

    pad = int(round(14 * scale))
    badge_w = logo_w + gap + text_w + pad * 2
    badge_h = max(logo_h, text_h, int(round(36 * scale))) + pad * 2

    if badge_w <= pad * 2:
        canvas.save(out_png, format="PNG")
        canvas.close()
        return out_png

    # Vẽ badge trên layer riêng để tạo drop shadow mềm + áp chuẩn opacity
    fg_layer = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    fg_draw = ImageDraw.Draw(fg_layer)
    sh_draw = ImageDraw.Draw(shadow_layer)

    cur_x = pad
    if logo_im is not None:
        ly = (badge_h - logo_h) // 2
        # Đổ bóng silhouette cho logo
        alpha_ch = logo_im.getchannel("A")
        sh_silhouette = Image.new("RGBA", logo_im.size, (0, 0, 0, 210))
        shadow_layer.paste(sh_silhouette, (cur_x + 2, ly + 3), alpha_ch)
        sh_silhouette.close()
        alpha_ch.close()
        fg_layer.paste(logo_im, (cur_x, ly), logo_im)
        logo_im.close()
        cur_x += logo_w + gap

    if label:
        bbox = fg_draw.textbbox((0, 0), label, font=font)
        ty = (badge_h - (bbox[3] - bbox[1])) // 2 - bbox[1]
        sh_draw.text((cur_x + 2, ty + 3), label, font=font, fill=(0, 0, 0, 220))
        fg_draw.text(
            (cur_x, ty),
            label,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=max(1, int(round(2 * scale))),
            stroke_fill=(11, 13, 18, 200),
        )

    blurred_shadow = shadow_layer.filter(ImageFilter.GaussianBlur(radius=max(1.5, 3.0 * scale)))
    shadow_layer.close()

    combined = Image.alpha_composite(blurred_shadow, fg_layer)
    blurred_shadow.close()
    fg_layer.close()

    # Áp dụng độ mờ (opacity 0.15 - 0.80)
    clamped_opacity = min(0.80, max(0.15, float(settings.opacity)))
    r, g, b, a = combined.split()
    a_scaled = a.point(lambda p: int(round(p * clamped_opacity)))
    combined.putalpha(a_scaled)

    # Định vị trong vùng an toàn Safe-Zone 9:16
    margin_x = int(round(44 * scale))
    margin_top = int(round(92 * scale))
    if settings.position == "top-left":
        pos_x = margin_x
        pos_y = margin_top
    elif settings.position == "center-subtle":
        pos_x = (width - badge_w) // 2
        pos_y = int(round(height * 0.46))
    else:  # top-right
        pos_x = max(margin_x, width - badge_w - margin_x)
        pos_y = margin_top

    canvas.alpha_composite(combined, (pos_x, pos_y))
    combined.close()

    canvas.save(out_png, format="PNG")
    canvas.close()
    return out_png


def build_watermark_overlay_filter(
    *,
    input_video: str = "0:v",
    input_wm: str = "1:v",
    output_label: str = "v_wm",
    visible_until_s: float | None = None,
) -> str:
    """Sinh chuỗi filter FFmpeg overlay lớp watermark (ẩn ở 4s outro cuối nếu có visible_until_s)."""
    enable_part = ""
    if visible_until_s is not None and visible_until_s > 0:
        enable_part = f":enable='between(t,0,{visible_until_s:.3f})'"
    return (
        f"[{input_video}][{input_wm}]overlay=0:0:eof_action=pass"
        f"{enable_part}:format=auto,format=yuv420p[{output_label}]"
    )
