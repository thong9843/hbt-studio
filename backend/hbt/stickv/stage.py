"""Sân khấu diễn hoạt StickV v6.1: Bảng minh họa co giãn, Karaoke & Lip-sync mượt."""

from __future__ import annotations

import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from hbt.config import REPO_ROOT
from hbt.shared.pillow_utils import load_cached_font
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
    "bullets": "PHÂN TÍCH",
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
    "recap_card": "TÓM TẮT",
    "pinned_photo": "ẢNH TƯ LIỆU",
    "none": "PHÂN TÍCH",
}

CAMERA_PRESETS: dict[str, dict[str, tuple[float, float, float]]] = {
    "wide_stage": {"9:16": (1.0, 0.5, 0.5), "16:9": (1.0, 0.5, 0.5)},
    "focus_board": {"9:16": (1.07, 0.5, 0.25), "16:9": (1.08, 0.65, 0.44)},
    "closeup_react": {"9:16": (1.22, 0.5, 0.72), "16:9": (1.22, 0.24, 0.56)},
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
    return load_cached_font(path, max(12, size))


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


def _highlight_color_for_card(
    pal: dict[str, tuple[int, int, int, int]],
) -> tuple[int, int, int, int]:
    """Chọn màu tô từ khóa **...**: vàng #FACC15 trên nền tối, đỏ #B91C1C trên nền sáng."""
    card_r, card_g, card_b = pal["card"][:3]
    luma = 0.299 * card_r + 0.587 * card_g + 0.114 * card_b
    return (250, 204, 21, 255) if luma < 128 else (185, 28, 28, 255)


def parse_rich_spans(text: str) -> list[tuple[str, bool]]:
    """Tách chuỗi chứa `**từ khóa**` thành danh sách `(văn_bản_sạch, is_highlight)`.

    Đảm bảo triệt tiêu 100% ký tự `**` thô kể cả khi chuỗi bị cắt nửa chừng không cân xứng.
    """
    raw = str(text or "").strip()
    if not raw:
        return []
    spans: list[tuple[str, bool]] = []
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*", raw):
        if m.start() > pos:
            plain = raw[pos : m.start()].replace("**", "")
            if plain:
                spans.append((plain, False))
        inner = m.group(1).replace("**", "")
        if inner:
            spans.append((inner, True))
        pos = m.end()
    if pos < len(raw):
        tail = raw[pos:].replace("**", "")
        if tail:
            spans.append((tail, False))
    return spans


def strip_rich_markup(text: str) -> str:
    """Trả về chuỗi thuần không còn bất kỳ dấu `**` nào để đo kích thước hoặc vẽ nhãn đơn sắc."""
    return "".join(seg for seg, _ in parse_rich_spans(text)).replace("**", "")


def draw_rich_text_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    highlight_fill: tuple[int, int, int, int],
    *,
    bold_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
    max_width_px: int | None = None,
) -> int:
    """Vẽ một dòng văn bản hỗ trợ `**từ khóa**` (0% lộ `**`), trả về tọa độ x cuối dòng."""
    spans = parse_rich_spans(text)
    if not spans:
        return xy[0]
    x, y = xy
    hl_font = bold_font or font
    for seg, is_hl in spans:
        fnt = hl_font if is_hl else font
        col = highlight_fill if is_hl else fill
        if max_width_px is not None:
            rem = max_width_px - (x - xy[0])
            if rem <= 12:
                break
            cur_seg = seg
            bb = draw.textbbox((0, 0), cur_seg, font=fnt)
            if (bb[2] - bb[0]) > rem:
                while len(cur_seg) > 1:
                    cur_seg = cur_seg[:-1]
                    tbb = draw.textbbox((0, 0), cur_seg.rstrip() + "…", font=fnt)
                    if (tbb[2] - tbb[0]) <= rem:
                        cur_seg = cur_seg.rstrip() + "…"
                        break
                seg = cur_seg
        draw.text((x, y), seg, font=fnt, fill=col)
        bb = draw.textbbox((0, 0), seg, font=fnt)
        x += max(1, bb[2] - bb[0])
    return x


def _draw_rich_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    highlight_fill: tuple[int, int, int, int],
    *,
    max_width_px: int,
    line_gap: int = 10,
    max_lines: int | None = None,
) -> int:
    """Vẽ chữ tự xuống dòng qua `parse_rich_spans` (tô màu `**từ khóa**`, 0% lộ `**`)."""
    tokens: list[tuple[str, bool]] = []
    for seg, is_hl in parse_rich_spans(text):
        for w in seg.split():
            if w:
                tokens.append((w, is_hl))
    if not tokens:
        return xy[1]

    space_bb = draw.textbbox((0, 0), " ", font=font)
    space_w = max(5, space_bb[2] - space_bb[0])
    x0, cur_y = xy
    cur_x = x0
    line_h = 0
    lines_drawn = 1

    for idx, (word, is_hl) in enumerate(tokens):
        bb = draw.textbbox((0, 0), word, font=font)
        ww = bb[2] - bb[0]
        wh = bb[3] - bb[1]
        if idx > 0 and cur_x + ww > x0 + max_width_px:
            if max_lines is not None and lines_drawn >= max_lines:
                break
            cur_y += max(24, line_h) + line_gap
            cur_x = x0
            line_h = 0
            lines_drawn += 1
        draw.text((cur_x, cur_y), word, font=font, fill=highlight_fill if is_hl else fill)
        cur_x += ww + space_w
        line_h = max(line_h, wh)

    return cur_y + max(24, line_h) + line_gap


def _measure_rich_wrapped_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    max_width_px: int,
    line_gap: int = 10,
    max_lines: int | None = None,
) -> int:
    """Đo chính xác chiều cao khối văn bản sau khi tách `parse_rich_spans` và xuống dòng."""
    words = strip_rich_markup(text).split()
    if not words:
        return 0
    space_bb = draw.textbbox((0, 0), " ", font=font)
    space_w = max(5, space_bb[2] - space_bb[0])
    cur_x = 0
    line_h = 0
    total_h = 0
    lines_cnt = 1
    for idx, word in enumerate(words):
        bb = draw.textbbox((0, 0), word, font=font)
        ww = bb[2] - bb[0]
        wh = bb[3] - bb[1]
        if idx > 0 and cur_x + ww > max_width_px:
            if max_lines is not None and lines_cnt >= max_lines:
                break
            total_h += max(24, line_h) + line_gap
            cur_x = 0
            line_h = 0
            lines_cnt += 1
        cur_x += ww + space_w
        line_h = max(line_h, wh)
    return total_h + max(24, line_h) + line_gap


