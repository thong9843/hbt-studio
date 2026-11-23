"""Bộ diễn hoạt nhân vật 2D Puppet phân cấp (Hierarchical Rig) & Khẩu hình EMA tự động."""

from __future__ import annotations

import hashlib
import json
import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from hbt.stickv.poses_init import remove_white_background_image

PUPPET_SLOTS: tuple[str, ...] = (
    "base_character",
    "eyes_neutral",
    "eyes_happy",
    "eyes_shock",
    "eyes_angry",
    "mouth_closed",
    "mouth_open",
)

SEG_CACHE_VERSION = "v4_hybrid_ik"
SEGMENT_NAMES: tuple[str, ...] = ("body_torso", "head_blank", "arm_left", "arm_right")
ARM_2SEG_NAMES: tuple[str, ...] = (
    "upper_arm_left",
    "forearm_left",
    "upper_arm_right",
    "forearm_right",
)
SHOE_NAMES: tuple[str, ...] = ("shoe_left", "shoe_right")
ALL_SEGMENT_NAMES: tuple[str, ...] = SEGMENT_NAMES + ARM_2SEG_NAMES + SHOE_NAMES
VALID_HAND_SHAPES: tuple[str, ...] = (
    "open_palm",
    "point_index",
    "fist_punch",
    "count_fingers",
)
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
JOINT_CAP_COLOR = (11, 14, 20, 255)  # #0B0E14

