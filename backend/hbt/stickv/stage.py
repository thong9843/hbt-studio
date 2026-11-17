"""Sân khấu diễn hoạt StickV v6.1: Bảng minh họa co giãn, Karaoke & Lip-sync mượt."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from hbt.config import REPO_ROOT
from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvAspect, StickvBeat, StickvTheme
from hbt.stickv.poses_init import (
    DEFAULT_POSES,
    convert_stickman_dir_to_transparent,
    ensure_default_poses,
)

FONTS_DIR = REPO_ROOT / "backend" / "hbt" / "fonts"
FONT_EXTRABOLD = FONTS_DIR / "BeVietnamPro-ExtraBold.ttf"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = FONTS_DIR / "BeVietnamPro-Medium.ttf"

BOARD_BADGES: dict[str, str] = {
    "bullets": "SỰ THẬT",
    "big_number": "CON SỐ",
    "comparison": "SO SÁNH",
    "flow_steps": "QUY TRÌNH",
}

THEME_PALETTES: dict[StickvTheme, dict[str, tuple[int, int, int, int]]] = {
    "cream": {
        "bg": (250, 247, 240, 255),
        "grid": (235, 229, 216, 255),
        "card": (255, 255, 255, 250),
        "card_border": (220, 210, 192, 255),
        "text": (15, 23, 42, 255),
        "muted": (71, 85, 105, 255),
        "accent": (217, 35, 46, 255),
        "amber": (245, 158, 11, 255),
        "pill_bg": (254, 243, 199, 255),
        "pill_text": (146, 64, 14, 255),
        "takeaway_bg": (255, 247, 237, 255),
    },
    "dark": {
        "bg": (17, 24, 39, 255),
        "grid": (31, 41, 55, 255),
        "card": (30, 41, 59, 250),
        "card_border": (51, 65, 85, 255),
        "text": (248, 250, 252, 255),
        "muted": (203, 213, 225, 255),
        "accent": (245, 158, 11, 255),
        "amber": (250, 204, 21, 255),
        "pill_bg": (51, 65, 85, 255),
        "pill_text": (253, 224, 71, 255),
        "takeaway_bg": (15, 23, 42, 255),
    },
}


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        if path.is_file():
            return ImageFont.truetype(str(path), size=max(12, size))
    except Exception:
        pass
    return ImageFont.load_default()


_POSE_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _match_pose_in_dir(directory: Path, pose_clean: str) -> Path | None:
    if not directory.is_dir():
        return None
    files = [
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in _POSE_IMG_EXTS and not p.name.startswith(".")
    ]
    if not files:
        return None

    low_pose = pose_clean.lower()
    stem = Path(low_pose).stem
    exact_names = {low_pose, f"{stem}.png", f"{stem}.jpg", f"{stem}.jpeg", f"{stem}.webp"}

    # 1. Khớp chính xác tên file
    exact = [p for p in files if p.name.lower() in exact_names]
    if exact:
        exact.sort(key=lambda p: (p.suffix.lower() == ".png", p.stat().st_mtime), reverse=True)
        return exact[0]

    # 2. Khớp tiền tố bắt đầu bằng {pose}. hoặc {pose}_ (vd: shock.png_Same_stickman_mascot_...png)
    prefixed = [
        p
        for p in files
        if p.name.lower().startswith(f"{stem}.") or p.name.lower().startswith(f"{stem}_")
    ]
    if prefixed:
        prefixed.sort(key=lambda p: (p.suffix.lower() == ".png", p.stat().st_mtime), reverse=True)
        return prefixed[0]

    # 3. File mặc định người dùng (default.png / stickman_mascot) hoặc file mới nhất trong thư mục
    defaults = [
        p
        for p in files
        if p.stem.lower() == "default" or p.name.lower().startswith("stickman_mascot")
    ]
    if defaults:
        defaults.sort(key=lambda p: (p.suffix.lower() == ".png", p.stat().st_mtime), reverse=True)
        return defaults[0]

    return None


def resolve_pose_png(pose: str, library_dir: Path, assets_dir: Path) -> Path:
    """Tìm file PNG dáng nhân vật theo thứ tự ưu tiên:
    1. Khớp chính xác `{pose}.png` trong `assets/stickman/` -> `library/stickman/poses/`
    2. Khớp tiền tố `{pose}.` / `{pose}_` (vd `shock.png_Same_stickman_...`) mới nhất
    3. `default.png` / `stickman_mascot` hoặc file mới nhất trong `assets/stickman/`
    4. Bộ mặc định trong `library/stickman/poses/`
    """
    clean = (pose or "explain").strip()
    user_dir = assets_dir / "stickman"
    poses_dir = library_dir / "stickman" / "poses"
    lib_stick_dir = library_dir / "stickman"

    for d in (user_dir, poses_dir):
        convert_stickman_dir_to_transparent(d)

    for d in (user_dir, user_dir / "poses", poses_dir, lib_stick_dir):
        found = _match_pose_in_dir(d, clean)
        if found is not None:
            return found

    # Nếu vẫn có ảnh bất kỳ trong assets/stickman, dùng ảnh mới nhất làm fallback
    if user_dir.is_dir():
        user_imgs = sorted(
            (p for p in user_dir.iterdir() if p.is_file() and p.suffix.lower() in _POSE_IMG_EXTS),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if user_imgs:
            return user_imgs[0]

    ensure_default_poses(poses_dir)
    stem = Path(clean).stem.lower()
    fallback = poses_dir / (f"{stem}.png" if stem in DEFAULT_POSES else "explain.png")
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


def _measure_wrapped_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width_chars: int,
    line_gap: int,
) -> tuple[list[str], int]:
    lines = textwrap.wrap(text.strip(), width=max(10, width_chars)) or [""]
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        total_h += (bbox[3] - bbox[1]) + line_gap
    return lines, total_h


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    *,
    width_chars: int = 32,
    line_gap: int = 10,
) -> int:
    x, y = xy
    lines = textwrap.wrap(text.strip(), width=max(10, width_chars)) or [""]
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
    """Vẽ bảng minh họa co giãn theo nội dung + Badge + VS + Takeaway."""
    if beat.board_type == "none":
        return

    x0, y0, x1, max_y1 = box
    bw = x1 - x0
    draw = ImageDraw.Draw(canvas)

    f_badge = _load_font(FONT_EXTRABOLD, 22)
    f_title = _load_font(FONT_EXTRABOLD, 44)
    f_body = _load_font(FONT_BOLD, 34)
    f_sub = _load_font(FONT_MEDIUM, 28)
    f_big = _load_font(FONT_EXTRABOLD, 136)

    data: dict[str, Any] = beat.board_data or {}
    takeaway = str(data.get("takeaway") or "").strip()

    # Ước lượng chiều cao nội dung để bảng co giãn vừa vặn (không thừa khoảng trắng)
    est_h = 92  # top padding + badge
    if beat.board_title:
        _, th = _measure_wrapped_height(draw, beat.board_title, f_title, max(18, bw // 26), 10)
        est_h += th + 14

    if beat.board_type == "bullets":
        items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:5]
        for it in items:
            _, ih = _measure_wrapped_height(draw, it, f_body, max(16, (bw - 140) // 21), 10)
            est_h += max(50, ih) + 18
    elif beat.board_type == "big_number":
        est_h += 240
    elif beat.board_type == "comparison":
        left_n = len((data.get("left_items") or [])[:4])
        right_n = len((data.get("right_items") or [])[:4])
        est_h += 76 + max(1, left_n, right_n) * 66
    elif beat.board_type == "flow_steps":
        steps = [str(s) for s in (data.get("steps") or []) if str(s).strip()][:4]
        est_h += len(steps) * 96

    if takeaway:
        est_h += 86

    card_h = min(max_y1 - y0, max(280, est_h + 36))
    y1 = y0 + card_h

    # Đổ bóng nhẹ + Thẻ bo góc
    draw.rounded_rectangle((x0 + 6, y0 + 10, x1 + 6, y1 + 10), radius=34, fill=(15, 23, 42, 28))
    draw.rounded_rectangle(
        (x0, y0, x1, y1),
        radius=34,
        fill=pal["card"],
        outline=pal["card_border"],
        width=3,
    )

    # Badge phân loại góc trên trái
    badge_txt = BOARD_BADGES.get(beat.board_type, "NỔI BẬT")
    bb = draw.textbbox((0, 0), badge_txt, font=f_badge)
    badge_w = (bb[2] - bb[0]) + 32
    draw.rounded_rectangle(
        (x0 + 32, y0 + 24, x0 + 32 + badge_w, y0 + 62),
        radius=999,
        fill=pal["accent"],
    )
    draw.text((x0 + 48, y0 + 30), badge_txt, font=f_badge, fill=(255, 255, 255, 255))

    cur_y = y0 + 82
    if beat.board_title:
        cur_y = _draw_wrapped_text(
            draw,
            beat.board_title,
            (x0 + 36, cur_y),
            f_title,
            pal["text"],
            width_chars=max(18, bw // 26),
            line_gap=10,
        )
        cur_y += 14

    content_bottom = y1 - (94 if takeaway else 28)

    if beat.board_type == "bullets":
        items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:5]
        for idx, item in enumerate(items, start=1):
            if cur_y > content_bottom - 48:
                break
            draw.ellipse((x0 + 38, cur_y + 4, x0 + 80, cur_y + 46), fill=pal["amber"])
            draw.text((x0 + 51, cur_y + 7), str(idx), font=f_sub, fill=(255, 255, 255, 255))
            cur_y = _draw_wrapped_text(
                draw,
                item,
                (x0 + 100, cur_y),
                f_body,
                pal["text"],
                width_chars=max(16, (bw - 140) // 21),
                line_gap=10,
            )
            cur_y += 14

    elif beat.board_type == "big_number":
        val = str(data.get("value") or "100%")
        lbl = str(data.get("label") or "")
        sub = str(data.get("sub") or "")
        draw.text((x0 + 44, cur_y + 4), val, font=f_big, fill=pal["accent"])
        bbox = draw.textbbox((x0 + 44, cur_y + 4), val, font=f_big)
        cur_y = bbox[3] + 22
        if lbl:
            cur_y = _draw_wrapped_text(
                draw, lbl, (x0 + 44, cur_y), f_title, pal["text"], width_chars=max(16, bw // 26)
            )
        if sub:
            _draw_wrapped_text(
                draw, sub, (x0 + 44, cur_y + 6), f_sub, pal["muted"], width_chars=max(20, bw // 19)
            )

    elif beat.board_type == "comparison":
        mid_x = (x0 + x1) // 2
        draw.line(
            [(mid_x, cur_y + 12), (mid_x, content_bottom - 12)], fill=pal["card_border"], width=3
        )
        # Huy hiệu VS ở giữa
        draw.ellipse((mid_x - 28, cur_y - 2, mid_x + 28, cur_y + 54), fill=pal["accent"])
        draw.text((mid_x - 16, cur_y + 12), "VS", font=f_badge, fill=(255, 255, 255, 255))

        left_t = str(data.get("left_title") or "Trước")
        right_t = str(data.get("right_title") or "Sau")
        draw.text((x0 + 36, cur_y + 8), left_t, font=f_body, fill=pal["muted"])
        draw.text((mid_x + 42, cur_y + 8), right_t, font=f_body, fill=pal["accent"])
        ly = cur_y + 64
        ry = cur_y + 64
        col_chars = max(12, (bw // 2 - 80) // 19)
        for item in (data.get("left_items") or [])[:4]:
            ly = (
                _draw_wrapped_text(
                    draw, f"• {item}", (x0 + 36, ly), f_sub, pal["text"], width_chars=col_chars
                )
                + 10
            )
        for item in (data.get("right_items") or [])[:4]:
            ry = (
                _draw_wrapped_text(
                    draw, f"✓ {item}", (mid_x + 42, ry), f_sub, pal["text"], width_chars=col_chars
                )
                + 10
            )

    elif beat.board_type == "flow_steps":
        steps = [str(s) for s in (data.get("steps") or []) if str(s).strip()][:4]
        for idx, step in enumerate(steps, start=1):
            if cur_y > content_bottom - 60:
                break
            draw.rounded_rectangle(
                (x0 + 36, cur_y, x1 - 36, cur_y + 74),
                radius=18,
                fill=pal["pill_bg"],
                outline=pal["amber"],
                width=2,
            )
            draw.text(
                (x0 + 56, cur_y + 18), f"{idx}. {step[:40]}", font=f_body, fill=pal["pill_text"]
            )
            cur_y += 94

    if takeaway:
        ty0 = y1 - 78
        draw.rounded_rectangle(
            (x0 + 28, ty0, x1 - 28, y1 - 20),
            radius=16,
            fill=pal["takeaway_bg"],
            outline=pal["amber"],
            width=2,
        )
        draw.text(
            (x0 + 46, ty0 + 14), f"Chốt lại: {takeaway[:54]}", font=f_sub, fill=pal["pill_text"]
        )


def draw_karaoke_strip(
    frame: Image.Image,
    word_timings: list[tuple[str, float, float]],
    t_sec: float,
    *,
    aspect: StickvAspect,
) -> None:
    """Vẽ dải phụ đề Karaoke (nền vàng #FFD43B cho từ đang đọc) ở vùng giữa màn hình."""
    if not word_timings:
        return

    w, h = frame.size
    active_idx = 0
    for idx, (_w, st, et) in enumerate(word_timings):
        if st <= t_sec <= et:
            active_idx = idx
            break
        if t_sec > et:
            active_idx = idx

    # Nhóm 5-6 từ quanh từ đang đọc để vừa 1 dòng gọn đẹp
    win_size = 5 if aspect == "9:16" else 7
    chunk_idx = active_idx // win_size
    chunk = word_timings[chunk_idx * win_size : (chunk_idx + 1) * win_size]
    if not chunk:
        return

    draw = ImageDraw.Draw(frame)
    font = _load_font(FONT_EXTRABOLD, 42 if aspect == "9:16" else 38)
    space_w = 14
    widths: list[int] = []
    for word, _, _ in chunk:
        bb = draw.textbbox((0, 0), word, font=font)
        widths.append(bb[2] - bb[0])
    total_w = sum(widths) + space_w * max(0, len(chunk) - 1)

    cur_x = (w - total_w) // 2
    base_y = 970 if aspect == "9:16" else h - 115

    for local_i, ((word, _, _), ww) in enumerate(zip(chunk, widths, strict=True)):
        global_i = chunk_idx * win_size + local_i
        is_active = global_i == active_idx
        if is_active:
            draw.rounded_rectangle(
                (cur_x - 10, base_y - 6, cur_x + ww + 10, base_y + 52),
                radius=12,
                fill=(255, 212, 59, 255),  # #FFD43B
            )
            draw.text((cur_x, base_y), word, font=font, fill=(15, 23, 42, 255))
        else:
            draw.text(
                (cur_x, base_y),
                word,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=4,
                stroke_fill=(15, 23, 42, 255),
            )
        cur_x += ww + space_w


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def render_animated_beat_frame(
    *,
    bg_img: Image.Image,
    char_img: Image.Image | None,
    beat: StickvBeat,
    aspect: StickvAspect,
    t_sec: float,
    mouth_open: float,
    word_timings: list[tuple[str, float, float]],
) -> Image.Image:
    """Tổng hợp 1 khung hình động: nhân vật ease-in-out + chớp mắt + lip-sync + karaoke."""
    frame = bg_img.copy()
    w, h = frame.size

    if char_img is not None:
        if aspect == "9:16":
            base_x = (w - char_img.width) // 2
            base_y = h - char_img.height - 220
        else:
            base_x = 90
            base_y = (h - char_img.height) // 2 + 40

        dx, dy = 0.0, 0.0
        if beat.motion == "slide_left":
            p = _ease_in_out(min(1.0, t_sec / 0.35))
            dx = (1.0 - p) * (w * 0.45)
        elif beat.motion == "slide_right":
            p = _ease_in_out(min(1.0, t_sec / 0.35))
            dx = -(1.0 - p) * (w * 0.45)
        elif beat.motion == "shake":
            dx = math.sin(t_sec * 36.0) * 10.0
        elif beat.motion == "float":
            dy = math.sin(t_sec * 3.0) * 12.0
        elif beat.motion == "bounce":
            dy = -abs(math.sin(t_sec * 6.0)) * 14.0

        # Nhún nhịp theo biên độ giọng đọc (bobbing) + gật đầu nhẹ
        dy += math.sin(t_sec * 4.2) * 3.0 - (mouth_open * 6.0)
        px = int(round(base_x + dx))
        py = int(round(base_y + dy))

        frame_rgba = frame.convert("RGBA")
        try:
            # Bóng đổ mềm dưới chân nhân vật (giữ nguyên tạo hình nhân vật, không vẽ đè mặt/tay)
            shadow_draw = ImageDraw.Draw(frame_rgba)
            sx0 = px + int(char_img.width * 0.2)
            sx1 = px + int(char_img.width * 0.8)
            sy0 = base_y + char_img.height - 26
            sy1 = base_y + char_img.height + 6
            shadow_draw.ellipse((sx0, sy0, sx1, sy1), fill=(15, 23, 42, 42))

            frame_rgba.alpha_composite(char_img, (px, py))

            draw_karaoke_strip(frame_rgba, word_timings, t_sec, aspect=aspect)
            rgb = frame_rgba.convert("RGB")
            return rgb
        finally:
            frame_rgba.close()
            frame.close()

    draw_karaoke_strip(frame, word_timings, t_sec, aspect=aspect)
    return frame.convert("RGB")


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
            board_box = (64, 150, w - 64, 930)
            char_target_h = 620
        else:
            board_box = (700, 100, w - 70, h - 150)
            char_target_h = 660

        beat_media = (project_dir / beat.media_path) if (project_dir and beat.media_path) else None
        if (
            beat_media
            and beat_media.is_file()
            and beat_media.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ):
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