def _fit_single_line_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_size: int,
    min_size: int,
    max_width_px: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Giảm cỡ chữ từ `max_size` xuống `min_size` để 1 dòng không vượt quá `max_width_px`."""
    clean = strip_rich_markup(text) or " "
    sz = max(min_size, int(max_size))
    while sz > min_size:
        fnt = _load_font(font_path, sz)
        bb = draw.textbbox((0, 0), clean, font=fnt)
        if (bb[2] - bb[0]) <= max_width_px:
            return fnt
        sz = max(min_size, sz - 2)
    return _load_font(font_path, min_size)


def _wrap_rich_tokens_lines(
    draw: ImageDraw.ImageDraw,
    tokens: list[tuple[str, bool]],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width_px: int,
) -> tuple[list[list[tuple[str, bool]]], int, int]:
    """Tách token `(word, is_hl)` thành các dòng khớp `max_width_px` bằng Pillow `textbbox`."""
    space_bb = draw.textbbox((0, 0), " ", font=font)
    space_w = max(4, space_bb[2] - space_bb[0])
    sample_bb = draw.textbbox((0, 0), "Âg", font=font)
    base_h = max(14, sample_bb[3] - sample_bb[1])

    lines: list[list[tuple[str, bool]]] = []
    cur_line: list[tuple[str, bool]] = []
    cur_w = 0
    for word, is_hl in tokens:
        bb = draw.textbbox((0, 0), word, font=font)
        ww = bb[2] - bb[0]
        if ww > max_width_px and len(word) > 2:
            # Cắt bớt từ đơn siêu dài để không bao giờ tràn mép phải
            trimmed = word
            while len(trimmed) > 1:
                trimmed = trimmed[:-1]
                tbb = draw.textbbox((0, 0), trimmed + "…", font=font)
                if (tbb[2] - tbb[0]) <= max_width_px:
                    word = trimmed + "…"
                    ww = tbb[2] - tbb[0]
                    break
        if cur_line and cur_w + space_w + ww > max_width_px:
            lines.append(cur_line)
            cur_line = [(word, is_hl)]
            cur_w = ww
        else:
            cur_w = (cur_w + space_w + ww) if cur_line else ww
            cur_line.append((word, is_hl))
    if cur_line:
        lines.append(cur_line)
    return lines, space_w, base_h


def _draw_rich_autofit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font_path: Path,
    max_size: int,
    min_size: int,
    fill: tuple[int, int, int, int],
    highlight_fill: tuple[int, int, int, int],
    *,
    max_width_px: int,
    max_height_px: int,
    line_gap: int = 8,
    max_lines: int | None = None,
    align: str = "left",
) -> int:
    """Tự xuống dòng và giảm cỡ chữ để khối văn bản giàu định dạng không bao giờ vượt biên box."""
    tokens: list[tuple[str, bool]] = []
    for seg, is_hl in parse_rich_spans(text):
        for w in seg.split():
            if w:
                tokens.append((w, is_hl))
    if not tokens or max_width_px <= 16 or max_height_px <= 12:
        return xy[1]

    best_font = _load_font(font_path, min_size)
    best_lines: list[list[tuple[str, bool]]] = []
    best_space = 4
    best_lh = 16
    best_gap = max(2, line_gap)

    for sz in range(max(min_size, int(max_size)), int(min_size) - 1, -2):
        fnt = _load_font(font_path, sz)
        gap = max(3, int(round(line_gap * (sz / max(1, max_size)))))
        lines, space_w, base_h = _wrap_rich_tokens_lines(draw, tokens, fnt, max_width_px)
        line_count = len(lines)
        total_h = line_count * base_h + max(0, line_count - 1) * gap
        best_font, best_lines, best_space, best_lh, best_gap = fnt, lines, space_w, base_h, gap
        if total_h <= max_height_px and (max_lines is None or line_count <= max_lines):
            break

    max_fit_lines = max(1, (max_height_px + best_gap) // max(1, best_lh + best_gap))
    if max_lines is not None:
        max_fit_lines = min(max_fit_lines, max_lines)

    truncated = len(best_lines) > max_fit_lines
    vis_lines = best_lines[:max_fit_lines]
    if truncated and vis_lines:
        last_line = list(vis_lines[-1])
        while last_line:
            w_txt, is_hl = last_line[-1]
            cand = w_txt.rstrip(".,;:!?…") + "…"
            test_line = last_line[:-1] + [(cand, is_hl)]
            line_w = sum(
                draw.textbbox((0, 0), wd, font=best_font)[2] for wd, _ in test_line
            ) + best_space * max(0, len(test_line) - 1)
            if line_w <= max_width_px or len(last_line) == 1:
                vis_lines[-1] = test_line
                break
            last_line.pop()

    x0, cur_y = xy
    for line in vis_lines:
        if cur_y + best_lh > xy[1] + max_height_px + 2:
            break
        if align == "center":
            line_w = sum(
                draw.textbbox((0, 0), wd, font=best_font)[2]
                - draw.textbbox((0, 0), wd, font=best_font)[0]
                for wd, _ in line
            ) + best_space * max(0, len(line) - 1)
            cur_x = x0 + max(0, (max_width_px - line_w) // 2)
        else:
            cur_x = x0
        for wd, is_hl in line:
            bb = draw.textbbox((0, 0), wd, font=best_font)
            ww = bb[2] - bb[0]
            draw.text(
                (cur_x, cur_y),
                wd,
                font=best_font,
                fill=highlight_fill if is_hl else fill,
            )
            cur_x += ww + best_space
        cur_y += best_lh + best_gap
    return cur_y


def _draw_topic_circle_badge(
    canvas: Image.Image,
    center_xy: tuple[int, int],
    size: int,
    pal: dict[str, tuple[int, int, int, int]],
    prop_img: Image.Image | None,
) -> None:
    """Vẽ huy hiệu tròn chứa Iconify sắc nét (`54×54px`) hoặc biểu tượng vector tương phản cao."""
    cx, cy = center_xy
    r = max(24, size // 2)
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=pal["pill_bg"],
        outline=pal["accent"],
        width=3,
    )
    if prop_img is not None:
        fit = prop_img.copy()
        target_d = max(30, int(round(size * 0.72)))
        fit.thumbnail((target_d, target_d), Image.Resampling.LANCZOS)
        canvas.alpha_composite(fit, (cx - fit.width // 2, cy - fit.height // 2))
        fit.close()
        return

    ir = max(12, int(round(r * 0.56)))
    draw.ellipse((cx - ir, cy - ir, cx + ir, cy + ir), outline=pal["accent"], width=3)
    draw.polygon(
        [(cx, cy - ir + 3), (cx + ir // 2, cy + 2), (cx, cy + ir - 3), (cx - ir // 2, cy + 2)],
        fill=pal["amber"],
    )


def _ease_out_cubic(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return 1.0 - (1.0 - u) ** 3


def _ease_in_cubic(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return u * u * u


def _draw_pinned_photo_card(
    canvas: Image.Image,
    beat: StickvBeat,
    box: tuple[int, int, int, int],
    pal: dict[str, tuple[int, int, int, int]],
    *,
    photo_img: Image.Image | None = None,
    content_alpha: float = 1.0,
) -> tuple[int, int, int, int]:
    """Vẽ thẻ Polaroid trắng `#FFFFFF`, ghim đỏ `#D9232E` hoặc băng dính mờ, xoay nghiêng ±2.2°."""
    x0, y0, x1, y1 = box
    bw = max(240, x1 - x0)
    bh = max(260, y1 - y0)

    # Kích thước khung Polaroid gọn trong vùng bảng (tuyệt đối không phủ kín phông nền)
    card_w = min(bw - 36, int(round(bh * 0.92)))
    card_h = min(bh - 28, int(round(card_w * 0.94)))
    card_w = max(220, card_w)
    card_h = max(240, card_h)

    vdata: dict[str, Any] = getattr(beat, "visual_data", None) or {}
    data: dict[str, Any] = {**(beat.board_data or {}), **vdata}
    pin_style = str(data.get("pin_style") or "pin").strip().lower()
    _generic_caps = {
        "phân tích cơ chế",
        "dữ kiện định lượng",
        "bản đồ ý chính",
        "hồ sơ phân tích",
        "ảnh tư liệu minh họa",
    }
    raw_caption = str(data.get("caption") or "").replace("**", "").strip()
    if raw_caption.lower() in _generic_caps:
        raw_caption = ""
    if not raw_caption:
        bt_clean = strip_rich_markup(beat.board_title or "").strip()
        if bt_clean.lower() not in _generic_caps:
            raw_caption = bt_clean
    if not raw_caption:
        raw_caption = _extract_highlight_keyword(beat.narration)
    cap_words = raw_caption.split()[:7]
    caption = " ".join(cap_words) if cap_words else "Hình ảnh minh họa"

    # Tạo lớp Polaroid có viền đệm đủ cho bóng đổ + đinh ghim + xoay nghiêng ±2.2°
    pad = 44
    pw = card_w + pad * 2
    ph = card_h + pad * 2
    polaroid = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    try:
        d = ImageDraw.Draw(polaroid)
        cx0, cy0 = pad, pad
        cx1, cy1 = pad + card_w, pad + card_h

        # Bóng đổ mềm nhiều lớp
        d.rounded_rectangle(
            (cx0 + 10, cy0 + 14, cx1 + 10, cy1 + 14),
            radius=10,
            fill=(15, 23, 42, 46),
        )
        d.rounded_rectangle(
            (cx0 + 5, cy0 + 8, cx1 + 5, cy1 + 8),
            radius=10,
            fill=(15, 23, 42, 28),
        )

        # Khung Polaroid trắng tinh #FFFFFF
        d.rounded_rectangle(
            (cx0, cy0, cx1, cy1),
            radius=8,
            fill=(255, 255, 255, 255),
            outline=(226, 232, 240, 255),
            width=3,
        )

        # Vùng ảnh bên trong (lề trên/trái/phải 20px, lề dưới 74px cho chú thích)
        inset = 20
        footer_h = 74
        ix0, iy0 = cx0 + inset, cy0 + inset
        ix1, iy1 = cx1 - inset, cy1 - footer_h
        iw = max(80, ix1 - ix0)
        ih = max(80, iy1 - iy0)

        if photo_img is not None:
            fitted = ImageOps.fit(
                photo_img.convert("RGBA"),
                (iw, ih),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            try:
                polaroid.alpha_composite(fitted, (ix0, iy0))
            finally:
                fitted.close()
        else:
            d.rectangle((ix0, iy0, ix1, iy1), fill=pal["takeaway_bg"])
            _draw_topic_circle_badge(polaroid, ((ix0 + ix1) // 2, (iy0 + iy1) // 2), 84, pal, None)

        d.rectangle((ix0, iy0, ix1, iy1), outline=(203, 213, 225, 255), width=2)

        # Chú thích ngắn căn giữa ở mép dưới Polaroid (auto-fit xuống dòng, không tràn viền)
        _draw_rich_autofit_text(
            d,
            caption,
            (ix0 + 4, iy1 + 10),
            FONT_BOLD,
            28,
            14,
            (30, 41, 59, 255),
            (30, 41, 59, 255),
            max_width_px=max(80, iw - 8),
            max_height_px=max(24, footer_h - 14),
            line_gap=4,
            max_lines=2,
            align="center",
        )

        # Đinh ghim đỏ #D9232E hoặc miếng băng dính mờ trên đỉnh
        pin_cx = (cx0 + cx1) // 2
        pin_cy = cy0 + 8
        if pin_style == "tape":
            d.rounded_rectangle(
                (pin_cx - 56, cy0 - 14, pin_cx + 56, cy0 + 18),
                radius=4,
                fill=(254, 243, 199, 175),
                outline=(217, 119, 6, 90),
                width=1,
            )
        else:
            d.ellipse((pin_cx - 15, pin_cy - 11, pin_cx + 17, pin_cy + 21), fill=(15, 23, 42, 60))
            d.ellipse(
                (pin_cx - 15, pin_cy - 15, pin_cx + 15, pin_cy + 15),
                fill=(217, 35, 46, 255),
                outline=(153, 27, 27, 255),
                width=2,
            )
            d.ellipse((pin_cx - 7, pin_cy - 9, pin_cx - 1, pin_cy - 3), fill=(255, 255, 255, 190))

        # Xoay nghiêng nhẹ ±2.2° theo beat id để tự nhiên như ghim tay
        sign = 1.0 if (sum(ord(c) for c in (beat.id or "b1")) % 2 == 0) else -1.0
        tilted = polaroid.rotate(sign * 2.2, resample=Image.Resampling.BICUBIC, expand=True)
        try:
            _scale_alpha_inplace(tilted, content_alpha)
            dest_x = x0 + (bw - tilted.width) // 2
            dest_y = y0 + (bh - tilted.height) // 2
            canvas.alpha_composite(tilted, (dest_x, dest_y))
            return dest_x, dest_y, dest_x + tilted.width, dest_y + tilted.height
        finally:
            tilted.close()
    finally:
        polaroid.close()


_ALPHA_LUT_CACHE: dict[int, list[int]] = {}


def _scale_alpha_inplace(img: Image.Image, factor: float) -> None:
    """Nhân kênh alpha tại chỗ bằng bảng tra C (LUT), tránh lambda từng pixel."""
    clamped = max(0.0, min(1.0, float(factor)))
    if clamped >= 0.995:
        return
    q = int(round(clamped * 255))
    lut = _ALPHA_LUT_CACHE.get(q)
    if lut is None:
        s = q / 255.0
        lut = [int(round(i * s)) for i in range(256)]
        _ALPHA_LUT_CACHE[q] = lut
    a_band = img.getchannel("A")
    try:
        scaled_a = a_band.point(lut)
        try:
            img.putalpha(scaled_a)
        finally:
            scaled_a.close()
    finally:
        a_band.close()


def close_stage_cache(cache: dict[str, Any] | None) -> None:
    """Giải phóng mọi `PIL.Image` nằm trong cache tạm của stage."""
    if not cache:
        return
    for val in cache.values():
        if isinstance(val, Image.Image):
            val.close()
        elif isinstance(val, tuple):
            for item in val:
                if isinstance(item, Image.Image):
                    item.close()
    cache.clear()


_VISUAL_GENERIC_TITLES = frozenset(
    {
        "phân tích cơ chế",
        "dữ kiện định lượng",
        "bản đồ ý chính",
        "góc nhìn thực nghiệm",
        "hồ sơ phân tích",
        "tổng hợp khoa học",
        "thông tin quan trọng",
        "ảnh tư liệu minh họa",
        "mở đầu video",
        "tóm tắt 3 ý cốt lõi",
        "kết luận",
        "tổng kết",
        "tổng kết nhanh",
    }
)


def _pick_visual_first_title(beat: StickvBeat) -> str:
    """Chọn tiêu đề Visual-First ngắn 3-6 từ (loại văn mẫu, không cắt '...')."""
    from hbt.stickv.llm import shorten_visual_title

    vdata: dict[str, Any] = getattr(beat, "visual_data", None) or {}
    data: dict[str, Any] = {**(beat.board_data or {}), **vdata}
    raw_title = strip_rich_markup(beat.board_title or "").strip()
    raw_cap = strip_rich_markup(str(data.get("caption") or "")).strip()

    low_t = raw_title.lower()
    low_c = raw_cap.lower()
    use_cap = (not raw_title or low_t in _VISUAL_GENERIC_TITLES) and bool(
        raw_cap and low_c not in _VISUAL_GENERIC_TITLES
    )
    seed = raw_cap if use_cap else raw_title
    return shorten_visual_title(
        seed, fallback_narration=beat.narration, min_words=3, max_words=6
    ).upper()


def _draw_visual_first_board(
    canvas: Image.Image,
    beat: StickvBeat,
    box: tuple[int, int, int, int],
    pal: dict[str, tuple[int, int, int, int]],
    *,
    photo_img: Image.Image | None = None,
    content_alpha: float = 1.0,
) -> tuple[int, int, int, int]:
    """Vẽ bố cục Visual-First tối giản: Tiêu đề ngắn (3-6 từ) + Khung Ảnh minh họa lớn."""
    x0, y0, x1, y1 = box
    bw = max(260, x1 - x0)
    bh = max(260, y1 - y0)

    headline = _pick_visual_first_title(beat).upper()
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    try:
        d = ImageDraw.Draw(layer)
        # 1. Dải Tiêu đề ngắn (3-6 từ) nằm trong safe zone đầu vùng bảng (không cắt '...')
        head_x0 = x0 + 8
        head_x1 = x1 - 8
        head_w = max(200, head_x1 - head_x0)
        head_h = min(98, max(70, int(round(bh * 0.14))))
        head_y0 = y0
        head_y1 = y0 + head_h

        d.rounded_rectangle(
            (head_x0 + 4, head_y0 + 6, head_x1 + 4, head_y1 + 6),
            radius=20,
            fill=(15, 23, 42, 34),
        )
        d.rounded_rectangle(
            (head_x0, head_y0, head_x1, head_y1),
            radius=20,
            fill=pal["card"],
            outline=pal["accent"],
            width=3,
        )
        # Thanh nhấn màu accent ở mép dưới tiêu đề
        bar_w = min(132, max(64, head_w // 5))
        bar_cx = (head_x0 + head_x1) // 2
        d.rounded_rectangle(
            (bar_cx - bar_w // 2, head_y1 - 8, bar_cx + bar_w // 2, head_y1 - 2),
            radius=999,
            fill=pal["accent"],
        )

        # Tự co cỡ chữ sao cho 3-6 từ nằm gọn 1-2 dòng trong head_w - 40, không chèn '...'
        text_max_w = max(140, head_w - 40)
        chosen_font = _load_font(FONT_EXTRABOLD, 38)
        wrapped_lines: list[str] = [headline]
        for fsz in range(42, 22, -2):
            f_cand = _load_font(FONT_EXTRABOLD, fsz)
            one_bb = d.textbbox((0, 0), headline, font=f_cand)
            if (one_bb[2] - one_bb[0]) <= text_max_w:
                chosen_font = f_cand
                wrapped_lines = [headline]
                break
            words = headline.split()
            if len(words) >= 4:
                mid = len(words) // 2
                l1 = " ".join(words[:mid])
                l2 = " ".join(words[mid:])
                bb1 = d.textbbox((0, 0), l1, font=f_cand)
                bb2 = d.textbbox((0, 0), l2, font=f_cand)
                if max(bb1[2] - bb1[0], bb2[2] - bb2[0]) <= text_max_w:
                    chosen_font = f_cand
                    wrapped_lines = [l1, l2]
                    break
            chosen_font = f_cand

        line_heights: list[int] = []
        line_widths: list[int] = []
        for ln in wrapped_lines:
            lbb = d.textbbox((0, 0), ln, font=chosen_font)
            line_widths.append(lbb[2] - lbb[0])
            line_heights.append(lbb[3] - lbb[1])
        gap_y = 6 if len(wrapped_lines) > 1 else 0
        total_th = sum(line_heights) + gap_y
        cur_ty = head_y0 + max(8, (head_h - 8 - total_th) // 2)
        for idx_l, ln in enumerate(wrapped_lines):
            lbb = d.textbbox((0, 0), ln, font=chosen_font)
            lx = head_x0 + max(16, (head_w - line_widths[idx_l]) // 2)
            d.text((lx, cur_ty - lbb[1]), ln, font=chosen_font, fill=pal["text"])
            cur_ty += line_heights[idx_l] + gap_y

        # 2. Khung Ảnh minh họa lớn chiếm trọng tâm vùng trên
        fy0 = head_y1 + 14
        fy1 = max(fy0 + 150, y1 - 8)
        frame_w = min(bw - 12, max(240, int(round((fy1 - fy0) * 1.48))))
        fx0 = x0 + max(6, (bw - frame_w) // 2)
        fx1 = fx0 + frame_w

        d.rounded_rectangle(
            (fx0 + 8, fy0 + 10, fx1 + 8, fy1 + 10),
            radius=24,
            fill=(15, 23, 42, 42),
        )
        d.rounded_rectangle(
            (fx0, fy0, fx1, fy1),
            radius=24,
            fill=pal["card"],
            outline=pal["card_border"],
            width=3,
        )

        inset = 10
        ix0, iy0 = fx0 + inset, fy0 + inset
        ix1, iy1 = fx1 - inset, fy1 - inset
        iw = max(80, ix1 - ix0)
        ih = max(80, iy1 - iy0)

        if photo_img is not None:
            fitted = ImageOps.fit(
                photo_img.convert("RGBA"),
                (iw, ih),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            mask = Image.new("L", (iw, ih), 0)
            try:
                md = ImageDraw.Draw(mask)
                md.rounded_rectangle((0, 0, iw - 1, ih - 1), radius=18, fill=255)
                fitted.putalpha(mask)
                layer.alpha_composite(fitted, (ix0, iy0))
            finally:
                mask.close()
                fitted.close()
        else:
            d.rounded_rectangle((ix0, iy0, ix1, iy1), radius=18, fill=pal["takeaway_bg"])
            badge_sz = max(72, min(140, min(iw, ih) // 2))
            _draw_topic_circle_badge(
                layer, ((ix0 + ix1) // 2, (iy0 + iy1) // 2), badge_sz, pal, None
            )

        d.rounded_rectangle((ix0, iy0, ix1, iy1), radius=18, outline=pal["card_border"], width=2)

        _scale_alpha_inplace(layer, content_alpha)
        canvas.alpha_composite(layer)
        return min(head_x0, fx0), head_y0, max(head_x1, fx1), fy1
    finally:
        layer.close()


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
    """Vẽ 100% beat theo chế độ Visual-First (Tiêu đề ngắn 3-6 từ + Ảnh minh họa lớn)."""
    _ = progress, total_chapters, draw_shell
    return _draw_visual_first_board(
        canvas,
        beat,
        box,
        pal,
        photo_img=prop_img,
        content_alpha=content_alpha,
    )


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
    cam_board_scale: float = 1.0,
    cam_board_alpha: float = 1.0,
    clamp_bounds: tuple[int, int, int, int] | None = None,
    anchor_top_center: tuple[float, float] | None = None,
    prev_board_img: Image.Image | None = None,
    board_cache: dict[str, Any] | None = None,
) -> None:
    """Chuyển tiếp thẻ bằng Cross-Fade 0.28s Cosine Ease-In-Out (0% chớp trống, 0% cắt cứng)."""
    if cam_board_alpha <= 0.015:
        return

    cur_title = strip_rich_markup(beat.board_title or "").strip()
    prev_title = strip_rich_markup(getattr(prev_stage_state, "last_board_title", "") or "").strip()
    same_title = prev_stage_state is not None and bool(cur_title) and cur_title == prev_title
    same_recap = (
        same_title
        and beat.board_type == "recap_card"
        and (getattr(prev_stage_state, "last_board_type", "") or "") == "recap_card"
    )

    if (
        same_title
        and abs(cam_board_scale - 1.0) < 0.004
        and cam_board_alpha > 0.99
        and clamp_bounds is None
    ):
        c_alpha = (
            1.0
            if same_recap
            else (_ease_out_cubic(min(1.0, t_sec / 0.22)) if t_sec < 0.22 else 1.0)
        )
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

    enter_t = 0.28
    scale = float(cam_board_scale)
    dy_px = 0.0
    alpha = float(cam_board_alpha)
    if not same_title and t_sec < enter_t:
        u = _cosine_ease_in_out(t_sec / enter_t)
        if prev_board_img is not None and prev_board_img.size == frame_rgba.size:
            prev_alpha = max(0.0, min(1.0, (1.0 - u) * float(cam_board_alpha)))
            if prev_alpha > 0.015:
                fading_prev = prev_board_img.copy()
                try:
                    _scale_alpha_inplace(fading_prev, prev_alpha)
                    frame_rgba.alpha_composite(fading_prev)
                finally:
                    fading_prev.close()
        scale *= 0.98 + 0.02 * u
        dy_px = 12.0 * (1.0 - u)
        alpha *= u

    if abs(scale - 1.0) < 0.004 and abs(dy_px) < 0.5 and alpha > 0.995 and clamp_bounds is None:
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

    # Tái sử dụng bảng gốc tĩnh đã crop ở t_sec=0 để mọi frame tween không vẽ lại Polaroid
    sub: Image.Image | None = None
    owns_sub = False
    cx0 = cy0 = 0
    is_static_type = beat.board_type not in _ANIMATED_BOARD_TYPES
    raw_cache_entry = (
        board_cache.get("raw_board_crop") if (board_cache is not None and is_static_type) else None
    )
    if isinstance(raw_cache_entry, tuple) and len(raw_cache_entry) == 4:
        cached_sub, c_x0, c_y0, cached_box = raw_cache_entry
        if cached_box == box and isinstance(cached_sub, Image.Image):
            sub = cached_sub
            cx0, cy0 = c_x0, c_y0

    if sub is None:
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
            cropped = layer.crop((cx0, cy0, cx1, cy1))
            if board_cache is not None and is_static_type:
                board_cache["raw_board_crop"] = (cropped, cx0, cy0, box)
                sub = cropped
                owns_sub = False
            else:
                sub = cropped
                owns_sub = True
        finally:
            layer.close()

    try:
        if abs(scale - 1.0) >= 0.004:
            nw = max(8, int(round(sub.width * scale)))
            nh = max(8, int(round(sub.height * scale)))
            if clamp_bounds is not None:
                cb_x0, cb_y0, cb_x1, cb_y1 = clamp_bounds
                max_w = max(8, cb_x1 - cb_x0)
                max_h = max(8, cb_y1 - cb_y0)
                if nw > max_w or nh > max_h:
                    fit = min(max_w / nw, max_h / nh)
                    nw = max(8, int(round(nw * fit)))
                    nh = max(8, int(round(nh * fit)))
            scaled = sub.resize((nw, nh), Image.Resampling.BICUBIC)
        else:
            scaled = sub.copy()
        try:
            if alpha < 0.995:
                _scale_alpha_inplace(scaled, alpha)
            if anchor_top_center is not None:
                dest_x = int(round(anchor_top_center[0] - scaled.width * 0.5))
                dest_y = int(round(anchor_top_center[1] + dy_px))
            else:
                dest_x = cx0 + (sub.width - scaled.width) // 2
                dest_y = cy0 + (sub.height - scaled.height) // 2 + int(round(dy_px))

            # Kẹp cứng biên an toàn cho Bảng tri thức (không bao giờ lọt ngoài khung)
            if clamp_bounds is not None:
                cb_x0, cb_y0, cb_x1, cb_y1 = clamp_bounds
                dest_x = max(cb_x0, min(cb_x1 - scaled.width, dest_x))
                dest_y = max(cb_y0, min(cb_y1 - scaled.height, dest_y))
            else:
                dest_x = max(0, min(frame_rgba.width - scaled.width, dest_x))
                dest_y = max(0, min(frame_rgba.height - scaled.height, dest_y))

            frame_rgba.alpha_composite(scaled, (dest_x, dest_y))
        finally:
            scaled.close()
    finally:
        if owns_sub and sub is not None:
            sub.close()


def compute_karaoke_word_boxes(
    words: list[str],
    active_local_idx: int,
    *,
    frame_w: int,
    base_y: int,
    aspect: StickvAspect,
    pad_x: int = 12,
    space_w: int = 18,
) -> tuple[
    ImageFont.FreeTypeFont | ImageFont.ImageFont,
    tuple[int, int, int, int],
    list[dict[str, Any]],
]:
    """Tính tọa độ hộp chữ & hộp highlight Karaoke: khoảng hở hộp highlight <-> từ kế >= 14px."""
    clean_words = [strip_rich_markup(w) for w in words]
    eff_pad_x = max(10, int(pad_x))
    eff_space = max(14, int(space_w))
    font_sz = 42 if aspect == "9:16" else 38
    if frame_w < 720:
        scale_f = frame_w / (1080.0 if aspect == "9:16" else 1920.0)
        font_sz = max(22, int(round(font_sz * scale_f)))

    probe_img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    try:
        probe_draw = ImageDraw.Draw(probe_img)
        while True:
            font = _load_font(FONT_EXTRABOLD, font_sz)
            widths: list[int] = []
            max_h = 0
            for w_txt in clean_words:
                bb = probe_draw.textbbox((0, 0), w_txt, font=font)
                widths.append(max(1, bb[2] - bb[0]))
                max_h = max(max_h, bb[3] - bb[1])
            slot_widths = [
                ww + (2 * eff_pad_x if idx == active_local_idx else 0)
                for idx, ww in enumerate(widths)
            ]
            total_w = sum(slot_widths) + eff_space * max(0, len(clean_words) - 1)
            if total_w <= max(180, frame_w - 64) or font_sz <= 20:
                break
            font_sz -= 2
    finally:
        probe_img.close()

    line_h = max(28, max_h)
    cur_x = (frame_w - total_w) // 2
    strip_box = (
        max(18, cur_x - 22),
        base_y - 10,
        min(frame_w - 18, cur_x + total_w + 22),
        base_y + line_h + 16,
    )

    items: list[dict[str, Any]] = []
    for idx, (w_txt, ww) in enumerate(zip(clean_words, widths, strict=True)):
        is_active = idx == active_local_idx
        if is_active:
            pill_box = (cur_x, base_y - 6, cur_x + ww + 2 * eff_pad_x, base_y + line_h + 10)
            text_x = cur_x + eff_pad_x
            text_box = (text_x, base_y, text_x + ww, base_y + line_h)
            cur_x = pill_box[2] + eff_space
        else:
            pill_box = None
            text_x = cur_x
            text_box = (text_x, base_y, text_x + ww, base_y + line_h)
            cur_x = text_box[2] + eff_space
        items.append(
            {
                "word": w_txt,
                "active": is_active,
                "text_xy": (text_x, base_y),
                "text_box": text_box,
                "highlight_box": pill_box,
            }
        )
    return font, strip_box, items


def draw_karaoke_strip(
    frame: Image.Image,
    word_timings: list[tuple[str, float, float]],
    t_sec: float,
    *,
    aspect: StickvAspect,
    spoken_segments: list[tuple[float, float, str]] | None = None,
    camera_shot: str = "wide_stage",
    karaoke_cache: dict[str, Any] | None = None,
) -> None:
    """Vẽ dải phụ đề Karaoke khóa câu đang nói, có đệm highlight >= 14px chống dính chữ."""
    if not word_timings:
        return

    for wd, _, _ in word_timings:
        ws = str(wd or "")
        if "{" in ws or "}" in ws or "'disp'" in ws or '"disp"' in ws:
            raise ValueError(f"Từ Karaoke không hợp lệ (lọt chuỗi dict thô): {ws[:80]}")

    filtered_timings = word_timings
    micro_gap_hold = False
    if spoken_segments:
        active_seg: tuple[float, float, str] | None = None
        for st, et, txt in spoken_segments:
            if (st - 0.035) <= t_sec <= (et + 0.015):
                active_seg = (st, et, txt)
                break
        if active_seg is None:
            for idx in range(len(spoken_segments) - 1):
                g_start = spoken_segments[idx][1]
                g_end = spoken_segments[idx + 1][0]
                if g_start < t_sec < g_end and (g_end - g_start) <= 0.24:
                    micro_gap_hold = True
                    break
            if not micro_gap_hold:
                return
        else:
            seg_st, seg_et, _ = active_seg
            seg_words = [
                (wd, wst, wet)
                for (wd, wst, wet) in word_timings
                if wst >= (seg_st - 0.04) and wet <= (seg_et + 0.02)
            ]
            if seg_words:
                filtered_timings = seg_words

    w, h = frame.size
    draw = ImageDraw.Draw(frame)
    shot = (camera_shot or "wide_stage").strip().lower()
    if aspect == "9:16":
        if shot == "closeup_react":
            base_y = int(round(h * (855.0 / 1920.0)))  # vùng 820..990 (cách đầu >= 100px)
        else:
            base_y = int(round(h * (935.0 / 1920.0)))  # vùng 895..1065
    else:
        base_y = int(round(h * (925.0 / 1080.0)))  # vùng 910..1030

    if micro_gap_hold:
        strip_w = min(w - 120, 620 if aspect == "9:16" else 880)
        sx0 = (w - strip_w) // 2
        draw.rounded_rectangle(
            (sx0, base_y - 10, sx0 + strip_w, base_y + 56),
            radius=18,
            fill=(15, 23, 42, 130),
        )
        return

    if t_sec > filtered_timings[-1][2] + 0.04:
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

    active_local = active_idx - chunk_idx * win_size
    words_key = tuple(wd for wd, _, _ in chunk)
    cache_key = (words_key, active_local, base_y, w, aspect)
    if (
        karaoke_cache is not None
        and karaoke_cache.get("key") == cache_key
        and isinstance(karaoke_cache.get("patch"), Image.Image)
    ):
        patch_img: Image.Image = karaoke_cache["patch"]
        px0, py0 = karaoke_cache["pos"]
        frame.alpha_composite(patch_img, (px0, py0))
        return

    font, strip_box, layout_items = compute_karaoke_word_boxes(
        list(words_key),
        active_local,
        frame_w=w,
        base_y=base_y,
        aspect=aspect,
    )
    if karaoke_cache is not None:
        pad = 12
        px0 = max(0, strip_box[0] - pad)
        py0 = max(0, strip_box[1] - pad)
        px1 = min(w, strip_box[2] + pad)
        py1 = min(h, strip_box[3] + pad)
        patch = Image.new("RGBA", (max(1, px1 - px0), max(1, py1 - py0)), (0, 0, 0, 0))
        pd = ImageDraw.Draw(patch)
        pd.rounded_rectangle(
            (strip_box[0] - px0, strip_box[1] - py0, strip_box[2] - px0, strip_box[3] - py0),
            radius=18,
            fill=(15, 23, 42, 145),
        )
        for item in layout_items:
            word = item["word"]
            tx, ty = item["text_xy"][0] - px0, item["text_xy"][1] - py0
            if item["active"] and item["highlight_box"] is not None:
                hb = item["highlight_box"]
                pd.rounded_rectangle(
                    (hb[0] - px0, hb[1] - py0, hb[2] - px0, hb[3] - py0),
                    radius=12,
                    fill=(255, 212, 59, 255),
                )
                pd.text((tx, ty), word, font=font, fill=(15, 23, 42, 255))
            else:
                pd.text(
                    (tx, ty),
                    word,
                    font=font,
                    fill=(255, 255, 255, 255),
                    stroke_width=4,
                    stroke_fill=(15, 23, 42, 255),
                )
        old_patch = karaoke_cache.get("patch")
        if isinstance(old_patch, Image.Image):
            old_patch.close()
        karaoke_cache["key"] = cache_key
        karaoke_cache["patch"] = patch
        karaoke_cache["pos"] = (px0, py0)
        frame.alpha_composite(patch, (px0, py0))
        return

    draw.rounded_rectangle(strip_box, radius=18, fill=(15, 23, 42, 145))

    for item in layout_items:
        word = item["word"]
        tx, ty = item["text_xy"]
        if item["active"] and item["highlight_box"] is not None:
            draw.rounded_rectangle(
                item["highlight_box"],
                radius=12,
                fill=(255, 212, 59, 255),  # #FFD43B
            )
            draw.text((tx, ty), word, font=font, fill=(15, 23, 42, 255))
        else:
            draw.text(
                (tx, ty),
                word,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=4,
                stroke_fill=(15, 23, 42, 255),
            )


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _cosine_ease_in_out(t: float) -> float:
    """Đường cong Cosine Ease-In-Out êm ái cho chuyển góc máy & dịch chuyển nhân vật."""
    u = max(0.0, min(1.0, float(t)))
    return 0.5 * (1.0 - math.cos(math.pi * u))


@dataclass(frozen=True)
class BeatStageState:
    """Trạng thái cuối beat (nhân vật, camera tách lớp, độ mờ bảng, chương) để nối mượt."""

    x: float
    y: float
    scale: float = 1.0
    pose_state: Any = None
    camera_zoom: float = 1.0
    camera_pan_x: float = 0.5
    camera_pan_y: float = 0.5
    board_alpha: float = 1.0
    camera_shot: str = "wide_stage"
    last_board_title: str = ""
    last_board_type: str = ""
    last_chapter: int = 1


@dataclass(frozen=True)
class LayeredCameraLayout:
    """Thông số biến đổi tách lớp kẹp biên an toàn cho Bảng tri thức & Stickman."""

    board_box: tuple[int, int, int, int]
    board_scale: float
    board_alpha: float
    clamp_bounds: tuple[int, int, int, int] | None
    anchor_top_center: tuple[float, float] | None
    char_scale: float
    char_center_x: float
    char_foot_y: float


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


def _target_layered_shot_params(
    shot_key: str, *, aspect: StickvAspect, w: int, h: int
) -> tuple[
    tuple[int, int, int, int],
    float,
    float,
    tuple[int, int, int, int] | None,
    tuple[float, float] | None,
    float,
    float,
    float,
]:
    if aspect == "9:16":
        sx, sy = w / 1080.0, h / 1920.0
        base_box = (
            int(round(56 * sx)),
            int(round(125 * sy)),
            w - int(round(56 * sx)),
            int(round(830 * sy)),
        )
        if shot_key == "focus_board":
            clamp = (
                int(round(20 * sx)),
                int(round(115 * sy)),
                w - int(round(20 * sx)),
                int(round(865 * sy)),
            )
            return (
                base_box,
                1.07,
                1.0,
                clamp,
                (w * 0.5, 118.0 * sy),
                0.92,
                0.48 * w,
                0.91 * h,
            )
        if shot_key == "closeup_react":
            return base_box, 1.0, 0.0, None, None, 1.06, 0.50 * w, 0.92 * h
        return (
            base_box,
            1.0,
            1.0,
            (
                int(round(20 * sx)),
                int(round(115 * sy)),
                w - int(round(20 * sx)),
                int(round(865 * sy)),
            ),
            None,
            1.0,
            0.50 * w,
            0.90 * h,
        )

    # 16:9 YouTube Khám phá dài (1920x1080)
    sx, sy = w / 1920.0, h / 1080.0
    base_box = (
        int(round(680 * sx)),
        int(round(115 * sy)),
        int(round(1840 * sx)),
        int(round(860 * sy)),
    )
    if shot_key == "focus_board":
        clamp = (
            int(round(650 * sx)),
            int(round(95 * sy)),
            int(round(1860 * sx)),
            int(round(900 * sy)),
        )
        return (
            base_box,
            1.08,
            1.0,
            clamp,
            (float((base_box[0] + base_box[2]) * 0.5), 105.0 * sy),
            0.88,
            0.16 * w,
            0.91 * h,
        )
    if shot_key == "closeup_react":
        return (
            base_box,
            0.94,
            0.35,
            (
                int(round(650 * sx)),
                int(round(95 * sy)),
                int(round(1860 * sx)),
                int(round(900 * sy)),
            ),
            None,
            1.22,
            0.24 * w,
            0.93 * h,
        )
    return base_box, 1.0, 1.0, None, None, 1.0, 0.21 * w, 0.91 * h


def compute_layered_camera_layout(
    camera_shot: StickvCameraShot | str,
    *,
    aspect: StickvAspect,
    w: int,
    h: int,
    t_sec: float,
    prev_stage_state: BeatStageState | None = None,
    transition_dur: float = 0.70,
) -> LayeredCameraLayout:
    """Tính tách lớp camera kẹp biên an toàn (Cosine Ease-In-Out 0.70s chống giật cảnh)."""
    shot_key = (camera_shot or "wide_stage").strip().lower()
    box, t_bscale, t_balpha, clamp, anchor, t_cscale, t_cx, t_fy = _target_layered_shot_params(
        shot_key, aspect=aspect, w=w, h=h
    )
    if prev_stage_state is None or transition_dur <= 0:
        return LayeredCameraLayout(
            board_box=box,
            board_scale=t_bscale,
            board_alpha=t_balpha,
            clamp_bounds=clamp,
            anchor_top_center=anchor,
            char_scale=t_cscale,
            char_center_x=t_cx,
            char_foot_y=t_fy,
        )

    prev_shot = (getattr(prev_stage_state, "camera_shot", "wide_stage") or "wide_stage").lower()
    _, p_bscale, _, _, _, p_cscale, p_cx, p_fy = _target_layered_shot_params(
        prev_shot, aspect=aspect, w=w, h=h
    )
    p_balpha = float(getattr(prev_stage_state, "board_alpha", 1.0))

    u = _cosine_ease_in_out(min(1.0, t_sec / transition_dur))
    # Riêng độ mờ bảng khi closeup_react (9:16) hạ về 0.0 mượt trong 0.30s đầu
    alpha_u = (
        _ease_out_cubic(min(1.0, t_sec / 0.30))
        if (shot_key == "closeup_react" and aspect == "9:16")
        else u
    )
    return LayeredCameraLayout(
        board_box=box,
        board_scale=p_bscale + (t_bscale - p_bscale) * u,
        board_alpha=p_balpha + (t_balpha - p_balpha) * alpha_u,
        clamp_bounds=clamp,
        anchor_top_center=anchor,
        char_scale=p_cscale + (t_cscale - p_cscale) * u,
        char_center_x=p_cx + (t_cx - p_cx) * u,
        char_foot_y=p_fy + (t_fy - p_fy) * u,
    )


def _extract_closeup_quote(board_title: str, takeaway: str, narration: str) -> str:
    """Trích 2–6 từ khóa/quote đắt giá nổi bật cho dải trên khi `closeup_react`."""
    for src in (board_title, takeaway, narration):
        clean = strip_rich_markup(src or "").strip(" .,:;!?…\"'“”")
        if not clean:
            continue
        words = clean.split()
        if 2 <= len(words) <= 6:
            return " ".join(words)
        if len(words) > 6:
            return " ".join(words[:6])
    return "ĐIỂM NHẤN CỐT LÕI"


def _draw_compact_topic_pill(
    frame_rgba: Image.Image,
    *,
    chapter: int,
    chapter_title: str,
    board_title: str,
    pal: dict[str, tuple[int, int, int, int]],
    aspect: StickvAspect,
    narration: str = "",
    takeaway: str = "",
    total_chapters: int = 1,
) -> None:
    """Vẽ huy hiệu Chương + dải Quote/Từ khóa nổi bật (2–6 từ) ở vùng trên khi `closeup_react`."""
    w, h = frame_rgba.size
    sy = h / (1920.0 if aspect == "9:16" else 1080.0)
    sx = w / (1080.0 if aspect == "9:16" else 1920.0)
    raw_lbl = strip_rich_markup(chapter_title or "").strip()
    if total_chapters <= 1:
        raw_lbl = re.sub(r"(?i)^chương\s*\d+\s*[-:—·]*\s*", "", raw_lbl).strip()
        label = (raw_lbl or "ĐIỂM NHẤN CHÍNH")[:34].upper()
    else:
        raw_lbl = raw_lbl or f"Chương {chapter}"
        label = (
            f"CHƯƠNG {chapter} · {raw_lbl[:28].upper()}"
            if raw_lbl and f"{chapter}" not in raw_lbl
            else raw_lbl[:34].upper()
        )
    f_pill = _load_font(FONT_EXTRABOLD, max(12, int(round(22 * sy))))
    d = ImageDraw.Draw(frame_rgba)
    bb = d.textbbox((0, 0), label, font=f_pill)
    pill_h = max(24, int(round(44 * sy)))
    pill_w = min(w - int(round(80 * sx)), (bb[2] - bb[0]) + int(round(44 * sx)))
    x0 = (w - pill_w) // 2
    y0 = int(round(118 * sy))
    d.rounded_rectangle(
        (x0, y0, x0 + pill_w, y0 + pill_h),
        radius=999,
        fill=pal["pill_bg"],
        outline=pal["accent"],
        width=max(1, int(round(2 * sy))),
    )
    tx = x0 + (pill_w - (bb[2] - bb[0])) // 2
    ty = y0 + (pill_h - (bb[3] - bb[1])) // 2 - bb[1]
    d.text((tx, ty), label, font=f_pill, fill=pal["pill_text"])

    # Dải Quote/Từ khóa nổi bật ở vùng trên (y=178..365 theo chuẩn 1080x1920)
    quote_txt = _extract_closeup_quote(board_title, takeaway, narration).upper()
    card_x0 = int(round(72 * sx))
    card_x1 = w - int(round(72 * sx))
    card_y0 = y0 + pill_h + int(round(18 * sy))
    card_h = int(round(176 * sy))
    card_y1 = card_y0 + card_h
    d.rounded_rectangle(
        (card_x0, card_y0, card_x1, card_y1),
        radius=max(12, int(round(26 * sy))),
        fill=pal["card"],
        outline=pal["accent"],
        width=max(1, int(round(3 * sy))),
    )
    bar_w = int(round(96 * sx))
    bar_x0 = (w - bar_w) // 2
    d.rounded_rectangle(
        (bar_x0, card_y0 + int(round(14 * sy)), bar_x0 + bar_w, card_y0 + int(round(21 * sy))),
        radius=999,
        fill=pal["amber"],
    )
    f_quote = _load_font(FONT_EXTRABOLD, max(16, int(round(44 * sy))))
    inner_w = max(120, (card_x1 - card_x0) - int(round(48 * sx)))
    words = quote_txt.split()
    lines: list[str] = []
    cur = ""
    for wd in words:
        cand = f"{cur} {wd}".strip()
        cbb = d.textbbox((0, 0), cand, font=f_quote)
        if cur and (cbb[2] - cbb[0]) > inner_w and len(lines) < 1:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    if cur:
        lines.append(cur)
    lines = lines[:2]
    line_step = max(20, int(round(52 * sy)))
    total_th = len(lines) * line_step
    start_y = card_y0 + int(round(28 * sy)) + max(0, (card_h - int(round(36 * sy)) - total_th) // 2)
    hl_fill = _highlight_color_for_card(pal)
    for li, ln in enumerate(lines):
        lbb = d.textbbox((0, 0), ln, font=f_quote)
        lx = (w - (lbb[2] - lbb[0])) // 2
        ly = start_y + li * line_step
        d.text((lx, ly), ln, font=f_quote, fill=hl_fill if li == 0 else pal["text"])


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
        _scale_alpha_inplace(banner, u)
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
    camera_shot: str = "wide_stage",
) -> tuple[float, float, float]:
    """Tính tọa độ `(target_x, target_y, target_scale)` chuẩn theo interaction, aspect và camera."""
    cam = compute_layered_camera_layout(camera_shot, aspect=aspect, w=w, h=h, t_sec=0.0)
    scale = cam.char_scale
    if aspect == "16:9":
        base_target_h = int(h * 0.64)
        if char_h > 0:
            scale = (base_target_h / char_h) * cam.char_scale
    elif interaction == "point_chart":
        target_h = int(h * 0.42)
        if char_h > target_h and char_h > 0:
            scale = (target_h / char_h) * cam.char_scale
        eff_w = char_w * scale
        eff_h = char_h * scale
        bx = w * 0.48 - eff_w * 0.5
        by = cam.char_foot_y - eff_h
        return bx, by, scale

    eff_w = char_w * scale
    eff_h = char_h * scale
    if interaction == "hold_prop" and aspect == "9:16":
        cx = w * 0.48
    elif interaction == "versus_split":
        cx = w * 0.5
    else:
        cx = cam.char_center_x
    return cx - eff_w * 0.5, cam.char_foot_y - eff_h, scale


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
    hl_fill = _highlight_color_for_card(pal)
    col_w = max(120, mid_x - 96)
    _draw_rich_wrapped_text(
        draw, left_lbl, (64, top_y + 32), f_lbl, pal["text"], hl_fill, max_width_px=col_w
    )
    _draw_rich_wrapped_text(
        draw, right_lbl, (mid_x + 44, top_y + 32), f_lbl, pal["text"], hl_fill, max_width_px=col_w
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
    board_cache: dict[str, Any] | None = None,
) -> None:
    w, h = frame_rgba.size
    pop_p = min(1.0, max(0.0, t_sec / 0.25))
    pop_scale = 1.0 + 0.14 * math.sin(pop_p * math.pi) if pop_p < 1.0 else 1.0
    if pop_p < 0.05:
        pop_scale = 0.2
    target_size = max(120, int((250 if aspect == "9:16" else 240) * pop_scale))
    owns_resized = True
    cached_prop = board_cache.get("prop_hold_resized") if board_cache is not None else None
    if (
        pop_p >= 1.0
        and isinstance(cached_prop, tuple)
        and len(cached_prop) == 2
        and cached_prop[0] == target_size
        and isinstance(cached_prop[1], Image.Image)
    ):
        resized = cached_prop[1]
        owns_resized = False
    else:
        resized = prop_img.resize((target_size, target_size), Image.Resampling.LANCZOS)
        if pop_p >= 1.0 and board_cache is not None:
            board_cache["prop_hold_resized"] = (target_size, resized)
            owns_resized = False

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
    if owns_resized:
        resized.close()


_ANIMATED_BOARD_TYPES: frozenset[str] = frozenset(
    {"counter_grow", "bar_compare", "location_map", "flow_steps", "timeline_era"}
)


def _is_dark_stage_bg(
    pal: dict[str, tuple[int, int, int, int]],
    theme: StickvTheme,
    domain: str,
) -> bool:
    if theme == "dark" or normalize_domain(domain) in (
        "physics_science",
        "cosmos_mystery",
        "psychology_story",
    ):
        return True
    r, g, b = pal["bg"][:3]
    return (0.299 * r + 0.587 * g + 0.114 * b) < 110.0


def _crop_rgba_layer(img: Image.Image) -> tuple[Image.Image, int, int] | None:
    """Cắt sát vùng pixel khác rỗng để bỏ phần nền trong suốt khi composite 60fps."""
    bbox = img.getbbox()
    if bbox is None:
        return None
    return img.crop(bbox), int(bbox[0]), int(bbox[1])


def _apply_dark_bg_rim_light(char_rgba: Image.Image) -> Image.Image:
    """Thêm viền sáng mảnh ~2px (#CBD5E1, 55% alpha) quanh silhouette trên nền tối."""
    bbox = char_rgba.getbbox()
    if bbox is None:
        return char_rgba.copy()
    px0 = max(0, bbox[0] - 4)
    py0 = max(0, bbox[1] - 4)
    px1 = min(char_rgba.width, bbox[2] + 4)
    py1 = min(char_rgba.height, bbox[3] + 4)
    sub = char_rgba.crop((px0, py0, px1, py1))
    try:
        a_ch = sub.getchannel("A")
        try:
            arr = np.asarray(a_ch, dtype=np.uint8)
        finally:
            a_ch.close()
        padded = np.pad(arr, 2, mode="edge")
        hmax = np.maximum.reduce([padded[2:-2, i : padded.shape[1] - 4 + i] for i in range(5)])
        vmax = np.maximum.reduce(
            [
                np.pad(hmax, ((2, 2), (0, 0)), mode="edge")[i : hmax.shape[0] + i, :]
                for i in range(5)
            ]
        )
        rim_a_arr = ((vmax.astype(np.uint16) * 140) // 255).astype(np.uint8)
        rim_arr = np.empty((sub.height, sub.width, 4), dtype=np.uint8)
        rim_arr[..., 0] = 203
        rim_arr[..., 1] = 213
        rim_arr[..., 2] = 225
        rim_arr[..., 3] = rim_a_arr
        rim_sub = Image.fromarray(rim_arr, mode="RGBA")
        try:
            rim_sub.alpha_composite(sub)
            out = Image.new("RGBA", char_rgba.size, (0, 0, 0, 0))
            out.paste(rim_sub, (px0, py0))
            return out
        finally:
            rim_sub.close()
    finally:
        sub.close()


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
    tween_dur: float = 0.55,
    spoken_segments: list[tuple[float, float, str]] | None = None,
    is_puppet: bool = False,
    total_chapters: int = 1,
    has_next_diff_title: bool = True,
    show_chapter_banner: bool = False,
    board_cache: dict[str, Any] | None = None,
    prev_board_img: Image.Image | None = None,
    mutate_bg: bool = False,
    karaoke_cache: dict[str, Any] | None = None,
    watermark_img: Image.Image | None = None,
    watermark_patch: tuple[Image.Image, int, int] | None = None,
    char_unscaled_size: tuple[int, int] | None = None,
) -> Image.Image:
    """Tổng hợp 1 frame động: backdrop + camera tách lớp + thẻ 2 tầng + puppet + karaoke."""
    w, h = bg_img.size
    pal = resolve_stage_palette(domain, theme)
    interaction = getattr(beat, "interaction", "none") or "none"
    camera_shot = getattr(beat, "camera_shot", "wide_stage") or "wide_stage"
    # Giữ nguyên thẻ recap_card ổn định ở beat CTA cuối khi beat liền trước đã là recap_card
    if (
        beat.board_type == "recap_card"
        and camera_shot == "closeup_react"
        and prev_stage_state is not None
        and getattr(prev_stage_state, "last_board_type", "") == "recap_card"
    ):
        camera_shot = "wide_stage"
    cam_layout = compute_layered_camera_layout(
        camera_shot,
        aspect=aspect,
        w=w,
        h=h,
        t_sec=t_sec,
        prev_stage_state=prev_stage_state,
    )

    owns_rgba = not (mutate_bg and bg_img.mode == "RGBA")
    if not owns_rgba:
        frame_rgba = bg_img
    elif bg_img.mode == "RGBA":
        frame_rgba = bg_img.copy()
    else:
        frame_rgba = bg_img.convert("RGBA")

    try:
        if interaction == "versus_split" and cam_layout.board_alpha > 0.05:
            if board_cache is not None:
                v_entry = board_cache.get("versus_layer")
                if v_entry is None:
                    v_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    try:
                        _draw_versus_split_layer(v_layer, beat, pal, aspect=aspect)
                        v_entry = _crop_rgba_layer(v_layer)
                    finally:
                        v_layer.close()
                    if v_entry is not None:
                        board_cache["versus_layer"] = v_entry
                if isinstance(v_entry, tuple) and isinstance(v_entry[0], Image.Image):
                    frame_rgba.alpha_composite(v_entry[0], (v_entry[1], v_entry[2]))
            else:
                _draw_versus_split_layer(frame_rgba, beat, pal, aspect=aspect)

        if draw_board:
            can_prebake = (
                board_cache is not None
                and beat.board_type not in _ANIMATED_BOARD_TYPES
                and t_sec >= 0.72
            )
            if can_prebake and board_cache is not None:
                baked = board_cache.get("static_board")
                if baked is None and "static_board_empty" not in board_cache:
                    tmp_baked = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    try:
                        _composite_transitioned_board(
                            tmp_baked,
                            beat,
                            cam_layout.board_box,
                            pal,
                            t_sec=t_sec,
                            duration_sec=duration_sec,
                            progress=1.0,
                            prop_img=prop_img,
                            prev_stage_state=prev_stage_state,
                            total_chapters=total_chapters,
                            has_next_diff_title=has_next_diff_title,
                            cam_board_scale=cam_layout.board_scale,
                            cam_board_alpha=cam_layout.board_alpha,
                            clamp_bounds=cam_layout.clamp_bounds,
                            anchor_top_center=cam_layout.anchor_top_center,
                            board_cache=board_cache,
                        )
                        baked = _crop_rgba_layer(tmp_baked)
                    finally:
                        tmp_baked.close()
                    if baked is not None:
                        board_cache["static_board"] = baked
                    else:
                        board_cache["static_board_empty"] = True
                if isinstance(baked, tuple) and isinstance(baked[0], Image.Image):
                    frame_rgba.alpha_composite(baked[0], (baked[1], baked[2]))
                elif isinstance(baked, Image.Image):
                    frame_rgba.alpha_composite(baked)
            else:
                anim_dur = max(0.5, float(duration_sec or 2.0) * 0.6)
                prog = min(1.0, max(0.0, t_sec / anim_dur))
                is_anim_type = beat.board_type in _ANIMATED_BOARD_TYPES
                if board_cache is not None and is_anim_type and t_sec >= 0.72:
                    step_q = int(round(prog * 30))
                    anim_entry = board_cache.get("anim_board_q")
                    if isinstance(anim_entry, tuple) and anim_entry[0] == step_q:
                        if len(anim_entry) == 4 and isinstance(anim_entry[1], Image.Image):
                            frame_rgba.alpha_composite(
                                anim_entry[1], (anim_entry[2], anim_entry[3])
                            )
                    else:
                        step_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                        try:
                            _composite_transitioned_board(
                                step_img,
                                beat,
                                cam_layout.board_box,
                                pal,
                                t_sec=t_sec,
                                duration_sec=duration_sec,
                                progress=step_q / 30.0,
                                prop_img=prop_img,
                                prev_stage_state=prev_stage_state,
                                total_chapters=total_chapters,
                                has_next_diff_title=has_next_diff_title,
                                cam_board_scale=cam_layout.board_scale,
                                cam_board_alpha=cam_layout.board_alpha,
                                clamp_bounds=cam_layout.clamp_bounds,
                                anchor_top_center=cam_layout.anchor_top_center,
                                prev_board_img=prev_board_img,
                                board_cache=board_cache,
                            )
                            cropped_step = _crop_rgba_layer(step_img)
                        finally:
                            step_img.close()
                        if isinstance(anim_entry, tuple) and len(anim_entry) >= 2:
                            old_im = anim_entry[1]
                            if isinstance(old_im, Image.Image):
                                old_im.close()
                        if cropped_step is not None:
                            c_im, c_ox, c_oy = cropped_step
                            board_cache["anim_board_q"] = (step_q, c_im, c_ox, c_oy)
                            frame_rgba.alpha_composite(c_im, (c_ox, c_oy))
                        else:
                            board_cache["anim_board_q"] = (step_q,)
                else:
                    _composite_transitioned_board(
                        frame_rgba,
                        beat,
                        cam_layout.board_box,
                        pal,
                        t_sec=t_sec,
                        duration_sec=duration_sec,
                        progress=prog,
                        prop_img=prop_img,
                        prev_stage_state=prev_stage_state,
                        total_chapters=total_chapters,
                        has_next_diff_title=has_next_diff_title,
                        cam_board_scale=cam_layout.board_scale,
                        cam_board_alpha=cam_layout.board_alpha,
                        clamp_bounds=cam_layout.clamp_bounds,
                        anchor_top_center=cam_layout.anchor_top_center,
                        prev_board_img=prev_board_img,
                        board_cache=board_cache,
                    )

        if aspect == "9:16" and camera_shot == "closeup_react" and cam_layout.board_alpha < 0.85:
            if board_cache is not None:
                pill_entry = board_cache.get("topic_pill_layer")
                if pill_entry is None:
                    pill_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    try:
                        _draw_compact_topic_pill(
                            pill_layer,
                            chapter=beat.chapter,
                            chapter_title=getattr(beat, "chapter_title", ""),
                            board_title=beat.board_title,
                            pal=pal,
                            aspect=aspect,
                            narration=beat.narration,
                            takeaway=getattr(beat, "takeaway", "")
                            or str((beat.board_data or {}).get("takeaway") or ""),
                            total_chapters=total_chapters,
                        )
                        pill_entry = _crop_rgba_layer(pill_layer)
                    finally:
                        pill_layer.close()
                    if pill_entry is not None:
                        board_cache["topic_pill_layer"] = pill_entry
                if isinstance(pill_entry, tuple) and isinstance(pill_entry[0], Image.Image):
                    frame_rgba.alpha_composite(pill_entry[0], (pill_entry[1], pill_entry[2]))
            else:
                _draw_compact_topic_pill(
                    frame_rgba,
                    chapter=beat.chapter,
                    chapter_title=getattr(beat, "chapter_title", ""),
                    board_title=beat.board_title,
                    pal=pal,
                    aspect=aspect,
                    narration=beat.narration,
                    takeaway=getattr(beat, "takeaway", "")
                    or str((beat.board_data or {}).get("takeaway") or ""),
                    total_chapters=total_chapters,
                )

        if interaction == "hold_prop" and prop_img is not None and cam_layout.board_alpha > 0.1:
            _composite_prop_overlay(
                frame_rgba,
                prop_img,
                aspect=aspect,
                t_sec=t_sec,
                pal=pal,
                board_cache=board_cache,
            )

        if char_img is not None:
            eff_cw, eff_ch = char_unscaled_size or (char_img.width, char_img.height)
            target_x, target_y, target_scale = compute_beat_character_target(
                w,
                h,
                eff_cw,
                eff_ch,
                interaction=interaction,
                aspect=aspect,
                camera_shot=camera_shot,
            )
            if prev_stage_state is not None and tween_dur > 0 and t_sec < tween_dur:
                p = _cosine_ease_in_out(t_sec / tween_dur)
                base_x = prev_stage_state.x + (target_x - prev_stage_state.x) * p
                base_y = prev_stage_state.y + (target_y - prev_stage_state.y) * p
                cur_scale = prev_stage_state.scale + (target_scale - prev_stage_state.scale) * p
            else:
                base_x, base_y, cur_scale = target_x, target_y, target_scale

            eff_char = char_img
            nw = max(32, int(round(eff_cw * cur_scale)))
            nh = max(32, int(round(eff_ch * cur_scale)))
            if char_img.size != (nw, nh) and abs(cur_scale - 1.0) > 0.01:
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

            if _is_dark_stage_bg(pal, theme, domain):
                rimmed = _apply_dark_bg_rim_light(eff_char)
                try:
                    frame_rgba.alpha_composite(rimmed, (px, py))
                finally:
                    rimmed.close()
            else:
                frame_rgba.alpha_composite(eff_char, (px, py))
            if eff_char is not char_img:
                eff_char.close()

        if total_chapters > 1 and show_chapter_banner and getattr(beat, "chapter_title", ""):
            _draw_chapter_banner(
                frame_rgba,
                chapter=beat.chapter,
                chapter_title=beat.chapter_title,
                t_sec=t_sec,
                pal=pal,
                aspect=aspect,
            )
        draw_karaoke_strip(
            frame_rgba,
            word_timings,
            t_sec,
            aspect=aspect,
            spoken_segments=spoken_segments,
            camera_shot=camera_shot,
            karaoke_cache=karaoke_cache,
        )
        if watermark_patch is not None:
            frame_rgba.alpha_composite(watermark_patch[0], (watermark_patch[1], watermark_patch[2]))
        elif watermark_img is not None and watermark_img.size == frame_rgba.size:
            frame_rgba.alpha_composite(watermark_img)
        return frame_rgba.convert("RGB")
    finally:
        if owns_rgba:
            frame_rgba.close()


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
