"""Sân khấu diễn hoạt StickV v6.1: Bảng minh họa co giãn, Karaoke & Lip-sync mượt."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from hbt.config import REPO_ROOT
from hbt.stickv.backdrops import DOMAIN_PALETTES, normalize_domain
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
    "list": "DANH SÁCH",
    "card": "THÔNG TIN",
    "quote": "TRÍCH DẪN",
    "big_number": "CON SỐ",
    "counter_grow": "THỐNG KÊ",
    "comparison": "SO SÁNH",
    "bar_compare": "BIỂU ĐỒ",
    "flow_steps": "QUY TRÌNH",
}


def resolve_stage_palette(
    domain: str | None, theme: StickvTheme = "cream"
) -> dict[str, tuple[int, int, int, int]]:
    norm = normalize_domain(domain)
    if norm == "paper_classic" and theme == "dark":
        return THEME_PALETTES["dark"]
    return DOMAIN_PALETTES.get(norm, THEME_PALETTES[theme])

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


def list_available_poses(library_dir: Path, assets_dir: Path) -> list[str]:
    """Quét động toàn bộ tên dáng khả dụng trong `assets/stickman/` và `library/stickman/poses/`."""
    found: list[str] = list(DEFAULT_POSES)
    seen: set[str] = set(DEFAULT_POSES)
    skip_stems = {"default", "stickman_mascot"}

    for d in (
        assets_dir / "stickman",
        library_dir / "stickman" / "poses",
        library_dir / "stickman",
    ):
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.name.startswith("."):
                continue
            if p.suffix.lower() not in _POSE_IMG_EXTS:
                continue
            name_low = p.name.lower()
            # Lấy tiền tố trước '.png_' nếu là file Google Flow, hoặc stem
            if ".png_" in name_low:
                pose_name = name_low.split(".png_", 1)[0]
            else:
                pose_name = p.stem.lower()
            if not pose_name or pose_name in skip_stems or pose_name in seen:
                continue
            seen.add(pose_name)
            found.append(pose_name)
    return found


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
    *,
    progress: float = 1.0,
) -> None:
    """Vẽ bảng minh họa co giãn theo nội dung + Badge + VS + Biểu đồ động + Takeaway."""
    if beat.board_type == "none":
        return

    prog = max(0.0, min(1.0, float(progress)))
    x0, y0, x1, max_y1 = box
    bw = x1 - x0
    draw = ImageDraw.Draw(canvas)

    f_badge = _load_font(FONT_EXTRABOLD, 22)
    f_title = _load_font(FONT_EXTRABOLD, 44)
    f_body = _load_font(FONT_BOLD, 34)
    f_sub = _load_font(FONT_MEDIUM, 28)
    f_big = _load_font(FONT_EXTRABOLD, 136)

    vdata: dict[str, Any] = getattr(beat, "visual_data", None) or {}
    data: dict[str, Any] = {**(beat.board_data or {}), **vdata}
    if not data.get("items") and getattr(beat, "board_items", None):
        data["items"] = list(beat.board_items)
    takeaway = str(data.get("takeaway") or "").strip()

    # Ước lượng chiều cao nội dung để bảng co giãn vừa vặn (không thừa khoảng trắng)
    est_h = 92  # top padding + badge
    if beat.board_title:
        _, th = _measure_wrapped_height(draw, beat.board_title, f_title, max(18, bw // 26), 10)
        est_h += th + 14

    if beat.board_type in ("bullets", "list", "card"):
        items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:5]
        for it in items:
            _, ih = _measure_wrapped_height(draw, it, f_body, max(16, (bw - 140) // 21), 10)
            est_h += max(50, ih) + 18
    elif beat.board_type in ("big_number", "counter_grow"):
        est_h += 240
    elif beat.board_type == "quote":
        q_txt = str(data.get("quote") or data.get("text") or beat.narration or "")
        _, qh = _measure_wrapped_height(draw, q_txt, f_body, max(18, (bw - 120) // 22), 12)
        est_h += max(120, qh + 60)
    elif beat.board_type == "comparison":
        left_n = len((data.get("left_items") or [])[:4])
        right_n = len((data.get("right_items") or [])[:4])
        est_h += 76 + max(1, left_n, right_n) * 66
    elif beat.board_type == "bar_compare":
        bars = (data.get("values") or data.get("bars") or [])[:4]
        est_h += max(220, len(bars) * 82 + 40)
    elif beat.board_type == "flow_steps":
        steps = [str(s) for s in (data.get("steps") or data.get("items") or []) if str(s).strip()][:4]
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

    if beat.board_type in ("bullets", "list", "card"):
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

    elif beat.board_type == "quote":
        q_txt = str(data.get("quote") or data.get("text") or beat.narration or "")
        draw.rectangle((x0 + 36, cur_y + 8, x0 + 46, content_bottom - 18), fill=pal["accent"])
        _draw_wrapped_text(
            draw,
            f'"{q_txt}"',
            (x0 + 68, cur_y + 8),
            f_body,
            pal["text"],
            width_chars=max(18, (bw - 110) // 22),
            line_gap=12,
        )

    elif beat.board_type == "counter_grow":
        raw_target = data.get("target", data.get("value", 100))
        try:
            target_num = float(str(raw_target).replace(",", "").replace("%", "").strip())
        except ValueError:
            target_num = 100.0
        unit = str(data.get("unit") or "").strip()
        cur_num = target_num * _ease_in_out(prog)
        if abs(target_num - round(target_num)) < 1e-6:
            num_str = f"{int(round(cur_num)):,}".replace(",", ".")
        else:
            num_str = f"{cur_num:.1f}"
        val_display = f"{num_str} {unit}".strip()
        draw.text((x0 + 44, cur_y + 4), val_display, font=f_big, fill=pal["accent"])
        bbox = draw.textbbox((x0 + 44, cur_y + 4), val_display, font=f_big)
        cur_y = bbox[3] + 22
        lbl = str(data.get("label") or "")
        if lbl:
            _draw_wrapped_text(
                draw, lbl, (x0 + 44, cur_y), f_title, pal["text"], width_chars=max(16, bw // 26)
            )

    elif beat.board_type == "bar_compare":
        raw_bars = data.get("values") or data.get("bars") or []
        bars: list[tuple[str, float]] = []
        for idx, entry in enumerate(raw_bars[:4]):
            if isinstance(entry, dict):
                lbl = str(entry.get("label") or entry.get("name") or f"Mục {idx + 1}")
                try:
                    val = float(entry.get("value") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                bars.append((lbl, max(0.0, val)))
            elif isinstance(entry, (int, float)):
                bars.append((f"Mục {idx + 1}", max(0.0, float(entry))))
        max_val = max((v for _, v in bars), default=1.0) or 1.0
        bar_max_w = max(120, bw - 120)
        eased = _ease_in_out(prog)
        for idx, (lbl, val) in enumerate(bars):
            if cur_y > content_bottom - 64:
                break
            cur_val = val * eased
            fill_w = max(16, int(round((cur_val / max_val) * bar_max_w)))
            bar_color = pal["accent"] if idx % 2 == 0 else pal["amber"]
            draw.text((x0 + 40, cur_y), lbl[:28], font=f_sub, fill=pal["text"])
            val_txt = f"{int(round(cur_val))}" if abs(val - round(val)) < 1e-6 else f"{cur_val:.1f}"
            draw.text((x1 - 120, cur_y), val_txt, font=f_sub, fill=bar_color)
            by = cur_y + 36
            draw.rounded_rectangle(
                (x0 + 40, by, x0 + 40 + bar_max_w, by + 26),
                radius=12,
                fill=pal["pill_bg"],
            )
            draw.rounded_rectangle(
                (x0 + 40, by, x0 + 40 + fill_w, by + 26),
                radius=12,
                fill=bar_color,
            )
            cur_y += 78

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
        steps = [str(s) for s in (data.get("steps") or data.get("items") or []) if str(s).strip()][:4]
        active_count = max(1, int(math.ceil(prog * max(1, len(steps)))))
        for idx, step in enumerate(steps, start=1):
            if cur_y > content_bottom - 60:
                break
            lit = idx <= active_count
            fill_c = pal["pill_bg"] if lit else pal["takeaway_bg"]
            out_c = pal["accent"] if lit else pal["card_border"]
            draw.rounded_rectangle(
                (x0 + 36, cur_y, x1 - 36, cur_y + 74),
                radius=18,
                fill=fill_c,
                outline=out_c,
                width=3 if lit else 2,
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


def _draw_versus_split_layer(
    frame_rgba: Image.Image,
    beat: StickvBeat,
    pal: dict[str, tuple[int, int, int, int]],
    *,
    aspect: StickvAspect,
) -> None:
    w, h = frame_rgba.size
    draw = ImageDraw.Draw(frame_rgba)
    vdata = {**(beat.board_data or {}), **(getattr(beat, "visual_data", None) or {})}
    left_lbl = str(vdata.get("left_label") or vdata.get("left_title") or "Bên A")
    right_lbl = str(vdata.get("right_label") or vdata.get("right_title") or "Bên B")

    top_y = 140 if aspect == "9:16" else 90
    bot_y = int(h * 0.56) if aspect == "9:16" else int(h * 0.72)
    mid_x = w // 2
    draw.rounded_rectangle((36, top_y, mid_x - 16, bot_y), radius=28, fill=(217, 35, 46, 36), outline=(217, 35, 46, 170), width=3)
    draw.rounded_rectangle((mid_x + 16, top_y, w - 36, bot_y), radius=28, fill=(37, 99, 235, 36), outline=(37, 99, 235, 170), width=3)

    f_lbl = _load_font(FONT_EXTRABOLD, 40 if aspect == "9:16" else 36)
    _draw_wrapped_text(draw, left_lbl, (64, top_y + 32), f_lbl, pal["text"], width_chars=14)
    _draw_wrapped_text(draw, right_lbl, (mid_x + 44, top_y + 32), f_lbl, pal["text"], width_chars=14)

    # Huy hiệu VS ở giữa
    draw.ellipse((mid_x - 36, top_y + 18, mid_x + 36, top_y + 90), fill=pal["accent"])
    f_vs = _load_font(FONT_EXTRABOLD, 28)
    draw.text((mid_x - 20, top_y + 38), "VS", font=f_vs, fill=(255, 255, 255, 255))


def _composite_prop_overlay(
    frame_rgba: Image.Image,
    prop_img: Image.Image,
    *,
    aspect: StickvAspect,
    t_sec: float,
    pal: dict[str, tuple[int, int, int, int]],
) -> None:
    w, h = frame_rgba.size
    # Pop-in lò xo trong 0.25s đầu + lơ lửng hình sin ±10px
    pop_p = min(1.0, max(0.0, t_sec / 0.25))
    pop_scale = 1.0 + 0.14 * math.sin(pop_p * math.pi) if pop_p < 1.0 else 1.0
    if pop_p < 0.05:
        pop_scale = 0.2
    target_size = max(120, int((250 if aspect == "9:16" else 240) * pop_scale))
    resized = prop_img.resize((target_size, target_size), Image.Resampling.LANCZOS)

    cx = int(w * (0.68 if aspect == "9:16" else 0.62))
    cy = int(h * (0.44 if aspect == "9:16" else 0.42) + math.sin(t_sec * 3.8) * 10.0)

    draw = ImageDraw.Draw(frame_rgba)
    halo_r = int(target_size * 0.62)
    accent = pal["accent"]
    draw.ellipse(
        (cx - halo_r, cy - halo_r, cx + halo_r, cy + halo_r),
        fill=(accent[0], accent[1], accent[2], 38),
        outline=(accent[0], accent[1], accent[2], 120),
        width=3,
    )
    frame_rgba.alpha_composite(resized, (cx - target_size // 2, cy - target_size // 2))
    resized.close()


def render_animated_beat_frame(
    *,
    bg_img: Image.Image,
    char_img: Image.Image | None,
    beat: StickvBeat,
    aspect: StickvAspect,
    t_sec: float,
    mouth_open: float,
    word_timings: list[tuple[str, float, float]],
    prop_img: Image.Image | None = None,
    domain: str = "paper_classic",
    theme: StickvTheme = "cream",
    duration_sec: float = 2.0,
    draw_board: bool = False,
    extra_dy: float = 0.0,
) -> Image.Image:
    """Tổng hợp 1 khung hình động: backdrop + tương tác 2.5D + prop/biểu đồ + nhân vật + karaoke."""
    frame = bg_img.copy()
    w, h = frame.size
    pal = resolve_stage_palette(domain, theme)
    interaction = getattr(beat, "interaction", "none") or "none"

    frame_rgba = frame.convert("RGBA")
    try:
        if interaction == "versus_split":
            _draw_versus_split_layer(frame_rgba, beat, pal, aspect=aspect)

        if draw_board and beat.board_type != "none":
            anim_dur = max(0.5, float(duration_sec or 2.0) * 0.6)
            prog = min(1.0, max(0.0, t_sec / anim_dur))
            if aspect == "9:16":
                board_box = (60, 150, w - 60, 930)
            else:
                board_box = (int(w * 0.36), 95, w - 60, h - 180)
            _draw_smart_board(frame_rgba, beat, board_box, pal, progress=prog)

        if interaction == "hold_prop" and prop_img is not None:
            _composite_prop_overlay(frame_rgba, prop_img, aspect=aspect, t_sec=t_sec, pal=pal)

        if char_img is not None:
            eff_char = char_img
            if interaction == "point_chart":
                target_h = int(h * 0.38)
                if eff_char.height > target_h:
                    sc = target_h / max(1, eff_char.height)
                    eff_char = eff_char.resize(
                        (max(32, int(round(eff_char.width * sc))), target_h),
                        Image.Resampling.LANCZOS,
                    )
                base_x = int(w * 0.24) - eff_char.width // 2
                base_y = h - eff_char.height - (220 if aspect == "9:16" else 140)
            elif interaction == "hold_prop":
                center_x = int(w * (0.34 if aspect == "9:16" else 0.38))
                base_x = center_x - eff_char.width // 2
                base_y = h - eff_char.height - (220 if aspect == "9:16" else 160)
            elif interaction == "versus_split":
                base_x = (w - eff_char.width) // 2
                base_y = h - eff_char.height - (220 if aspect == "9:16" else 140)
            elif aspect == "9:16":
                base_x = (w - eff_char.width) // 2
                base_y = h - eff_char.height - 220
            else:
                base_x = 90
                base_y = (h - eff_char.height) // 2 + 40

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

            dy += math.sin(t_sec * 4.2) * 3.0 - (mouth_open * 6.0) + extra_dy
            px = int(round(base_x + dx))
            py = int(round(base_y + dy))

            # Bóng đổ mềm dưới chân nhân vật
            shadow_draw = ImageDraw.Draw(frame_rgba)
            sx0 = px + int(eff_char.width * 0.2)
            sx1 = px + int(eff_char.width * 0.8)
            sy0 = base_y + eff_char.height - 26
            sy1 = base_y + eff_char.height + 6
            shadow_draw.ellipse((sx0, sy0, sx1, sy1), fill=(15, 23, 42, 42))

            frame_rgba.alpha_composite(eff_char, (px, py))
            if eff_char is not char_img:
                eff_char.close()

        draw_karaoke_strip(frame_rgba, word_timings, t_sec, aspect=aspect)
        return frame_rgba.convert("RGB")
    finally:
        frame_rgba.close()
        frame.close()


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