DEFAULT_RIG_CONFIG: dict[str, Any] = {
    "neck_pivot_head": [0.50, 0.94],
    "neck_anchor_torso": [0.50, 0.04],
    "shoulder_left_pivot": [0.88, 0.12],
    "shoulder_left_torso": [0.36, 0.14],
    "shoulder_right_pivot": [0.12, 0.12],
    "shoulder_right_torso": [0.64, 0.14],
    "hip_left_torso": [0.36, 0.94],
    "hip_right_torso": [0.64, 0.94],
    "elbow_anchor_left": [0.50, 0.90],
    "elbow_left_pivot": [0.50, 0.12],
    "elbow_anchor_right": [0.50, 0.90],
    "elbow_right_pivot": [0.50, 0.12],
    "eyes_center_head": [0.50, 0.44],
    "eyes_width_ratio": 0.58,
    "mouth_center_head": [0.50, 0.72],
    "mouth_width_ratio": 0.32,
    "limb_stroke_px": 9.0,
    "torso_leg_ratio": 0.62,
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _crop_rgba_with_padding(img: Image.Image, padding: int = 4) -> Image.Image:
    rgba = img.convert("RGBA")
    bbox = rgba.getbbox()
    if bbox is None:
        return rgba
    x0, y0, x1, y1 = bbox
    cropped = rgba.crop((x0, y0, x1, y1))
    if padding <= 0:
        return cropped
    out = Image.new(
        "RGBA", (cropped.width + padding * 2, cropped.height + padding * 2), (0, 0, 0, 0)
    )
    out.alpha_composite(cropped, (padding, padding))
    cropped.close()
    return out


def clean_puppet_sprite(img: Image.Image, *, padding: int = 4, threshold: int = 235) -> Image.Image:
    """Tách nền trắng ngoài + crop sát bounding box có padding."""
    cleaned, _ = remove_white_background_image(img, threshold=threshold)
    try:
        return _crop_rgba_with_padding(cleaned, padding=padding)
    finally:
        cleaned.close()


def _find_slot_in_dir(folder: Path, slot: str, *, allow_prefix: bool) -> Path | None:
    if not folder.is_dir():
        return None
    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        exact = folder / f"{slot}{ext}"
        if exact.is_file():
            return exact
    if not allow_prefix:
        return None
    cands = [
        p
        for p in folder.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in _IMG_EXTS
        and (p.name.lower().startswith(f"{slot}.") or p.name.lower().startswith(f"{slot}_"))
    ]
    if not cands:
        return None
    cands.sort(key=lambda p: (p.suffix.lower() == ".png", p.stat().st_mtime), reverse=True)
    return cands[0]


def find_puppet_slot_paths(
    library_dir: Path, assets_dir: Path
) -> dict[str, tuple[Path | None, str]]:
    """Tìm 7 mảnh Puppet theo thứ tự: assets/puppet -> library/puppet -> tiền tố trong stickman/."""
    found: dict[str, tuple[Path | None, str]] = {}
    search_order: list[tuple[Path, str, bool]] = [
        (Path(assets_dir) / "stickman" / "puppet", "assets", False),
        (Path(library_dir) / "stickman" / "puppet", "library", False),
        (Path(assets_dir) / "stickman", "assets", True),
        (Path(library_dir) / "stickman", "library", True),
    ]
    for slot in PUPPET_SLOTS:
        matched_path: Path | None = None
        matched_src = ""
        for folder, src, allow_prefix in search_order:
            p = _find_slot_in_dir(folder, slot, allow_prefix=allow_prefix)
            if p is not None:
                matched_path = p
                matched_src = src
                break
        found[slot] = (matched_path, matched_src)
    return found


def prepare_puppet_sprite(src_path: Path, cache_dir: Path, slot: str) -> Path:
    """Chuẩn hóa linh kiện (tách nền trắng + crop + cache PNG RGBA theo SHA-256)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = _sha256_file(src_path)[:16]
    cached = cache_dir / f"{slot}_{digest}.png"
    if cached.is_file():
        return cached
    with Image.open(src_path) as raw:
        cleaned = clean_puppet_sprite(raw, padding=4)
    try:
        cleaned.save(cached, format="PNG")
    finally:
        cleaned.close()
    return cached


def _has_any_eyes(slot_paths: dict[str, tuple[Path | None, str]]) -> bool:
    return any(
        slot_paths[s][0] is not None
        for s in ("eyes_neutral", "eyes_happy", "eyes_shock", "eyes_angry")
    )


def _has_any_mouth(slot_paths: dict[str, tuple[Path | None, str]]) -> bool:
    return any(slot_paths[s][0] is not None for s in ("mouth_closed", "mouth_open"))


def is_puppet_ready(library_dir: Path, assets_dir: Path) -> bool:
    """Đủ điều kiện bật chế độ Puppet 2D (có base_character + >=1 mắt + >=1 miệng)."""
    slot_paths = find_puppet_slot_paths(library_dir, assets_dir)
    has_base = slot_paths["base_character"][0] is not None
    if not has_base:
        for pdir in (
            Path(assets_dir) / "stickman" / "puppet",
            Path(library_dir) / "stickman" / "puppet",
        ):
            if all((pdir / f"{s}.png").is_file() for s in SEGMENT_NAMES):
                has_base = True
                break
    return has_base and _has_any_eyes(slot_paths) and _has_any_mouth(slot_paths)


def get_puppet_status(library_dir: Path, assets_dir: Path) -> dict[str, Any]:
    """Trả về trạng thái 7 mảnh Puppet 2D cho `/library`."""
    slot_paths = find_puppet_slot_paths(library_dir, assets_dir)
    slots_info: dict[str, dict[str, Any]] = {}
    present_count = 0
    for slot in PUPPET_SLOTS:
        path, src = slot_paths[slot]
        if path is not None:
            present_count += 1
            base_root = Path(assets_dir if src == "assets" else library_dir) / "stickman"
            try:
                rel = path.resolve().relative_to(base_root.resolve()).as_posix()
                url = f"/api/asset-hub/file/{src}/stickman/{rel}"
            except ValueError:
                url = None
            slots_info[slot] = {
                "found": True,
                "name": path.name,
                "source": src,
                "url": url,
            }
        else:
            slots_info[slot] = {"found": False, "name": "", "source": "", "url": None}

    return {
        "ready": is_puppet_ready(library_dir, assets_dir),
        "present_count": present_count,
        "total": len(PUPPET_SLOTS),
        "slots": slots_info,
    }


def _draw_joint_cap(img: Image.Image, xy: tuple[float, float], radius: int) -> None:
    draw = ImageDraw.Draw(img)
    cx, cy = int(round(xy[0])), int(round(xy[1]))
    r = max(3, int(radius))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=JOINT_CAP_COLOR)


def _crop_rgba_mask(
    arr: np.ndarray, mask: np.ndarray, pad: int = 4
) -> tuple[Image.Image, tuple[int, int]]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return Image.new("RGBA", (32, 32), (0, 0, 0, 0)), (0, 0)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    sub = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
    sub_m = mask[y0:y1, x0:x1]
    sub[sub_m] = arr[y0:y1, x0:x1][sub_m]
    cropped = Image.fromarray(sub, mode="RGBA")
    out = Image.new("RGBA", (cropped.width + pad * 2, cropped.height + pad * 2), (0, 0, 0, 0))
    out.alpha_composite(cropped, (pad, pad))
    cropped.close()
    return out, (x0 - pad, y0 - pad)


def _norm_in_img(pt: tuple[float, float], off: tuple[int, int], im: Image.Image) -> list[float]:
    nx = max(0.0, min(1.0, (pt[0] - off[0]) / max(1, im.width)))
    ny = max(0.0, min(1.0, (pt[1] - off[1]) / max(1, im.height)))
    return [round(nx, 4), round(ny, 4)]


def _split_arm_two_segments(
    arr: np.ndarray,
    arm_mask: np.ndarray,
    shoulder_pt: tuple[float, float],
    min_cap_r: int,
) -> tuple[
    Image.Image,
    Image.Image,
    list[float],
    list[float],
    list[float],
]:
    """Tách 1 cánh tay thành (upper_arm, forearm) tại mốc 52% và vá khớp vai + khuỷu `#0B0E14`."""
    ys, xs = np.nonzero(arm_mask)
    if len(xs) == 0:
        blank = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        return blank, blank.copy(), [0.5, 0.15], [0.5, 0.85], [0.5, 0.15]

    sx, sy = float(shoulder_pt[0]), float(shoulder_pt[1])
    dx = xs.astype(np.float32) - sx
    dy = ys.astype(np.float32) - sy
    dist2 = dx * dx + dy * dy
    far_idx = int(np.argmax(dist2))
    hx, hy = float(xs[far_idx]), float(ys[far_idx])
    vx, vy = hx - sx, hy - sy
    length = max(1.0, math.hypot(vx, vy))
    ux, uy = vx / length, vy / length

    # Chiếu từng pixel dọc trục shoulder -> hand_tip để cắt tại 52% chiều dài
    proj = (dx * ux + dy * uy) / length
    upper_mask = np.zeros_like(arm_mask)
    forearm_mask = np.zeros_like(arm_mask)

    upper_sel = proj <= 0.52
    # Đảm bảo cả 2 đoạn đều có pixel nếu tay quá ngắn
    if not np.any(upper_sel) or np.all(upper_sel):
        med = float(np.median(proj))
        upper_sel = proj <= med

    upper_mask[ys[upper_sel], xs[upper_sel]] = True
    forearm_mask[ys[~upper_sel], xs[~upper_sel]] = True

    # Điểm khuỷu tay nằm tại 52% (hút về trọng tâm pixel quanh mốc 52% để nằm đúng tâm nét mực)
    band = (proj >= 0.44) & (proj <= 0.60)
    if np.any(band):
        elbow_pt = (float(np.mean(xs[band])), float(np.mean(ys[band])))
    else:
        elbow_pt = (sx + 0.52 * vx, sy + 0.52 * vy)

    # Ước lượng độ dày nét tay quanh khuỷu để chọn bán kính vá khớp = 0.52 * độ dày
    mid_band = (proj >= 0.36) & (proj <= 0.64)
    if np.any(mid_band):
        perp = np.abs(
            -uy * (xs[mid_band].astype(np.float32) - sx)
            + ux * (ys[mid_band].astype(np.float32) - sy)
        )
        p_low, p_high = float(np.percentile(perp, 10)), float(np.percentile(perp, 90))
        arm_thickness = max(6.0, p_high - p_low + 2.0)
    else:
        arm_thickness = float(max(6, min_cap_r * 2))
    joint_r = max(min_cap_r, int(round(0.52 * arm_thickness)))

    upper_img, upper_off = _crop_rgba_mask(arr, upper_mask, pad=max(6, joint_r + 2))
    forearm_img, forearm_off = _crop_rgba_mask(arr, forearm_mask, pad=max(6, joint_r + 2))

    sh_pivot = _norm_in_img(shoulder_pt, upper_off, upper_img)
    el_anchor_upper = _norm_in_img(elbow_pt, upper_off, upper_img)
    el_pivot_forearm = _norm_in_img(elbow_pt, forearm_off, forearm_img)

    # Vá khớp tròn kép #0B0E14 tại cả vai và khuỷu để gập -118° không bao giờ hở khe
    _draw_joint_cap(
        upper_img,
        (sh_pivot[0] * upper_img.width, sh_pivot[1] * upper_img.height),
        joint_r,
    )
    _draw_joint_cap(
        upper_img,
        (el_anchor_upper[0] * upper_img.width, el_anchor_upper[1] * upper_img.height),
        joint_r,
    )
    _draw_joint_cap(
        forearm_img,
        (el_pivot_forearm[0] * forearm_img.width, el_pivot_forearm[1] * forearm_img.height),
        joint_r,
    )
    return upper_img, forearm_img, sh_pivot, el_anchor_upper, el_pivot_forearm


def auto_segment_puppet(
    base_char_path: Path,
    cache_dir: Path,
    *,
    puppet_dir: Path | None = None,
) -> dict[str, Any]:
    """Tự tách `base_character.png` thành các lớp RGBA (kèm bắp tay + cẳng tay) & cache v2_elbow."""
    # Nếu người dùng đã upload sẵn 4 file rời trong puppet_dir thì dùng (nếu đã tách 2 đoạn)
    if puppet_dir is not None and all((puppet_dir / f"{s}.png").is_file() for s in SEGMENT_NAMES):
        cfg = dict(DEFAULT_RIG_CONFIG)
        cfg_file = puppet_dir / "rig_config.json"
        if cfg_file.is_file():
            try:
                cfg.update(json.loads(cfg_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        segs: dict[str, Path] = {s: puppet_dir / f"{s}.png" for s in SEGMENT_NAMES}
        if all((puppet_dir / f"{s}.png").is_file() for s in ARM_2SEG_NAMES):
            for s in ARM_2SEG_NAMES:
                segs[s] = puppet_dir / f"{s}.png"
            return {"segments": segs, "rig_config": cfg, "cached": True}

    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = _sha256_file(base_char_path)[:16]
    meta_file = cache_dir / f"segments_{SEG_CACHE_VERSION}_{digest}.json"
    seg_paths = {s: cache_dir / f"{s}_{SEG_CACHE_VERSION}_{digest}.png" for s in ALL_SEGMENT_NAMES}
    if meta_file.is_file() and all(p.is_file() for p in seg_paths.values()):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("version") == SEG_CACHE_VERSION:
                return {"segments": seg_paths, "rig_config": meta["rig_config"], "cached": True}
        except Exception:
            pass

    with Image.open(base_char_path) as raw:
        cleaned = clean_puppet_sprite(raw, padding=4)
    try:
        arr = np.array(cleaned, dtype=np.uint8)
    finally:
        cleaned.close()

    h, w, _ = arr.shape
    alpha = arr[:, :, 3] > 24

    # 1. Tìm ranh giới cổ (neck_y): đầu nằm ở phần trên, thắt hẹp tại cổ trước khi nở ra cổ áo
    row_widths = np.zeros(h, dtype=np.int32)
    row_xs_center = np.full(h, w * 0.5, dtype=np.float32)
    for y in range(h):
        xs = np.flatnonzero(alpha[y])
        if len(xs) > 0:
            row_widths[y] = int(xs[-1] - xs[0] + 1)
            row_xs_center[y] = float(0.5 * (xs[0] + xs[-1]))

    head_top = max(0, min(h - 1, int(0.06 * h)))
    head_mid_end = max(head_top + 4, min(h - 1, int(0.32 * h)))
    head_widest_y = head_top + int(np.argmax(row_widths[head_top:head_mid_end]))

    neck_search_start = min(h - 2, head_widest_y + max(4, int(0.04 * h)))
    neck_search_end = max(neck_search_start + 2, min(h - 1, int(0.45 * h)))
    sub_w = row_widths[neck_search_start:neck_search_end]
    positive = np.where(sub_w > 0, sub_w, 10**9)
    neck_y = neck_search_start + int(np.argmin(positive))
    neck_y = max(int(0.18 * h), min(int(0.44 * h), neck_y))

    # 2. Tìm trục giữa thân và ranh giới tách tay trái / tay phải khỏi thân
    head_xs = np.flatnonzero(alpha[head_widest_y])
    x_center = int(round(float(np.mean(head_xs)))) if len(head_xs) else w // 2

    # Tìm khoảng rộng nửa thân tại vùng eo/ngực dưới cổ áo (tìm khe trống alpha==0 đầu tiên hai bên)
    chest_y = min(h - 1, neck_y + max(6, int(0.16 * h)))
    torso_half_w = max(8, int(round(w * 0.11)))
    if chest_y < h:
        # Quét từ x_center sang trái để tìm khoảng hở trong suốt giữa thân và tay trái
        left_gap = None
        for dx in range(4, int(w * 0.30)):
            x = x_center - dx
            if x <= 1:
                break
            if not alpha[chest_y, x] and not alpha[min(h - 1, chest_y + 4), x]:
                left_gap = dx
                break
        right_gap = None
        for dx in range(4, int(w * 0.30)):
            x = x_center + dx
            if x >= w - 2:
                break
            if not alpha[chest_y, x] and not alpha[min(h - 1, chest_y + 4), x]:
                right_gap = dx
                break
        gaps = [g for g in (left_gap, right_gap) if g is not None]
        if gaps:
            torso_half_w = max(6, min(int(w * 0.22), max(gaps)))

    # 3. Tạo mask từng bộ phận (v4_hybrid_ik: tách sạch thân áo sơ mi + 2 giày vàng đáy)
    head_mask = np.zeros((h, w), dtype=bool)
    head_mask[: neck_y + 2, :] = alpha[: neck_y + 2, :]

    arm_y_end = min(h, int(0.80 * h))
    hip_y = min(h - 4, max(neck_y + 12, neck_y + int(round(0.46 * (h - neck_y)))))
    shoe_y_start = min(h - 2, max(hip_y + 4, int(round(0.84 * h))))

    arm_left_mask = np.zeros((h, w), dtype=bool)
    arm_right_mask = np.zeros((h, w), dtype=bool)
    torso_mask = np.zeros((h, w), dtype=bool)

    shoulder_y = min(h - 1, neck_y + max(2, int(0.04 * h)))
    torso_mask[neck_y:hip_y, :] = alpha[neck_y:hip_y, :]

    # Tách tay trái/phải trong khoảng [neck_y, arm_y_end] bên ngoài phần thân giữa
    cut_l = max(1, x_center - torso_half_w)
    cut_r = min(w - 2, x_center + torso_half_w)
    # Mở rộng nhẹ vùng cổ áo ngay sát neck_y để không cắt mất ve cổ áo trắng
    collar_y_end = min(arm_y_end, neck_y + max(4, int(0.06 * h)))

    for y in range(neck_y, arm_y_end):
        # Tại vùng sát cổ áo (neck_y..collar_y_end), ranh giới vai hẹp hơn ở ngoài tay một chút
        eff_cut_l = cut_l
        eff_cut_r = cut_r
        if y < collar_y_end:
            eff_cut_l = max(1, x_center - int(torso_half_w * 0.92))
            eff_cut_r = min(w - 2, x_center + int(torso_half_w * 0.92))

        left_px = alpha[y, :eff_cut_l]
        if np.any(left_px):
            arm_left_mask[y, :eff_cut_l] = left_px
            if y < hip_y:
                torso_mask[y, :eff_cut_l] = False

        right_px = alpha[y, eff_cut_r + 1 :]
        if np.any(right_px):
            arm_right_mask[y, eff_cut_r + 1 :] = right_px
            if y < hip_y:
                torso_mask[y, eff_cut_r + 1 :] = False

    # Đảm bảo không có mask rỗng nếu ảnh synthetic rất nhỏ
    if not np.any(torso_mask):
        torso_mask[neck_y:hip_y, :] = alpha[neck_y:hip_y, :]
    if not np.any(torso_mask):
        torso_mask[neck_y:, :] = alpha[neck_y:, :]

    # Tách 2 chiếc giày vàng (shoe_left / shoe_right) ở vùng đáy ảnh gốc
    shoe_l_mask = np.zeros((h, w), dtype=bool)
    shoe_r_mask = np.zeros((h, w), dtype=bool)
    shoe_l_mask[shoe_y_start:, :x_center] = alpha[shoe_y_start:, :x_center]
    shoe_r_mask[shoe_y_start:, x_center:] = alpha[shoe_y_start:, x_center:]

    def _make_default_shoe(facing_left: bool) -> Image.Image:
        sw_px = max(24, int(round(w * 0.14)))
        sh_px = max(14, int(round(sw_px * 0.56)))
        im = Image.new("RGBA", (sw_px, sh_px), (0, 0, 0, 0))
        d_s = ImageDraw.Draw(im)
        d_s.rounded_rectangle(
            (2, 2, sw_px - 3, sh_px - 3),
            radius=max(5, sh_px // 2),
            fill=(250, 204, 21, 255),
            outline=JOINT_CAP_COLOR,
            width=max(2, int(round(sh_px * 0.16))),
        )
        return im.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if facing_left else im

    head_img, _head_off = _crop_rgba_mask(arr, head_mask)
    torso_img, torso_off = _crop_rgba_mask(arr, torso_mask)
    arm_l_img, arm_l_off = _crop_rgba_mask(arr, arm_left_mask)
    arm_r_img, arm_r_off = _crop_rgba_mask(arr, arm_right_mask)
    shoe_l_img = (
        _crop_rgba_mask(arr, shoe_l_mask, pad=2)[0]
        if int(np.count_nonzero(shoe_l_mask)) >= 20
        else _make_default_shoe(True)
    )
    shoe_r_img = (
        _crop_rgba_mask(arr, shoe_r_mask, pad=2)[0]
        if int(np.count_nonzero(shoe_r_mask)) >= 20
        else _make_default_shoe(False)
    )

    # 4. Tính tọa độ khớp giải phẫu & tách bắp tay / cẳng tay + vá khớp `#0B0E14`
    cap_r = max(4, int(round(min(w, h) * 0.014)))
    rig_cfg = dict(DEFAULT_RIG_CONFIG)

    sh_l_global = (float(cut_l), float(shoulder_y))
    sh_r_global = (float(cut_r), float(shoulder_y))

    rig_cfg["neck_anchor_torso"] = _norm_in_img(
        (float(x_center), float(neck_y + 2)), torso_off, torso_img
    )
    rig_cfg["shoulder_left_torso"] = _norm_in_img(sh_l_global, torso_off, torso_img)
    rig_cfg["shoulder_right_torso"] = _norm_in_img(sh_r_global, torso_off, torso_img)
    rig_cfg["hip_left_torso"] = [0.36, 0.94]
    rig_cfg["hip_right_torso"] = [0.64, 0.94]
    rig_cfg["limb_stroke_px"] = round(max(6.0, min(18.0, min(w, h) * 0.024)), 2)
    rig_cfg["torso_leg_ratio"] = round(max(0.45, min(0.85, (h - hip_y) / max(1.0, hip_y - neck_y))), 3)

    if np.any(arm_left_mask):
        rig_cfg["shoulder_left_pivot"] = _norm_in_img(sh_l_global, arm_l_off, arm_l_img)
        _draw_joint_cap(
            arm_l_img,
            (
                rig_cfg["shoulder_left_pivot"][0] * arm_l_img.width,
                rig_cfg["shoulder_left_pivot"][1] * arm_l_img.height,
            ),
            cap_r,
        )
        up_l_img, fore_l_img, sh_l_up, el_l_up, el_l_fore = _split_arm_two_segments(
            arr, arm_left_mask, sh_l_global, cap_r
        )
        rig_cfg["upper_shoulder_left_pivot"] = sh_l_up
        rig_cfg["elbow_anchor_left"] = el_l_up
        rig_cfg["elbow_left_pivot"] = el_l_fore
    else:
        up_l_img = arm_l_img.copy()
        fore_l_img = arm_l_img.copy()
        rig_cfg["upper_shoulder_left_pivot"] = list(rig_cfg["shoulder_left_pivot"])

    if np.any(arm_right_mask):
        rig_cfg["shoulder_right_pivot"] = _norm_in_img(sh_r_global, arm_r_off, arm_r_img)
        _draw_joint_cap(
            arm_r_img,
            (
                rig_cfg["shoulder_right_pivot"][0] * arm_r_img.width,
                rig_cfg["shoulder_right_pivot"][1] * arm_r_img.height,
            ),
            cap_r,
        )
        up_r_img, fore_r_img, sh_r_up, el_r_up, el_r_fore = _split_arm_two_segments(
            arr, arm_right_mask, sh_r_global, cap_r
        )
        rig_cfg["upper_shoulder_right_pivot"] = sh_r_up
        rig_cfg["elbow_anchor_right"] = el_r_up
        rig_cfg["elbow_right_pivot"] = el_r_fore
    else:
        up_r_img = arm_r_img.copy()
        fore_r_img = arm_r_img.copy()
        rig_cfg["upper_shoulder_right_pivot"] = list(rig_cfg["shoulder_right_pivot"])

    # Vá khớp vai trên thân để khi tay xoay không bao giờ hở khe
    _draw_joint_cap(
        torso_img,
        (
            rig_cfg["shoulder_left_torso"][0] * torso_img.width,
            rig_cfg["shoulder_left_torso"][1] * torso_img.height,
        ),
        cap_r,
    )
    _draw_joint_cap(
        torso_img,
        (
            rig_cfg["shoulder_right_torso"][0] * torso_img.width,
            rig_cfg["shoulder_right_torso"][1] * torso_img.height,
        ),
        cap_r,
    )

    imgs_to_save = {
        "body_torso": torso_img,
        "head_blank": head_img,
        "arm_left": arm_l_img,
        "arm_right": arm_r_img,
        "upper_arm_left": up_l_img,
        "forearm_left": fore_l_img,
        "upper_arm_right": up_r_img,
        "forearm_right": fore_r_img,
        "shoe_left": shoe_l_img,
        "shoe_right": shoe_r_img,
    }
    try:
        for seg_key, seg_im in imgs_to_save.items():
            seg_im.save(seg_paths[seg_key], format="PNG")
        meta_file.write_text(
            json.dumps(
                {"version": SEG_CACHE_VERSION, "sha256": digest, "rig_config": rig_cfg},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        for seg_im in imgs_to_save.values():
            seg_im.close()

    return {"segments": seg_paths, "rig_config": rig_cfg, "cached": False}


def rotate_around_pivot(
    layer_rgba: Image.Image,
    angle_deg: float,
    pivot_xy: tuple[float, float],
) -> tuple[Image.Image, tuple[float, float]]:
    """Xoay ảnh RGBA quanh đúng `pivot_xy` bằng phép biến đổi affine BICUBIC, không cắt góc."""
    if abs(angle_deg) < 0.05:
        return layer_rgba.copy(), pivot_xy

    w, h = layer_rgba.size
    px, py = float(pivot_xy[0]), float(pivot_xy[1])
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # Tọa độ 4 góc sau khi xoay quanh (px, py)
    corners = [(0.0, 0.0), (float(w), 0.0), (0.0, float(h)), (float(w), float(h))]
    rot_pts: list[tuple[float, float]] = []
    for cx, cy in corners:
        dx = cx - px
        dy = cy - py
        rx = dx * cos_t + dy * sin_t
        ry = -dx * sin_t + dy * cos_t
        rot_pts.append((rx, ry))

    min_x = min(p[0] for p in rot_pts) - 2.0
    max_x = max(p[0] for p in rot_pts) + 2.0
    min_y = min(p[1] for p in rot_pts) - 2.0
    max_y = max(p[1] for p in rot_pts) + 2.0

    out_w = max(2, int(math.ceil(max_x - min_x)))
    out_h = max(2, int(math.ceil(max_y - min_y)))
    ox = -min_x
    oy = -min_y

    # Ma trận nghịch đảo Pillow AFFINE: x_in = a*x_out + b*y_out + c, y_in = d*x_out + e*y_out + f
    a = cos_t
    b = -sin_t
    c = px - cos_t * ox + sin_t * oy
    d = sin_t
    e = cos_t
    f = py - sin_t * ox - cos_t * oy

    rotated = layer_rgba.transform(
        (out_w, out_h),
        Image.Transform.AFFINE,
        (a, b, c, d, e, f),
        resample=Image.Resampling.BICUBIC,
    )
    return rotated, (ox, oy)


def smooth_rms_envelope(raw_rms: list[float], fps: int = 30) -> list[float]:
    """Áp dụng bộ lọc mượt EMA chuẩn hóa theo `fps` (tương đương 0.55/0.45 ở 30fps)."""
    if not raw_rms:
        return []
    decay = 0.45 ** (30.0 / max(15, int(fps)))
    alpha = 1.0 - decay
    out: list[float] = []
    prev = 0.0
    for val in raw_rms:
        clamped = max(0.0, min(1.0, float(val)))
        cur = alpha * clamped + decay * prev
        out.append(round(cur, 4))
        prev = cur
    return out


def compute_smoothed_rms(wav_path: Path, fps: int, duration_sec: float) -> list[float]:
    """Tính RMS từng frame từ WAV (chuẩn hóa theo P92) và lọc mượt EMA."""
    n_frames = max(1, int(round(max(0.1, duration_sec) * max(1, fps))))
    if not wav_path.is_file():
        return [0.0] * n_frames
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if not raw or sw != 2:
            return [0.0] * n_frames
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if ch > 1:
            samples = samples.reshape(-1, ch).mean(axis=1)
        samples /= 32768.0
        win = max(1, int(sr / max(1, fps)))
        frame_rms: list[float] = []
        for idx in range(n_frames):
            s0 = idx * win
            s1 = s0 + win
            if s0 >= len(samples):
                frame_rms.append(0.0)
            else:
                seg = samples[s0:s1]
                frame_rms.append(float(np.sqrt(np.mean(seg**2))))
        p92 = float(np.percentile(frame_rms, 92)) if frame_rms else 0.1
        peak_ref = max(0.02, p92)
        rms_norm = [min(1.0, r / peak_ref) for r in frame_rms]
        return smooth_rms_envelope(rms_norm, fps=fps)
    except Exception:
        return [0.0] * n_frames


def compute_mouth_transform(env_val: float) -> tuple[str, float, float]:
    """Lip-Sync 4 mức: closed (<0.12), narrow (0.12-0.32), medium (0.32-0.60), wide (>0.60)."""
    val = max(0.0, float(env_val))
    if val < 0.12:
        return "mouth_closed", 1.0, 1.0
    if val < 0.32:
        u = (val - 0.12) / 0.20
        scale_y = 0.50 + 0.18 * u
        scale_x = 1.01 - 0.03 * u
        return "mouth_open", round(scale_x, 4), round(scale_y, 4)
    if val < 0.60:
        u = (val - 0.32) / 0.28
        scale_y = 0.72 + 0.26 * u
        scale_x = 0.99 - 0.03 * u
        return "mouth_open", round(scale_x, 4), round(scale_y, 4)
    # wide_emphasis (> 0.60): Squash & Stretch nhẹ (kéo dọc 1.02..1.30, thu ngang < 1.0)
    t = min(1.0, (val - 0.60) / 0.30)
    scale_y = 1.02 + 0.28 * t
    scale_x = 0.96 - 0.11 * t
    return "mouth_open", round(scale_x, 4), round(scale_y, 4)


VALID_FACE_MOODS: tuple[str, ...] = (
    "explaining",
    "curious",
    "excited",
    "skeptical",
    "shocked",
    "warm_cta",
)

FACE_MOOD_TO_EMOTION: dict[str, str] = {
    "explaining": "confident",
    "curious": "curious",
    "excited": "excited",
    "skeptical": "skeptical",
    "shocked": "shock",
    "warm_cta": "happy",
}

GUIDING_BOARD_POSES: frozenset[str] = frozenset(
    {
        "point_up",
        "point_board_high",
        "present_board",
        "guide_sweep_board",
        "guide_two_sides",
        "guide_zoom_focus",
    }
)


VALID_EMOTIONS: tuple[str, ...] = (
    "neutral",
    "confident",
    "curious",
    "idea",
    "shock",
    "skeptical",
    "serious",
    "sad",
    "happy",
    "excited",
)

POSE_ALIASES: dict[str, str] = {
    "explain": "present_board",
    "think": "think_chin",
    "shock": "shock_hands_up",
    "happy": "present_board",
    "point": "point_up",
    "point_high": "point_board_high",
    "walk": "walk_explore",
    "sad": "idle_breathe",
    "bored": "idle_breathe",
    "angry": "arms_crossed",
    "strict": "arms_crossed",
    "scared": "shock_hands_up",
    "confused": "scratch_head",
    "laugh": "present_board",
    "winner": "present_board",
    "idea": "point_up",
    "wave": "wave_hello",
    "facepalm": "facepalm_light",
    "nod": "nod_yes",
    "stop": "shake_no",
    "guide": "guide_sweep_board",
    "compare": "guide_two_sides",
    "welcome": "welcome_open",
}

# 12 Hành động biểu cảm kể chuyện dùng hệ xương tay 2 đoạn (vai + khuỷu tay)
POSE_PRESETS: dict[str, dict[str, Any]] = {
    "point_up": {
        "shoulder_l": 12.0,
        "elbow_l": 8.0,
        "shoulder_r": -48.0,
        "elbow_r": -58.0,
        "head_deg": -6.0,
        "torso_deg": 1.5,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (0.0, -4.0),
    },
    "think_chin": {
        "shoulder_l": -28.0,
        "elbow_l": -68.0,
        "shoulder_r": 18.0,
        "elbow_r": -118.0,
        "head_deg": 9.0,
        "torso_deg": -1.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (3.0, -3.0),
    },
    "arms_crossed": {
        "shoulder_l": 22.0,
        "elbow_l": 78.0,
        "shoulder_r": -22.0,
        "elbow_r": -78.0,
        "head_deg": -2.0,
        "torso_deg": 0.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    "hands_on_hips": {
        "shoulder_l": 34.0,
        "elbow_l": -72.0,
        "shoulder_r": -34.0,
        "elbow_r": 72.0,
        "head_deg": 0.0,
        "torso_deg": 0.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    "shrug_ask": {
        "shoulder_l": -28.0,
        "elbow_l": -48.0,
        "shoulder_r": 28.0,
        "elbow_r": 48.0,
        "head_deg": 7.0,
        "torso_deg": 0.0,
        "dy_px": -4.0,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    "present_board": {
        "shoulder_l": 30.0,
        "elbow_l": -68.0,
        "shoulder_r": -38.0,
        "elbow_r": -24.0,
        "head_deg": -4.0,
        "torso_deg": 1.5,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (3.0, -2.0),
    },
    "emphatic_chop": {
        "shoulder_l": 14.0,
        "elbow_l": 12.0,
        "shoulder_r": -32.0,
        "elbow_r": -40.0,
        "head_deg": -4.0,
        "torso_deg": 1.8,
        "dy_px": -2.5,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    "shock_hands_up": {
        "shoulder_l": -52.0,
        "elbow_l": -62.0,
        "shoulder_r": 52.0,
        "elbow_r": 62.0,
        "head_deg": -8.0,
        "torso_deg": 0.0,
        "dy_px": -18.0,
        "eye_override": "eyes_shock",
        "eye_gaze": (0.0, 0.0),
    },
    "lean_secret": {
        "shoulder_l": 16.0,
        "elbow_l": 20.0,
        "shoulder_r": 12.0,
        "elbow_r": -105.0,
        "head_deg": 5.0,
        "torso_deg": 4.5,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (5.0, 0.0),
    },
    "count_points": {
        "shoulder_l": -15.0,
        "elbow_l": -75.0,
        "shoulder_r": -26.0,
        "elbow_r": -40.0,
        "head_deg": -3.0,
        "torso_deg": 0.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (2.0, 0.0),
    },
    "walk_explore": {
        "shoulder_l": 18.0,
        "elbow_l": 14.0,
        "shoulder_r": -18.0,
        "elbow_r": -14.0,
        "head_deg": 2.0,
        "torso_deg": 1.5,
        "dy_px": -3.0,
        "eye_override": None,
        "eye_gaze": (2.0, 0.0),
    },
    "idle_breathe": {
        "shoulder_l": 14.0,
        "elbow_l": 12.0,
        "shoulder_r": -14.0,
        "elbow_r": -12.0,
        "head_deg": 0.0,
        "torso_deg": 0.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    # 6 hành động kể chuyện mới (StickV v9)
    "point_board_high": {
        "shoulder_l": 14.0,
        "elbow_l": 10.0,
        "shoulder_r": -138.0,
        "elbow_r": -14.0,
        "head_deg": -8.0,
        "torso_deg": -4.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (2.0, -5.0),
    },
    "wave_hello": {
        "shoulder_l": 16.0,
        "elbow_l": 12.0,
        "shoulder_r": -115.0,
        "elbow_r": -20.0,
        "head_deg": -3.0,
        "torso_deg": 1.0,
        "dy_px": -2.0,
        "eye_override": "eyes_happy",
        "eye_gaze": (0.0, 0.0),
    },
    "scratch_head": {
        "shoulder_l": 16.0,
        "elbow_l": 12.0,
        "shoulder_r": -128.0,
        "elbow_r": 115.0,
        "head_deg": 10.0,
        "torso_deg": -1.5,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (3.0, -3.0),
    },
    "facepalm_light": {
        "shoulder_l": 18.0,
        "elbow_l": 14.0,
        "shoulder_r": -95.0,
        "elbow_r": 118.0,
        "head_deg": 9.0,
        "torso_deg": 2.0,
        "dy_px": 2.0,
        "eye_override": None,
        "eye_gaze": (0.0, 2.0),
    },
    "nod_yes": {
        "shoulder_l": 18.0,
        "elbow_l": -18.0,
        "shoulder_r": -28.0,
        "elbow_r": -42.0,
        "head_deg": 6.0,
        "torso_deg": 1.0,
        "dy_px": -2.0,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    "shake_no": {
        "shoulder_l": 16.0,
        "elbow_l": 12.0,
        "shoulder_r": -38.0,
        "elbow_r": -47.0,
        "head_deg": 0.0,
        "torso_deg": 0.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (0.0, 0.0),
    },
    # 6 cử chỉ hướng dẫn & điều hướng MC mượt mà (GD4-StickV)
    "guide_sweep_board": {
        "shoulder_l": 24.0,
        "elbow_l": -48.0,
        "shoulder_r": -64.0,
        "elbow_r": -22.0,
        "head_deg": -5.0,
        "torso_deg": 2.6,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (5.0, -2.0),
    },
    "guide_two_sides": {
        "shoulder_l": -36.0,
        "elbow_l": -34.0,
        "shoulder_r": -36.0,
        "elbow_r": -34.0,
        "head_deg": 0.0,
        "torso_deg": 0.0,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (5.0, 0.0),
    },
    "guide_step_count": {
        "shoulder_l": 20.0,
        "elbow_l": -54.0,
        "shoulder_r": -34.0,
        "elbow_r": -50.0,
        "head_deg": -3.0,
        "torso_deg": 1.2,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (2.0, 0.0),
    },
    "guide_zoom_focus": {
        "shoulder_l": -32.0,
        "elbow_l": -46.0,
        "shoulder_r": 32.0,
        "elbow_r": 46.0,
        "head_deg": -2.0,
        "torso_deg": 1.5,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (5.0, -1.0),
    },
    "welcome_open": {
        "shoulder_l": -44.0,
        "elbow_l": -18.0,
        "shoulder_r": 44.0,
        "elbow_r": 18.0,
        "head_deg": -2.0,
        "torso_deg": 0.8,
        "dy_px": 0.0,
        "eye_override": "eyes_happy",
        "eye_gaze": (0.0, 0.0),
    },
    "lean_curious": {
        "shoulder_l": 18.0,
        "elbow_l": -32.0,
        "shoulder_r": -24.0,
        "elbow_r": -68.0,
        "head_deg": 10.5,
        "torso_deg": 3.4,
        "dy_px": 0.0,
        "eye_override": None,
        "eye_gaze": (4.0, -2.0),
    },
}


def normalize_stickv_pose(pose: str | None) -> str:
    """Chuẩn hóa tên pose (tương thích ngược các tên cũ sang 18 hành động v9)."""
    key = (pose or "present_board").strip().lower()
    if key in POSE_PRESETS:
        return key
    return POSE_ALIASES.get(key, "present_board")


def resolve_stickv_emotion(
    emotion: str | None,
    pose: str | None = None,
    narration: str = "",
    *,
    face_mood: str | None = None,
) -> str:
    """Giải mã `emotion` trong 10 biểu cảm; hỗ trợ 6 `face_mood` và tự suy luận theo pose/thoại."""
    emo = (emotion or "auto").strip().lower()
    if emo in VALID_EMOTIONS:
        return emo
    mood = (face_mood or "").strip().lower()
    if mood in FACE_MOOD_TO_EMOTION:
        return FACE_MOOD_TO_EMOTION[mood]

    raw_pose = (pose or "").strip().lower()
    norm_pose = normalize_stickv_pose(pose)
    if raw_pose in ("happy", "laugh", "winner") or norm_pose in ("wave_hello", "welcome_open"):
        return "happy"
    if raw_pose in ("shock", "scared") or norm_pose == "shock_hands_up":
        return "shock"
    if raw_pose in ("sad", "cry"):
        return "sad"
    if raw_pose in ("angry", "strict") or norm_pose == "arms_crossed":
        return "serious"
    if norm_pose in ("think_chin", "scratch_head", "shrug_ask", "lean_curious"):
        return "curious"
    if norm_pose == "facepalm_light":
        return "skeptical"
    if norm_pose in ("hands_on_hips", "guide_sweep_board", "guide_zoom_focus"):
        return "confident"

    low = (narration or "").strip().lower()
    if low:
        if any(k in low for k in ("sốc", "bất ngờ", "không thể tin", "kinh ngạc")):
            return "shock"
        if any(k in low for k in ("ý tưởng", "phát hiện", "bí quyết", "khám phá")):
            return "idea"
        if "?" in low or any(k in low for k in ("tại sao", "vì sao", "liệu")):
            return "curious"
        if any(k in low for k in ("sai lầm", "lầm tưởng", "thật ra", "ngờ")):
            return "skeptical"
        if any(k in low for k in ("cảnh báo", "nguy hiểm", "hậu quả", "nghiêm trọng")):
            return "serious"
    return "neutral"


class EyeController:
    """Điều khiển biểu cảm mắt (10 emotion), chớp mắt sinh học 3.2s và liếc mắt."""

    _SHOCK_POSES = {"shock", "shock_hands_up", "scared", "shock_jump", "confused"}
    _HAPPY_POSES = {"happy", "laugh", "winner", "love", "idea", "idea_bulb", "celebrate", "rich"}
    _ANGRY_POSES = {"angry", "evil_grin", "run", "stop", "stop_hand"}

    def __init__(
        self,
        *,
        pose: str,
        emotion: str = "auto",
        face_mood: str | None = None,
        anim_oneshot: str | None = None,
        interaction: str = "none",
        beat_id: str = "b001",
        fps: int = 30,
    ) -> None:
        self.fps = max(15, int(fps))
        self.raw_pose = (pose or "").strip().lower()
        self.norm_pose = normalize_stickv_pose(pose)
        self.face_mood = (face_mood or "").strip().lower() or None
        self.emotion = (emotion or "auto").strip().lower()
        if self.emotion == "auto" and self.face_mood in FACE_MOOD_TO_EMOTION:
            self.emotion = FACE_MOOD_TO_EMOTION[self.face_mood]
        self.interaction = (interaction or "none").strip().lower()
        self.eye_slot = self._resolve_slot(pose, anim_oneshot, emotion=self.emotion)
        seed_num = sum(ord(ch) * (i + 1) for i, ch in enumerate(beat_id or "b001"))
        # Lịch chớp mắt biến thiên tự nhiên 2.4s - 4.2s (không đều máy móc)
        self.blink_intervals_s: list[float] = []
        self._blink_starts: list[int] = [0]
        cur = 0
        for step in range(40):
            h_val = ((seed_num * 37 + step * 73 + 19) % 100) / 100.0
            interval_s = round(2.4 + h_val * 1.8, 3)
            self.blink_intervals_s.append(interval_s)
            cur += max(30, int(round(interval_s * self.fps)))
            self._blink_starts.append(cur)
        self.blink_period_frames = self._blink_starts[1]

    @classmethod
    def _resolve_slot(cls, pose: str, anim_oneshot: str | None, *, emotion: str = "auto") -> str:
        emo = (emotion or "auto").strip().lower()
        if emo in ("happy", "idea"):
            return "eyes_happy"
        if emo in ("shock", "excited"):
            return "eyes_shock"
        if emo in ("neutral", "confident", "curious", "skeptical", "serious", "sad"):
            # Nếu emotion chỉ định rõ thì ưu tiên slot mắt của emotion đó
            if emo in ("skeptical", "serious", "sad", "curious", "confident"):
                return "eyes_neutral"

        norm = normalize_stickv_pose(pose)
        preset_eye = POSE_PRESETS.get(norm, {}).get("eye_override")
        for raw in (anim_oneshot or "", pose or ""):
            key = raw.strip().lower()
            if key in cls._SHOCK_POSES:
                return "eyes_shock"
            if key in cls._HAPPY_POSES:
                return "eyes_happy"
            if key in cls._ANGRY_POSES:
                return "eyes_angry"
        if isinstance(preset_eye, str) and preset_eye:
            return preset_eye
        return "eyes_neutral"

    def _blink_phase(self, frame_idx: int) -> int | None:
        """Trả về pha chớp mắt (0, 1, 2) kéo dài ~0.10s theo `fps`, hoặc None nếu mắt mở."""
        if frame_idx < 0:
            return None
        phase_frames = max(1, int(round(self.fps / 30.0)))
        blink_len = 3 * phase_frames
        for start in self._blink_starts:
            diff = frame_idx - start
            if 0 <= diff < blink_len:
                return diff // phase_frames
            if start > frame_idx:
                break
        return None

    def state_at(
        self, frame_idx: int, *, env_val: float = 0.0, progress: float = 0.5
    ) -> tuple[str, float, float, float]:
        """Trả về `(eye_slot, eye_scale_y, offset_x_px, offset_y_px)` kèm Prosody & Gaze Target."""
        eye_scale_y = 1.0
        blinking = False
        if self.eye_slot != "eyes_happy":
            phase = self._blink_phase(frame_idx)
            if phase == 0:
                eye_scale_y = 0.45
                blinking = True
            elif phase == 1:
                eye_scale_y = 0.12
                blinking = True
            elif phase == 2:
                eye_scale_y = 0.50
                blinking = True

        if self.emotion == "skeptical" and eye_scale_y > 0.72:
            eye_scale_y = 0.72

        gaze = POSE_PRESETS.get(self.norm_pose, {}).get("eye_gaze", (0.0, 0.0))
        ox, oy = float(gaze[0]), float(gaze[1])
        if self.interaction == "hold_prop":
            ox, oy = 4.0, -2.0
        elif self.interaction == "point_chart":
            ox, oy = 5.0, -4.0
        elif self.norm_pose in GUIDING_BOARD_POSES:
            # Gaze Target: nhìn lên bảng (+5px) lúc hướng dẫn, quay về khán giả (0px) ở cuối câu
            if progress < 0.78:
                ox = 5.0
            else:
                tail_u = min(1.0, (progress - 0.78) / 0.18)
                ox = round(5.0 * (1.0 - tail_u), 2)

        # Prosody Micro-Brows: nhướng nhẹ cụm mắt (+4% chiều cao, nâng 2.5px) ở đỉnh nhấn giọng
        if not blinking and env_val > 0.65:
            eye_scale_y = round(eye_scale_y * 1.04, 4)
            oy -= 2.5

        return self.eye_slot, eye_scale_y, ox, oy


@dataclass(frozen=True)
class PuppetPoseState:
    head_angle: float = 0.0
    head_dx: float = 0.0
    arm_l_angle: float = 0.0
    elbow_l_angle: float = 0.0
    arm_r_angle: float = 0.0
    elbow_r_angle: float = 0.0
    torso_angle: float = 0.0
    torso_dx: float = 0.0
    torso_dy: float = 0.0
    torso_scale_y: float = 1.0


def _hermite_smoothstep(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return u * u * (3.0 - 2.0 * u)


class _SpringChannel:
    """Bộ lọc lò xo giảm chấn (hỗ trợ overshoot/settle 8-12% khi `zeta < 1.0`), ổn định mọi fps."""

    def __init__(self, initial: float = 0.0) -> None:
        self.pos = float(initial)
        self.vel = 0.0

    def step(self, target: float, dt: float, omega: float = 12.0, zeta: float = 1.0) -> float:
        f = 1.0 + 2.0 * zeta * omega * dt
        oo = omega * omega
        hoo = dt * oo
        hhoo = dt * hoo
        det_inv = 1.0 / (f + hhoo)
        x = f * self.pos + dt * self.vel + hhoo * target
        v = self.vel + hoo * (target - self.pos)
        self.pos = x * det_inv
        self.vel = v * det_inv
        return self.pos


def lerp_pose_state(a: PuppetPoseState, b: PuppetPoseState, alpha: float) -> PuppetPoseState:
    t = _hermite_smoothstep(alpha)
    return PuppetPoseState(
        head_angle=a.head_angle + (b.head_angle - a.head_angle) * t,
        head_dx=a.head_dx + (b.head_dx - a.head_dx) * t,
        arm_l_angle=a.arm_l_angle + (b.arm_l_angle - a.arm_l_angle) * t,
        elbow_l_angle=a.elbow_l_angle + (b.elbow_l_angle - a.elbow_l_angle) * t,
        arm_r_angle=a.arm_r_angle + (b.arm_r_angle - a.arm_r_angle) * t,
        elbow_r_angle=a.elbow_r_angle + (b.elbow_r_angle - a.elbow_r_angle) * t,
        torso_angle=a.torso_angle + (b.torso_angle - a.torso_angle) * t,
        torso_dx=a.torso_dx + (b.torso_dx - a.torso_dx) * t,
        torso_dy=a.torso_dy + (b.torso_dy - a.torso_dy) * t,
        torso_scale_y=a.torso_scale_y + (b.torso_scale_y - a.torso_scale_y) * t,
    )


def evaluate_pose_preset(
    pose: str, t_sec: float, env_val: float, *, beat_t: float | None = None
) -> PuppetPoseState:
    """Tính góc khớp vai & khuỷu tay cho 12 hành động `POSE_PRESETS` kèm nhịp RMS sống động."""
    key = normalize_stickv_pose(pose)
    cfg = POSE_PRESETS[key]
    env = max(0.0, min(1.0, float(env_val)))
    t = max(0.0, float(t_sec))
    local_t = t if beat_t is None else max(0.0, float(beat_t))

    sh_l = float(cfg["shoulder_l"])
    el_l = float(cfg["elbow_l"])
    sh_r = float(cfg["shoulder_r"])
    el_r = float(cfg["elbow_r"])
    head = float(cfg["head_deg"])
    torso = float(cfg["torso_deg"])
    dy = float(cfg["dy_px"])
    # Weight Shift tự nhiên: chuyển trọng tâm ngang ±4-7px, nghiêng nhẹ ±3.5° & nhún gối 1.5-2.5%
    weight_wave = math.sin(1.7 * t)
    torso_dx = 4.5 * weight_wave
    knee_dip = 0.020 * (0.5 + 0.5 * math.sin(3.4 * t)) * (0.35 + 0.65 * env)
    scale_y = 1.0 + 0.010 * math.sin(2.2 * t) - knee_dip

    if key == "point_up":
        sh_r += 4.5 * math.sin(2.4 * t) * (0.3 + 0.7 * env)
        el_r += 6.0 * math.sin(2.4 * t) * (0.3 + 0.7 * env)
        head += -2.5 * env + 1.2 * math.sin(2.0 * t)
    elif key == "think_chin":
        head += 1.5 * math.sin(1.5 * t)
        el_r += 2.5 * math.sin(1.8 * t)
    elif key == "arms_crossed":
        head += -1.5 * env + 1.2 * math.sin(1.8 * t)
        dy += -2.0 * env
    elif key == "hands_on_hips":
        head += -3.0 * env + 1.4 * math.sin(2.2 * t)
        torso += 0.8 * math.sin(2.0 * t)
    elif key == "shrug_ask":
        sign = 1.0 if int(local_t * 1.4) % 2 == 0 else -1.0
        head = sign * 7.0 + 1.8 * math.sin(2.6 * t)
        sh_l += -4.0 * math.sin(2.8 * t)
        sh_r += 4.0 * math.sin(2.8 * t)
        dy = -4.0 - 2.0 * env
    elif key == "present_board":
        wave_r = math.sin(3.4 * t) * (0.35 + 0.65 * env)
        sh_r += 8.0 * wave_r
        el_r += -9.0 * wave_r
        head += -2.5 * env + 1.5 * math.sin(2.4 * t)
    elif key == "emphatic_chop":
        chop = math.sin(5.2 * t) * (0.25 + 0.75 * env)
        el_r = -40.0 + 25.0 * chop
        sh_r += 5.0 * chop
        head += -4.0 * env
        dy += -2.5 * env
    elif key == "shock_hands_up":
        damp = max(0.0, 1.0 - local_t / 0.65)
        dy = -18.0 * math.sin(math.pi * local_t / 0.40) if local_t < 0.40 else -2.0 * env
        sh_l = -52.0 + 8.0 * (1.0 - damp)
        sh_r = 52.0 - 8.0 * (1.0 - damp)
    elif key == "lean_secret":
        head += 1.8 * math.sin(2.2 * t)
        el_r += 3.0 * math.sin(2.4 * t) * env
    elif key == "count_points":
        el_r = -40.0 + 15.0 * math.sin(4.6 * t) * (0.3 + 0.7 * env)
        head += -2.5 * env + 1.5 * math.sin(2.0 * t)
    elif key == "walk_explore":
        stride = math.sin(3.6 * t)
        stride_lag = math.sin(3.6 * t - 0.35)
        sh_l = 28.0 * stride
        sh_r = -28.0 * stride
        el_l = 18.0 - 12.0 * stride_lag
        el_r = -18.0 - 12.0 * stride_lag
        torso_dx = 6.5 * stride
        torso = 2.4 * stride
        head = 2.2 * stride_lag
        dy = 0.0  # Chân bám mặt đất, tạo nhịp bước bằng nhún gối scale_y
        scale_y = 1.0 - 0.024 * abs(stride)
    elif key == "guide_sweep_board":
        arc = math.sin(2.4 * t) * (0.4 + 0.6 * env)
        sh_r = -64.0 + 18.0 * arc
        el_r = -22.0 - 14.0 * math.sin(2.4 * t - 0.35) * (0.4 + 0.6 * env)
        sh_l = 24.0 + 6.0 * math.sin(1.8 * t)
        torso = 2.6 + 1.0 * arc
        torso_dx = 5.5 * math.sin(1.9 * t)
        head = -5.0 - 2.2 * env + 1.4 * math.sin(2.0 * t)
        dy = 0.0
    elif key == "guide_two_sides":
        alt = math.sin(2.8 * t)
        sh_l = -36.0 + 16.0 * alt
        el_l = -34.0 + 12.0 * math.sin(2.8 * t - 0.3)
        sh_r = -36.0 - 16.0 * alt
        el_r = -34.0 - 12.0 * math.sin(2.8 * t - 0.3)
        torso = 2.8 * alt
        torso_dx = 6.0 * alt
        head = 4.5 * alt
        dy = 0.0
    elif key == "guide_step_count":
        beat_pulse = math.sin(4.4 * t) * (0.35 + 0.65 * env)
        sh_r = -34.0 + 10.0 * beat_pulse
        el_r = -50.0 + 20.0 * math.sin(4.4 * t - 0.3) * (0.35 + 0.65 * env)
        head = -3.0 - 3.0 * env + 1.5 * beat_pulse
        torso = 1.4 + 1.2 * beat_pulse
        torso_dx = 4.5 * math.sin(2.2 * t)
        dy = 0.0
    elif key == "guide_zoom_focus":
        pulse = math.sin(2.8 * t) * (0.4 + 0.6 * env)
        sh_l = -32.0 - 14.0 * pulse
        el_l = -46.0 - 10.0 * pulse
        sh_r = 32.0 + 14.0 * pulse
        el_r = 46.0 + 10.0 * pulse
        torso = 1.5 + 1.4 * pulse
        torso_dx = 4.0 * math.sin(1.8 * t)
        head = -2.0 - 2.5 * env
        dy = 0.0
    elif key == "welcome_open":
        open_wave = math.sin(2.2 * t)
        sh_l = -44.0 - 10.0 * open_wave
        el_l = -18.0 - 8.0 * math.sin(2.2 * t - 0.3)
        sh_r = 44.0 + 10.0 * open_wave
        el_r = 18.0 + 8.0 * math.sin(2.2 * t - 0.3)
        head = -2.0 + 5.0 * (0.5 - 0.5 * math.cos(2.0 * math.pi * 1.4 * t))
        torso_dx = 4.2 * math.sin(1.6 * t)
        dy = 0.0
    elif key == "lean_curious":
        sway = math.sin(1.8 * t)
        torso = 3.4 + 0.8 * sway
        torso_dx = 5.5 + 1.5 * sway
        head = 10.5 + 2.0 * sway
        el_r = -68.0 + 7.0 * math.sin(2.4 * t) * (0.3 + 0.7 * env)
        dy = 0.0
    elif key == "point_board_high":
        sh_r += 4.0 * math.sin(2.4 * t) * (0.3 + 0.7 * env)
        el_r += 5.0 * math.sin(2.4 * t) * (0.3 + 0.7 * env)
        head += -2.0 * env + 1.2 * math.sin(2.0 * t)
    elif key == "wave_hello":
        wave = math.sin(2.0 * math.pi * 3.2 * t)
        el_r = -20.0 + 22.0 * wave
        sh_r += 5.0 * wave
        head += 2.0 * math.sin(2.4 * t)
    elif key == "scratch_head":
        el_r = 115.0 + 8.0 * math.sin(2.0 * math.pi * 2.5 * t)
        head = 10.0 + 1.8 * math.sin(2.0 * t)
    elif key == "facepalm_light":
        head = 9.0 + 1.5 * math.sin(1.8 * t)
        dy = 2.0
    elif key == "nod_yes":
        nod = 0.5 * (1.0 - math.cos(2.0 * math.pi * 2.2 * t))
        head = -3.0 + 12.0 * nod
        el_r = -42.0 + 8.0 * nod
    elif key == "shake_no":
        wag = math.sin(2.0 * math.pi * 2.8 * t)
        head = 10.0 * wag
        el_r = -47.0 + 18.0 * wag
    else:  # idle_breathe
        breathe = math.sin(1.8 * t)
        sh_l += 3.0 * breathe
        sh_r -= 3.0 * breathe
        head += 2.0 * breathe

    return PuppetPoseState(
        head_angle=head,
        arm_l_angle=sh_l,
        elbow_l_angle=el_l,
        arm_r_angle=sh_r,
        elbow_r_angle=el_r,
        torso_angle=max(-3.5, min(3.5, torso)) if key != "lean_secret" else torso,
        torso_dx=max(-7.0, min(7.0, torso_dx)),
        torso_dy=dy,
        torso_scale_y=scale_y,
    )


def evaluate_action_curve(action: str, t_sec: float, env_val: float) -> PuppetPoseState:
    """Tính góc xoay & dịch chuyển khớp theo action oneshot/loop hoặc POSE_PRESETS."""
    act = (action or "talk_explain").strip().lower()
    env = max(0.0, min(1.0, float(env_val)))
    t = max(0.0, float(t_sec))

    if act in POSE_PRESETS:
        return evaluate_pose_preset(act, t, env, beat_t=t)
    if act == "point_board" or act == "point_chart":
        return evaluate_pose_preset("point_up", t, env, beat_t=t)
    if act == "hold_prop":
        st = evaluate_pose_preset("present_board", t, env, beat_t=t)
        return PuppetPoseState(
            head_angle=st.head_angle + 4.0,
            arm_l_angle=st.arm_l_angle,
            elbow_l_angle=st.elbow_l_angle,
            arm_r_angle=-42.0 + 7.0 * math.sin(2.6 * t) * (0.4 + 0.6 * env),
            elbow_r_angle=-32.0,
            torso_angle=st.torso_angle,
            torso_dy=-2.5 * env,
            torso_scale_y=st.torso_scale_y,
        )
    if act in ("talk_excited", "celebrate"):
        return PuppetPoseState(
            head_angle=-7.0 * env + 2.0 * math.sin(5.0 * t),
            arm_l_angle=-45.0 + 18.0 * math.sin(6.0 * t),
            elbow_l_angle=-32.0 + 12.0 * math.sin(6.0 * t),
            arm_r_angle=45.0 - 18.0 * math.sin(6.0 * t),
            elbow_r_angle=32.0 - 12.0 * math.sin(6.0 * t),
            torso_dy=-8.0 * abs(math.sin(5.0 * t)),
        )
    if act == "think_loop":
        return evaluate_pose_preset("think_chin", t, env, beat_t=t)
    if act == "shock_jump":
        return evaluate_pose_preset("shock_hands_up", t, env, beat_t=t)
    if act == "nod_agree":
        return PuppetPoseState(
            head_angle=-12.0 * math.sin(2.0 * math.pi * t / 0.6),
            arm_l_angle=10.0,
            elbow_l_angle=12.0,
            arm_r_angle=-10.0,
            elbow_r_angle=-12.0,
            torso_dy=-2.0 * abs(math.sin(2.0 * math.pi * t / 0.6)),
        )
    if act == "shake_head":
        return PuppetPoseState(
            head_dx=7.0 * math.sin(3.0 * math.pi * t / 0.7),
            arm_l_angle=12.0,
            elbow_l_angle=10.0,
            arm_r_angle=-12.0,
            elbow_r_angle=-10.0,
        )
    if act == "walk_loop":
        return evaluate_pose_preset("walk_explore", t, env, beat_t=t)
    return evaluate_pose_preset("present_board", t, env, beat_t=t)


def _transform_anchor_world(
    local_xy: tuple[float, float],
    pivot_local: tuple[float, float],
    world_pivot: tuple[float, float],
    angle_deg: float,
) -> tuple[float, float]:
    """Ánh xạ điểm neo cục bộ sang tọa độ world sau phép xoay quanh `pivot_local`."""
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    lx = local_xy[0] - pivot_local[0]
    ly = local_xy[1] - pivot_local[1]
    return (
        world_pivot[0] + (lx * cos_t + ly * sin_t),
        world_pivot[1] + (-lx * sin_t + ly * cos_t),
    )


def solve_2bone_ik(
    root: tuple[float, float],
    target: tuple[float, float],
    l1: float,
    l2: float,
    bend_dir: int = 1,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Giải bài toán 2-Bone Analytical IK (Law of Cosines) chống gãy khớp/quá duỗi."""
    rx, ry = float(root[0]), float(root[1])
    tx, ty = float(target[0]), float(target[1])
    len1 = max(2.0, float(l1))
    len2 = max(2.0, float(l2))
    total = len1 + len2

    dx, dy = tx - rx, ty - ry
    raw_d = math.hypot(dx, dy)
    if raw_d < 1e-5:
        ux, uy = 0.0, 1.0
    else:
        ux, uy = dx / raw_d, dy / raw_d

    min_d = max(abs(len1 - len2) + 1.0, 0.25 * total)
    max_d = 0.98 * total
    d = max(min_d, min(max_d, raw_d))

    cos_a = (len1 * len1 + d * d - len2 * len2) / max(1e-6, 2.0 * len1 * d)
    cos_a = max(-1.0, min(1.0, cos_a))
    sin_a = math.sqrt(max(0.0, 1.0 - cos_a * cos_a))

    # Pháp tuyến theo chiều gập giải phẫu cố định
    sign = 1.0 if bend_dir >= 0 else -1.0
    px, py = -uy * sign, ux * sign
    ex = rx + (len1 * cos_a) * ux + (len1 * sin_a) * px
    ey = ry + (len1 * cos_a) * uy + (len1 * sin_a) * py
    wx = rx + d * ux
    wy = ry + d * uy
    return (ex, ey), (wx, wy)


def clamp_arm_target(
    side: str,
    shoulder: tuple[float, float],
    target: tuple[float, float],
    torso_cx: float,
    torso_w: float,
    l1: float,
    l2: float,
    *,
    pose: str = "present_board",
) -> tuple[float, float]:
    """Khóa giải phẫu: kẹp tầm với `[0.25, 0.98]*(L1+L2)` & cấm vắt chéo dị dạng qua trục thân."""
    tx, ty = float(target[0]), float(target[1])
    allow_cross = pose in ("arms_crossed", "think_chin")
    if not allow_cross:
        margin = max(6.0, torso_w * 0.14)
        if side == "left":
            tx = min(tx, torso_cx + margin)
        else:
            tx = max(tx, torso_cx - margin)

    dx = tx - shoulder[0]
    dy = ty - shoulder[1]
    dist = math.hypot(dx, dy)
    total = max(4.0, l1 + l2)
    min_d = 0.25 * total
    max_d = 0.98 * total
    if dist < 1e-5:
        return shoulder[0] + (-min_d if side == "left" else min_d), shoulder[1] + min_d * 0.5
    if dist < min_d or dist > max_d:
        clamped = max(min_d, min(max_d, dist))
        scale = clamped / dist
        tx = shoulder[0] + dx * scale
        ty = shoulder[1] + dy * scale
    return tx, ty


def resolve_hand_shape(pose: str, side: str, interaction: str = "none") -> str:
    """Chọn 1 trong 4 hình bàn tay găng trắng vector theo pose & bên tay."""
    p = normalize_stickv_pose(pose)
    if interaction == "point_chart" and side == "right":
        return "point_index"
    if p in ("point_up", "point_board_high", "guide_sweep_board", "guide_zoom_focus") and side == "right":
        return "point_index"
    if p in ("count_points", "guide_step_count") and side == "right":
        return "count_fingers"
    if p in ("emphatic_chop", "shock_hands_up", "shake_no"):
        return "fist_punch"
    return "open_palm"


def detect_rms_peaks(
    env: list[float],
    fps: int,
    *,
    threshold: float = 0.62,
    min_gap_s: float = 0.75,
) -> list[float]:
    """Tìm các mốc đỉnh nhấn giọng RMS (`env > 0.62`, cách nhau `>= 0.75s`) cho diễn hoạt pha 2."""
    if not env or fps <= 0:
        return []
    peaks: list[float] = []
    last_t = -min_gap_s
    for idx, val in enumerate(env):
        if val <= threshold:
            continue
        t_s = idx / float(fps)
        if t_s - last_t < min_gap_s:
            continue
        prev_v = env[idx - 1] if idx > 0 else 0.0
        next_v = env[idx + 1] if idx + 1 < len(env) else 0.0
        if val >= prev_v and val >= next_v:
            peaks.append(round(t_s, 3))
            last_t = t_s
    return peaks


def _draw_capsule_bone(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    width_px: float,
    color: tuple[int, int, int, int] = JOINT_CAP_COLOR,
) -> None:
    w = max(2, int(round(width_px)))
    r = w / 2.0
    draw.line([(p0[0], p0[1]), (p1[0], p1[1])], fill=color, width=w)
    for px, py in (p0, p1):
        draw.ellipse((px - r, py - r, px + r, py + r), fill=color)


def _draw_vector_hand(
    draw: ImageDraw.ImageDraw,
    wrist: tuple[float, float],
    elbow: tuple[float, float],
    hand_shape: str,
    *,
    hand_r: float,
    outline_w: int,
) -> None:
    """Vẽ 4 kiểu bàn tay găng trắng vector xoay theo trục cẳng tay (`elbow -> wrist`)."""
    dx = wrist[0] - elbow[0]
    dy = wrist[1] - elbow[1]
    norm = max(1e-5, math.hypot(dx, dy))
    ux, uy = dx / norm, dy / norm
    px, py = -uy, ux

    cx = wrist[0] + ux * (hand_r * 0.65)
    cy = wrist[1] + uy * (hand_r * 0.65)
    white = (255, 255, 255, 255)
    ink = JOINT_CAP_COLOR
    r = max(4.0, hand_r)

    if hand_shape == "fist_punch":
        fr = r * 1.08
        draw.ellipse((cx - fr, cy - fr, cx + fr, cy + fr), fill=white, outline=ink, width=outline_w)
        # Vạch ngón nắm gọn
        draw.line(
            [
                (cx - px * fr * 0.45, cy - py * fr * 0.45),
                (cx + px * fr * 0.45, cy + py * fr * 0.45),
            ],
            fill=ink,
            width=max(2, outline_w - 1),
        )
        return

    # Lòng bàn tay tròn mềm
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=white, outline=ink, width=outline_w)

    if hand_shape == "point_index":
        tip = (cx + ux * (r * 1.95), cy + uy * (r * 1.95))
        _draw_capsule_bone(draw, (cx + ux * r * 0.35, cy + uy * r * 0.35), tip, r * 0.62, ink)
        _draw_capsule_bone(draw, (cx + ux * r * 0.40, cy + uy * r * 0.40), tip, max(2.0, r * 0.32), white)
        return

    if hand_shape == "count_fingers":
        for offset in (-0.55, 0.0, 0.55):
            base = (cx + px * r * offset, cy + py * r * offset)
            tip = (base[0] + ux * r * 1.45, base[1] + uy * r * 1.45)
            _draw_capsule_bone(draw, base, tip, r * 0.46, ink)
            _draw_capsule_bone(draw, base, tip, max(2.0, r * 0.22), white)
        return

    # open_palm: 3 ngón xòe thân thiện
    for ang_off in (-0.42, 0.0, 0.42):
        ca, sa = math.cos(ang_off), math.sin(ang_off)
        fx, fy = ux * ca - uy * sa, ux * sa + uy * ca
        base = (cx + fx * r * 0.45, cy + fy * r * 0.45)
        tip = (cx + fx * r * 1.45, cy + fy * r * 1.45)
        _draw_capsule_bone(draw, base, tip, r * 0.44, ink)
        _draw_capsule_bone(draw, base, tip, max(2.0, r * 0.20), white)


