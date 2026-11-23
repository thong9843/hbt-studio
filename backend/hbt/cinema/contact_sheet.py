"""Bộ xuất Contact Sheet 1 trang duyệt toàn bộ timeline (< 2.0 giây)."""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from hbt.cinema.layer_cache import FontCache
from hbt.cinema.preflight import PreflightReport, default_boxes_for_shot
from hbt.cinema.schema import BeatSpec, TimelineSpec
from hbt.config import REPO_ROOT

FONTS_DIR = REPO_ROOT / "backend" / "hbt" / "fonts"
FONT_BOLD = FONTS_DIR / "BeVietnamPro-Bold.ttf"
FONT_MEDIUM = FONTS_DIR / "BeVietnamPro-Medium.ttf"

_SHOT_LABELS_VI: dict[str, str] = {
    "desk_wide": "Toàn cảnh Bàn",
    "card_hero": "Thẻ Trung tâm",
    "split_compare": "Đối chiếu 2 Cột",
    "data_spotlight": "Tiêu điểm Số liệu",
    "puppet_closeup": "Cận Biểu cảm",
    "recap_grid": "Tổng kết 3 Ý",
}


def _atomic_save_image(img: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ext = out_path.suffix.lower()
    fmt = "PNG" if ext == ".png" else "JPEG"
    tmp = out_path.with_name(f"{out_path.name}.tmp")
    try:
        save_img = img.convert("RGB") if fmt == "JPEG" and img.mode != "RGB" else img
        try:
            save_kwargs: dict[str, Any] = {"format": fmt}
            if fmt == "JPEG":
                save_kwargs["quality"] = 88
            save_img.save(tmp, **save_kwargs)
        finally:
            if save_img is not img:
                save_img.close()
        os.replace(tmp, out_path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _draw_mini_beat_card(
    draw: ImageDraw.ImageDraw,
    beat: BeatSpec,
    idx: int,
    *,
    cell_x: int,
    cell_y: int,
    cell_w: int,
    thumb_h: int,
    src_w: int,
    src_h: int,
    aspect: str,
    theme: str,
    font_cache: FontCache,
) -> None:
    is_dark = theme == "dark"
    bg_col = (20, 27, 45) if is_dark else (248, 245, 236)
    card_col = (34, 46, 74) if is_dark else (255, 255, 255)
    txt_col = (244, 246, 250) if is_dark else (15, 23, 42)
    muted_col = (160, 174, 192) if is_dark else (71, 85, 105)
    accent_col = (250, 204, 21) if is_dark else (217, 35, 46)

    # Khung thu nhỏ của beat
    draw.rounded_rectangle(
        (cell_x, cell_y, cell_x + cell_w, cell_y + thumb_h),
        radius=12,
        fill=bg_col,
        outline=(203, 213, 225) if not is_dark else (51, 65, 85),
        width=2,
    )

    sx = cell_w / max(1, src_w)
    sy = thumb_h / max(1, src_h)
    def_b, def_p, def_k = default_boxes_for_shot(beat.shot_type, aspect)  # type: ignore[arg-type]
    b_box = beat.board.bbox or def_b
    p_box = beat.puppet.bbox or def_p
    k_box = beat.karaoke_bbox or def_k

    # Vẽ hộp Bảng tri thức thu nhỏ
    if beat.board.board_type != "none":
        bx0 = cell_x + int(b_box.x * sx)
        by0 = cell_y + int(b_box.y * sy)
        bx1 = cell_x + int(b_box.x2 * sx)
        by1 = cell_y + int(b_box.y2 * sy)
        draw.rounded_rectangle(
            (bx0, by0, max(bx0 + 8, bx1), max(by0 + 8, by1)),
            radius=6,
            fill=card_col,
            outline=accent_col,
            width=2,
        )
        f_title = font_cache.get_font(FONT_BOLD, 13)
        title_txt = (beat.board.title or beat.board.board_type).strip()[:26]
        draw.text((bx0 + 6, by0 + 6), title_txt, font=f_title, fill=txt_col)
        if beat.board.bullets:
            f_sub = font_cache.get_font(FONT_MEDIUM, 11)
            b_preview = beat.board.bullets[0].replace("**", "")[:28]
            draw.text((bx0 + 6, by0 + 24), f"• {b_preview}", font=f_sub, fill=muted_col)

    # Vẽ dải Karaoke thu nhỏ
    kx0 = cell_x + int(k_box.x * sx)
    ky0 = cell_y + int(k_box.y * sy)
    kx1 = cell_x + int(k_box.x2 * sx)
    ky1 = cell_y + int(k_box.y2 * sy)
    draw.rounded_rectangle(
        (kx0, ky0, max(kx0 + 8, kx1), max(ky0 + 6, ky1)),
        radius=4,
        fill=(15, 23, 42),
        outline=(250, 204, 21),
        width=1,
    )

    # Vẽ hình bóng nhân vật Stickman thu nhỏ
    if beat.puppet.enabled:
        px0 = cell_x + int(p_box.x * sx)
        py0 = cell_y + int(p_box.y * sy)
        px1 = cell_x + int(p_box.x2 * sx)
        py1 = cell_y + int(p_box.y2 * sy)
        cx = (px0 + px1) // 2
        head_r = max(6, min(14, (px1 - px0) // 6))
        head_cy = py0 + head_r + 6
        draw.ellipse(
            (cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r),
            outline=txt_col,
            width=2,
        )
        body_bot = min(py1 - 6, head_cy + head_r * 3)
        draw.line([(cx, head_cy + head_r), (cx, body_bot)], fill=txt_col, width=2)
        draw.line([(cx, head_cy + head_r + 6), (cx - head_r, body_bot - 4)], fill=txt_col, width=2)
        draw.line([(cx, head_cy + head_r + 6), (cx + head_r, body_bot - 4)], fill=txt_col, width=2)

    # Nhãn số beat + góc máy phía trên trái thumbnail
    f_badge = font_cache.get_font(FONT_BOLD, 12)
    badge = f"#{idx + 1} · {beat.duration_sec:.1f}s"
    draw.rounded_rectangle(
        (cell_x + 6, cell_y + 6, cell_x + 92, cell_y + 26), radius=6, fill=accent_col
    )
    draw.text(
        (cell_x + 12, cell_y + 9),
        badge,
        font=f_badge,
        fill=(15, 23, 42) if is_dark else (255, 255, 255),
    )

    # Chú thích bên dưới ô
    meta_y = cell_y + thumb_h + 6
    f_meta = font_cache.get_font(FONT_BOLD, 12)
    f_nar = font_cache.get_font(FONT_MEDIUM, 11)
    shot_vi = _SHOT_LABELS_VI.get(beat.shot_type, beat.shot_type)
    draw.text(
        (cell_x + 2, meta_y), f"{shot_vi} [{beat.transition_in}]", font=f_meta, fill=(15, 23, 42)
    )
    nar_short = (beat.narration or "").strip()[:36]
    if len((beat.narration or "").strip()) > 36:
        nar_short += "…"
    draw.text((cell_x + 2, meta_y + 18), nar_short, font=f_nar, fill=(71, 85, 105))


def render_contact_sheet(
    spec: TimelineSpec,
    out_path: Path,
    *,
    cols: int = 4,
    thumb_w: int = 270,
    max_beats: int = 24,
    preflight_report: PreflightReport | None = None,
    font_cache: FontCache | None = None,
) -> dict[str, Any]:
    """Xuất ảnh Contact Sheet 1 trang duyệt nhanh toàn bộ beat của TimelineSpec (< 2.0 giây)."""
    t0 = time.perf_counter()
    fc = font_cache or FontCache()
    beats = spec.beats[: max(1, int(max_beats))]
    n = len(beats)
    cols = max(1, min(6, int(cols)))
    rows = max(1, math.ceil(max(1, n) / cols))

    src_w, src_h = spec.width, spec.height
    thumb_h = max(120, int(round(thumb_w * (src_h / max(1, src_w)))))
    # Giới hạn chiều cao thumbnail khi 9:16 để ảnh 1 trang gọn nhẹ, render cực nhanh
    if thumb_h > 360:
        thumb_h = 360
        thumb_w = max(140, int(round(thumb_h * (src_w / max(1, src_h)))))

    pad = 24
    gap = 18
    header_h = 84
    caption_h = 44
    cell_h = thumb_h + caption_h

    sheet_w = pad * 2 + cols * thumb_w + (cols - 1) * gap
    sheet_h = pad * 2 + header_h + rows * cell_h + (rows - 1) * gap

    canvas = Image.new("RGB", (sheet_w, sheet_h), (244, 246, 250))
    try:
        draw = ImageDraw.Draw(canvas)
        f_head = fc.get_font(FONT_BOLD, 24)
        f_sub = fc.get_font(FONT_MEDIUM, 14)

        draw.rounded_rectangle(
            (pad, pad, sheet_w - pad, pad + header_h - 10),
            radius=14,
            fill=(15, 23, 42),
        )
        draw.text(
            (pad + 18, pad + 14),
            f"HBT CINEMA CONTACT SHEET — {spec.title[:48]}",
            font=f_head,
            fill=(248, 250, 252),
        )
        ok_flag = preflight_report.ok if preflight_report is not None else spec.preflight_passed
        status_lbl = "PREFLIGHT ĐẠT CHUẨN" if ok_flag else "CHƯA QUA PREFLIGHT"
        draw.text(
            (pad + 18, pad + 46),
            f"{len(spec.beats)} beats · {spec.total_duration_sec:.1f}s · {spec.aspect} · "
            f"{spec.fps}fps · {status_lbl}",
            font=f_sub,
            fill=(250, 204, 21) if ok_flag else (248, 113, 113),
        )

        for idx, beat in enumerate(beats):
            r = idx // cols
            c = idx % cols
            cx = pad + c * (thumb_w + gap)
            cy = pad + header_h + r * (cell_h + gap)
            _draw_mini_beat_card(
                draw,
                beat,
                idx,
                cell_x=cx,
                cell_y=cy,
                cell_w=thumb_w,
                thumb_h=thumb_h,
                src_w=src_w,
                src_h=src_h,
                aspect=spec.aspect,
                theme=spec.theme,
                font_cache=fc,
            )

        out = Path(out_path)
        _atomic_save_image(canvas, out)
    finally:
        canvas.close()

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "file_path": str(out_path),
        "width": sheet_w,
        "height": sheet_h,
        "beats_rendered": n,
        "elapsed_ms": elapsed_ms,
    }
