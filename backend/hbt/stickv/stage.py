"""Sân khấu diễn hoạt StickV v6.1: Bảng minh họa co giãn, Karaoke & Lip-sync mượt."""

from __future__ import annotations

import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from hbt.config import REPO_ROOT
from hbt.stickv.backdrops import DOMAIN_PALETTES, normalize_domain
from hbt.stickv.models import (
    STICKV_ASPECT_SIZES,
    StickvAspect,
    StickvBeat,
    StickvCameraShot,
    StickvTheme,
)
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
    "timeline_era": "NIÊN ĐẠI",
    "location_map": "ĐỊA DANH",
    "myth_vs_fact": "GIẢI MÃ",
    "none": "ĐIỂM NHẤN",
}

CAMERA_PRESETS: dict[str, dict[str, tuple[float, float, float]]] = {
    "wide_stage": {"9:16": (1.0, 0.5, 0.5), "16:9": (1.0, 0.5, 0.5)},
    "focus_board": {"9:16": (1.15, 0.5, 0.30), "16:9": (1.15, 0.65, 0.44)},
    "closeup_react": {"9:16": (1.28, 0.5, 0.72), "16:9": (1.28, 0.24, 0.56)},
}

_AUTO_ICON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("kim tự tháp", "ai cập", "pharaoh", "lăng mộ", "cổ đại"), "pyramid"),
    (("bản đồ", "địa điểm", "vị trí", "hải trình", "vùng đất", "lục địa"), "compass"),
    (("năm", "thế kỷ", "tcn", "triệu năm", "thời gian", "niên đại"), "hourglass"),
    (("não", "tư duy", "tâm lý", "ký ức", "suy nghĩ"), "brain"),
    (("vũ trụ", "sao", "thiên hà", "hố đen", "hành tinh", "mặt trời"), "planet"),
    (("nguyên tử", "năng lượng", "điện", "ánh sáng", "sóng", "vật lý"), "atom"),
    (("di truyền", "adn", "tế bào", "sinh học", "tiến hóa"), "dna"),
    (("bí ẩn", "bí mật", "nghi vấn", "giả thuyết"), "magnifying-glass"),
    (("lịch sử", "cổ thư", "ghi chép", "văn tự", "sử sách"), "scroll"),
)


def infer_auto_prop_query(narration: str) -> str:
    """Trích xuất từ khóa icon tiếng Anh tự động cho Iconify khi beat không có `prop_query`."""
    low = (narration or "").strip().lower()
    for keywords, icon_q in _AUTO_ICON_RULES:
        if any(kw in low for kw in keywords):
            return icon_q
    return "lightbulb"


def _extract_highlight_keyword(narration: str) -> str:
    """Rút cụm từ khóa/con số nổi bật nhất từ câu thoại cho Thẻ Minh Họa Tự Động."""
    clean = re.sub(r"\s+", " ", (narration or "").strip())
    if not clean:
        return "Điểm mấu chốt"
    num_match = re.search(
        r"(\d[\d.,]*\s*(?:%|năm|tcn|triệu|tỷ|nghìn|km|mét|giờ|phút)?)", clean, re.I
    )
    if num_match and len(num_match.group(1).strip()) >= 2:
        words = clean.split()
        return " ".join(words[: min(6, len(words))]).rstrip(".,;:!?")
    clauses = [c.strip() for c in re.split(r"[,.;:!?…]", clean) if c.strip()]
    head = clauses[0] if clauses else clean
    words = head.split()
    return (" ".join(words[:6]) + ("…" if len(words) > 6 else "")).strip()


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


