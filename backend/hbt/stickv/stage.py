"""Sân khấu diễn hoạt StickV v6.1: Bảng minh họa co giãn, Karaoke & Lip-sync mượt."""

from __future__ import annotations

import math
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

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
    raw_caption = (
        str(data.get("caption") or "").strip()
        or strip_rich_markup(beat.board_title or "").strip()
        or _extract_highlight_keyword(beat.narration)
    )
    cap_words = raw_caption.split()[:6]
    caption = " ".join(cap_words) if cap_words else "Ảnh tư liệu minh họa"

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

        # Chú thích ngắn 3-6 từ căn giữa ở mép dưới Polaroid
        f_cap = _load_font(FONT_BOLD, 28)
        cbb = d.textbbox((0, 0), caption, font=f_cap)
        tw = cbb[2] - cbb[0]
        th = cbb[3] - cbb[1]
        if tw > iw:
            f_cap = _load_font(FONT_BOLD, 22)
            cbb = d.textbbox((0, 0), caption, font=f_cap)
            tw = cbb[2] - cbb[0]
            th = cbb[3] - cbb[1]
        tx = cx0 + (card_w - tw) // 2
        ty = iy1 + (footer_h - th) // 2 - cbb[1]
        d.text((tx, ty), caption, font=f_cap, fill=(30, 41, 59, 255))

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
            if content_alpha < 0.995:
                a_band = tilted.getchannel("A").point(
                    lambda p: int(round(p * max(0.0, min(1.0, content_alpha))))
                )
                tilted.putalpha(a_band)
            dest_x = x0 + (bw - tilted.width) // 2
            dest_y = y0 + (bh - tilted.height) // 2
            canvas.alpha_composite(tilted, (dest_x, dest_y))
            return dest_x, dest_y, dest_x + tilted.width, dest_y + tilted.height
        finally:
            tilted.close()
    finally:
        polaroid.close()


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
    """Vẽ bảng minh họa 100% beat (gồm thẻ tự động `none` & thẻ Polaroid `pinned_photo`)."""
    if beat.board_type == "pinned_photo":
        return _draw_pinned_photo_card(
            canvas, beat, box, pal, photo_img=prop_img, content_alpha=content_alpha
        )
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
    takeaway = str(getattr(beat, "takeaway", "") or data.get("takeaway") or "").strip()
    hl_fill = _highlight_color_for_card(pal)

    tmp_draw = ImageDraw.Draw(canvas)
    est_h = 104
    eff_title = beat.board_title or (
        _extract_highlight_keyword(beat.narration) if beat.board_type == "none" else ""
    )
    if eff_title:
        th = _measure_rich_wrapped_height(
            tmp_draw, eff_title, f_title, max_width_px=max(200, bw - 140), line_gap=8
        )
        est_h += max(58, th + 16)

    if beat.board_type in ("none", "bullets", "list", "card"):
        items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:3]
        if not items and beat.board_type == "none":
            clauses = [
                c.strip()
                for c in re.split(r"[.;:!?…]", (beat.narration or "").strip())
                if len(c.strip().split()) >= 3
            ]
            items = clauses[:2] or [beat.narration[:70]]
        for it in items:
            ih = _measure_rich_wrapped_height(
                tmp_draw, it, f_body, max_width_px=max(200, bw - 96), line_gap=8
            )
            est_h += max(56, ih) + 22
    elif beat.board_type == "recap_card":
        est_h += 300
    elif beat.board_type in ("big_number", "counter_grow"):
        est_h += 240
    elif beat.board_type == "quote":
        q_txt = str(data.get("quote") or data.get("text") or beat.narration or "")
        qh = _measure_rich_wrapped_height(
            tmp_draw, q_txt, f_body, max_width_px=max(200, bw - 110), line_gap=12
        )
        est_h += max(140, qh + 64)
    elif beat.board_type == "comparison":
        left_items = [str(x) for x in (data.get("left_items") or []) if str(x).strip()][:4]
        right_items = [str(x) for x in (data.get("right_items") or []) if str(x).strip()][:4]
        col_w_px = max(140, (bw - 120) // 2)
        lh = sum(
            _measure_rich_wrapped_height(
                tmp_draw, f"• {x}", f_sub, max_width_px=col_w_px, line_gap=6
            )
            + 8
            for x in left_items
        )
        rh = sum(
            _measure_rich_wrapped_height(
                tmp_draw, f"✓ {x}", f_sub, max_width_px=col_w_px, line_gap=6
            )
            + 8
            for x in right_items
        )
        est_h += 96 + max(110, lh, rh)
    elif beat.board_type == "bar_compare":
        bars = (data.get("values") or data.get("bars") or [])[:4]
        est_h += max(230, len(bars) * 82 + 44)
    elif beat.board_type == "flow_steps":
        steps = [str(s) for s in (data.get("steps") or data.get("items") or []) if str(s).strip()][
            :4
        ]
        for stp in steps:
            sh = _measure_rich_wrapped_height(
                tmp_draw, stp, f_sub, max_width_px=max(180, bw - 160), line_gap=6, max_lines=2
            )
            est_h += max(78, sh + 34) + 14
    elif beat.board_type == "timeline_era":
        ev_count = max(2, len((data.get("events") or data.get("items") or [])[:4]))
        est_h += ev_count * 88 + 24
    elif beat.board_type == "location_map":
        est_h += 260
    elif beat.board_type == "myth_vs_fact":
        m_txt = str(data.get("myth") or data.get("left") or "Lầm tưởng phổ biến")
        f_txt = str(data.get("fact") or data.get("right") or beat.narration or "Sự thật thực tế")
        mh = _measure_rich_wrapped_height(
            tmp_draw, m_txt, f_sub, max_width_px=max(200, bw - 120), line_gap=8, max_lines=4
        )
        fh = _measure_rich_wrapped_height(
            tmp_draw, f_txt, f_sub, max_width_px=max(200, bw - 120), line_gap=8, max_lines=4
        )
        est_h += max(108, mh + 64) + max(108, fh + 64) + 28

    if takeaway:
        est_h += 92

    # Co giãn thông minh theo mật độ thực tế (đủ đầy đặn nhưng không dư khoảng trống > 25%)
    min_ratio = 0.68 if beat.board_type in ("myth_vs_fact", "comparison") else 0.84
    min_card_h = max(280, int(round((max_y1 - y0) * min_ratio)))
    card_h = min(max_y1 - y0, max(min_card_h, est_h + 36))
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

        badge_txt = BOARD_BADGES.get(beat.board_type, "PHÂN TÍCH")
        bb = shell_draw.textbbox((0, 0), badge_txt, font=f_badge)
        badge_w = (bb[2] - bb[0]) + 32
        shell_draw.rounded_rectangle(
            (x0 + 32, y0 + 24, x0 + 32 + badge_w, y0 + 62),
            radius=999,
            fill=pal["accent"],
        )
        shell_draw.text((x0 + 48, y0 + 30), badge_txt, font=f_badge, fill=(255, 255, 255, 255))

        chap_txt = (
            f"CHƯƠNG {beat.chapter}"
            if total_chapters > 1
            else (beat.chapter_title or "KIẾN THỨC")[:18].upper()
        )
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
        cur_y = y0 + 84

        # TẦNG 1: Huy hiệu tròn Iconify 54x54 + Tiêu đề chính
        if beat.board_type in ("none", "bullets", "list", "card", "recap_card"):
            icon_sz = 56
            _draw_topic_circle_badge(inner_layer, (x0 + 62, cur_y + 28), icon_sz, pal, prop_img)
            title_x = x0 + 106
            title_max_w = max(200, bw - 140)
            if eff_title:
                cur_y = _draw_rich_wrapped_text(
                    draw,
                    eff_title,
                    (title_x, cur_y + 4),
                    f_title,
                    pal["text"],
                    hl_fill,
                    max_width_px=title_max_w,
                    line_gap=8,
                )
            cur_y = max(cur_y + 12, y0 + 156)
        elif eff_title:
            cur_y = _draw_rich_wrapped_text(
                draw,
                eff_title,
                (x0 + 36, cur_y),
                f_title,
                pal["text"],
                hl_fill,
                max_width_px=max(200, bw - 72),
                line_gap=10,
            )
            cur_y += 10

        content_bottom = y1 - (96 if takeaway else 28)

        if beat.board_type in ("none", "bullets", "list", "card"):
            # TẦNG 2: 2-3 ý phân tích có vạch nhấn màu trái & highlight **từ khóa**
            items = [str(it) for it in (data.get("items") or []) if str(it).strip()][:3]
            if not items:
                clauses = [
                    c.strip()
                    for c in re.split(r"[.;:!?…]", (beat.narration or "").strip())
                    if len(c.strip().split()) >= 3
                ]
                items = clauses[:2] or [(beat.narration or "Phân tích trọng tâm")[:75]]
            for idx, item in enumerate(items):
                if cur_y > content_bottom - 52:
                    break
                bar_c = pal["accent"] if idx % 2 == 0 else pal["amber"]
                row_top = cur_y + 4
                end_y = _draw_rich_wrapped_text(
                    draw,
                    item,
                    (x0 + 58, row_top),
                    f_body,
                    pal["text"],
                    hl_fill,
                    max_width_px=max(200, bw - 96),
                    line_gap=8,
                )
                draw.rounded_rectangle(
                    (x0 + 38, row_top + 2, x0 + 46, max(row_top + 30, end_y - 10)),
                    radius=4,
                    fill=bar_c,
                )
                cur_y = end_y + 10

        elif beat.board_type == "recap_card":
            # 3 thẻ ngang đúc kết kiến thức cốt lõi (1 · 2 · 3)
            recap_items = [
                str(it)
                for it in (data.get("items") or data.get("bullets") or [])
                if str(it).strip()
            ][:3]
            if not recap_items:
                recap_items = [
                    "Nắm vững cơ chế gốc",
                    "Loại bỏ lầm tưởng cũ",
                    "Áp dụng ngay thực tế",
                ]
            slot_h = max(72, (content_bottom - cur_y - 24) // max(1, len(recap_items)) - 12)
            for idx, item in enumerate(recap_items, start=1):
                if cur_y > content_bottom - 58:
                    break
                cy1 = min(content_bottom - 8, cur_y + slot_h)
                fill_c = pal["takeaway_bg"] if idx % 2 == 1 else pal["pill_bg"]
                badge_c = pal["accent"] if idx == 1 else pal["amber"]
                draw.rounded_rectangle(
                    (x0 + 34, cur_y, x1 - 34, cy1),
                    radius=18,
                    fill=fill_c,
                    outline=badge_c,
                    width=2,
                )
                draw.ellipse((x0 + 48, cur_y + 14, x0 + 92, cur_y + 58), fill=badge_c)
                draw.text((x0 + 62, cur_y + 20), str(idx), font=f_body, fill=(255, 255, 255, 255))
                _draw_rich_wrapped_text(
                    draw,
                    item,
                    (x0 + 108, cur_y + 14),
                    f_body,
                    pal["text"],
                    hl_fill,
                    max_width_px=max(180, bw - 160),
                    line_gap=6,
                )
                cur_y = cy1 + 12

        elif beat.board_type == "quote":
            q_txt = str(data.get("quote") or data.get("text") or beat.narration or "")
            draw.rectangle((x0 + 36, cur_y + 8, x0 + 46, content_bottom - 18), fill=pal["accent"])
            _draw_rich_wrapped_text(
                draw,
                f'"{q_txt}"',
                (x0 + 68, cur_y + 8),
                f_body,
                pal["text"],
                hl_fill,
                max_width_px=max(200, bw - 110),
                line_gap=12,
            )

        elif beat.board_type == "counter_grow":
            raw_target = data.get("target", data.get("value", 100))
            try:
                target_num = float(
                    strip_rich_markup(str(raw_target)).replace(",", "").replace("%", "").strip()
                )
            except ValueError:
                target_num = 100.0
            unit = strip_rich_markup(str(data.get("unit") or "")).strip()
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
                _draw_rich_wrapped_text(
                    draw,
                    lbl,
                    (x0 + 44, cur_y),
                    f_title,
                    pal["text"],
                    hl_fill,
                    max_width_px=max(200, bw - 88),
                    line_gap=8,
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
                draw_rich_text_line(
                    draw,
                    lbl,
                    (x0 + 40, cur_y),
                    f_sub,
                    pal["text"],
                    hl_fill,
                    max_width_px=max(120, bw - 190),
                )
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
            val = strip_rich_markup(str(data.get("value") or "100%"))
            lbl = str(data.get("label") or "")
            sub = str(data.get("sub") or "")
            draw.text((x0 + 44, cur_y + 4), val, font=f_big, fill=pal["accent"])
            bbox = draw.textbbox((x0 + 44, cur_y + 4), val, font=f_big)
            cur_y = bbox[3] + 22
            if lbl:
                cur_y = _draw_rich_wrapped_text(
                    draw,
                    lbl,
                    (x0 + 44, cur_y),
                    f_title,
                    pal["text"],
                    hl_fill,
                    max_width_px=max(200, bw - 88),
                    line_gap=8,
                )
            if sub:
                _draw_rich_wrapped_text(
                    draw,
                    sub,
                    (x0 + 44, cur_y + 6),
                    f_sub,
                    pal["muted"],
                    hl_fill,
                    max_width_px=max(200, bw - 88),
                    line_gap=8,
                )

        elif beat.board_type == "comparison":
            mid_x = (x0 + x1) // 2
            col_gap = 18
            lx0, lx1 = x0 + 32, mid_x - col_gap
            rx0, rx1 = mid_x + col_gap, x1 - 32
            col_w_px = max(120, lx1 - lx0 - 32)
            box_bottom = max(cur_y + 120, content_bottom - 10)
            draw.rounded_rectangle(
                (lx0, cur_y, lx1, box_bottom),
                radius=18,
                fill=pal["takeaway_bg"],
                outline=pal["card_border"],
                width=2,
            )
            draw.rounded_rectangle(
                (rx0, cur_y, rx1, box_bottom),
                radius=18,
                fill=pal["pill_bg"],
                outline=pal["accent"],
                width=2,
            )
            draw.ellipse((mid_x - 26, cur_y + 8, mid_x + 26, cur_y + 60), fill=pal["accent"])
            draw.text((mid_x - 16, cur_y + 22), "VS", font=f_badge, fill=(255, 255, 255, 255))

            left_t = str(data.get("left_title") or "Trước")
            right_t = str(data.get("right_title") or "Sau")
            draw_rich_text_line(
                draw,
                left_t,
                (lx0 + 16, cur_y + 14),
                f_body,
                pal["muted"],
                hl_fill,
                max_width_px=col_w_px,
            )
            draw_rich_text_line(
                draw,
                right_t,
                (rx0 + 16, cur_y + 14),
                f_body,
                pal["accent"],
                hl_fill,
                max_width_px=col_w_px,
            )
            ly = cur_y + 66
            ry = cur_y + 66
            for item in (data.get("left_items") or [])[:4]:
                if ly > box_bottom - 34:
                    break
                ly = (
                    _draw_rich_wrapped_text(
                        draw,
                        f"• {item}",
                        (lx0 + 16, ly),
                        f_sub,
                        pal["text"],
                        hl_fill,
                        max_width_px=col_w_px,
                        line_gap=6,
                    )
                    + 8
                )
            for item in (data.get("right_items") or [])[:4]:
                if ry > box_bottom - 34:
                    break
                ry = (
                    _draw_rich_wrapped_text(
                        draw,
                        f"✓ {item}",
                        (rx0 + 16, ry),
                        f_sub,
                        pal["text"],
                        hl_fill,
                        max_width_px=col_w_px,
                        line_gap=6,
                    )
                    + 8
                )

        elif beat.board_type == "flow_steps":
            steps = [
                str(s) for s in (data.get("steps") or data.get("items") or []) if str(s).strip()
            ][:4]
            active_count = max(1, int(math.ceil(prog * max(1, len(steps)))))
            n_steps = max(1, len(steps))
            avail_h = max(160, content_bottom - cur_y - 8)
            step_gap = 14
            max_slot_h = max(72, (avail_h - step_gap * (n_steps - 1)) // n_steps)
            text_max_w = max(180, bw - 168)
            for idx, step in enumerate(steps, start=1):
                if cur_y > content_bottom - 58:
                    break
                lit = idx <= active_count
                fill_c = pal["pill_bg"] if lit else pal["takeaway_bg"]
                out_c = pal["accent"] if lit else pal["card_border"]
                needed_h = _measure_rich_wrapped_height(
                    draw, step, f_sub, max_width_px=text_max_w, line_gap=6, max_lines=2
                )
                box_h = min(max_slot_h, max(72, needed_h + 24))
                cy1 = min(content_bottom - 6, cur_y + box_h)
                draw.rounded_rectangle(
                    (x0 + 36, cur_y, x1 - 36, cy1),
                    radius=18,
                    fill=fill_c,
                    outline=out_c,
                    width=3 if lit else 2,
                )
                badge_r = 20
                bx = x0 + 68
                by = (cur_y + cy1) // 2
                draw.ellipse(
                    (bx - badge_r, by - badge_r, bx + badge_r, by + badge_r),
                    fill=pal["accent"] if lit else pal["amber"],
                )
                nbb = draw.textbbox((0, 0), str(idx), font=f_badge)
                draw.text(
                    (bx - (nbb[2] - nbb[0]) // 2, by - (nbb[3] - nbb[1]) // 2 - nbb[1]),
                    str(idx),
                    font=f_badge,
                    fill=(255, 255, 255, 255),
                )
                _draw_rich_wrapped_text(
                    draw,
                    step,
                    (x0 + 104, cur_y + 14),
                    f_sub,
                    pal["pill_text"],
                    hl_fill,
                    max_width_px=text_max_w,
                    line_gap=6,
                    max_lines=2,
                )
                cur_y = cy1 + step_gap

        elif beat.board_type == "timeline_era":
            raw_ev = data.get("events") or data.get("items") or []
            events: list[tuple[str, str]] = []
            for idx, ev in enumerate(raw_ev[:4]):
                if isinstance(ev, dict):
                    events.append(
                        (
                            strip_rich_markup(
                                str(ev.get("year") or ev.get("era") or f"Mốc {idx + 1}")
                            ),
                            str(ev.get("title") or ev.get("label") or ev.get("text") or ""),
                        )
                    )
                else:
                    s = str(ev)
                    if ":" in s:
                        yr, tt = s.split(":", 1)
                        events.append((strip_rich_markup(yr).strip(), tt.strip()))
                    else:
                        events.append((f"Mốc {idx + 1}", s))
            if not events:
                events = [("Cổ đại", _extract_highlight_keyword(beat.narration))]
            spine_x = x0 + 62
            end_y = min(content_bottom - 18, cur_y + len(events) * 86 - 20)
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
                _draw_rich_wrapped_text(
                    draw,
                    ev_txt,
                    (spine_x + 28, cur_y + 30),
                    f_sub,
                    pal["text"],
                    hl_fill,
                    max_width_px=max(160, bw - 130),
                    line_gap=6,
                    max_lines=2,
                )
                cur_y += 84

        elif beat.board_type == "location_map":
            loc_name = str(
                data.get("location") or data.get("place") or eff_title or "Di tích cổ đại"
            )
            coords = strip_rich_markup(
                str(data.get("coordinates") or data.get("region") or "29.9792° N, 31.1342° E")
            )
            map_x0, map_y0, map_x1, map_y1 = x0 + 36, cur_y + 4, x1 - 36, content_bottom - 10
            draw.rounded_rectangle(
                (map_x0, map_y0, map_x1, map_y1),
                radius=22,
                fill=pal["takeaway_bg"],
                outline=pal["amber"],
                width=2,
            )
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
            draw_rich_text_line(
                draw,
                loc_name,
                (map_x0 + 20, map_y0 + 14),
                f_body,
                pal["text"],
                hl_fill,
                max_width_px=max(140, (map_x1 - map_x0) - 40),
            )
            draw.text((map_x0 + 20, map_y1 - 40), coords[:40], font=f_badge, fill=pal["pill_text"])

        elif beat.board_type == "myth_vs_fact":
            myth_title = str(data.get("myth_title") or "").strip()
            fact_title = str(data.get("fact_title") or "").strip()
            myth_raw = str(data.get("myth") or data.get("left") or "Lầm tưởng phổ biến").strip()
            fact_raw = str(
                data.get("fact") or data.get("right") or beat.narration or "Sự thật khoa học"
            ).strip()
            myth_full = f"**{myth_title}:** {myth_raw}" if myth_title else myth_raw
            fact_full = f"**{fact_title}:** {fact_raw}" if fact_title else fact_raw

            text_w = max(200, bw - 116)
            m_text_h = _measure_rich_wrapped_height(
                draw, myth_full, f_sub, max_width_px=text_w, line_gap=8, max_lines=4
            )
            f_text_h = _measure_rich_wrapped_height(
                draw, fact_full, f_sub, max_width_px=text_w, line_gap=8, max_lines=4
            )
            avail_h = max(200, content_bottom - cur_y - 16)
            m_want = max(96, m_text_h + 56)
            f_want = max(96, f_text_h + 56)
            total_want = m_want + f_want
            if total_want > avail_h:
                ratio = avail_h / total_want
                m_h = max(84, int(round(m_want * ratio)))
                f_h = max(84, avail_h - m_h)
            else:
                # Co giãn gọn gàng quanh chiều cao nội dung (trống thừa <= 25%)
                slack = min(int(round(total_want * 0.20)), avail_h - total_want)
                m_h = m_want + slack // 2
                f_h = f_want + (slack - slack // 2)

            # Tầng LẦM TƯỞNG
            draw.rounded_rectangle(
                (x0 + 36, cur_y, x1 - 36, cur_y + m_h),
                radius=18,
                fill=(254, 226, 226, 235),
                outline=(220, 38, 38, 255),
                width=2,
            )
            draw.text((x0 + 54, cur_y + 12), "✕ LẦM TƯỞNG", font=f_badge, fill=(185, 28, 28, 255))
            _draw_rich_wrapped_text(
                draw,
                myth_full,
                (x0 + 54, cur_y + 44),
                f_sub,
                (69, 10, 10, 255),
                (185, 28, 28, 255),
                max_width_px=text_w,
                line_gap=8,
                max_lines=4,
            )
            # Tầng SỰ THẬT
            fy0 = cur_y + m_h + 14
            draw.rounded_rectangle(
                (x0 + 36, fy0, x1 - 36, fy0 + f_h),
                radius=18,
                fill=(209, 250, 229, 240),
                outline=(5, 150, 105, 255),
                width=2,
            )
            draw.text((x0 + 54, fy0 + 12), "✓ SỰ THẬT", font=f_badge, fill=(4, 120, 87, 255))
            _draw_rich_wrapped_text(
                draw,
                fact_full,
                (x0 + 54, fy0 + 44),
                f_sub,
                (6, 78, 59, 255),
                (4, 120, 87, 255),
                max_width_px=text_w,
                line_gap=8,
                max_lines=4,
            )

        if takeaway:
            ty0 = y1 - 80
            draw.rounded_rectangle(
                (x0 + 28, ty0, x1 - 28, y1 - 18),
                radius=16,
                fill=pal["takeaway_bg"],
                outline=pal["amber"],
                width=2,
            )
            draw_rich_text_line(
                draw,
                f"**CHỐT LẠI:** {takeaway}",
                (x0 + 46, ty0 + 16),
                f_sub,
                pal["pill_text"],
                hl_fill,
                max_width_px=max(180, bw - 92),
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
    cam_board_scale: float = 1.0,
    cam_board_alpha: float = 1.0,
    clamp_bounds: tuple[int, int, int, int] | None = None,
    anchor_top_center: tuple[float, float] | None = None,
) -> None:
    """Chuyển tiếp thẻ không hard-cut + tách lớp camera kẹp biên an toàn (không cắt chữ)."""
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

    enter_t = 0.35 if beat.board_type == "pinned_photo" else 0.30
    exit_t = 0.35 if beat.board_type == "pinned_photo" else 0.22
    scale = float(cam_board_scale)
    dy_px = 0.0
    alpha = float(cam_board_alpha)
    if not same_title:
        if t_sec < enter_t:
            u = _ease_out_cubic(t_sec / enter_t)
            scale *= 0.96 + 0.04 * u
            dy_px = 18.0 * (1.0 - u)
            alpha *= u
        elif (
            has_next_diff_title
            and duration_sec > (enter_t + exit_t)
            and t_sec > (duration_sec - exit_t)
        ):
            u = _ease_in_cubic((t_sec - (duration_sec - exit_t)) / exit_t)
            dy_px = -14.0 * u
            alpha *= 1.0 - u

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
                    a_band = scaled.getchannel("A").point(
                        lambda p: int(round(p * max(0.0, min(1.0, alpha))))
                    )
                    scaled.putalpha(a_band)
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
            sub.close()
    finally:
        layer.close()


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
) -> None:
    """Vẽ dải phụ đề Karaoke khóa câu đang nói, có đệm highlight >= 14px chống dính chữ."""
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
                if wst >= (seg_st - 0.01) and wet <= (seg_et + 0.01)
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
    font, strip_box, layout_items = compute_karaoke_word_boxes(
        [wd for wd, _, _ in chunk],
        active_local,
        frame_w=w,
        base_y=base_y,
        aspect=aspect,
    )
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
                0.82,
                0.36 * w,
                0.91 * h,
            )
        if shot_key == "closeup_react":
            return base_box, 1.0, 0.0, None, None, 1.22, 0.50 * w, 0.93 * h
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
    transition_dur: float = 0.55,
) -> LayeredCameraLayout:
    """Tính tách lớp camera kẹp biên an toàn (mờ bảng mượt 0.30s ở closeup_react)."""
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

    u = _ease_in_out(min(1.0, t_sec / transition_dur))
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
) -> None:
    """Vẽ huy hiệu Chương + dải Quote/Từ khóa nổi bật (2–6 từ) ở vùng trên khi `closeup_react`."""
    w, h = frame_rgba.size
    sy = h / (1920.0 if aspect == "9:16" else 1080.0)
    sx = w / (1080.0 if aspect == "9:16" else 1920.0)
    raw_lbl = strip_rich_markup(chapter_title or f"Chương {chapter}").strip()
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
        target_h = int(h * 0.38)
        if char_h > target_h and char_h > 0:
            scale = (target_h / char_h) * cam.char_scale
        eff_w = char_w * scale
        eff_h = char_h * scale
        bx = w * 0.24 - eff_w * 0.5
        by = cam.char_foot_y - eff_h
        return bx, by, scale

    eff_w = char_w * scale
    eff_h = char_h * scale
    if interaction == "hold_prop" and aspect == "9:16":
        cx = w * (0.34 if cam.char_scale <= 1.0 else 0.50)
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
    """Tổng hợp 1 frame động: backdrop + camera tách lớp + thẻ 2 tầng + puppet + karaoke."""
    frame = bg_img.copy()
    w, h = frame.size
    pal = resolve_stage_palette(domain, theme)
    interaction = getattr(beat, "interaction", "none") or "none"
    camera_shot = getattr(beat, "camera_shot", "wide_stage") or "wide_stage"
    cam_layout = compute_layered_camera_layout(
        camera_shot,
        aspect=aspect,
        w=w,
        h=h,
        t_sec=t_sec,
        prev_stage_state=prev_stage_state,
    )

    frame_rgba = frame.convert("RGBA")
    try:
        if interaction == "versus_split" and cam_layout.board_alpha > 0.05:
            _draw_versus_split_layer(frame_rgba, beat, pal, aspect=aspect)

        if draw_board:
            anim_dur = max(0.5, float(duration_sec or 2.0) * 0.6)
            prog = min(1.0, max(0.0, t_sec / anim_dur))
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
            )

        if aspect == "9:16" and camera_shot == "closeup_react" and cam_layout.board_alpha < 0.85:
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
            )

        if interaction == "hold_prop" and prop_img is not None and cam_layout.board_alpha > 0.1:
            _composite_prop_overlay(frame_rgba, prop_img, aspect=aspect, t_sec=t_sec, pal=pal)

        if char_img is not None:
            target_x, target_y, target_scale = compute_beat_character_target(
                w,
                h,
                char_img.width,
                char_img.height,
                interaction=interaction,
                aspect=aspect,
                camera_shot=camera_shot,
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

        if show_chapter_banner and getattr(beat, "chapter_title", ""):
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
        )
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
