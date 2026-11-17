"""Sân khấu diễn hoạt StickV & Bảng minh họa thông minh bằng Pillow (tối ưu RAM)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from hbt.config import REPO_ROOT
from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvAspect, StickvBeat, StickvTheme
from hbt.stickv.poses_init import DEFAULT_POSES, ensure_default_poses

FONTS_DIR = REPO_ROOT / "backend" / "hbt" / "fonts"
FONT_EXTRABOLD = FONTS_DIR / "BeVietnamPro-ExtraBold.ttf"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = FONTS_DIR / "BeVietnamPro-Medium.ttf"

THEME_PALETTES: dict[StickvTheme, dict[str, tuple[int, int, int, int]]] = {
    "cream": {
        "bg": (250, 247, 240, 255),          # #FAF7F0 Giấy kem ấm
        "grid": (235, 229, 216, 255),
        "card": (255, 255, 255, 245),
        "card_border": (224, 215, 198, 255),
        "text": (30, 41, 59, 255),
        "muted": (71, 85, 105, 255),
        "accent": (217, 35, 46, 255),        # HBT Red
        "amber": (245, 158, 11, 255),        # HBT Amber
        "pill_bg": (254, 243, 199, 255),
        "pill_text": (146, 64, 14, 255),
    },
    "dark": {
        "bg": (17, 24, 39, 255),             # #111827 Bảng tối hiện đại
        "grid": (31, 41, 55, 255),
        "card": (30, 41, 59, 245),
        "card_border": (51, 65, 85, 255),
        "text": (248, 250, 252, 255),
        "muted": (203, 213, 225, 255),
        "accent": (245, 158, 11, 255),       # HBT Amber
        "amber": (250, 204, 21, 255),
        "pill_bg": (51, 65, 85, 255),
        "pill_text": (253, 224, 71, 255),
    },
}


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        if path.is_file():
            return ImageFont.truetype(str(path), size=max(12, size))
    except Exception:
        pass
    return ImageFont.load_default()


def resolve_pose_png(pose: str, library_dir: Path, assets_dir: Path) -> Path:
    """Tìm file PNG dáng nhân vật trong assets/stickman -> library/stickman/poses."""
    clean = (pose or "explain").strip()
    fname = clean if clean.lower().endswith(".png") else f"{clean}.png"
    candidates = [
        assets_dir / "stickman" / fname,
        assets_dir / "stickman" / clean,
        library_dir / "stickman" / "poses" / fname,
        library_dir / "stickman" / fname,
    ]
    for c in candidates:
        if c.is_file():
            return c
    poses_dir = library_dir / "stickman" / "poses"
    ensure_default_poses(poses_dir)
    fallback = poses_dir / (fname if clean in DEFAULT_POSES else "explain.png")
    return fallback if fallback.is_file() else poses_dir / "explain.png"


def _draw_grid_background(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    pal: dict[str, tuple[int, int, int, int]],
) -> None:
    step = 64
    grid_c = pal["grid"]
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=grid_c, width=1)
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=grid_c, width=1)


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    *,
    width_chars: int = 34,
    line_gap: int = 10,
) -> int:
    x, y = xy
    lines = textwrap.wrap(text.strip(), width=width_chars) or [""]
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, cur_y), line, font=font)
        cur_y = bbox[3] + line_gap
    return cur_y


def _draw_smart_board(
    canvas: Image.Image,
    beat: StickvBeat,
    box: tuple[int, int, int, int],
    pal: dict[str, tuple[int, int, int, int]],
) -> None:
    """Vẽ bảng minh họa thông minh (bullets / big_number / comparison / flow_steps)."""
    if beat.board_type == "none":
        return

    x0, y0, x1, y1 = box
    bw = x1 - x0
    draw = ImageDraw.Draw(canvas)

    # Thẻ bảng bo góc
    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=32,
        fill=pal["card"],
        outline=pal["card_border"],
        width=3,
    )
    # Thanh nhấn trên đầu bảng
    draw.rounded_rectangle((x0 + 28, y0 + 22, x0 + 168, y0 + 32), radius=5, fill=pal["accent"])

    f_title = _load_font(FONT_EXTRABOLD, 42)
    f_body = _load_font(FONT_BOLD, 32)
    f_sub = _load_font(FONT_MEDIUM, 26)
    f_big = _load_font(FONT_EXTRABOLD, 132)

    cur_y = y0 + 52
    if beat.board_title:
        cur_y = _draw_wrapped_text(
            draw,
            beat.board_title,
            (x0 + 36, cur_y),
            f_title,
            pal["text"],
            width_chars=max(20, bw // 26),
            line_gap=8,
        )
        cur_y += 16

    data: dict[str, Any] = beat.board_data or {}

    if beat.board_type == "bullets":
        items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:5]
        for idx, item in enumerate(items, start=1):
            if cur_y > y1 - 70:
                break
            draw.ellipse((x0 + 38, cur_y + 6, x0 + 76, cur_y + 44), fill=pal["amber"])
            draw.text((x0 + 50, cur_y + 6), str(idx), font=f_sub, fill=(255, 255, 255, 255))
            cur_y = _draw_wrapped_text(
                draw,
                item,
                (x0 + 96, cur_y),
                f_body,
                pal["text"],
                width_chars=max(18, (bw - 130) // 20),
                line_gap=10,
            )
            cur_y += 14

    elif beat.board_type == "big_number":
        val = str(data.get("value") or "100%")
        lbl = str(data.get("label") or "")
        sub = str(data.get("sub") or "")
        draw.text((x0 + 44, cur_y + 10), val, font=f_big, fill=pal["accent"])
        bbox = draw.textbbox((x0 + 44, cur_y + 10), val, font=f_big)
        cur_y = bbox[3] + 24
        if lbl:
            cur_y = _draw_wrapped_text(
                draw, lbl, (x0 + 44, cur_y), f_title, pal["text"], width_chars=max(18, bw // 26)
            )
        if sub:
            _draw_wrapped_text(
                draw, sub, (x0 + 44, cur_y + 10), f_sub, pal["muted"], width_chars=max(22, bw // 18)
            )

    elif beat.board_type == "comparison":
        mid_x = (x0 + x1) // 2
        draw.line([(mid_x, cur_y), (mid_x, y1 - 36)], fill=pal["card_border"], width=3)
        left_t = str(data.get("left_title") or "Trước")
        right_t = str(data.get("right_title") or "Sau")
        draw.text((x0 + 36, cur_y), left_t, font=f_body, fill=pal["muted"])
        draw.text((mid_x + 28, cur_y), right_t, font=f_body, fill=pal["accent"])
        ly = cur_y + 52
        ry = cur_y + 52
        col_chars = max(12, (bw // 2 - 70) // 18)
        for item in (data.get("left_items") or [])[:4]:
            ly = _draw_wrapped_text(draw, f"• {item}", (x0 + 36, ly), f_sub, pal["text"], width_chars=col_chars) + 10
        for item in (data.get("right_items") or [])[:4]:
            ry = _draw_wrapped_text(draw, f"✓ {item}", (mid_x + 28, ry), f_sub, pal["text"], width_chars=col_chars) + 10

    elif beat.board_type == "flow_steps":
        steps = [str(s) for s in (data.get("steps") or []) if str(s).strip()][:4]
        for idx, step in enumerate(steps, start=1):
            if cur_y > y1 - 80:
                break
            draw.rounded_rectangle(
                (x0 + 36, cur_y, x1 - 36, cur_y + 72),
                radius=18,
                fill=pal["pill_bg"],
                outline=pal["amber"],
                width=2,
            )
            draw.text((x0 + 56, cur_y + 18), f"{idx}. {step[:42]}", font=f_body, fill=pal["pill_text"])
            cur_y += 92


def render_beat_layers(
    beat: StickvBeat,
    *,
    aspect: StickvAspect,
    theme: StickvTheme,
    out_dir: Path,
    library_dir: Path,
    assets_dir: Path,
    project_dir: Path | None = None,
) -> tuple[Path, Path | None]:
    """Vẽ lớp nền + bảng minh họa (`bg.png`) và nhân vật (`char.png`), giải phóng RAM ngay."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = STICKV_ASPECT_SIZES[aspect]
    pal = THEME_PALETTES[theme]

    bg_path = out_dir / f"{beat.id}_bg.png"
    char_path: Path | None = out_dir / f"{beat.id}_char.png"

    bg_img = Image.new("RGBA", (w, h), pal["bg"])
    try:
        draw = ImageDraw.Draw(bg_img)
        _draw_grid_background(draw, w, h, pal)

        if aspect == "9:16":
            board_box = (64, 180, w - 64, 920)
            char_target_h = 620
        else:
            board_box = (720, 120, w - 80, h - 140)
            char_target_h = 680

        # Nếu beat có ảnh minh họa riêng (PNG/JPG/WEBP), vẽ lồng vào khung bảng
        beat_media = (project_dir / beat.media_path) if (project_dir and beat.media_path) else None
        if beat_media and beat_media.is_file() and beat_media.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            with Image.open(beat_media) as raw_media:
                media_rgba = raw_media.convert("RGBA")
                try:
                    bx0, by0, bx1, by1 = board_box
                    media_rgba.thumbnail((bx1 - bx0, by1 - by0), Image.Resampling.LANCZOS)
                    mx = bx0 + ((bx1 - bx0) - media_rgba.width) // 2
                    my = by0 + ((by1 - by0) - media_rgba.height) // 2
                    bg_img.alpha_composite(media_rgba, (mx, my))
                finally:
                    media_rgba.close()
        else:
            _draw_smart_board(bg_img, beat, board_box, pal)

        bg_img.convert("RGB").save(bg_path, format="PNG")
    finally:
        bg_img.close()

    # Chuẩn bị lớp nhân vật PNG trong suốt (trừ khi beat dùng video clip .mp4 riêng)
    if beat.media_path and Path(beat.media_path).suffix.lower() in {".mp4", ".mov", ".webm"}:
        char_path = None
    else:
        pose_file = resolve_pose_png(beat.pose, library_dir, assets_dir)
        with Image.open(pose_file) as raw_pose:
            pose_img = raw_pose.convert("RGBA")
            try:
                ratio = char_target_h / max(1, pose_img.height)
                new_w = max(2, int(pose_img.width * ratio))
                resized = pose_img.resize((new_w, char_target_h), Image.Resampling.LANCZOS)
                try:
                    if beat.facing == "left":
                        flipped = resized.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                        try:
                            flipped.save(char_path, format="PNG")
                        finally:
                            flipped.close()
                    else:
                        resized.save(char_path, format="PNG")
                finally:
                    resized.close()
            finally:
                pose_img.close()

    return bg_path, char_path