def _ease_out_cubic(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return 1.0 - (1.0 - u) ** 3


def _ease_in_cubic(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return u * u * u


def _draw_smart_board_content(
    canvas: Image.Image,
    beat: StickvBeat,
    box: tuple[int, int, int, int],
    pal: dict[str, tuple[int, int, int, int]],
    *,
    progress: float = 1.0,
    prop_img: Image.Image | None = None,
    total_chapters: int = 1,
    draw_shell: bool = True,
    content_alpha: float = 1.0,
) -> tuple[int, int, int, int]:
    """Vẽ bảng minh họa 100% beat (kể cả thẻ tự động khi `board_type='none'` & 3 mẫu lịch sử)."""
    prog = max(0.0, min(1.0, float(progress)))
    x0, y0, x1, max_y1 = box
    bw = x1 - x0

    f_badge = _load_font(FONT_EXTRABOLD, 22)
    f_title = _load_font(FONT_EXTRABOLD, 42)
    f_body = _load_font(FONT_BOLD, 32)
    f_sub = _load_font(FONT_MEDIUM, 26)
    f_big = _load_font(FONT_EXTRABOLD, 128)

    vdata: dict[str, Any] = getattr(beat, "visual_data", None) or {}
    data: dict[str, Any] = {**(beat.board_data or {}), **vdata}
    if not data.get("items") and getattr(beat, "board_items", None):
        data["items"] = list(beat.board_items)
    takeaway = str(data.get("takeaway") or "").strip()

    tmp_draw = ImageDraw.Draw(canvas)
    est_h = 92
    eff_title = beat.board_title or (
        _extract_highlight_keyword(beat.narration) if beat.board_type == "none" else ""
    )
    if eff_title:
        _, th = _measure_wrapped_height(tmp_draw, eff_title, f_title, max(18, bw // 26), 10)
        est_h += th + 14

    if beat.board_type == "none":
        est_h += 220
    elif beat.board_type in ("bullets", "list", "card"):
        items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:5]
        for it in items:
            _, ih = _measure_wrapped_height(tmp_draw, it, f_body, max(16, (bw - 140) // 21), 10)
            est_h += max(50, ih) + 18
    elif beat.board_type in ("big_number", "counter_grow"):
        est_h += 240
    elif beat.board_type == "quote":
        q_txt = str(data.get("quote") or data.get("text") or beat.narration or "")
        _, qh = _measure_wrapped_height(tmp_draw, q_txt, f_body, max(18, (bw - 120) // 22), 12)
        est_h += max(120, qh + 60)
    elif beat.board_type == "comparison":
        left_n = len((data.get("left_items") or [])[:4])
        right_n = len((data.get("right_items") or [])[:4])
        est_h += 76 + max(1, left_n, right_n) * 66
    elif beat.board_type == "bar_compare":
        bars = (data.get("values") or data.get("bars") or [])[:4]
        est_h += max(220, len(bars) * 82 + 40)
    elif beat.board_type == "flow_steps":
        steps = [str(s) for s in (data.get("steps") or data.get("items") or []) if str(s).strip()][
            :4
        ]
        est_h += len(steps) * 96
    elif beat.board_type == "timeline_era":
        ev_count = max(2, len((data.get("events") or data.get("items") or [])[:4]))
        est_h += ev_count * 84 + 24
    elif beat.board_type == "location_map":
        est_h += 250
    elif beat.board_type == "myth_vs_fact":
        est_h += 270

    if takeaway:
        est_h += 86

    card_h = min(max_y1 - y0, max(280, est_h + 36))
    y1 = y0 + card_h

    if draw_shell:
        shell_draw = ImageDraw.Draw(canvas)
        shell_draw.rounded_rectangle(
            (x0 + 6, y0 + 10, x1 + 6, y1 + 10), radius=34, fill=(15, 23, 42, 28)
        )
        shell_draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=34,
            fill=pal["card"],
            outline=pal["card_border"],
            width=3,
        )

        # Badge phân loại góc trên trái + chỉ báo Chương
        badge_txt = BOARD_BADGES.get(beat.board_type, "NỔI BẬT")
        bb = shell_draw.textbbox((0, 0), badge_txt, font=f_badge)
        badge_w = (bb[2] - bb[0]) + 32
        shell_draw.rounded_rectangle(
            (x0 + 32, y0 + 24, x0 + 32 + badge_w, y0 + 62),
            radius=999,
            fill=pal["accent"],
        )
        shell_draw.text((x0 + 48, y0 + 30), badge_txt, font=f_badge, fill=(255, 255, 255, 255))

        chap_txt = f"CHƯƠNG {beat.chapter}"
        cbb = shell_draw.textbbox((0, 0), chap_txt, font=f_badge)
        cw_pill = (cbb[2] - cbb[0]) + 28
        shell_draw.rounded_rectangle(
            (x1 - 32 - cw_pill, y0 + 24, x1 - 32, y0 + 62),
            radius=999,
            fill=pal["pill_bg"],
        )
        shell_draw.text((x1 - 18 - cw_pill, y0 + 30), chap_txt, font=f_badge, fill=pal["pill_text"])

    inner_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0)) if content_alpha < 0.999 else canvas
    try:
        draw = ImageDraw.Draw(inner_layer)
        cur_y = y0 + 82
        if eff_title:
            cur_y = _draw_wrapped_text(
                draw,
                eff_title,
                (x0 + 36, cur_y),
                f_title,
                pal["text"],
                width_chars=max(18, bw // 26),
                line_gap=10,
            )
            cur_y += 14

        content_bottom = y1 - (94 if takeaway else 28)

        if beat.board_type == "none":
            # Thẻ Minh Họa Tự Động (Icon màu Iconify/Vector + câu nhấn + thanh tiến trình chương)
            icon_box_size = 112
            ix0, iy0 = x0 + 38, cur_y + 4
            draw.rounded_rectangle(
                (ix0, iy0, ix0 + icon_box_size, iy0 + icon_box_size),
                radius=24,
                fill=pal["pill_bg"],
                outline=pal["accent"],
                width=2,
            )
            if prop_img is not None:
                icon_fit = prop_img.copy()
                icon_fit.thumbnail(
                    (icon_box_size - 20, icon_box_size - 20), Image.Resampling.LANCZOS
                )
                inner_layer.alpha_composite(
                    icon_fit,
                    (
                        ix0 + (icon_box_size - icon_fit.width) // 2,
                        iy0 + (icon_box_size - icon_fit.height) // 2,
                    ),
                )
                icon_fit.close()
            else:
                # Vẽ huy hiệu la bàn/tia sáng vector rõ nét
                cx_i, cy_i = ix0 + icon_box_size // 2, iy0 + icon_box_size // 2
                draw.ellipse(
                    (cx_i - 28, cy_i - 28, cx_i + 28, cy_i + 28), outline=pal["accent"], width=4
                )
                draw.polygon(
                    [
                        (cx_i, cy_i - 22),
                        (cx_i + 12, cy_i + 4),
                        (cx_i, cy_i + 22),
                        (cx_i - 12, cy_i + 4),
                    ],
                    fill=pal["amber"],
                )
            text_x = ix0 + icon_box_size + 26
            snippet = (beat.narration or "").strip()
            _draw_wrapped_text(
                draw,
                snippet,
                (text_x, iy0 + 4),
                f_body,
                pal["text"],
                width_chars=max(14, (x1 - text_x - 36) // 20),
                line_gap=10,
            )
            # Thanh tiến trình chương ở đáy thẻ
            bar_y = max(iy0 + icon_box_size + 22, content_bottom - 26)
            bar_w = max(80, bw - 76)
            ratio = max(0.12, min(1.0, float(beat.chapter) / max(1, total_chapters)))
            draw.rounded_rectangle(
                (x0 + 38, bar_y, x0 + 38 + bar_w, bar_y + 12),
                radius=6,
                fill=pal["pill_bg"],
            )
            draw.rounded_rectangle(
                (x0 + 38, bar_y, x0 + 38 + int(bar_w * ratio), bar_y + 12),
                radius=6,
                fill=pal["accent"],
            )

        elif beat.board_type in ("bullets", "list", "card"):
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
                val_txt = (
                    f"{int(round(cur_val))}" if abs(val - round(val)) < 1e-6 else f"{cur_val:.1f}"
                )
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
                    draw,
                    sub,
                    (x0 + 44, cur_y + 6),
                    f_sub,
                    pal["muted"],
                    width_chars=max(20, bw // 19),
                )

        elif beat.board_type == "comparison":
            mid_x = (x0 + x1) // 2
            draw.line(
                [(mid_x, cur_y + 12), (mid_x, content_bottom - 12)],
                fill=pal["card_border"],
                width=3,
            )
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
                        draw,
                        f"✓ {item}",
                        (mid_x + 42, ry),
                        f_sub,
                        pal["text"],
                        width_chars=col_chars,
                    )
                    + 10
                )

        elif beat.board_type == "flow_steps":
            steps = [
                str(s) for s in (data.get("steps") or data.get("items") or []) if str(s).strip()
            ][:4]
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
                    (x0 + 56, cur_y + 18),
                    f"{idx}. {step[:40]}",
                    font=f_body,
                    fill=pal["pill_text"],
                )
                cur_y += 94

        elif beat.board_type == "timeline_era":
            raw_ev = data.get("events") or data.get("items") or []
            events: list[tuple[str, str]] = []
            for idx, ev in enumerate(raw_ev[:4]):
                if isinstance(ev, dict):
                    events.append(
                        (
                            str(ev.get("year") or ev.get("era") or f"Mốc {idx + 1}"),
                            str(ev.get("title") or ev.get("label") or ev.get("text") or ""),
                        )
                    )
                else:
                    s = str(ev)
                    if ":" in s:
                        yr, tt = s.split(":", 1)
                        events.append((yr.strip(), tt.strip()))
                    else:
                        events.append((f"Mốc {idx + 1}", s))
            if not events:
                events = [("Cổ đại", _extract_highlight_keyword(beat.narration))]
            spine_x = x0 + 62
            end_y = min(content_bottom - 18, cur_y + len(events) * 80 - 20)
            draw.line([(spine_x, cur_y + 18), (spine_x, end_y)], fill=pal["amber"], width=5)
            lit_n = max(1, int(math.ceil(prog * len(events))))
            for idx, (era_lbl, ev_txt) in enumerate(events, start=1):
                if cur_y > content_bottom - 52:
                    break
                lit = idx <= lit_n
                node_fill = pal["accent"] if lit else pal["pill_bg"]
                draw.ellipse(
                    (spine_x - 12, cur_y + 10, spine_x + 12, cur_y + 34),
                    fill=node_fill,
                    outline=pal["amber"],
                    width=3,
                )
                draw.text((spine_x + 28, cur_y + 2), era_lbl[:22], font=f_badge, fill=pal["accent"])
                _draw_wrapped_text(
                    draw,
                    ev_txt[:68],
                    (spine_x + 28, cur_y + 30),
                    f_sub,
                    pal["text"],
                    width_chars=max(14, (bw - 150) // 17),
                )
                cur_y += 80

        elif beat.board_type == "location_map":
            loc_name = str(
                data.get("location") or data.get("place") or eff_title or "Di tích cổ đại"
            )
            coords = str(data.get("coordinates") or data.get("region") or "29.9792° N, 31.1342° E")
            map_x0, map_y0, map_x1, map_y1 = x0 + 36, cur_y + 4, x1 - 36, content_bottom - 10
            draw.rounded_rectangle(
                (map_x0, map_y0, map_x1, map_y1),
                radius=22,
                fill=pal["takeaway_bg"],
                outline=pal["amber"],
                width=2,
            )
            # Lưới tọa độ bản đồ + điểm ghim địa danh
            for gx in range(map_x0 + 48, map_x1, 72):
                draw.line([(gx, map_y0 + 10), (gx, map_y1 - 10)], fill=pal["card_border"], width=1)
            for gy in range(map_y0 + 42, map_y1, 56):
                draw.line([(map_x0 + 10, gy), (map_x1 - 10, gy)], fill=pal["card_border"], width=1)
            pin_x = (map_x0 + map_x1) // 2
            pin_y = (map_y0 + map_y1) // 2 - 14
            pulse_r = int(20 + 10 * abs(math.sin(prog * math.pi * 2.0)))
            draw.ellipse(
                (pin_x - pulse_r, pin_y - pulse_r, pin_x + pulse_r, pin_y + pulse_r),
                outline=pal["accent"],
                width=3,
            )
            draw.ellipse((pin_x - 10, pin_y - 10, pin_x + 10, pin_y + 10), fill=pal["accent"])
            draw.text((map_x0 + 20, map_y0 + 14), loc_name[:36], font=f_body, fill=pal["text"])
            draw.text((map_x0 + 20, map_y1 - 40), coords[:40], font=f_badge, fill=pal["pill_text"])

        elif beat.board_type == "myth_vs_fact":
            myth_txt = str(data.get("myth") or data.get("left") or "Lầm tưởng phổ biến")
            fact_txt = str(
                data.get("fact") or data.get("right") or beat.narration or "Sự thật lịch sử"
            )
            half_h = max(92, (content_bottom - cur_y - 18) // 2)
            # Tầng LẦM TƯỞNG
            draw.rounded_rectangle(
                (x0 + 36, cur_y, x1 - 36, cur_y + half_h),
                radius=18,
                fill=(254, 226, 226, 230),
                outline=(220, 38, 38, 255),
                width=2,
            )
            draw.text((x0 + 54, cur_y + 12), "✕ LẦM TƯỞNG", font=f_badge, fill=(185, 28, 28, 255))
            _draw_wrapped_text(
                draw,
                myth_txt[:85],
                (x0 + 54, cur_y + 42),
                f_sub,
                (69, 10, 10, 255),
                width_chars=max(16, (bw - 120) // 17),
            )
            # Tầng SỰ THẬT
            fy0 = cur_y + half_h + 14
            draw.rounded_rectangle(
                (x0 + 36, fy0, x1 - 36, fy0 + half_h),
                radius=18,
                fill=(209, 250, 229, 235),
                outline=(5, 150, 105, 255),
                width=2,
            )
            draw.text((x0 + 54, fy0 + 12), "✓ SỰ THẬT", font=f_badge, fill=(4, 120, 87, 255))
            _draw_wrapped_text(
                draw,
                fact_txt[:85],
                (x0 + 54, fy0 + 42),
                f_sub,
                (6, 78, 59, 255),
                width_chars=max(16, (bw - 120) // 17),
            )

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
                (x0 + 46, ty0 + 14),
                f"Chốt lại: {takeaway[:54]}",
                font=f_sub,
                fill=pal["pill_text"],
            )

        if inner_layer is not canvas:
            a_band = inner_layer.getchannel("A").point(
                lambda p: int(round(p * max(0.0, min(1.0, content_alpha))))
            )
            inner_layer.putalpha(a_band)
            canvas.alpha_composite(inner_layer)
    finally:
        if inner_layer is not canvas:
            inner_layer.close()
    return x0, y0, x1, y1


def _draw_smart_board(
    canvas: Image.Image,
    beat: StickvBeat,
    box: tuple[int, int, int, int],
    pal: dict[str, tuple[int, int, int, int]],
    *,
    progress: float = 1.0,
    prop_img: Image.Image | None = None,
) -> None:
    _draw_smart_board_content(canvas, beat, box, pal, progress=progress, prop_img=prop_img)


def _composite_transitioned_board(
    frame_rgba: Image.Image,
    beat: StickvBeat,
    box: tuple[int, int, int, int],
    pal: dict[str, tuple[int, int, int, int]],
    *,
    t_sec: float,
    duration_sec: float,
    progress: float,
    prop_img: Image.Image | None = None,
    prev_stage_state: BeatStageState | None = None,
    total_chapters: int = 1,
    has_next_diff_title: bool = True,
) -> None:
    """Chuyển tiếp thẻ không hard-cut: slide+scale+fade (0.35s vào / 0.30s ra) hoặc cross-fade."""
    cur_title = (beat.board_title or "").strip()
    same_title = (
        prev_stage_state is not None
        and bool(cur_title)
        and cur_title == (getattr(prev_stage_state, "last_board_title", "") or "").strip()
    )

    if same_title:
        c_alpha = _ease_out_cubic(min(1.0, t_sec / 0.25)) if t_sec < 0.25 else 1.0
        _draw_smart_board_content(
            frame_rgba,
            beat,
            box,
            pal,
            progress=progress,
            prop_img=prop_img,
            total_chapters=total_chapters,
            draw_shell=True,
            content_alpha=c_alpha,
        )
        return

    enter_t = 0.35
    exit_t = 0.30
    scale = 1.0
    dy_px = 0.0
    alpha = 1.0
    if t_sec < enter_t:
        u = _ease_out_cubic(t_sec / enter_t)
        scale = 0.94 + 0.06 * u
        dy_px = 28.0 * (1.0 - u)
        alpha = u
    elif (
        has_next_diff_title
        and duration_sec > (enter_t + exit_t)
        and t_sec > (duration_sec - exit_t)
    ):
        u = _ease_in_cubic((t_sec - (duration_sec - exit_t)) / exit_t)
        dy_px = -18.0 * u
        alpha = 1.0 - u

    if abs(scale - 1.0) < 0.004 and abs(dy_px) < 0.5 and alpha > 0.995:
        _draw_smart_board_content(
            frame_rgba,
            beat,
            box,
            pal,
            progress=progress,
            prop_img=prop_img,
            total_chapters=total_chapters,
        )
        return

    layer = Image.new("RGBA", frame_rgba.size, (0, 0, 0, 0))
    try:
        bx0, by0, bx1, by1 = _draw_smart_board_content(
            layer,
            beat,
            box,
            pal,
            progress=progress,
            prop_img=prop_img,
            total_chapters=total_chapters,
        )
        pad = 16
        cx0 = max(0, bx0 - pad)
        cy0 = max(0, by0 - pad)
        cx1 = min(layer.width, bx1 + pad)
        cy1 = min(layer.height, by1 + pad)
        sub = layer.crop((cx0, cy0, cx1, cy1))
        try:
            if abs(scale - 1.0) >= 0.004:
                nw = max(8, int(round(sub.width * scale)))
                nh = max(8, int(round(sub.height * scale)))
                scaled = sub.resize((nw, nh), Image.Resampling.BICUBIC)
            else:
                scaled = sub.copy()
            try:
                if alpha < 0.995:
                    a_band = scaled.getchannel("A").point(
                        lambda p: int(round(p * max(0.0, min(1.0, alpha))))
                    )
                    scaled.putalpha(a_band)
                dest_x = cx0 + (sub.width - scaled.width) // 2
                dest_y = cy0 + (sub.height - scaled.height) // 2 + int(round(dy_px))
                frame_rgba.alpha_composite(scaled, (dest_x, dest_y))
            finally:
                scaled.close()
        finally:
            sub.close()
    finally:
        layer.close()


def draw_karaoke_strip(
    frame: Image.Image,
    word_timings: list[tuple[str, float, float]],
    t_sec: float,
    *,
    aspect: StickvAspect,
    spoken_segments: list[tuple[float, float, str]] | None = None,
) -> None:
    """Vẽ dải phụ đề Karaoke khóa trong câu đang nói (ổn định nền qua ngắt <=0.22s)."""
    if not word_timings:
        return

    filtered_timings = word_timings
    micro_gap_hold = False
    if spoken_segments:
        active_seg: tuple[float, float, str] | None = None
        for st, et, txt in spoken_segments:
            if st <= t_sec <= et:
                active_seg = (st, et, txt)
                break
        if active_seg is None:
            # Kiểm tra khoảng ngắt hơi ngắn (<= 0.22s) giữa 2 câu để giữ ổn định nền mờ
            for idx in range(len(spoken_segments) - 1):
                g_start = spoken_segments[idx][1]
                g_end = spoken_segments[idx + 1][0]
                if g_start < t_sec < g_end and (g_end - g_start) <= 0.22:
                    micro_gap_hold = True
                    break
            if not micro_gap_hold:
                return
        else:
            seg_st, seg_et, _ = active_seg
            seg_words = [
                (wd, wst, wet)
                for (wd, wst, wet) in word_timings
                if wst >= (seg_st - 0.01) and wet <= (seg_et + 0.01)
            ]
            if seg_words:
                filtered_timings = seg_words

    w, h = frame.size
    draw = ImageDraw.Draw(frame)
    base_y = 970 if aspect == "9:16" else int(h * 0.86)
    if micro_gap_hold:
        strip_w = min(w - 120, 620 if aspect == "9:16" else 880)
        sx0 = (w - strip_w) // 2
        draw.rounded_rectangle(
            (sx0, base_y - 10, sx0 + strip_w, base_y + 56),
            radius=18,
            fill=(15, 23, 42, 130),
        )
        return

    active_idx = 0
    for idx, (_w, st, et) in enumerate(filtered_timings):
        if st <= t_sec <= et:
            active_idx = idx
            break
        if t_sec > et:
            active_idx = idx

    win_size = 5 if aspect == "9:16" else 7
    chunk_idx = active_idx // win_size
    chunk = filtered_timings[chunk_idx * win_size : (chunk_idx + 1) * win_size]
    if not chunk:
        return

    font = _load_font(FONT_EXTRABOLD, 42 if aspect == "9:16" else 38)
    space_w = 14
    widths: list[int] = []
    for word, _, _ in chunk:
        bb = draw.textbbox((0, 0), word, font=font)
        widths.append(bb[2] - bb[0])
    total_w = sum(widths) + space_w * max(0, len(chunk) - 1)

    cur_x = (w - total_w) // 2
    draw.rounded_rectangle(
        (max(24, cur_x - 22), base_y - 10, min(w - 24, cur_x + total_w + 22), base_y + 56),
        radius=18,
        fill=(15, 23, 42, 130),
    )

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
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class BeatStageState:
    """Trạng thái cuối beat (vị trí nhân vật, camera, tiêu đề thẻ, chương) để nối mượt."""

    x: float
    y: float
    scale: float = 1.0
    pose_state: Any = None
    camera_zoom: float = 1.0
    camera_pan_x: float = 0.5
    camera_pan_y: float = 0.5
    last_board_title: str = ""
    last_board_type: str = ""
    last_chapter: int = 1


def compute_camera_state(
    camera_shot: StickvCameraShot | str,
    *,
    aspect: StickvAspect,
    t_sec: float,
    prev_stage_state: BeatStageState | None = None,
    transition_dur: float = 0.55,
) -> tuple[float, float, float]:
    """Nội suy `(zoom, pan_x, pan_y)` mượt trong 0.55s theo `camera_shot` và `aspect`."""
    shot_key = (camera_shot or "wide_stage").strip().lower()
    preset_map = CAMERA_PRESETS.get(shot_key, CAMERA_PRESETS["wide_stage"])
    tz, tx, ty = preset_map.get(aspect, (1.0, 0.5, 0.5))
    if prev_stage_state is None or transition_dur <= 0 or t_sec >= transition_dur:
        return tz, tx, ty
    p = _ease_in_out(t_sec / transition_dur)
    pz = getattr(prev_stage_state, "camera_zoom", 1.0)
    px = getattr(prev_stage_state, "camera_pan_x", 0.5)
    py = getattr(prev_stage_state, "camera_pan_y", 0.5)
    return pz + (tz - pz) * p, px + (tx - px) * p, py + (ty - py) * p


def _apply_virtual_camera(
    frame_rgba: Image.Image,
    zoom: float,
    pan_x: float,
    pan_y: float,
) -> Image.Image:
    if zoom <= 1.002:
        return frame_rgba
    w, h = frame_rgba.size
    cw = max(16.0, w / zoom)
    ch = max(16.0, h / zoom)
    cx0 = max(0.0, min(float(w) - cw, pan_x * w - cw * 0.5))
    cy0 = max(0.0, min(float(h) - ch, pan_y * h - ch * 0.5))
    return frame_rgba.transform(
        (w, h),
        Image.Transform.EXTENT,
        (cx0, cy0, cx0 + cw, cy0 + ch),
        resample=Image.Resampling.BICUBIC,
    )


def _draw_chapter_banner(
    frame_rgba: Image.Image,
    *,
    chapter: int,
    chapter_title: str,
    t_sec: float,
    pal: dict[str, tuple[int, int, int, int]],
    aspect: StickvAspect,
) -> None:
    """Hiển thị dải băng `CHƯƠNG X: ...` trượt mượt trong 2.8s đầu chương mới."""
    title = (chapter_title or "").strip()
    if not title or t_sec > 2.8:
        return
    if t_sec < 0.35:
        u = _ease_out_cubic(t_sec / 0.35)
    elif t_sec > 2.40:
        u = 1.0 - _ease_in_cubic((t_sec - 2.40) / 0.40)
    else:
        u = 1.0
    if u <= 0.02:
        return

    w, _h = frame_rgba.size
    f_chap = _load_font(FONT_EXTRABOLD, 26 if aspect == "9:16" else 28)
    label = f"CHƯƠNG {chapter}: {title[:44]}"
    tmp = ImageDraw.Draw(frame_rgba)
    bb = tmp.textbbox((0, 0), label, font=f_chap)
    tw = bb[2] - bb[0]
    pill_w = min(w - 80, tw + 48)
    base_x = 42 if aspect == "16:9" else (w - pill_w) // 2
    slide_y = int(round(-44 + (84 * u))) if aspect == "9:16" else int(round(-40 + (72 * u)))

    banner = Image.new("RGBA", frame_rgba.size, (0, 0, 0, 0))
    try:
        d = ImageDraw.Draw(banner)
        d.rounded_rectangle(
            (base_x, slide_y, base_x + pill_w, slide_y + 50),
            radius=999,
            fill=pal["accent"],
            outline=pal["amber"],
            width=2,
        )
        d.text((base_x + 24, slide_y + 11), label, font=f_chap, fill=(255, 255, 255, 255))
        if u < 0.99:
            a_band = banner.getchannel("A").point(lambda p: int(round(p * u)))
            banner.putalpha(a_band)
        frame_rgba.alpha_composite(banner)
    finally:
        banner.close()


def compute_beat_character_target(
    w: int,
    h: int,
    char_w: int,
    char_h: int,
    *,
    interaction: str,
    aspect: StickvAspect,
) -> tuple[float, float, float]:
    """Tính tọa độ `(target_x, target_y, target_scale)` chuẩn theo interaction và aspect."""
    scale = 1.0
    if interaction == "point_chart":
        target_h = int(h * (0.38 if aspect == "9:16" else 0.56))
        if char_h > target_h and char_h > 0:
            scale = target_h / char_h
        eff_w = char_w * scale
        eff_h = char_h * scale
        bx = w * (0.24 if aspect == "9:16" else 0.22) - eff_w * 0.5
        by = (h - eff_h - 220) if aspect == "9:16" else (h * 0.84 - eff_h)
        return bx, by, scale
    if interaction == "hold_prop":
        center_x = w * (0.34 if aspect == "9:16" else 0.24)
        bx = center_x - char_w * 0.5
        by = (h - char_h - 220) if aspect == "9:16" else (h * 0.84 - char_h)
        return bx, by, scale
    if interaction == "versus_split":
        bx = (w - char_w) * 0.5
        by = (h - char_h - 220) if aspect == "9:16" else (h * 0.84 - char_h)
        return bx, by, scale
    if aspect == "9:16":
        return (w - char_w) * 0.5, float(h - char_h - 220), scale
    # 16:9 YouTube Khám phá dài: Stickman đứng bên trái (x: 22%, đáy y: 84%, cao 64%)
    target_h = int(h * 0.64)
    if char_h > 0 and abs(char_h - target_h) > 16:
        scale = target_h / char_h
    eff_w = char_w * scale
    eff_h = char_h * scale
    return w * 0.22 - eff_w * 0.5, h * 0.84 - eff_h, scale


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
    draw.rounded_rectangle(
        (36, top_y, mid_x - 16, bot_y),
        radius=28,
        fill=(217, 35, 46, 36),
        outline=(217, 35, 46, 170),
        width=3,
    )
    draw.rounded_rectangle(
        (mid_x + 16, top_y, w - 36, bot_y),
        radius=28,
        fill=(37, 99, 235, 36),
        outline=(37, 99, 235, 170),
        width=3,
    )

    f_lbl = _load_font(FONT_EXTRABOLD, 40 if aspect == "9:16" else 36)
    _draw_wrapped_text(draw, left_lbl, (64, top_y + 32), f_lbl, pal["text"], width_chars=14)
    _draw_wrapped_text(
        draw, right_lbl, (mid_x + 44, top_y + 32), f_lbl, pal["text"], width_chars=14
    )

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
    pop_p = min(1.0, max(0.0, t_sec / 0.25))
    pop_scale = 1.0 + 0.14 * math.sin(pop_p * math.pi) if pop_p < 1.0 else 1.0
    if pop_p < 0.05:
        pop_scale = 0.2
    target_size = max(120, int((250 if aspect == "9:16" else 240) * pop_scale))
    resized = prop_img.resize((target_size, target_size), Image.Resampling.LANCZOS)

    cx = int(w * (0.68 if aspect == "9:16" else 0.36))
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
    prev_stage_state: BeatStageState | None = None,
    tween_dur: float = 0.40,
    spoken_segments: list[tuple[float, float, str]] | None = None,
    is_puppet: bool = False,
    total_chapters: int = 1,
    has_next_diff_title: bool = True,
    show_chapter_banner: bool = False,
) -> Image.Image:
    """Tổng hợp 1 frame động: backdrop + thẻ không hard-cut + puppet + camera ảo + karaoke."""
    frame = bg_img.copy()
    w, h = frame.size
    pal = resolve_stage_palette(domain, theme)
    interaction = getattr(beat, "interaction", "none") or "none"

    frame_rgba = frame.convert("RGBA")
    try:
        if interaction == "versus_split":
            _draw_versus_split_layer(frame_rgba, beat, pal, aspect=aspect)

        if draw_board:
            anim_dur = max(0.5, float(duration_sec or 2.0) * 0.6)
            prog = min(1.0, max(0.0, t_sec / anim_dur))
            if aspect == "9:16":
                board_box = (60, int(h * 0.09), w - 60, int(h * 0.51))
            else:
                board_box = (int(w * 0.38), int(h * 0.12), int(w * 0.94), int(h * 0.76))
            _composite_transitioned_board(
                frame_rgba,
                beat,
                board_box,
                pal,
                t_sec=t_sec,
                duration_sec=duration_sec,
                progress=prog,
                prop_img=prop_img,
                prev_stage_state=prev_stage_state,
                total_chapters=total_chapters,
                has_next_diff_title=has_next_diff_title,
            )

        if interaction == "hold_prop" and prop_img is not None:
            _composite_prop_overlay(frame_rgba, prop_img, aspect=aspect, t_sec=t_sec, pal=pal)

        if char_img is not None:
            target_x, target_y, target_scale = compute_beat_character_target(
                w,
                h,
                char_img.width,
                char_img.height,
                interaction=interaction,
                aspect=aspect,
            )
            if prev_stage_state is not None and tween_dur > 0 and t_sec < tween_dur:
                p = _ease_in_out(t_sec / tween_dur)
                base_x = prev_stage_state.x + (target_x - prev_stage_state.x) * p
                base_y = prev_stage_state.y + (target_y - prev_stage_state.y) * p
                cur_scale = prev_stage_state.scale + (target_scale - prev_stage_state.scale) * p
            else:
                base_x, base_y, cur_scale = target_x, target_y, target_scale

            eff_char = char_img
            if abs(cur_scale - 1.0) > 0.01:
                nw = max(32, int(round(char_img.width * cur_scale)))
                nh = max(32, int(round(char_img.height * cur_scale)))
                eff_char = char_img.resize((nw, nh), Image.Resampling.LANCZOS)

            dx, dy = 0.0, 0.0
            if beat.motion == "slide_left" and prev_stage_state is None:
                p = _ease_in_out(min(1.0, t_sec / 0.35))
                dx = (1.0 - p) * (w * 0.45)
            elif beat.motion == "slide_right" and prev_stage_state is None:
                p = _ease_in_out(min(1.0, t_sec / 0.35))
                dx = -(1.0 - p) * (w * 0.45)
            elif not is_puppet:
                if beat.motion in ("float", "shake"):
                    dy = math.sin(t_sec * 3.0) * 10.0
                elif beat.motion == "bounce":
                    dy = -abs(math.sin(t_sec * 6.0)) * 14.0
                dy += math.sin(t_sec * 4.2) * 3.0 - (mouth_open * 6.0) + extra_dy

            px = int(round(base_x + dx))
            py = int(round(base_y + dy))

            shadow_draw = ImageDraw.Draw(frame_rgba)
            sx0 = px + int(eff_char.width * 0.2)
            sx1 = px + int(eff_char.width * 0.8)
            sy0 = int(round(base_y)) + eff_char.height - 26
            sy1 = int(round(base_y)) + eff_char.height + 6
            shadow_draw.ellipse((sx0, sy0, sx1, sy1), fill=(15, 23, 42, 42))

            frame_rgba.alpha_composite(eff_char, (px, py))
            if eff_char is not char_img:
                eff_char.close()

        # Áp dụng góc máy ảo (virtual camera) lên sân khấu trước khi vẽ Karaoke & Banner
        cam_zoom, cam_px, cam_py = compute_camera_state(
            getattr(beat, "camera_shot", "wide_stage"),
            aspect=aspect,
            t_sec=t_sec,
            prev_stage_state=prev_stage_state,
        )
        cam_frame = _apply_virtual_camera(frame_rgba, cam_zoom, cam_px, cam_py)
        try:
            if show_chapter_banner and getattr(beat, "chapter_title", ""):
                _draw_chapter_banner(
                    cam_frame,
                    chapter=beat.chapter,
                    chapter_title=beat.chapter_title,
                    t_sec=t_sec,
                    pal=pal,
                    aspect=aspect,
                )
            draw_karaoke_strip(
                cam_frame,
                word_timings,
                t_sec,
                aspect=aspect,
                spoken_segments=spoken_segments,
            )
            return cam_frame.convert("RGB")
        finally:
            if cam_frame is not frame_rgba:
                cam_frame.close()
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
    domain: str = "paper_classic",
) -> tuple[Path, Path | None]:
    """Vẽ lớp nền + bảng minh họa (`bg.png`) và nhân vật (`char.png`), giải phóng RAM ngay."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    w, h = STICKV_ASPECT_SIZES[aspect]
    pal = resolve_stage_palette(domain, theme)

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