def _load_rgba_scaled(path: Path, scale: float) -> Image.Image:
    with Image.open(path) as raw:
        rgba = raw.convert("RGBA")
        if abs(scale - 1.0) < 0.005:
            return rgba.copy()
        nw = max(4, int(round(rgba.width * scale)))
        nh = max(4, int(round(rgba.height * scale)))
        return rgba.resize((nw, nh), Image.Resampling.LANCZOS)


class PuppetRig:
    """Bộ diễn hoạt Puppet 2D hoàn chỉnh (xương tay 2 đoạn vai–khuỷu + hierarchical bone tree)."""

    def __init__(
        self,
        *,
        library_dir: Path,
        assets_dir: Path,
        target_height: int,
        pose: str = "present_board",
        emotion: str = "auto",
        face_mood: str | None = None,
        narration: str = "",
        anim_oneshot: str | None = None,
        anim_loop: str = "talk_explain",
        interaction: str = "none",
        facing: str = "right",
        beat_id: str = "b001",
        fps: int = 30,
        duration_sec: float = 3.5,
        speech_start: float = 0.0,
        speech_end: float = 2.0,
        rms_env: list[float] | None = None,
        prev_pose_state: PuppetPoseState | None = None,
        global_t_offset: float = 0.0,
        board_type: str = "bullets",
    ) -> None:
        self.target_height = max(120, int(target_height))
        self.raw_pose = (pose or "present_board").strip().lower()
        self.pose = normalize_stickv_pose(pose)
        self.face_mood = (face_mood or "").strip().lower() or None
        self.emotion = resolve_stickv_emotion(emotion, pose, narration, face_mood=self.face_mood)
        self.anim_oneshot = (anim_oneshot or "").strip() or None
        self.anim_loop = (anim_loop or "talk_explain").strip() or "talk_explain"
        self.interaction = (interaction or "none").strip().lower()
        self.board_type = (board_type or "bullets").strip().lower()
        self.facing = facing
        self.fps = max(15, int(fps))
        self.duration_sec = max(0.8, float(duration_sec))
        self.speech_start = max(0.0, float(speech_start))
        self.speech_end = max(self.speech_start, float(speech_end))
        self.env = smooth_rms_envelope(rms_env or [], fps=self.fps)
        self.rms_peaks = detect_rms_peaks(self.env, self.fps)
        self.prev_pose_state = prev_pose_state
        self.global_t_offset = max(0.0, float(global_t_offset))
        self.tween_dur = 0.38 if prev_pose_state is not None else 0.0
        init_st = prev_pose_state or PuppetPoseState()
        self._springs = {
            "head_angle": _SpringChannel(init_st.head_angle),
            "head_dx": _SpringChannel(init_st.head_dx),
            "arm_l_angle": _SpringChannel(init_st.arm_l_angle),
            "elbow_l_angle": _SpringChannel(init_st.elbow_l_angle),
            "arm_r_angle": _SpringChannel(init_st.arm_r_angle),
            "elbow_r_angle": _SpringChannel(init_st.elbow_r_angle),
            "torso_angle": _SpringChannel(init_st.torso_angle),
            "torso_dx": _SpringChannel(init_st.torso_dx),
            "torso_dy": _SpringChannel(init_st.torso_dy),
            "torso_scale_y": _SpringChannel(init_st.torso_scale_y),
        }
        self._head_lag_frames = max(1, int(round(self.fps / 30.0)))
        self._shoulder_lag_frames = max(2, int(round(2.0 * self.fps / 30.0)))
        self._elbow_lag_frames = max(4, int(round(4.0 * self.fps / 30.0)))
        self._follow_hist_len = self._elbow_lag_frames + 2
        self._follow_history: list[PuppetPoseState] = [init_st] * self._follow_hist_len
        self._mouth_ema_decay: float = 0.40 ** (30.0 / self.fps)
        self._mouth_sy_smooth: float = 1.0
        self.last_pose_state: PuppetPoseState = init_st

        slot_paths = find_puppet_slot_paths(library_dir, assets_dir)
        base_path = slot_paths["base_character"][0]
        pdir = Path(assets_dir) / "stickman" / "puppet"
        if not (pdir / "base_character.png").is_file():
            pdir = Path(library_dir) / "stickman" / "puppet"
        cache_dir = pdir / ".segments"

        if base_path is None:
            raise FileNotFoundError("Không tìm thấy base_character cho Puppet 2D")

        seg_info = auto_segment_puppet(
            base_path, cache_dir, puppet_dir=pdir if pdir.is_dir() else None
        )
        self.rig_cfg: dict[str, Any] = seg_info["rig_config"]
        seg_paths: dict[str, Path] = seg_info["segments"]

        # Tính hệ số scale sao cho tổng chiều cao (đầu + thân áo + chân IK) khớp `target_height`
        leg_ratio = float(self.rig_cfg.get("torso_leg_ratio", 0.62))
        with Image.open(seg_paths["body_torso"]) as bt, Image.open(seg_paths["head_blank"]) as hb:
            raw_total_h = max(1, int(bt.height * (1.0 + leg_ratio)) + int(hb.height * 0.85))
        scale = (self.target_height * 0.88) / raw_total_h
        self._scale = scale

        self.parts: dict[str, Image.Image] = {}
        for name in ALL_SEGMENT_NAMES:
            sp = seg_paths.get(name)
            if sp is not None and sp.is_file():
                self.parts[name] = _load_rgba_scaled(sp, scale)

        # Nạp mắt và miệng (đã tách nền trắng + crop + cache)
        self.eyes: dict[str, Image.Image] = {}
        for eslot in ("eyes_neutral", "eyes_happy", "eyes_shock", "eyes_angry"):
            ep = slot_paths[eslot][0]
            if ep is not None:
                cleaned_p = prepare_puppet_sprite(ep, cache_dir, eslot)
                with Image.open(cleaned_p) as raw_e:
                    self.eyes[eslot] = raw_e.convert("RGBA")
        if "eyes_neutral" not in self.eyes and self.eyes:
            first_e = next(iter(self.eyes.values()))
            self.eyes["eyes_neutral"] = first_e.copy()

        self.mouths: dict[str, Image.Image] = {}
        for mslot in ("mouth_closed", "mouth_open"):
            mp = slot_paths[mslot][0]
            if mp is not None:
                cleaned_p = prepare_puppet_sprite(mp, cache_dir, mslot)
                with Image.open(cleaned_p) as raw_m:
                    self.mouths[mslot] = raw_m.convert("RGBA")
        if "mouth_closed" not in self.mouths and "mouth_open" in self.mouths:
            self.mouths["mouth_closed"] = self.mouths["mouth_open"].copy()
        if "mouth_open" not in self.mouths and "mouth_closed" in self.mouths:
            self.mouths["mouth_open"] = self.mouths["mouth_closed"].copy()

        self.eye_ctrl = EyeController(
            pose=pose,
            emotion=self.emotion,
            face_mood=self.face_mood,
            anim_oneshot=self.anim_oneshot,
            interaction=self.interaction,
            beat_id=beat_id,
            fps=self.fps,
        )
        self.oneshot_dur = 0.65 if self.anim_oneshot else 0.0
        self.blend_dur = 0.15  # 5 frames @ 30fps

    def _evaluate_main_pose(self, t_sec: float, gt: float, env_val: float) -> PuppetPoseState:
        if self.interaction == "point_chart":
            return evaluate_pose_preset("point_up", gt, env_val, beat_t=t_sec)
        if self.interaction == "hold_prop":
            return evaluate_action_curve("hold_prop", gt, env_val)
        if self.raw_pose in POSE_PRESETS or self.raw_pose in POSE_ALIASES:
            return evaluate_pose_preset(self.pose, gt, env_val, beat_t=t_sec)
        return evaluate_action_curve(self.anim_loop, gt, env_val)

    def _raw_pose_state_at(self, t_sec: float, env_val: float) -> PuppetPoseState:
        gt = self.global_t_offset + t_sec

        if t_sec > self.speech_end:
            idle_state = evaluate_pose_preset("idle_breathe", gt, 0.0, beat_t=t_sec)
            dt_idle = t_sec - self.speech_end
            if dt_idle < self.blend_dur:
                prev_state = self._evaluate_main_pose(t_sec, gt, env_val)
                return lerp_pose_state(prev_state, idle_state, dt_idle / self.blend_dur)
            return idle_state

        if self.anim_oneshot and t_sec < self.oneshot_dur:
            target_st = evaluate_action_curve(self.anim_oneshot, t_sec, env_val)
        else:
            loop_state = self._evaluate_main_pose(t_sec, gt, env_val)
            if self.anim_oneshot and t_sec < (self.oneshot_dur + self.blend_dur):
                alpha = (t_sec - self.oneshot_dur) / self.blend_dur
                oneshot_tail = evaluate_action_curve(self.anim_oneshot, t_sec, env_val)
                target_st = lerp_pose_state(oneshot_tail, loop_state, alpha)
            else:
                target_st = loop_state

        if self.prev_pose_state is not None and t_sec < self.tween_dur:
            st_out = lerp_pose_state(self.prev_pose_state, target_st, t_sec / self.tween_dur)
        else:
            st_out = target_st

        # Áp dụng biến đổi hình học đặc trưng theo 10 biểu cảm khuôn mặt
        dh = 0.0
        dy_mul = 1.0
        extra_dy = 0.0
        if self.emotion == "confident":
            dh = -3.0
        elif self.emotion == "curious":
            dh = 10.0 if abs(st_out.head_angle) < 4.0 else 4.0
        elif self.emotion == "skeptical":
            dh = -5.0
        elif self.emotion == "sad":
            dh = 7.0
        elif self.emotion == "excited":
            dy_mul = 1.3
            extra_dy = -4.0 * env_val
        if dh != 0.0 or dy_mul != 1.0 or extra_dy != 0.0:
            st_out = PuppetPoseState(
                head_angle=st_out.head_angle + dh,
                head_dx=st_out.head_dx,
                arm_l_angle=st_out.arm_l_angle,
                elbow_l_angle=st_out.elbow_l_angle,
                arm_r_angle=st_out.arm_r_angle,
                elbow_r_angle=st_out.elbow_r_angle,
                torso_angle=st_out.torso_angle,
                torso_dy=st_out.torso_dy * dy_mul + extra_dy,
                torso_scale_y=st_out.torso_scale_y,
            )
        return st_out

    def _pose_state_at(self, t_sec: float, env_val: float) -> PuppetPoseState:
        raw_target = self._raw_pose_state_at(t_sec, env_val)
        dt = 1.0 / self.fps
        # Follow-through phân tầng giữ nguyên độ trễ theo giây (33ms / 67ms / 133ms ở mọi fps)
        self._follow_history.append(raw_target)
        if len(self._follow_history) > self._follow_hist_len:
            self._follow_history.pop(0)
        head_lag = self._follow_history[-1 - self._head_lag_frames]
        shoulder_lag = self._follow_history[-1 - self._shoulder_lag_frames]
        elbow_lag = self._follow_history[-1 - self._elbow_lag_frames]

        smoothed = PuppetPoseState(
            head_angle=self._springs["head_angle"].step(
                head_lag.head_angle, dt, omega=11.0, zeta=0.74
            ),
            head_dx=self._springs["head_dx"].step(head_lag.head_dx, dt, omega=12.0, zeta=0.80),
            arm_l_angle=self._springs["arm_l_angle"].step(
                shoulder_lag.arm_l_angle, dt, omega=10.5, zeta=0.64
            ),
            elbow_l_angle=self._springs["elbow_l_angle"].step(
                elbow_lag.elbow_l_angle, dt, omega=11.0, zeta=0.62
            ),
            arm_r_angle=self._springs["arm_r_angle"].step(
                shoulder_lag.arm_r_angle, dt, omega=10.5, zeta=0.64
            ),
            elbow_r_angle=self._springs["elbow_r_angle"].step(
                elbow_lag.elbow_r_angle, dt, omega=11.0, zeta=0.62
            ),
            torso_angle=self._springs["torso_angle"].step(
                raw_target.torso_angle, dt, omega=14.0, zeta=0.88
            ),
            torso_dx=self._springs["torso_dx"].step(raw_target.torso_dx, dt, omega=13.0, zeta=0.88),
            torso_dy=self._springs["torso_dy"].step(raw_target.torso_dy, dt, omega=14.0, zeta=0.90),
            torso_scale_y=self._springs["torso_scale_y"].step(
                raw_target.torso_scale_y, dt, omega=13.0, zeta=0.90
            ),
        )
        self.last_pose_state = smoothed
        return smoothed

    def _draw_emotion_details(
        self,
        head: Image.Image,
        *,
        pad_x: int,
        pad_top: int,
        hw: int,
        hh: int,
        t_sec: float,
        env_val: float = 0.0,
    ) -> None:
        """Vẽ lông mày & ký hiệu cảm xúc (bóng đèn, ?, !, mồ hôi, tia sáng) trên lề Head."""
        d = ImageDraw.Draw(head)
        emo = self.emotion
        ink = JOINT_CAP_COLOR
        stroke = max(2, int(round(hw * 0.028)))
        ecx_l = pad_x + hw * 0.34
        ecx_r = pad_x + hw * 0.66
        brow_w = max(8, hw * 0.13)
        # Prosody Micro-Brows: nâng nhẹ chân mày 2.5px ở đỉnh nhấn giọng nói (env > 0.65)
        brow_lift = 2.5 if env_val > 0.65 else 0.0
        brow_y = pad_top + hh * 0.25 - brow_lift

        # 1. Lông mày biểu cảm
        if emo == "confident":
            d.line([(ecx_l - brow_w, brow_y), (ecx_l + brow_w, brow_y - 1)], fill=ink, width=stroke)
            d.arc(
                (ecx_r - brow_w, brow_y - 10, ecx_r + brow_w, brow_y + 4),
                start=195,
                end=345,
                fill=ink,
                width=stroke,
            )
        elif emo == "curious":
            d.line([(ecx_l - brow_w, brow_y), (ecx_l + brow_w, brow_y + 2)], fill=ink, width=stroke)
            d.arc(
                (ecx_r - brow_w, brow_y - 11, ecx_r + brow_w, brow_y + 3),
                start=190,
                end=350,
                fill=ink,
                width=stroke,
            )
        elif emo == "skeptical":
            d.line(
                [(ecx_l - brow_w, brow_y + 4), (ecx_l + brow_w, brow_y + 5)], fill=ink, width=stroke
            )
            d.arc(
                (ecx_r - brow_w, brow_y - 11, ecx_r + brow_w, brow_y + 3),
                start=190,
                end=350,
                fill=ink,
                width=stroke,
            )
        elif emo == "serious":
            d.line(
                [(ecx_l - brow_w, brow_y - 3), (ecx_l + brow_w, brow_y + 5)], fill=ink, width=stroke
            )
            d.line(
                [(ecx_r - brow_w, brow_y + 5), (ecx_r + brow_w, brow_y - 3)], fill=ink, width=stroke
            )
        elif emo == "sad":
            d.line(
                [(ecx_l - brow_w, brow_y + 5), (ecx_l + brow_w, brow_y - 2)], fill=ink, width=stroke
            )
            d.line(
                [(ecx_r - brow_w, brow_y - 2), (ecx_r + brow_w, brow_y + 5)], fill=ink, width=stroke
            )
        elif emo in ("happy", "idea", "excited"):
            for bx in (ecx_l, ecx_r):
                d.arc(
                    (bx - brow_w, brow_y - 8, bx + brow_w, brow_y + 6),
                    start=195,
                    end=345,
                    fill=ink,
                    width=stroke,
                )

        # 2. Ký hiệu cảm xúc vẽ trên vùng đệm quanh đầu (xoay mượt cùng cổ)
        if emo == "curious":
            bob = math.sin(4.0 * t_sec) * 3.5
            qx = pad_x + hw + max(8, int(hw * 0.14))
            qy = pad_top + hh * 0.14 + bob
            r = max(6, int(hw * 0.08))
            amber = (245, 158, 11, 255)
            d.arc((qx - r, qy - r, qx + r, qy + r), start=180, end=40, fill=amber, width=stroke + 1)
            d.line([(qx, qy + r - 1), (qx, qy + r + 5)], fill=amber, width=stroke + 1)
            d.ellipse((qx - 2, qy + r + 8, qx + 2, qy + r + 12), fill=amber)
        elif emo == "idea":
            pop = min(1.0, max(0.35, t_sec / 0.25)) if t_sec < 0.25 else 1.0
            bx = pad_x + hw * 0.5
            by = max(14.0, pad_top - hh * 0.16)
            br = max(8, int(round(hw * 0.11 * pop)))
            gold = (250, 204, 21, 255)
            d.ellipse((bx - br, by - br, bx + br, by + br), fill=gold, outline=ink, width=2)
            d.rectangle(
                (bx - br * 0.45, by + br - 2, bx + br * 0.45, by + br + 5), fill=(71, 85, 105, 255)
            )
            for ang in (-75, -35, 0, 35, 75):
                rad = math.radians(ang - 90)
                r0, r1 = br + 3, br + max(6, int(br * 0.7))
                d.line(
                    [
                        (bx + math.cos(rad) * r0, by + math.sin(rad) * r0),
                        (bx + math.cos(rad) * r1, by + math.sin(rad) * r1),
                    ],
                    fill=gold,
                    width=max(2, stroke),
                )
        elif emo == "shock":
            red = (217, 35, 46, 255)
            jit = math.sin(18.0 * t_sec) * 2.0
            for side_x in (pad_x - max(10, int(hw * 0.16)), pad_x + hw + max(10, int(hw * 0.16))):
                ey0 = pad_top + hh * 0.08 + jit
                d.line(
                    [(side_x, ey0), (side_x, ey0 + max(14, hh * 0.22))], fill=red, width=stroke + 1
                )
                d.ellipse(
                    (
                        side_x - 3,
                        ey0 + max(18, hh * 0.27),
                        side_x + 3,
                        ey0 + max(18, hh * 0.27) + 6,
                    ),
                    fill=red,
                )
        elif emo == "sad":
            slide = (t_sec * 14.0) % 10.0
            tx = pad_x + hw * 0.86
            ty = pad_top + hh * 0.24 + slide
            blue = (56, 189, 248, 255)
            d.polygon([(tx, ty - 8), (tx - 5, ty + 2), (tx + 5, ty + 2)], fill=blue)
            d.ellipse((tx - 5, ty - 2, tx + 5, ty + 8), fill=blue)
        elif emo == "excited":
            gold = (250, 204, 21, 255)
            pulse = 1.0 + 0.25 * abs(math.sin(6.0 * t_sec))
            sr = max(5, int(round(hw * 0.07 * pulse)))
            pts = [
                (pad_x - 8, pad_top + hh * 0.15),
                (pad_x + hw + 8, pad_top + hh * 0.15),
                (pad_x + hw * 0.22, max(10.0, pad_top - 6)),
                (pad_x + hw * 0.78, max(10.0, pad_top - 6)),
            ]
            for sx, sy in pts:
                d.line([(sx - sr, sy), (sx + sr, sy)], fill=gold, width=max(2, stroke))
                d.line([(sx, sy - sr), (sx, sy + sr)], fill=gold, width=max(2, stroke))

    def _build_head_layer(
        self, frame_idx: int, env_val: float, t_sec: float = 0.0
    ) -> tuple[Image.Image, tuple[float, float]]:
        """Lắp Eyes, Mouth & Emotion trên Head (có lề an toàn không cắt ký hiệu) + trả pivot."""
        head_raw = self.parts["head_blank"]
        hw, hh = head_raw.size
        pad_x = max(24, int(round(hw * 0.40)))
        pad_top = max(28, int(round(hh * 0.42)))
        pad_bot = 4
        head = Image.new("RGBA", (hw + 2 * pad_x, hh + pad_top + pad_bot), (0, 0, 0, 0))
        head.alpha_composite(head_raw, (pad_x, pad_top))

        # 1. Eyes layer (kèm Prosody Micro-Brows & Gaze Target)
        progress = min(1.0, max(0.0, t_sec / max(0.25, self.speech_end)))
        eslot, eye_sy, eox, eoy = self.eye_ctrl.state_at(
            frame_idx, env_val=env_val, progress=progress
        )
        eye_src = self.eyes.get(eslot) or self.eyes.get("eyes_neutral")
        if eye_src is not None:
            ew = max(8, int(round(hw * float(self.rig_cfg["eyes_width_ratio"]))))
            eh = max(2, int(round((ew * eye_src.height / max(1, eye_src.width)) * eye_sy)))
            eye_resized = eye_src.resize((ew, eh), Image.Resampling.LANCZOS)
            ecx = pad_x + hw * float(self.rig_cfg["eyes_center_head"][0]) + eox
            ecy = pad_top + hh * float(self.rig_cfg["eyes_center_head"][1]) + eoy
            ex = max(pad_x + 2, min(pad_x + hw - ew - 2, int(round(ecx - ew / 2))))
            ey = max(pad_top + 2, min(pad_top + hh - eh - 2, int(round(ecy - eh / 2))))
            head.alpha_composite(eye_resized, (ex, ey))
            eye_resized.close()

        # 2. Mouth layer (3 mức closed -> half_open -> open + độ mở 1.18x khi shock/excited)
        mslot, msx, msy_target = compute_mouth_transform(env_val)
        if self.emotion in ("shock", "excited"):
            msy_target *= 1.18
            mslot = "mouth_open" if env_val >= 0.08 or self.emotion == "shock" else mslot
        self._mouth_sy_smooth = (
            1.0 - self._mouth_ema_decay
        ) * msy_target + self._mouth_ema_decay * self._mouth_sy_smooth
        msy = self._mouth_sy_smooth if mslot == "mouth_open" else 1.0
        mouth_src = self.mouths.get(mslot) or self.mouths.get("mouth_closed")
        if mouth_src is not None:
            base_mw = max(8, int(round(hw * float(self.rig_cfg["mouth_width_ratio"]))))
            base_mh = max(4, int(round(base_mw * mouth_src.height / max(1, mouth_src.width))))
            mw = max(4, min(int(hw * 0.65), int(round(base_mw * msx))))
            mh = max(3, min(int(hh * 0.42), int(round(base_mh * msy))))
            mouth_resized = mouth_src.resize((mw, mh), Image.Resampling.LANCZOS)
            mcx = pad_x + hw * float(self.rig_cfg["mouth_center_head"][0])
            mcy = pad_top + hh * float(self.rig_cfg["mouth_center_head"][1])
            mx = max(pad_x + 2, min(pad_x + hw - mw - 2, int(round(mcx - mw / 2))))
            my = max(pad_top + 2, min(pad_top + hh - mh - 2, int(round(mcy - mh / 2))))
            head.alpha_composite(mouth_resized, (mx, my))
            mouth_resized.close()

        self._draw_emotion_details(
            head, pad_x=pad_x, pad_top=pad_top, hw=hw, hh=hh, t_sec=t_sec, env_val=env_val
        )
        head_piv = (
            pad_x + float(self.rig_cfg["neck_pivot_head"][0]) * hw,
            pad_top + float(self.rig_cfg["neck_pivot_head"][1]) * hh,
        )
        return head, head_piv

    def _render_upper_arm(
        self,
        canvas: Image.Image,
        side: str,
        sh_world: tuple[float, float],
        sh_angle: float,
        torso_angle: float,
    ) -> tuple[float, float] | None:
        """Vẽ bắp tay xoay quanh vai và trả về tọa độ world của khớp khuỷu (fallback 1 đoạn)."""
        up_img = self.parts.get(f"upper_arm_{side}")
        fore_img = self.parts.get(f"forearm_{side}")
        if up_img is not None and fore_img is not None and f"elbow_anchor_{side}" in self.rig_cfg:
            piv_cfg = self.rig_cfg.get(
                f"upper_shoulder_{side}_pivot", self.rig_cfg[f"shoulder_{side}_pivot"]
            )
            up_piv = (float(piv_cfg[0]) * up_img.width, float(piv_cfg[1]) * up_img.height)
            total_sh = sh_angle + torso_angle
            up_rot, up_rpiv = rotate_around_pivot(up_img, total_sh, up_piv)
            canvas.alpha_composite(
                up_rot,
                (int(round(sh_world[0] - up_rpiv[0])), int(round(sh_world[1] - up_rpiv[1]))),
            )
            up_rot.close()
            el_cfg = self.rig_cfg[f"elbow_anchor_{side}"]
            el_local = (float(el_cfg[0]) * up_img.width, float(el_cfg[1]) * up_img.height)
            return _transform_anchor_world(el_local, up_piv, sh_world, total_sh)

        # Fallback 1 đoạn nếu người dùng tự nạp bộ segment thủ công chưa tách khuỷu
        arm_src = self.parts[f"arm_{side}"]
        arm_piv = (
            float(self.rig_cfg[f"shoulder_{side}_pivot"][0]) * arm_src.width,
            float(self.rig_cfg[f"shoulder_{side}_pivot"][1]) * arm_src.height,
        )
        arm_rot, arm_rpiv = rotate_around_pivot(arm_src, sh_angle + torso_angle, arm_piv)
        canvas.alpha_composite(
            arm_rot,
            (int(round(sh_world[0] - arm_rpiv[0])), int(round(sh_world[1] - arm_rpiv[1]))),
        )
        arm_rot.close()
        return None

    def _render_forearm(
        self,
        canvas: Image.Image,
        side: str,
        elbow_world: tuple[float, float] | None,
        sh_angle: float,
        elbow_angle: float,
        torso_angle: float,
    ) -> None:
        """Vẽ cẳng tay + găng tay xoay quanh khớp khuỷu nối liền bắp tay."""
        if elbow_world is None:
            return
        fore_img = self.parts.get(f"forearm_{side}")
        if fore_img is None:
            return
        piv_cfg = self.rig_cfg[f"elbow_{side}_pivot"]
        fore_piv = (float(piv_cfg[0]) * fore_img.width, float(piv_cfg[1]) * fore_img.height)
        total_fore = sh_angle + elbow_angle + torso_angle
        fore_rot, fore_rpiv = rotate_around_pivot(fore_img, total_fore, fore_piv)
        canvas.alpha_composite(
            fore_rot,
            (int(round(elbow_world[0] - fore_rpiv[0])), int(round(elbow_world[1] - fore_rpiv[1]))),
        )
        fore_rot.close()

    def _choreography_offsets(self, t_sec: float, env_val: float) -> tuple[float, float, float, float, float, float]:
        """Diễn hoạt 3 pha trong 1 Beat:
        - Pha 1 (0..0.55s): chuyển trọng tâm hông + nhún gối nhẹ.
        - Pha 2 (0.55..end-0.55s): đánh nhịp tay theo đỉnh RMS & dịch mục tiêu chỉ bảng 1->2->3.
        - Pha 3 (0.55s cuối): thu tay mềm về tư thế nối cảnh.
        Trả về `(hip_dx, knee_dip_px, l_dx, l_dy, r_dx, r_dy)`.
        """
        dur = max(1.1, self.duration_sec)
        p1_end = min(0.55, dur * 0.28)
        p3_start = max(p1_end + 0.1, dur - 0.55)

        if t_sec < p1_end:
            u = 1.0 - (1.0 - max(0.0, t_sec / max(0.05, p1_end))) ** 3
            hip_dx = math.sin(u * math.pi * 0.5) * 6.5
            knee_dip = math.sin(u * math.pi) * (self.target_height * 0.026)
            return hip_dx, knee_dip, 0.0, 0.0, 0.0, 0.0

        if t_sec >= p3_start:
            u = min(1.0, (t_sec - p3_start) / max(0.1, dur - p3_start))
            ease = 1.0 - u
            return 3.0 * ease, 0.0, 0.0, 8.0 * u, 0.0, 8.0 * u

        # Pha 2: nhấn giọng theo đỉnh RMS + dịch mục tiêu ngón trỏ theo ý 1 -> 2 -> 3
        phase2_u = (t_sec - p1_end) / max(0.2, p3_start - p1_end)
        pulse = 0.0
        peak_idx = 0
        for idx_p, pt in enumerate(self.rms_peaks):
            dt_p = t_sec - pt
            if 0.0 <= dt_p <= 0.42:
                pulse = max(pulse, math.sin((dt_p / 0.42) * math.pi))
                peak_idx = idx_p

        hip_dx = math.sin(phase2_u * math.pi * 2.0) * 7.0
        knee_dip = max(0.0, pulse * self.target_height * 0.022 + env_val * self.target_height * 0.012)

        l_dx = 0.0
        l_dy = 0.0
        r_dx = 0.0
        r_dy = 0.0
        if self.board_type in ("comparison", "myth_vs_fact"):
            # Luân phiên nhấn tay trái / phải theo đỉnh giọng nói
            if peak_idx % 2 == 0:
                l_dy = -18.0 * pulse - 6.0 * env_val
                l_dx = -10.0 * pulse
            else:
                r_dy = -18.0 * pulse - 6.0 * env_val
                r_dx = 10.0 * pulse
        elif self.board_type in ("bullets", "flow_steps", "recap_card"):
            # Dịch mục tiêu ngón trỏ dần từ Ý 1 -> Ý 2 -> Ý 3 trên bảng
            step_slot = min(2, int(phase2_u * 3.0))
            r_dy = (-22.0 + step_slot * 16.0) - 10.0 * pulse
            r_dx = 8.0 * math.sin(phase2_u * math.pi)
            l_dy = -6.0 * pulse
        else:
            r_dy = -14.0 * pulse - 5.0 * env_val
            l_dy = -8.0 * pulse
        return hip_dx, knee_dip, l_dx, l_dy, r_dx, r_dy

    def render_frame(self, frame_idx: int, t_sec: float) -> Image.Image:
        """Dựng 1 frame Hybrid 2D IK Puppet (`v4_hybrid_ik`): tứ chi 2-Bone IK 3x SSAA cục bộ, chân bám đất 0% trượt."""
        env_val = self.env[frame_idx] if 0 <= frame_idx < len(self.env) else 0.0
        st = self._pose_state_at(t_sec, env_val)

        torso_base = self.parts["body_torso"]
        head_local, head_piv = self._build_head_layer(frame_idx, env_val, t_sec=t_sec)
        leg_ratio = float(self.rig_cfg.get("torso_leg_ratio", 0.62))
        leg_total_h = max(32.0, torso_base.height * leg_ratio)

        # Canvas cục bộ ôm sát nhân vật (nhẹ CPU trên i5-10400)
        cw = max(int(self.target_height * 0.96), torso_base.width * 3 + 48)
        ch = self.target_height
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

        hip_dx_c, knee_dip_c, l_dx_c, l_dy_c, r_dx_c, r_dy_c = self._choreography_offsets(
            t_sec, env_val
        )

        try:
            # Neo mặt đất cố định cho 2 chiếc giày (0% trượt chân)
            ground_y = float(ch - 10)
            shoe_l = self.parts.get("shoe_left")
            shoe_r = self.parts.get("shoe_right")
            shoe_h = float(max(shoe_l.height if shoe_l else 18, shoe_r.height if shoe_r else 18))
            ankle_y = ground_y - shoe_h * 0.65
            stance_half = max(18.0, torso_base.width * 0.34)
            ankle_l = (cw * 0.5 - stance_half, ankle_y)
            ankle_r = (cw * 0.5 + stance_half, ankle_y)

            # [1] BODY_TORSO nằm phía trên chân IK, nhún gối & chuyển trọng tâm mượt
            t_w = torso_base.width
            t_h = max(16, int(round(torso_base.height * st.torso_scale_y)))
            torso_scaled = (
                torso_base.resize((t_w, t_h), Image.Resampling.BICUBIC)
                if t_h != torso_base.height
                else torso_base.copy()
            )
            torso_pivot_local = (t_w * 0.5, float(t_h))
            torso_rot, torso_rot_pivot = rotate_around_pivot(
                torso_scaled, st.torso_angle, torso_pivot_local
            )
            torso_scaled.close()

            hip_center_x = cw * 0.5 + st.torso_dx + hip_dx_c
            hip_center_y = ankle_y - leg_total_h * 0.92 + st.torso_dy + knee_dip_c
            torso_tl_x = int(round(hip_center_x - torso_rot_pivot[0]))
            torso_tl_y = int(round(hip_center_y - torso_rot_pivot[1]))

            def _torso_anchor_world(norm_xy: list[float]) -> tuple[float, float]:
                lx = float(norm_xy[0]) * t_w
                ly = float(norm_xy[1]) * t_h
                return _transform_anchor_world(
                    (lx, ly), torso_pivot_local, (hip_center_x, hip_center_y), st.torso_angle
                )

            sh_l = _torso_anchor_world(self.rig_cfg["shoulder_left_torso"])
            sh_r = _torso_anchor_world(self.rig_cfg["shoulder_right_torso"])
            hip_l = _torso_anchor_world(self.rig_cfg.get("hip_left_torso", [0.36, 0.94]))
            hip_r = _torso_anchor_world(self.rig_cfg.get("hip_right_torso", [0.64, 0.94]))
            neck_world = _torso_anchor_world(self.rig_cfg["neck_anchor_torso"])

            # Chiều dài 2 đoạn xương tay & chân tỷ lệ giải phẫu với thân áo
            arm_l1 = max(24.0, t_h * 0.54)
            arm_l2 = max(22.0, t_h * 0.50)
            leg_l1 = max(24.0, leg_total_h * 0.51)
            leg_l2 = max(24.0, leg_total_h * 0.51)

            def _fk_to_ik_target(
                sh: tuple[float, float],
                sh_deg: float,
                el_deg: float,
                base_out_deg: float,
                extra_dx: float,
                extra_dy: float,
            ) -> tuple[float, float]:
                # Quy đổi góc pose cũ (tương thích 100% 24 pose) sang điểm mục tiêu cổ tay IK
                a1 = math.radians(base_out_deg - sh_deg - st.torso_angle)
                a2 = math.radians(base_out_deg - sh_deg - el_deg - st.torso_angle)
                ex = sh[0] + math.sin(a1) * arm_l1
                ey = sh[1] + math.cos(a1) * arm_l1
                wx = ex + math.sin(a2) * arm_l2 + extra_dx
                wy = ey + math.cos(a2) * arm_l2 + extra_dy
                return wx, wy

            raw_target_l = _fk_to_ik_target(sh_l, st.arm_l_angle, st.elbow_l_angle, -24.0, l_dx_c, l_dy_c)
            raw_target_r = _fk_to_ik_target(sh_r, st.arm_r_angle, st.elbow_r_angle, 24.0, r_dx_c, r_dy_c)
            target_l = clamp_arm_target(
                "left", sh_l, raw_target_l, hip_center_x, float(t_w), arm_l1, arm_l2, pose=self.pose
            )
            target_r = clamp_arm_target(
                "right", sh_r, raw_target_r, hip_center_x, float(t_w), arm_l1, arm_l2, pose=self.pose
            )

            el_l, wr_l = solve_2bone_ik(sh_l, target_l, arm_l1, arm_l2, bend_dir=-1)
            el_r, wr_r = solve_2bone_ik(sh_r, target_r, arm_l1, arm_l2, bend_dir=1)
            knee_l, foot_l = solve_2bone_ik(hip_l, ankle_l, leg_l1, leg_l2, bend_dir=-1)
            knee_r, foot_r = solve_2bone_ik(hip_r, ankle_r, leg_l1, leg_l2, bend_dir=1)

            stroke_base = max(4.0, float(self.rig_cfg.get("limb_stroke_px", 9.0)) * self._scale)
            ss = 3  # 3x Supersampled AA trên canvas cục bộ nhân vật
            hand_r = max(7.0, stroke_base * 1.45)

            # Lớp 1 (Sau thân): Bóng sàn + 2 chân IK + tay trái IK (3x SSAA cục bộ)
            back_hi = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
            try:
                db = ImageDraw.Draw(back_hi)
                # Bóng bầu dục mềm dưới chân
                db.ellipse(
                    (
                        (ankle_l[0] - stance_half * 0.7) * ss,
                        (ground_y - 10) * ss,
                        (ankle_r[0] + stance_half * 0.7) * ss,
                        (ground_y + 8) * ss,
                    ),
                    fill=(15, 23, 42, 46),
                )
                for h_pt, k_pt, f_pt in ((hip_l, knee_l, foot_l), (hip_r, knee_r, foot_r)):
                    _draw_capsule_bone(db, (h_pt[0] * ss, h_pt[1] * ss), (k_pt[0] * ss, k_pt[1] * ss), stroke_base * ss)
                    _draw_capsule_bone(db, (k_pt[0] * ss, k_pt[1] * ss), (f_pt[0] * ss, f_pt[1] * ss), stroke_base * ss)
                # Tay trái (tay sau)
                _draw_capsule_bone(db, (sh_l[0] * ss, sh_l[1] * ss), (el_l[0] * ss, el_l[1] * ss), stroke_base * ss)
                _draw_capsule_bone(db, (el_l[0] * ss, el_l[1] * ss), (wr_l[0] * ss, wr_l[1] * ss), stroke_base * ss)
                _draw_vector_hand(
                    db,
                    (wr_l[0] * ss, wr_l[1] * ss),
                    (el_l[0] * ss, el_l[1] * ss),
                    resolve_hand_shape(self.pose, "left", self.interaction),
                    hand_r=hand_r * ss,
                    outline_w=max(3, int(round(stroke_base * 0.42 * ss))),
                )
                back_lo = back_hi.resize((cw, ch), Image.Resampling.LANCZOS)
                try:
                    canvas.alpha_composite(back_lo)
                finally:
                    back_lo.close()
            finally:
                back_hi.close()

            # Lớp 2: Thân áo sơ mi & cà vạt đỏ (che gọn gốc khớp vai/hông)
            canvas.alpha_composite(torso_rot, (torso_tl_x, torso_tl_y))
            torso_rot.close()

            # Lớp 3 (Trước thân): Tay phải IK + bàn tay chỉ bảng (3x SSAA cục bộ)
            front_hi = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
            try:
                df = ImageDraw.Draw(front_hi)
                _draw_capsule_bone(df, (sh_r[0] * ss, sh_r[1] * ss), (el_r[0] * ss, el_r[1] * ss), stroke_base * ss)
                _draw_capsule_bone(df, (el_r[0] * ss, el_r[1] * ss), (wr_r[0] * ss, wr_r[1] * ss), stroke_base * ss)
                _draw_vector_hand(
                    df,
                    (wr_r[0] * ss, wr_r[1] * ss),
                    (el_r[0] * ss, el_r[1] * ss),
                    resolve_hand_shape(self.pose, "right", self.interaction),
                    hand_r=hand_r * ss,
                    outline_w=max(3, int(round(stroke_base * 0.42 * ss))),
                )
                front_lo = front_hi.resize((cw, ch), Image.Resampling.LANCZOS)
                try:
                    canvas.alpha_composite(front_lo)
                finally:
                    front_lo.close()
            finally:
                front_hi.close()

            # Lớp 4: Đầu + Mắt + Miệng + Biểu cảm (xoay quanh cổ)
            head_rot, head_rpiv = rotate_around_pivot(
                head_local, st.head_angle + st.torso_angle, head_piv
            )
            canvas.alpha_composite(
                head_rot,
                (
                    int(round(neck_world[0] + st.head_dx - head_rpiv[0])),
                    int(round(neck_world[1] - head_rpiv[1])),
                ),
            )
            head_rot.close()

            # Lớp 5: Đôi giày vàng HBT bám sàn 0% trượt
            if shoe_l is not None:
                canvas.alpha_composite(
                    shoe_l,
                    (int(round(ankle_l[0] - shoe_l.width * 0.62)), int(round(ground_y - shoe_l.height))),
                )
            if shoe_r is not None:
                canvas.alpha_composite(
                    shoe_r,
                    (int(round(ankle_r[0] - shoe_r.width * 0.38)), int(round(ground_y - shoe_r.height))),
                )
        finally:
            head_local.close()

        if self.facing == "left":
            flipped = canvas.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            canvas.close()
            return flipped
        return canvas

    def close(self) -> None:
        for group in (self.parts, self.eyes, self.mouths):
            for im in group.values():
                im.close()
            group.clear()
