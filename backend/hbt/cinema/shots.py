"""6 Ngữ pháp Khung hình độc bản 'HBT Tactile Desk' (9:16 & 16:9) với pre-bake 1 lần/beat."""

from __future__ import annotations

import re
import textwrap
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageFilter
from pydantic import BaseModel

from hbt.cinema.layer_cache import FontCache
from hbt.cinema.preflight import default_boxes_for_shot
from hbt.cinema.schema import ASPECT_DIMENSIONS, AspectRatio, BBox, BeatSpec, CinemaTheme, ShotType
from hbt.config import REPO_ROOT
from hbt.stickv.stage import BOARD_BADGES, resolve_stage_palette

FONTS_DIR = REPO_ROOT / "backend" / "hbt" / "fonts"
FONT_EXTRABOLD = FONTS_DIR / "BeVietnamPro-ExtraBold.ttf"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = FONTS_DIR / "BeVietnamPro-Medium.ttf"

CardStyle = Literal[
    "desk_card",
    "hero_full",
    "split_vs",
    "data_big",
    "topic_pill",
    "recap_grid",
]

_SHOT_TO_STYLE: dict[ShotType, CardStyle] = {
    "desk_wide": "desk_card",
    "card_hero": "hero_full",
    "split_compare": "split_vs",
    "data_spotlight": "data_big",
    "puppet_closeup": "topic_pill",
    "recap_grid": "recap_grid",
}

_BOLD_SEG_RE = re.compile(r"(\*\*[^*]+\*\*)")


class ShotLayout(BaseModel):
    """Bố cục hình học hoàn chỉnh cho 1 beat trên khung canvas đích."""

    shot_type: ShotType
    aspect: AspectRatio
    card_style: CardStyle
    board_box: BBox
    puppet_box: BBox
    karaoke_box: BBox


def _scale_box(box: BBox, sx: float, sy: float) -> BBox:
    return BBox(
        x=round(box.x * sx, 2),
        y=round(box.y * sy, 2),
        w=round(box.w * sx, 2),
        h=round(box.h * sy, 2),
    )


def compute_shot_layout(
    shot_type: ShotType,
    aspect: AspectRatio,
    *,
    beat: BeatSpec | None = None,
    width: int | None = None,
    height: int | None = None,
) -> ShotLayout:
    """Tính tọa độ bộ 3 lớp (board, puppet, karaoke) chuẩn Safe-Zone cho cả 6 góc máy."""
    base_w, base_h = ASPECT_DIMENSIONS[aspect]
    target_w = int(width or base_w)
    target_h = int(height or base_h)
    sx = target_w / max(1, base_w)
    sy = target_h / max(1, base_h)

    def_b, def_p, def_k = default_boxes_for_shot(shot_type, aspect)
    b_box = beat.board.bbox if (beat is not None and beat.board.bbox is not None) else def_b
    p_box = beat.puppet.bbox if (beat is not None and beat.puppet.bbox is not None) else def_p
    k_box = beat.karaoke_bbox if (beat is not None and beat.karaoke_bbox is not None) else def_k

    return ShotLayout(
        shot_type=shot_type,
        aspect=aspect,
        card_style=_SHOT_TO_STYLE[shot_type],
        board_box=_scale_box(b_box, sx, sy),
        puppet_box=_scale_box(p_box, sx, sy),
        karaoke_box=_scale_box(k_box, sx, sy),
    )


def _draw_rich_line(
    draw: ImageDraw.ImageDraw,
    pos: tuple[int, int],
    line: str,
    *,
    font_reg: Any,
    font_bold: Any,
    base_color: tuple[int, int, int, int],
    hi_color: tuple[int, int, int, int],
) -> None:
    x, y = pos
    parts = _BOLD_SEG_RE.split(line)
    for part in parts:
        if not part:
            continue
        is_hi = part.startswith("**") and part.endswith("**") and len(part) > 4
        txt = part[2:-2] if is_hi else part
        fnt = font_bold if is_hi else font_reg
        col = hi_color if is_hi else base_color
        draw.text((x, y), txt, font=fnt, fill=col)
        bb = draw.textbbox((0, 0), txt, font=fnt)
        x += max(1, bb[2] - bb[0])


def _draw_tactile_desk_bg(
    canvas: Image.Image,
    *,
    pal: dict[str, tuple[int, int, int, int]],
    scale: float,
) -> None:
    w, h = canvas.size
    draw = ImageDraw.Draw(canvas)
    step = max(24, int(round(64 * scale)))
    grid_c = pal["grid"]
    dot_c = (grid_c[0], grid_c[1], grid_c[2], 140)
    r = max(1, int(round(1.5 * scale)))
    for gx in range(step // 2, w, step):
        for gy in range(step // 2, h, step):
            draw.ellipse((gx - r, gy - r, gx + r, gy + r), fill=dot_c)

    pad = max(8, int(round(20 * scale)))
    draw.rounded_rectangle(
        (pad, pad, w - pad, h - pad),
        radius=max(10, int(round(24 * scale))),
        outline=(grid_c[0], grid_c[1], grid_c[2], 180),
        width=max(1, int(round(2 * scale))),
    )


def _draw_card_with_shadow(
    canvas: Image.Image,
    box: BBox,
    *,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    radius: int,
    scale: float,
) -> None:
    w, h = canvas.size
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    try:
        sdraw = ImageDraw.Draw(shadow)
        off_y = max(3, int(round(10 * scale)))
        sdraw.rounded_rectangle(
            (int(box.x), int(box.y + off_y), int(box.x2), int(box.y2 + off_y)),
            radius=radius,
            fill=(15, 23, 42, 46),
        )
        blurred = shadow.filter(ImageFilter.GaussianBlur(radius=max(2.0, 12.0 * scale)))
        try:
            canvas.alpha_composite(blurred)
        finally:
            blurred.close()
    finally:
        shadow.close()

    cdraw = ImageDraw.Draw(canvas)
    cdraw.rounded_rectangle(
        (int(box.x), int(box.y), int(box.x2), int(box.y2)),
        radius=radius,
        fill=fill,
        outline=outline,
        width=max(1, int(round(3 * scale))),
    )


def _draw_topic_pill_content(
    canvas: Image.Image,
    beat: BeatSpec,
    box: BBox,
    *,
    pal: dict[str, tuple[int, int, int, int]],
    scale: float,
    font_cache: FontCache,
) -> None:
    draw = ImageDraw.Draw(canvas)
    radius = max(14, int(box.h // 2))
    draw.rounded_rectangle(
        (int(box.x), int(box.y), int(box.x2), int(box.y2)),
        radius=radius,
        fill=pal["pill_bg"],
        outline=pal["accent"],
        width=max(1, int(round(2 * scale))),
    )
    f_pill = font_cache.get_font(FONT_BOLD, max(12, int(round(28 * scale))))
    label = (beat.chapter_title or beat.board.title or f"Chương {beat.chapter}").strip()[:42]
    bb = draw.textbbox((0, 0), label, font=f_pill)
    tx = int(box.x + (box.w - (bb[2] - bb[0])) / 2)
    ty = int(box.y + (box.h - (bb[3] - bb[1])) / 2 - bb[1])
    draw.text((tx, ty), label, font=f_pill, fill=pal["pill_text"])


def _draw_split_vs_body(
    draw: ImageDraw.ImageDraw,
    beat: BeatSpec,
    inner: tuple[int, int, int, int],
    *,
    pal: dict[str, tuple[int, int, int, int]],
    scale: float,
    font_cache: FontCache,
) -> None:
    ix0, iy0, ix1, iy1 = inner
    mid_x = (ix0 + ix1) // 2
    gap = max(8, int(round(16 * scale)))
    col_w = max(40, (ix1 - ix0 - gap * 2) // 2)

    left_txt = beat.board.bullets[0] if len(beat.board.bullets) > 0 else "Lầm tưởng phổ biến"
    right_txt = beat.board.bullets[1] if len(beat.board.bullets) > 1 else "Cơ chế thực tế"
    left_txt = left_txt.replace("**", "")
    right_txt = right_txt.replace("**", "")

    draw.rounded_rectangle(
        (ix0, iy0, ix0 + col_w, iy1),
        radius=max(8, int(round(16 * scale))),
        fill=(254, 226, 226, 220),
        outline=(220, 38, 38, 180),
        width=max(1, int(round(2 * scale))),
    )
    draw.rounded_rectangle(
        (ix1 - col_w, iy0, ix1, iy1),
        radius=max(8, int(round(16 * scale))),
        fill=(220, 252, 231, 220),
        outline=(22, 163, 74, 180),
        width=max(1, int(round(2 * scale))),
    )

    f_hdr = font_cache.get_font(FONT_EXTRABOLD, max(11, int(round(24 * scale))))
    f_body = font_cache.get_font(FONT_MEDIUM, max(11, int(round(25 * scale))))
    pad = max(8, int(round(16 * scale)))

    draw.text((ix0 + pad, iy0 + pad), "LẦM TƯỞNG", font=f_hdr, fill=(185, 28, 28, 255))
    draw.text((ix1 - col_w + pad, iy0 + pad), "SỰ THẬT", font=f_hdr, fill=(21, 128, 61, 255))

    wrap_w = max(12, int(col_w / max(8, int(14 * scale))))
    for idx_l, ln in enumerate(textwrap.wrap(left_txt, width=wrap_w)[:4]):
        draw.text(
            (ix0 + pad, iy0 + pad + int(round(40 * scale)) + idx_l * int(round(32 * scale))),
            ln,
            font=f_body,
            fill=(15, 23, 42, 255),
        )
    for idx_r, ln in enumerate(textwrap.wrap(right_txt, width=wrap_w)[:4]):
        draw.text(
            (
                ix1 - col_w + pad,
                iy0 + pad + int(round(40 * scale)) + idx_r * int(round(32 * scale)),
            ),
            ln,
            font=f_body,
            fill=(15, 23, 42, 255),
        )

    vs_r = max(14, int(round(24 * scale)))
    vs_y = (iy0 + iy1) // 2
    draw.ellipse((mid_x - vs_r, vs_y - vs_r, mid_x + vs_r, vs_y + vs_r), fill=pal["accent"])
    f_vs = font_cache.get_font(FONT_EXTRABOLD, max(10, int(round(20 * scale))))
    vbb = draw.textbbox((0, 0), "VS", font=f_vs)
    draw.text(
        (mid_x - (vbb[2] - vbb[0]) // 2, vs_y - (vbb[3] - vbb[1]) // 2 - vbb[1]),
        "VS",
        font=f_vs,
        fill=(255, 255, 255, 255),
    )


def _draw_recap_grid_body(
    draw: ImageDraw.ImageDraw,
    beat: BeatSpec,
    inner: tuple[int, int, int, int],
    *,
    pal: dict[str, tuple[int, int, int, int]],
    scale: float,
    font_cache: FontCache,
) -> None:
    ix0, iy0, ix1, iy1 = inner
    items = (beat.board.bullets or ["Ý chính 1", "Ý chính 2", "Ý chính 3"])[:3]
    row_gap = max(6, int(round(12 * scale)))
    row_h = max(36, (iy1 - iy0 - row_gap * 2) // 3)
    f_num = font_cache.get_font(FONT_EXTRABOLD, max(12, int(round(26 * scale))))
    f_txt = font_cache.get_font(FONT_BOLD, max(11, int(round(26 * scale))))
    f_reg = font_cache.get_font(FONT_MEDIUM, max(11, int(round(26 * scale))))

    for i, item in enumerate(items):
        ry0 = iy0 + i * (row_h + row_gap)
        ry1 = min(iy1, ry0 + row_h)
        draw.rounded_rectangle(
            (ix0, ry0, ix1, ry1),
            radius=max(8, int(round(14 * scale))),
            fill=pal["takeaway_bg"],
            outline=pal["amber"],
            width=max(1, int(round(2 * scale))),
        )
        badge_r = max(12, int(round(22 * scale)))
        bx = ix0 + max(14, int(round(28 * scale)))
        by = (ry0 + ry1) // 2
        draw.ellipse((bx - badge_r, by - badge_r, bx + badge_r, by + badge_r), fill=pal["accent"])
        num_s = str(i + 1)
        nbb = draw.textbbox((0, 0), num_s, font=f_num)
        draw.text(
            (bx - (nbb[2] - nbb[0]) // 2, by - (nbb[3] - nbb[1]) // 2 - nbb[1]),
            num_s,
            font=f_num,
            fill=(255, 255, 255, 255),
        )
        clean_line = item.strip()[:54]
        _draw_rich_line(
            draw,
            (bx + badge_r + max(8, int(round(16 * scale))), by - max(8, int(round(15 * scale)))),
            clean_line,
            font_reg=f_reg,
            font_bold=f_txt,
            base_color=pal["text"],
            hi_color=pal["accent"],
        )


def _draw_data_big_body(
    draw: ImageDraw.ImageDraw,
    beat: BeatSpec,
    inner: tuple[int, int, int, int],
    *,
    pal: dict[str, tuple[int, int, int, int]],
    scale: float,
    font_cache: FontCache,
) -> None:
    ix0, iy0, ix1, iy1 = inner
    raw_val = str(beat.board.data.get("number") or beat.board.data.get("value") or "").strip()
    if not raw_val:
        joined = " ".join(beat.board.bullets)
        m = re.search(r"\d[\d.,]*\s*(?:%|ms|s|km|x|lần|năm|tỷ|triệu)?", joined, re.I)
        raw_val = m.group(0).strip() if m else "100%"

    f_big = font_cache.get_font(FONT_EXTRABOLD, max(24, int(round(78 * scale))))
    bb = draw.textbbox((0, 0), raw_val[:14], font=f_big)
    tx = ix0 + max(0, (ix1 - ix0 - (bb[2] - bb[0])) // 2)
    ty = iy0 + max(4, int(round(16 * scale)))
    draw.text((tx, ty), raw_val[:14], font=f_big, fill=pal["accent"])

    sub_y = ty + (bb[3] - bb[1]) + max(12, int(round(24 * scale)))
    f_reg = font_cache.get_font(FONT_MEDIUM, max(11, int(round(26 * scale))))
    f_bld = font_cache.get_font(FONT_BOLD, max(11, int(round(26 * scale))))
    for idx, bullet in enumerate((beat.board.bullets or [])[:2]):
        line_y = sub_y + idx * max(18, int(round(40 * scale)))
        if line_y + 20 > iy1:
            break
        _draw_rich_line(
            draw,
            (ix0 + max(8, int(round(16 * scale))), line_y),
            f"• {bullet[:52]}",
            font_reg=f_reg,
            font_bold=f_bld,
            base_color=pal["text"],
            hi_color=pal["amber"],
        )


def _draw_bullets_body(
    draw: ImageDraw.ImageDraw,
    beat: BeatSpec,
    inner: tuple[int, int, int, int],
    *,
    pal: dict[str, tuple[int, int, int, int]],
    scale: float,
    font_cache: FontCache,
) -> None:
    ix0, iy0, ix1, iy1 = inner
    f_reg = font_cache.get_font(FONT_MEDIUM, max(11, int(round(28 * scale))))
    f_bld = font_cache.get_font(FONT_BOLD, max(11, int(round(28 * scale))))
    items = (beat.board.bullets or ["Ý chính phân tích"])[:3]
    wrap_chars = max(18, int((ix1 - ix0) / max(8, int(15 * scale))))
    cur_y = iy0 + max(4, int(round(8 * scale)))
    line_step = max(16, int(round(38 * scale)))

    for item in items:
        if cur_y + line_step > iy1:
            break
        bar_h = max(14, int(round(28 * scale)))
        draw.rounded_rectangle(
            (ix0, cur_y + 4, ix0 + max(3, int(round(6 * scale))), cur_y + 4 + bar_h),
            radius=2,
            fill=pal["accent"],
        )
        for wrapped in textwrap.wrap(item.strip(), width=wrap_chars)[:2]:
            if cur_y + line_step > iy1:
                break
            _draw_rich_line(
                draw,
                (ix0 + max(10, int(round(18 * scale))), cur_y),
                wrapped,
                font_reg=f_reg,
                font_bold=f_bld,
                base_color=pal["text"],
                hi_color=pal["amber"] if pal["card"][0] < 80 else pal["accent"],
            )
            cur_y += line_step
        cur_y += max(4, int(round(10 * scale)))


def bake_static_shot_layer(
    beat: BeatSpec,
    layout: ShotLayout,
    *,
    domain: str = "paper_classic",
    theme: CinemaTheme = "cream",
    width: int = 1080,
    height: int = 1920,
    font_cache: FontCache | None = None,
) -> Image.Image:
    """Pre-bake 1 lần duy nhất lớp nền bàn làm việc + thẻ bảng + chữ tĩnh cho cả beat."""
    fc = font_cache or FontCache()
    pal = resolve_stage_palette(domain, theme)
    base_w, _ = ASPECT_DIMENSIONS[layout.aspect]
    scale = width / max(1, base_w)

    canvas = Image.new("RGBA", (width, height), pal["bg"])
    _draw_tactile_desk_bg(canvas, pal=pal, scale=scale)

    box = layout.board_box
    if beat.board.board_type == "none":
        return canvas

    if layout.card_style == "topic_pill":
        _draw_topic_pill_content(canvas, beat, box, pal=pal, scale=scale, font_cache=fc)
        return canvas

    radius = max(10, int(round(26 * scale)))
    _draw_card_with_shadow(
        canvas,
        box,
        fill=pal["card"],
        outline=pal["card_border"],
        radius=radius,
        scale=scale,
    )

    draw = ImageDraw.Draw(canvas)
    pad = max(12, int(round(28 * scale)))
    header_y = int(box.y + pad)

    # Huy hiệu loại bảng (Badge) + Tiêu đề chính
    badge_txt = BOARD_BADGES.get(beat.board.board_type, "PHÂN TÍCH")
    f_badge = fc.get_font(FONT_BOLD, max(10, int(round(20 * scale))))
    bbb = draw.textbbox((0, 0), badge_txt, font=f_badge)
    bw = (bbb[2] - bbb[0]) + max(14, int(round(28 * scale)))
    bh = max(20, int(round(36 * scale)))
    draw.rounded_rectangle(
        (int(box.x + pad), header_y, int(box.x + pad + bw), header_y + bh),
        radius=bh // 2,
        fill=pal["pill_bg"],
    )
    draw.text(
        (
            int(box.x + pad + (bw - (bbb[2] - bbb[0])) // 2),
            header_y + max(3, int(round(6 * scale))),
        ),
        badge_txt,
        font=f_badge,
        fill=pal["pill_text"],
    )

    title_txt = (beat.board.title or beat.chapter_title or "Phân tích chuyên sâu").strip()[:44]
    f_title = fc.get_font(FONT_EXTRABOLD, max(13, int(round(38 * scale))))
    title_y = header_y + bh + max(8, int(round(14 * scale)))
    draw.text((int(box.x + pad), title_y), title_txt, font=f_title, fill=pal["text"])
    tbb = draw.textbbox((0, 0), title_txt, font=f_title)
    body_top = title_y + (tbb[3] - tbb[1]) + max(10, int(round(18 * scale)))

    # Khối Chốt lại (Takeaway) ở đáy thẻ
    takeaway = (beat.board.takeaway or "").strip()
    take_h = max(28, int(round(60 * scale))) if takeaway else 0
    body_bot = int(box.y2 - pad - (take_h + max(8, int(round(14 * scale))) if takeaway else 0))

    inner = (int(box.x + pad), body_top, int(box.x2 - pad), max(body_top + 24, body_bot))
    if layout.card_style == "split_vs":
        _draw_split_vs_body(draw, beat, inner, pal=pal, scale=scale, font_cache=fc)
    elif layout.card_style == "recap_grid":
        _draw_recap_grid_body(draw, beat, inner, pal=pal, scale=scale, font_cache=fc)
    elif layout.card_style == "data_big":
        _draw_data_big_body(draw, beat, inner, pal=pal, scale=scale, font_cache=fc)
    else:
        _draw_bullets_body(draw, beat, inner, pal=pal, scale=scale, font_cache=fc)

    if takeaway:
        ty0 = int(box.y2 - pad - take_h)
        ty1 = int(box.y2 - pad)
        draw.rounded_rectangle(
            (int(box.x + pad), ty0, int(box.x2 - pad), ty1),
            radius=max(8, int(round(14 * scale))),
            fill=pal["takeaway_bg"],
            outline=pal["accent"],
            width=max(1, int(round(2 * scale))),
        )
        f_tk = fc.get_font(FONT_BOLD, max(10, int(round(22 * scale))))
        tk_txt = f"CHỐT LẠI: {takeaway[:52]}"
        t_bb = draw.textbbox((0, 0), tk_txt, font=f_tk)
        draw.text(
            (
                int(box.x + pad + max(8, int(round(14 * scale)))),
                ty0 + max(4, (take_h - (t_bb[3] - t_bb[1])) // 2 - t_bb[1]),
            ),
            tk_txt,
            font=f_tk,
            fill=pal["text"],
        )

    return canvas
