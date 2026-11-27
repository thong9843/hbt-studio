"""Bộ diễn hoạt nhân vật 2D Puppet phân cấp (Hierarchical Rig) & Khẩu hình EMA tự động."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from hbt.shared.audio_utils import extract_wav_rms_frames
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

SEG_CACHE_VERSION = "v5_a_stance_legs"
SEGMENT_NAMES: tuple[str, ...] = ("body_torso", "head_blank", "arm_left", "arm_right")
ARM_2SEG_NAMES: tuple[str, ...] = (
    "upper_arm_left",
    "forearm_left",
    "upper_arm_right",
    "forearm_right",
)
ALL_SEGMENT_NAMES: tuple[str, ...] = SEGMENT_NAMES + ARM_2SEG_NAMES
VALID_HAND_SHAPES: tuple[str, ...] = (
    "open_palm",
    "point_index",
    "fist_punch",
    "thumb_up",
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

    # 3. Tạo mask từng bộ phận (v5_a_stance_legs: giữ nguyên thân áo + 2 chân chữ A + giày vàng)
    head_mask = np.zeros((h, w), dtype=bool)
    head_mask[: neck_y + 2, :] = alpha[: neck_y + 2, :]

    arm_y_end = min(h, int(0.80 * h))

    arm_left_mask = np.zeros((h, w), dtype=bool)
    arm_right_mask = np.zeros((h, w), dtype=bool)
    torso_mask = np.zeros((h, w), dtype=bool)

    shoulder_y = min(h - 1, neck_y + max(2, int(0.04 * h)))
    torso_mask[neck_y:, :] = alpha[neck_y:, :]

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
            torso_mask[y, :eff_cut_l] = False

        right_px = alpha[y, eff_cut_r + 1 :]
        if np.any(right_px):
            arm_right_mask[y, eff_cut_r + 1 :] = right_px
            torso_mask[y, eff_cut_r + 1 :] = False

    # Đảm bảo không có mask rỗng nếu ảnh synthetic rất nhỏ
    if not np.any(torso_mask):
        torso_mask[neck_y:, :] = alpha[neck_y:, :]

    head_img, _head_off = _crop_rgba_mask(arr, head_mask)
    torso_img, torso_off = _crop_rgba_mask(arr, torso_mask)
    arm_l_img, arm_l_off = _crop_rgba_mask(arr, arm_left_mask)
    arm_r_img, arm_r_off = _crop_rgba_mask(arr, arm_right_mask)

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
    rig_cfg["limb_stroke_px"] = round(max(6.0, min(18.0, min(w, h) * 0.024)), 2)
    rig_cfg["torso_full_legs"] = True

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
    *,
    resample: int = Image.Resampling.BICUBIC,
) -> tuple[Image.Image, tuple[float, float]]:
    """Xoay ảnh RGBA quanh đúng `pivot_xy` bằng phép biến đổi affine, không cắt góc."""
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
        resample=resample,
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
    rms_norm = extract_wav_rms_frames(wav_path, fps, duration_sec, norm_mode="frame_p92")
    return smooth_rms_envelope(rms_norm, fps=fps)


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
        "shoulder_l": -108.0,
        "elbow_l": -34.0,
        "shoulder_r": -108.0,
        "elbow_r": -34.0,
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
        "shoulder_l": -68.0,
        "elbow_l": -24.0,
        "shoulder_r": -68.0,
        "elbow_r": -24.0,
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
    # 6 kênh lò xo giảm chấn tới hạn liên tục (vị trí chuẩn hóa theo target_height + vận tốc)
    lw_x: float | None = None
    lw_y: float | None = None
    rw_x: float | None = None
    rw_y: float | None = None
    lw_vx: float = 0.0
    lw_vy: float = 0.0
    rw_vx: float = 0.0
    rw_vy: float = 0.0
    head_vel: float = 0.0
    torso_vel: float = 0.0


def _hermite_smoothstep(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return u * u * (3.0 - 2.0 * u)


class _SpringChannel:
    """Bộ lọc lò xo giảm chấn tới hạn (`zeta = 1.0`), kế thừa liên tục `(pos, vel)` xuyên beat."""

    def __init__(self, initial: float = 0.0, velocity: float = 0.0) -> None:
        self.pos = float(initial)
        self.vel = float(velocity)

    def step(self, target: float, dt: float, omega: float = 7.8, zeta: float = 1.0) -> float:
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


def lowpass_slow_rms(env: list[float], fps: int, *, tau_s: float = 0.50) -> list[float]:
    """Lọc thông thấp cực chậm (tau >= 0.45s, < 0.8Hz) cho cử chỉ tay, tách khỏi kênh nhép miệng."""
    if not env:
        return []
    dt = 1.0 / max(15, int(fps))
    alpha = dt / (max(0.45, float(tau_s)) + dt)
    out: list[float] = []
    cur = float(env[0])
    for v in env:
        cur = cur + alpha * (max(0.0, min(1.0, float(v))) - cur)
        out.append(round(cur, 5))
    return out


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
    """Tính tư thế điềm tĩnh theo `POSE_PRESETS` với nhịp thở siêu chậm 0.35Hz (0 rung giật)."""
    key = normalize_stickv_pose(pose)
    cfg = POSE_PRESETS[key]
    env = max(0.0, min(1.0, float(env_val)))
    t = max(0.0, float(t_sec))
    _ = beat_t

    sh_l = float(cfg["shoulder_l"])
    el_l = float(cfg["elbow_l"])
    sh_r = float(cfg["shoulder_r"])
    el_r = float(cfg["elbow_r"])
    head = max(-4.5, min(4.5, float(cfg["head_deg"]) * 0.55))
    torso = max(-2.5, min(2.5, float(cfg["torso_deg"]) * 0.65))

    # Nhịp thở người dẫn chuyện siêu chậm 0.35 Hz (chu kỳ ~2.85s, không đảo chiều đột ngột)
    breath = math.sin(2.0 * math.pi * 0.35 * t)
    breath_lag = math.sin(2.0 * math.pi * 0.35 * t - 0.5)
    torso_dx = 2.6 * breath
    scale_y = 1.0 + 0.008 * breath

    if key in ("point_up", "point_board_high", "guide_sweep_board"):
        sh_r += 3.5 * breath
        el_r += 3.0 * breath_lag
        head += 1.2 * breath
    elif key in ("guide_two_sides", "welcome_open"):
        sh_l += 4.0 * breath
        sh_r -= 4.0 * breath
        torso += 1.0 * breath
        head += 1.4 * breath_lag
    elif key in ("shrug_ask", "think_chin", "lean_curious"):
        head += 1.5 * breath
        el_r += 3.0 * breath_lag
    elif key == "shock_hands_up":
        sh_l += 3.5 * breath
        sh_r += 3.5 * breath
        head += -1.5 + 1.0 * breath
    elif key in ("nod_yes", "count_points", "guide_step_count"):
        head += 2.2 * breath
        el_r += 4.0 * breath_lag
    elif key == "walk_explore":
        sh_l = 16.0 * breath
        sh_r = -16.0 * breath
        torso_dx = 3.5 * breath
        torso = 1.4 * breath
    else:
        sh_l += 2.5 * breath
        sh_r -= 2.5 * breath
        head += 1.2 * breath

    head = max(-4.5, min(4.5, head - 0.8 * env))
    return PuppetPoseState(
        head_angle=head,
        arm_l_angle=sh_l,
        elbow_l_angle=el_l,
        arm_r_angle=sh_r,
        elbow_r_angle=el_r,
        torso_angle=max(-2.8, min(2.8, torso)),
        torso_dx=max(-4.5, min(4.5, torso_dx)),
        torso_dy=0.0,
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


def solve_arm_ik_natural(
    side: str,
    shoulder: tuple[float, float],
    target: tuple[float, float],
    l1: float,
    l2: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Giải 2-Bone IK với `bend_dir` cố định theo giải phẫu (Zero IK Elbow Pop, cấm lật dấu)."""
    # Tay trái màn hình (ux < 0) dùng bend_dir=-1, tay phải (ux > 0) dùng bend_dir=+1
    # => khuỷu tay luôn cong tự nhiên ra ngoài/xuống dưới, tuyệt đối không lật dấu đột ngột.
    fixed_bend = -1 if side == "left" else 1
    return solve_2bone_ik(shoulder, target, l1, l2, bend_dir=fixed_bend)


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
    """Khóa giải phẫu Silhouette Lock: cấm bàn tay vắt chéo qua trục cà vạt đỏ giữa thân."""
    _ = pose
    tx, ty = float(target[0]), float(target[1])
    margin = max(8.0, torso_w * 0.14)
    if side == "left":
        tx = min(tx, torso_cx - margin)
    else:
        tx = max(tx, torso_cx + margin)

    dx = tx - shoulder[0]
    dy = ty - shoulder[1]
    dist = math.hypot(dx, dy)
    total = max(4.0, l1 + l2)
    min_d = 0.28 * total
    max_d = 0.96 * total
    if dist < 1e-5:
        return shoulder[0] + (-min_d if side == "left" else min_d), shoulder[1] + min_d * 0.5
    if dist < min_d or dist > max_d:
        clamped = max(min_d, min(max_d, dist))
        scale = clamped / dist
        tx = shoulder[0] + dx * scale
        ty = shoulder[1] + dy * scale
        # Tái kẹp lần cuối để đảm bảo sau khi scale chiều dài vẫn không lấn qua cà vạt đỏ
        if side == "left":
            tx = min(tx, torso_cx - margin)
        else:
            tx = max(tx, torso_cx + margin)
    return tx, ty


def resolve_hand_shape(
    pose: str,
    side: str,
    interaction: str = "none",
    *,
    board_type: str = "",
) -> str:
    """Chọn dáng găng tay bo tròn (`open_palm`, `point_index`, `fist_punch`, `thumb_up`)."""
    p = normalize_stickv_pose(pose)
    if interaction == "point_chart" and side == "right":
        return "point_index"
    if (
        p in ("point_up", "point_board_high", "guide_sweep_board", "guide_zoom_focus")
        and side == "right"
    ):
        return "point_index"
    if p in ("count_points", "guide_step_count", "nod_yes") and side == "right":
        return "thumb_up"
    if board_type == "recap_card" and side == "right":
        return "thumb_up"
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


def _draw_bezier_arm(
    draw: ImageDraw.ImageDraw,
    shoulder: tuple[float, float],
    elbow: tuple[float, float],
    wrist: tuple[float, float],
    width_px: float,
    color: tuple[int, int, int, int] = JOINT_CAP_COLOR,
    *,
    steps: int = 18,
) -> tuple[float, float]:
    """Vẽ cánh tay bằng đường cong Quadratic Bézier mượt (`shoulder -> elbow -> wrist`).
    Trả về điểm gần cổ tay `(prev_x, prev_y)` để xoay găng tay khớp tiếp tuyến cong.
    """
    sx, sy = float(shoulder[0]), float(shoulder[1])
    ex, ey = float(elbow[0]), float(elbow[1])
    wx, wy = float(wrist[0]), float(wrist[1])
    # Điểm điều khiển Bézier kéo nhẹ qua khớp khuỷu để giữ đúng độ cong giải phẫu
    cx = ex * 1.12 - (sx + wx) * 0.06
    cy = ey * 1.12 - (sy + wy) * 0.06

    pts: list[tuple[float, float]] = []
    n = max(8, int(steps))
    for i in range(n + 1):
        t = i / float(n)
        mt = 1.0 - t
        bx = mt * mt * sx + 2.0 * mt * t * cx + t * t * wx
        by = mt * mt * sy + 2.0 * mt * t * cy + t * t * wy
        pts.append((bx, by))

    w = max(2, int(round(width_px)))
    r = w / 2.0
    draw.line(pts, fill=color, width=w, joint="curve")
    for px, py in (pts[0], pts[-1]):
        draw.ellipse((px - r, py - r, px + r, py + r), fill=color)
    return pts[-3] if len(pts) >= 3 else (ex, ey)


def _draw_oriented_capsule(
    draw: ImageDraw.ImageDraw,
    p0: tuple[float, float],
    p1: tuple[float, float],
    radius: float,
    color: tuple[int, int, int, int],
) -> None:
    """Vẽ viên nang bo tròn mượt nối p0 -> p1 (dùng cho kỹ thuật Unified Silhouette Outline)."""
    r = max(1.5, float(radius))
    w = max(2, int(round(r * 2.0)))
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
    side: str = "right",
) -> None:
    """Vẽ 4 dáng găng tay hoạt hình bo tròn liền khối (Unified Silhouette Outline, 0 móng nhọn)."""
    shape = "thumb_up" if hand_shape == "count_fingers" else (hand_shape or "open_palm")
    dx = wrist[0] - elbow[0]
    dy = wrist[1] - elbow[1]
    norm = max(1e-5, math.hypot(dx, dy))
    ux, uy = dx / norm, dy / norm
    # Pháp tuyến hướng lên trên (phía ngón cái tự nhiên)
    px, py = -uy, ux
    if py > 0.0:
        px, py = -px, -py
    elif abs(py) < 0.15:
        px, py = (0.0, -1.0)

    white = (255, 255, 255, 255)
    ink = JOINT_CAP_COLOR
    r = max(5.0, float(hand_r) * 1.18)
    ow = max(2.5, float(outline_w) * 1.05)

    # Tâm bàn tay nối kín với cổ tay
    cx = wrist[0] + ux * (r * 0.72)
    cy = wrist[1] + uy * (r * 0.72)
    palm_p0 = (cx - ux * (r * 0.18), cy - uy * (r * 0.18))
    palm_p1 = (cx + ux * (r * 0.24), cy + uy * (r * 0.24))

    if shape == "fist_punch":
        fr = r * 1.06
        for rad, col in ((fr + ow, ink), (fr, white)):
            _draw_oriented_capsule(draw, palm_p0, palm_p1, rad, col)
        # 1 nếp gấp nhỏ gọn bên trong nắm tay
        k0 = (cx + ux * fr * 0.15 - px * fr * 0.36, cy + uy * fr * 0.15 - py * fr * 0.36)
        k1 = (cx + ux * fr * 0.15 + px * fr * 0.32, cy + uy * fr * 0.15 + py * fr * 0.32)
        draw.line([k0, k1], fill=ink, width=max(2, int(round(ow * 0.72))))
        return

    if shape == "point_index":
        # Nắm tay tròn gọn + 1 ngón trỏ mập bo tròn dày hướng thẳng theo trục cẳng tay
        base_r = r * 0.94
        idx_r = r * 0.44
        idx_start = (cx + ux * (r * 0.22), cy + uy * (r * 0.22))
        idx_tip = (cx + ux * (r * 1.52), cy + uy * (r * 1.52))
        thumb_tip = (
            cx + ux * (r * 0.18) + px * (r * 0.85),
            cy + uy * (r * 0.18) + py * (r * 0.85),
        )
        # Pass 1: Unified dark ink silhouette -> Pass 2: Unified pure white fill
        for pad, col in ((ow, ink), (0.0, white)):
            _draw_oriented_capsule(draw, palm_p0, palm_p1, base_r + pad, col)
            _draw_oriented_capsule(draw, idx_start, idx_tip, idx_r + pad, col)
            _draw_oriented_capsule(draw, (cx, cy), thumb_tip, r * 0.36 + pad, col)
        return

    if shape == "thumb_up":
        # Nắm tay tròn gọn + ngón cái bầu bĩnh dựng lên rõ dáng
        base_r = r * 0.98
        t_dir_x = -0.18 if side == "left" else 0.18
        t_dir_y = -0.98
        t_start = (cx + t_dir_x * (r * 0.15), cy + t_dir_y * (r * 0.15))
        t_tip = (cx + t_dir_x * (r * 1.48), cy + t_dir_y * (r * 1.48))
        for pad, col in ((ow, ink), (0.0, white)):
            _draw_oriented_capsule(draw, palm_p0, palm_p1, base_r + pad, col)
            _draw_oriented_capsule(draw, t_start, t_tip, r * 0.44 + pad, col)
        # Nếp gấp nhỏ tinh tế ở thân nắm tay
        k0 = (cx + ux * r * 0.25, cy + uy * r * 0.25 - r * 0.20)
        k1 = (cx + ux * r * 0.25, cy + uy * r * 0.25 + r * 0.30)
        draw.line([k0, k1], fill=ink, width=max(2, int(round(ow * 0.65))))
        return

    # open_palm: Găng tay hoạt hình mitten bầu bĩnh liền khối (oval lòng bàn tay + 1 ngón cái mập)
    mitten_r = r * 1.02
    mitten_p0 = (cx - ux * (r * 0.22), cy - uy * (r * 0.22))
    mitten_p1 = (cx + ux * (r * 0.42), cy + uy * (r * 0.42))
    thumb_root = (cx - ux * (r * 0.08), cy - uy * (r * 0.08))
    thumb_tip = (
        cx + ux * (r * 0.26) + px * (r * 1.12),
        cy + uy * (r * 0.26) + py * (r * 1.12),
    )
    for pad, col in ((ow, ink), (0.0, white)):
        _draw_oriented_capsule(draw, mitten_p0, mitten_p1, mitten_r + pad, col)
        _draw_oriented_capsule(draw, thumb_root, thumb_tip, r * 0.46 + pad, col)
    # 1 đường cong ngắn tinh tế đánh dấu gốc ngón cái (không chĩa que rời)
    c0 = (cx + px * (r * 0.34), cy + py * (r * 0.34))
    c1 = (cx + ux * (r * 0.30) + px * (r * 0.48), cy + uy * (r * 0.30) + py * (r * 0.48))
    draw.line([c0, c1], fill=ink, width=max(2, int(round(ow * 0.62))))


def _load_optional_custom_hands(
    library_dir: Path, assets_dir: Path, scale: float
) -> dict[str, Image.Image]:
    """Khe mở rộng tùy chọn: tự ưu tiên PNG trong `library/stickman/puppet/hands/{shape}.png`."""
    loaded: dict[str, Image.Image] = {}
    search_dirs = (
        Path(assets_dir) / "stickman" / "puppet" / "hands",
        Path(library_dir) / "stickman" / "puppet" / "hands",
    )
    for shape in VALID_HAND_SHAPES:
        for folder in search_dirs:
            cand = folder / f"{shape}.png"
            if cand.is_file():
                loaded[shape] = _load_rgba_scaled(cand, scale)
                break
    return loaded


def _load_rgba_scaled(path: Path, scale: float) -> Image.Image:
    with Image.open(path) as raw:
        rgba = raw.convert("RGBA")
        if abs(scale - 1.0) < 0.005:
            return rgba.copy()
        nw = max(4, int(round(rgba.width * scale)))
        nh = max(4, int(round(rgba.height * scale)))
        return rgba.resize((nw, nh), Image.Resampling.LANCZOS)


@dataclass
class _CachedPuppetSprites:
    """Bộ sprite Puppet đã giải nén & scale sẵn, chia sẻ qua nhiều beat trong cùng render."""

    rig_cfg: dict[str, Any]
    scale: float
    parts: dict[str, Image.Image]
    torso_2x: Image.Image | None
    custom_hands: dict[str, Image.Image]
    eyes: dict[str, Image.Image]
    mouths: dict[str, Image.Image]

    def close(self) -> None:
        for group in (self.parts, self.custom_hands, self.eyes, self.mouths):
            for im in group.values():
                im.close()
            group.clear()
        if self.torso_2x is not None:
            self.torso_2x.close()
            self.torso_2x = None


class PuppetAssetCache:
    """Cache tập sprite `PuppetRig` theo `(library_dir, assets_dir, target_height)`."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, int], _CachedPuppetSprites] = {}

    def get_or_load(
        self,
        library_dir: Path,
        assets_dir: Path,
        target_height: int,
    ) -> _CachedPuppetSprites:
        key = (
            str(Path(library_dir).resolve()),
            str(Path(assets_dir).resolve()),
            int(target_height),
        )
        cached = self._entries.get(key)
        if cached is not None:
            return cached

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
        rig_cfg: dict[str, Any] = seg_info["rig_config"]
        seg_paths: dict[str, Path] = seg_info["segments"]

        with Image.open(seg_paths["body_torso"]) as bt, Image.open(seg_paths["head_blank"]) as hb:
            raw_total_h = max(1, bt.height + int(hb.height * 1.22))
        scale = (target_height * 0.88) / raw_total_h

        parts: dict[str, Image.Image] = {}
        for name in ALL_SEGMENT_NAMES:
            sp = seg_paths.get(name)
            if sp is not None and sp.is_file():
                parts[name] = _load_rgba_scaled(sp, scale)
        torso_2x: Image.Image | None = None
        torso_bt = parts.get("body_torso")
        if torso_bt is not None:
            torso_2x = torso_bt.resize(
                (max(8, torso_bt.width * 2), max(16, torso_bt.height * 2)),
                Image.Resampling.BICUBIC,
            )

        custom_hands = _load_optional_custom_hands(library_dir, assets_dir, scale)

        eyes: dict[str, Image.Image] = {}
        for eslot in ("eyes_neutral", "eyes_happy", "eyes_shock", "eyes_angry"):
            ep = slot_paths[eslot][0]
            if ep is not None:
                cleaned_p = prepare_puppet_sprite(ep, cache_dir, eslot)
                with Image.open(cleaned_p) as raw_e:
                    eyes[eslot] = raw_e.convert("RGBA")
        if "eyes_neutral" not in eyes and eyes:
            first_e = next(iter(eyes.values()))
            eyes["eyes_neutral"] = first_e.copy()

        mouths: dict[str, Image.Image] = {}
        for mslot in ("mouth_closed", "mouth_open"):
            mp = slot_paths[mslot][0]
            if mp is not None:
                cleaned_p = prepare_puppet_sprite(mp, cache_dir, mslot)
                with Image.open(cleaned_p) as raw_m:
                    mouths[mslot] = raw_m.convert("RGBA")
        if "mouth_closed" not in mouths and "mouth_open" in mouths:
            mouths["mouth_closed"] = mouths["mouth_open"].copy()
        if "mouth_open" not in mouths and "mouth_closed" in mouths:
            mouths["mouth_open"] = mouths["mouth_closed"].copy()

        entry = _CachedPuppetSprites(
            rig_cfg=rig_cfg,
            scale=scale,
            parts=parts,
            torso_2x=torso_2x,
            custom_hands=custom_hands,
            eyes=eyes,
            mouths=mouths,
        )
        self._entries[key] = entry
        return entry

    def close(self) -> None:
        for entry in self._entries.values():
            entry.close()
        self._entries.clear()


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
        asset_cache: PuppetAssetCache | None = None,
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
        self.slow_env = lowpass_slow_rms(self.env, fps=self.fps, tau_s=0.50)
        self.rms_peaks = detect_rms_peaks(self.env, self.fps)
        self.prev_pose_state = prev_pose_state
        self.global_t_offset = max(0.0, float(global_t_offset))
        self.tween_dur = 0.45 if prev_pose_state is not None else 0.0
        init_st = prev_pose_state or PuppetPoseState()
        # 6 kênh lò xo giảm chấn tới hạn (zeta=1.0, omega=7.0..8.5) kế thừa cả (pos, vel) xuyên beat
        self._springs = {
            "head_angle": _SpringChannel(init_st.head_angle, init_st.head_vel),
            "head_dx": _SpringChannel(init_st.head_dx),
            "arm_l_angle": _SpringChannel(init_st.arm_l_angle),
            "elbow_l_angle": _SpringChannel(init_st.elbow_l_angle),
            "arm_r_angle": _SpringChannel(init_st.arm_r_angle),
            "elbow_r_angle": _SpringChannel(init_st.elbow_r_angle),
            "torso_angle": _SpringChannel(init_st.torso_angle, init_st.torso_vel),
            "torso_dx": _SpringChannel(init_st.torso_dx),
            "torso_dy": _SpringChannel(init_st.torso_dy),
            "torso_scale_y": _SpringChannel(init_st.torso_scale_y),
        }
        self._wrist_initialized = init_st.lw_x is not None and init_st.rw_x is not None
        self._wrist_springs = {
            "lw_x": _SpringChannel(init_st.lw_x or 0.0, init_st.lw_vx),
            "lw_y": _SpringChannel(init_st.lw_y or 0.0, init_st.lw_vy),
            "rw_x": _SpringChannel(init_st.rw_x or 0.0, init_st.rw_vx),
            "rw_y": _SpringChannel(init_st.rw_y or 0.0, init_st.rw_vy),
        }
        self._elbow_springs: dict[str, _SpringChannel] | None = None
        self.last_wrists: tuple[tuple[float, float], tuple[float, float]] = (
            (0.0, 0.0),
            (0.0, 0.0),
        )
        self._head_lag_frames = max(1, int(round(self.fps / 30.0)))
        self._shoulder_lag_frames = max(2, int(round(2.0 * self.fps / 30.0)))
        self._elbow_lag_frames = max(4, int(round(4.0 * self.fps / 30.0)))
        self._follow_hist_len = self._elbow_lag_frames + 2
        self._follow_history: list[PuppetPoseState] = [init_st] * self._follow_hist_len
        self._mouth_ema_decay: float = 0.40 ** (30.0 / self.fps)
        self._mouth_sy_smooth: float = 1.0
        self.last_pose_state: PuppetPoseState = init_st

        self._shared_assets = asset_cache is not None
        loader = asset_cache if asset_cache is not None else PuppetAssetCache()
        sprites = loader.get_or_load(library_dir, assets_dir, self.target_height)
        self.rig_cfg: dict[str, Any] = sprites.rig_cfg
        self._scale = sprites.scale
        self.parts: dict[str, Image.Image] = sprites.parts
        self._torso_2x: Image.Image | None = sprites.torso_2x
        self.custom_hands: dict[str, Image.Image] = sprites.custom_hands
        self.eyes: dict[str, Image.Image] = sprites.eyes
        self.mouths: dict[str, Image.Image] = sprites.mouths
        self._eye_resize_cache: dict[tuple[str, int, int], Image.Image] = {}
        self._mouth_resize_cache: dict[tuple[str, int, int], Image.Image] = {}
        self._torso_rot_cache: dict[tuple[int, float], tuple[Image.Image, tuple[float, float]]] = {}
        bt_ref = self.parts["body_torso"]
        self.canvas_size: tuple[int, int] = (
            max(int(self.target_height * 0.96), bt_ref.width * 3 + 48),
            self.target_height,
        )

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
        is_cta_or_recap = (
            self.board_type == "recap_card"
            or self.face_mood == "warm_cta"
            or self.pose == "welcome_open"
        )

        if t_sec > self.speech_end:
            # Beat tổng kết / CTA giữ dáng chào mở tay + gật nhẹ (không đứng xuôi tay bất động)
            idle_pose = "welcome_open" if is_cta_or_recap else "idle_breathe"
            idle_env = max(0.28, env_val) if is_cta_or_recap else 0.18
            idle_state = evaluate_pose_preset(idle_pose, gt, idle_env, beat_t=t_sec)
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
                max(-4.5, min(4.5, head_lag.head_angle)), dt, omega=7.0, zeta=1.0
            ),
            head_dx=self._springs["head_dx"].step(head_lag.head_dx, dt, omega=7.5, zeta=1.0),
            arm_l_angle=self._springs["arm_l_angle"].step(
                shoulder_lag.arm_l_angle, dt, omega=7.5, zeta=1.0
            ),
            elbow_l_angle=self._springs["elbow_l_angle"].step(
                elbow_lag.elbow_l_angle, dt, omega=7.8, zeta=1.0
            ),
            arm_r_angle=self._springs["arm_r_angle"].step(
                shoulder_lag.arm_r_angle, dt, omega=7.5, zeta=1.0
            ),
            elbow_r_angle=self._springs["elbow_r_angle"].step(
                elbow_lag.elbow_r_angle, dt, omega=7.8, zeta=1.0
            ),
            torso_angle=self._springs["torso_angle"].step(
                raw_target.torso_angle, dt, omega=7.5, zeta=1.0
            ),
            torso_dx=self._springs["torso_dx"].step(raw_target.torso_dx, dt, omega=7.5, zeta=1.0),
            torso_dy=self._springs["torso_dy"].step(raw_target.torso_dy, dt, omega=8.0, zeta=1.0),
            torso_scale_y=self._springs["torso_scale_y"].step(
                raw_target.torso_scale_y, dt, omega=8.0, zeta=1.0
            ),
            lw_x=self._wrist_springs["lw_x"].pos if self._wrist_initialized else None,
            lw_y=self._wrist_springs["lw_y"].pos if self._wrist_initialized else None,
            rw_x=self._wrist_springs["rw_x"].pos if self._wrist_initialized else None,
            rw_y=self._wrist_springs["rw_y"].pos if self._wrist_initialized else None,
            lw_vx=self._wrist_springs["lw_x"].vel,
            lw_vy=self._wrist_springs["lw_y"].vel,
            rw_vx=self._wrist_springs["rw_x"].vel,
            rw_vy=self._wrist_springs["rw_y"].vel,
            head_vel=self._springs["head_angle"].vel,
            torso_vel=self._springs["torso_angle"].vel,
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
            ekey = (eslot, ew, eh)
            eye_resized = self._eye_resize_cache.get(ekey)
            if eye_resized is None:
                if len(self._eye_resize_cache) >= 32:
                    old_k = next(iter(self._eye_resize_cache))
                    self._eye_resize_cache.pop(old_k).close()
                eye_resized = eye_src.resize((ew, eh), Image.Resampling.LANCZOS)
                self._eye_resize_cache[ekey] = eye_resized
            ecx = pad_x + hw * float(self.rig_cfg["eyes_center_head"][0]) + eox
            ecy = pad_top + hh * float(self.rig_cfg["eyes_center_head"][1]) + eoy
            ex = max(pad_x + 2, min(pad_x + hw - ew - 2, int(round(ecx - ew / 2))))
            ey = max(pad_top + 2, min(pad_top + hh - eh - 2, int(round(ecy - eh / 2))))
            head.alpha_composite(eye_resized, (ex, ey))

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
            mkey = (mslot, mw, mh)
            mouth_resized = self._mouth_resize_cache.get(mkey)
            if mouth_resized is None:
                if len(self._mouth_resize_cache) >= 32:
                    old_k = next(iter(self._mouth_resize_cache))
                    self._mouth_resize_cache.pop(old_k).close()
                mouth_resized = mouth_src.resize((mw, mh), Image.Resampling.LANCZOS)
                self._mouth_resize_cache[mkey] = mouth_resized
            mcx = pad_x + hw * float(self.rig_cfg["mouth_center_head"][0])
            mcy = pad_top + hh * float(self.rig_cfg["mouth_center_head"][1])
            mx = max(pad_x + 2, min(pad_x + hw - mw - 2, int(round(mcx - mw / 2))))
            my = max(pad_top + 2, min(pad_top + hh - mh - 2, int(round(mcy - mh / 2))))
            head.alpha_composite(mouth_resized, (mx, my))

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

    def _choreography_offsets(
        self, t_sec: float, slow_env_val: float
    ) -> tuple[float, float, float, float, float, float]:
        """Nhịp cử chỉ người dẫn chuyện điềm tĩnh (tối đa 2 điểm neo/beat, giữ >= 1.2-1.8s):
        - Nhịp thở sin siêu chậm 0.35 Hz (biên độ 3-5px) + cộng hưởng slow_env <= 6px.
        - Tuyệt đối không bật/tắt đổi tay trái <-> phải 4-5 lần/giây.
        Trả về `(head_extra_deg, torso_extra_deg, l_dx, l_dy, r_dx, r_dy)`.
        """
        dur = max(1.2, self.duration_sec)
        amp_scale = max(0.75, min(1.4, self.target_height / 420.0))
        gt = self.global_t_offset + t_sec

        # Nhịp thở siêu chậm 0.35 Hz (3-5px) + lực nhấn slow_env cực nhẹ (<= 6px)
        breath = math.sin(2.0 * math.pi * 0.35 * gt)
        breath_l = math.sin(2.0 * math.pi * 0.35 * gt + 0.6)
        slow_lift = min(6.0, max(0.0, float(slow_env_val)) * 5.5) * amp_scale

        # Tối đa 2 điểm neo có chủ đích trong 1 beat (giữ mỗi điểm >= 1.2-1.8s)
        anchor2 = 1.0 if (dur >= 2.4 and t_sec >= dur * 0.52) else 0.0
        # Thay thế lật gương FLIP_LEFT_RIGHT tức thì bằng hướng tay dẫn êm ái
        lead_left = self.facing == "left"

        is_cta = (
            self.board_type == "recap_card"
            or self.face_mood == "warm_cta"
            or self.pose == "welcome_open"
        )
        if is_cta:
            head_deg = 2.0 * breath
            torso_deg = 1.0 * breath
            l_dx = (-6.0 - 3.5 * abs(breath_l)) * amp_scale
            l_dy = (-4.0 * anchor2 + 4.0 * breath_l - slow_lift * 0.5) * amp_scale
            r_dx = (8.0 + 3.5 * abs(breath)) * amp_scale
            r_dy = (-8.0 * anchor2 + 4.5 * breath - slow_lift * 0.7) * amp_scale
            return head_deg, torso_deg, l_dx, l_dy, r_dx, r_dy

        if self.board_type in ("comparison", "myth_vs_fact"):
            # Chuyển trọng tâm từ tay 1 (nửa đầu beat) sang tay 2 (nửa sau beat) ĐÚNG 1 LẦN
            if anchor2 < 0.5:
                l_dx, l_dy = -10.0 * amp_scale, (-12.0 - slow_lift + 3.5 * breath_l) * amp_scale
                r_dx, r_dy = 4.0 * amp_scale, (4.0 + 3.0 * breath) * amp_scale
                head_deg, torso_deg = -2.2 + 1.0 * breath, -1.2
            else:
                l_dx, l_dy = -4.0 * amp_scale, (4.0 + 3.0 * breath_l) * amp_scale
                r_dx, r_dy = 10.0 * amp_scale, (-12.0 - slow_lift + 3.5 * breath) * amp_scale
                head_deg, torso_deg = 2.2 + 1.0 * breath, 1.2
        elif self.board_type in ("bullets", "flow_steps"):
            lift_main = (-14.0 if anchor2 < 0.5 else -6.0) * amp_scale - slow_lift
            if lead_left:
                l_dx, l_dy = -10.0 * amp_scale, lift_main + 3.5 * breath_l * amp_scale
                r_dx, r_dy = 5.0 * amp_scale, 3.5 * breath * amp_scale
                head_deg, torso_deg = -1.8 + 1.0 * breath, -1.0
            else:
                r_dx, r_dy = 10.0 * amp_scale, lift_main + 3.5 * breath * amp_scale
                l_dx, l_dy = -5.0 * amp_scale, 3.5 * breath_l * amp_scale
                head_deg, torso_deg = 1.8 + 1.0 * breath, 1.0
        else:
            lift_main = (-10.0 if anchor2 < 0.5 else -15.0) * amp_scale - slow_lift
            if lead_left:
                l_dx, l_dy = -9.0 * amp_scale, lift_main + 3.5 * breath_l * amp_scale
                r_dx, r_dy = 5.0 * amp_scale, (3.0 + 3.0 * breath) * amp_scale
                head_deg, torso_deg = -1.5 + 1.0 * breath, -0.8
            else:
                r_dx, r_dy = 9.0 * amp_scale, lift_main + 3.5 * breath * amp_scale
                l_dx, l_dy = -5.0 * amp_scale, (3.0 + 3.0 * breath_l) * amp_scale
                head_deg, torso_deg = 1.5 + 1.0 * breath, 0.8
        return head_deg, torso_deg, l_dx, l_dy, r_dx, r_dy

    def _composite_custom_or_vector_hand(
        self,
        hi_canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        wrist_ss: tuple[float, float],
        tangent_prev_ss: tuple[float, float],
        shape: str,
        *,
        hand_r_ss: float,
        outline_w_ss: int,
        side: str,
        ss: int,
    ) -> None:
        custom = self.custom_hands.get(shape)
        if custom is not None:
            dx = wrist_ss[0] - tangent_prev_ss[0]
            dy = wrist_ss[1] - tangent_prev_ss[1]
            ang_deg = -math.degrees(math.atan2(dy, dx))
            scaled = custom.resize(
                (max(8, custom.width * ss), max(8, custom.height * ss)),
                Image.Resampling.LANCZOS,
            )
            try:
                rot = scaled.rotate(ang_deg, resample=Image.Resampling.BICUBIC, expand=True)
                try:
                    hi_canvas.alpha_composite(
                        rot,
                        (
                            int(round(wrist_ss[0] - rot.width * 0.5)),
                            int(round(wrist_ss[1] - rot.height * 0.5)),
                        ),
                    )
                finally:
                    rot.close()
            finally:
                scaled.close()
            return
        _draw_vector_hand(
            draw,
            wrist_ss,
            tangent_prev_ss,
            shape,
            hand_r=hand_r_ss,
            outline_w=outline_w_ss,
            side=side,
        )

    def render_frame(
        self, frame_idx: int, t_sec: float, *, output_scale: float = 1.0
    ) -> Image.Image:
        """Dựng 1 frame Puppet 60fps siêu mượt (`v5_a_stance_legs`): 6 kênh lò xo giảm chấn tới hạn
        (zeta=1.0), 0 lật gương 1-frame, 0 lật khuỷu IK và ghép 1 lượt trên canvas 2x SSAA."""
        # Tách 2 kênh tốc độ: env_val nhanh CHỈ cho miệng Lip-Sync; slow_val (<0.8Hz) cho tay/đầu
        env_val = self.env[frame_idx] if 0 <= frame_idx < len(self.env) else 0.0
        slow_val = self.slow_env[frame_idx] if 0 <= frame_idx < len(self.slow_env) else 0.0
        dt = 1.0 / self.fps
        st = self._pose_state_at(t_sec, slow_val)

        torso_base = self.parts["body_torso"]
        head_local, head_piv = self._build_head_layer(frame_idx, env_val, t_sec=t_sec)

        cw, ch = self.canvas_size

        (
            head_extra_deg,
            torso_extra_deg,
            l_dx_c,
            l_dy_c,
            r_dx_c,
            r_dy_c,
        ) = self._choreography_offsets(t_sec, slow_val)

        try:
            ground_y = float(ch - 8)
            eff_scale_y = 1.0 + (st.torso_scale_y - 1.0) * 0.30
            eff_torso_angle = max(-3.2, min(3.2, st.torso_angle * 0.50 + torso_extra_deg * 0.35))
            eff_head_angle = max(-4.5, min(4.5, st.head_angle + head_extra_deg * 0.40))

            t_w = torso_base.width
            t_h = max(16, int(round(torso_base.height * eff_scale_y)))
            foot_center_x = cw * 0.5 + st.torso_dx * 0.30
            foot_center_y = ground_y
            torso_pivot_local = (t_w * 0.5, float(t_h))

            def _torso_anchor_world(norm_xy: list[float]) -> tuple[float, float]:
                lx = float(norm_xy[0]) * t_w
                ly = float(norm_xy[1]) * t_h
                return _transform_anchor_world(
                    (lx, ly), torso_pivot_local, (foot_center_x, foot_center_y), eff_torso_angle
                )

            sh_l = _torso_anchor_world(self.rig_cfg["shoulder_left_torso"])
            sh_r = _torso_anchor_world(self.rig_cfg["shoulder_right_torso"])
            neck_world = _torso_anchor_world(self.rig_cfg["neck_anchor_torso"])

            upper_body_w = max(24.0, float(t_w) * 0.55)
            arm_l1 = max(22.0, t_h * 0.25)
            arm_l2 = max(20.0, t_h * 0.23)

            def _fk_to_ik_target(
                side: str,
                sh: tuple[float, float],
                sh_deg: float,
                el_deg: float,
                base_out_deg: float,
                extra_dx: float,
                extra_dy: float,
            ) -> tuple[float, float]:
                if side == "left":
                    a1 = math.radians(base_out_deg + sh_deg - eff_torso_angle)
                    a2 = math.radians(base_out_deg + sh_deg + el_deg - eff_torso_angle)
                else:
                    a1 = math.radians(base_out_deg - sh_deg - eff_torso_angle)
                    a2 = math.radians(base_out_deg - sh_deg - el_deg - eff_torso_angle)
                ex = sh[0] + math.sin(a1) * arm_l1
                ey = sh[1] + math.cos(a1) * arm_l1
                wx = ex + math.sin(a2) * arm_l2 + extra_dx
                wy = ey + math.cos(a2) * arm_l2 + extra_dy
                return wx, wy

            raw_target_l = _fk_to_ik_target(
                "left", sh_l, st.arm_l_angle, st.elbow_l_angle, -24.0, l_dx_c, l_dy_c
            )
            raw_target_r = _fk_to_ik_target(
                "right", sh_r, st.arm_r_angle, st.elbow_r_angle, 24.0, r_dx_c, r_dy_c
            )
            clamped_l = clamp_arm_target(
                "left",
                sh_l,
                raw_target_l,
                foot_center_x,
                upper_body_w,
                arm_l1,
                arm_l2,
                pose=self.pose,
            )
            clamped_r = clamp_arm_target(
                "right",
                sh_r,
                raw_target_r,
                foot_center_x,
                upper_body_w,
                arm_l1,
                arm_l2,
                pose=self.pose,
            )

            # Đưa TẤT CẢ tọa độ cổ tay (chuẩn hóa theo target_height) qua lò xo giảm chấn tới hạn
            inv_h = 1.0 / max(1.0, float(self.target_height))
            rel_lx = (clamped_l[0] - foot_center_x) * inv_h
            rel_ly = (clamped_l[1] - ground_y) * inv_h
            rel_rx = (clamped_r[0] - foot_center_x) * inv_h
            rel_ry = (clamped_r[1] - ground_y) * inv_h

            if not self._wrist_initialized:
                self._wrist_springs["lw_x"].pos = rel_lx
                self._wrist_springs["lw_y"].pos = rel_ly
                self._wrist_springs["rw_x"].pos = rel_rx
                self._wrist_springs["rw_y"].pos = rel_ry
                self._wrist_initialized = True
            else:
                self._wrist_springs["lw_x"].step(rel_lx, dt, omega=7.0, zeta=1.0)
                self._wrist_springs["lw_y"].step(rel_ly, dt, omega=7.0, zeta=1.0)
                self._wrist_springs["rw_x"].step(rel_rx, dt, omega=7.0, zeta=1.0)
                self._wrist_springs["rw_y"].step(rel_ry, dt, omega=7.0, zeta=1.0)

            smooth_l = clamp_arm_target(
                "left",
                sh_l,
                (
                    foot_center_x + self._wrist_springs["lw_x"].pos * self.target_height,
                    ground_y + self._wrist_springs["lw_y"].pos * self.target_height,
                ),
                foot_center_x,
                upper_body_w,
                arm_l1,
                arm_l2,
                pose=self.pose,
            )
            smooth_r = clamp_arm_target(
                "right",
                sh_r,
                (
                    foot_center_x + self._wrist_springs["rw_x"].pos * self.target_height,
                    ground_y + self._wrist_springs["rw_y"].pos * self.target_height,
                ),
                foot_center_x,
                upper_body_w,
                arm_l1,
                arm_l2,
                pose=self.pose,
            )

            # Cập nhật last_pose_state để truyền nguyên (pos, vel) sang đầu beat kế tiếp
            self.last_pose_state = PuppetPoseState(
                head_angle=st.head_angle,
                head_dx=st.head_dx,
                arm_l_angle=st.arm_l_angle,
                elbow_l_angle=st.elbow_l_angle,
                arm_r_angle=st.arm_r_angle,
                elbow_r_angle=st.elbow_r_angle,
                torso_angle=st.torso_angle,
                torso_dx=st.torso_dx,
                torso_dy=st.torso_dy,
                torso_scale_y=st.torso_scale_y,
                lw_x=self._wrist_springs["lw_x"].pos,
                lw_y=self._wrist_springs["lw_y"].pos,
                rw_x=self._wrist_springs["rw_x"].pos,
                rw_y=self._wrist_springs["rw_y"].pos,
                lw_vx=self._wrist_springs["lw_x"].vel,
                lw_vy=self._wrist_springs["lw_y"].vel,
                rw_vx=self._wrist_springs["rw_x"].vel,
                rw_vy=self._wrist_springs["rw_y"].vel,
                head_vel=self._springs["head_angle"].vel,
                torso_vel=self._springs["torso_angle"].vel,
            )

            raw_el_l, wr_l = solve_arm_ik_natural("left", sh_l, smooth_l, arm_l1, arm_l2)
            raw_el_r, wr_r = solve_arm_ik_natural("right", sh_r, smooth_r, arm_l1, arm_l2)
            self.last_wrists = (wr_l, wr_r)

            # Làm mượt điểm điều khiển khuỷu tay để đường cong Bézier 0% gợn giật
            if self._elbow_springs is None:
                self._elbow_springs = {
                    "el_lx": _SpringChannel(raw_el_l[0]),
                    "el_ly": _SpringChannel(raw_el_l[1]),
                    "el_rx": _SpringChannel(raw_el_r[0]),
                    "el_ry": _SpringChannel(raw_el_r[1]),
                }
                el_l, el_r = raw_el_l, raw_el_r
            else:
                el_l = (
                    self._elbow_springs["el_lx"].step(raw_el_l[0], dt, omega=9.0, zeta=1.0),
                    self._elbow_springs["el_ly"].step(raw_el_l[1], dt, omega=9.0, zeta=1.0),
                )
                el_r = (
                    self._elbow_springs["el_rx"].step(raw_el_r[0], dt, omega=9.0, zeta=1.0),
                    self._elbow_springs["el_ry"].step(raw_el_r[1], dt, omega=9.0, zeta=1.0),
                )

            # Ghép TOÀN BỘ cụm bóng + tay trái + thân + tay phải + đầu trên CÙNG 1 canvas 2x SSAA
            ss = 2
            stroke_base = max(4.0, float(self.rig_cfg.get("limb_stroke_px", 9.0)) * self._scale)
            hand_r = max(7.5, stroke_base * 1.48)
            shadow_half_w = max(24.0, t_w * 0.46)
            outline_w_ss = max(3, int(round(stroke_base * 0.44 * ss)))
            w_ss = stroke_base * ss

            hi_canvas = Image.new("RGBA", (cw * ss, ch * ss), (0, 0, 0, 0))
            try:
                dh = ImageDraw.Draw(hi_canvas)
                # Lớp 1: Bóng sàn mềm + tay trái Bézier mượt
                dh.ellipse(
                    (
                        (foot_center_x - shadow_half_w) * ss,
                        (ground_y - 10) * ss,
                        (foot_center_x + shadow_half_w) * ss,
                        (ground_y + 6) * ss,
                    ),
                    fill=(15, 23, 42, 42),
                )
                tan_l = _draw_bezier_arm(
                    dh,
                    (sh_l[0] * ss, sh_l[1] * ss),
                    (el_l[0] * ss, el_l[1] * ss),
                    (wr_l[0] * ss, wr_l[1] * ss),
                    w_ss,
                )
                self._composite_custom_or_vector_hand(
                    hi_canvas,
                    dh,
                    (wr_l[0] * ss, wr_l[1] * ss),
                    tan_l,
                    resolve_hand_shape(
                        self.pose, "left", self.interaction, board_type=self.board_type
                    ),
                    hand_r_ss=hand_r * ss,
                    outline_w_ss=outline_w_ss,
                    side="left",
                    ss=ss,
                )

                # Lớp 2: Thân áo + cà vạt đỏ + nguyên 2 chân chữ A + giày vàng gốc (scale 2x mượt)
                rot_ang_q = round(eff_torso_angle, 1)
                trot_key = (t_h, rot_ang_q)
                trot_cached = self._torso_rot_cache.get(trot_key)
                if trot_cached is not None:
                    torso_rot_hi, torso_rpiv_hi = trot_cached
                    owns_torso_rot = False
                else:
                    torso_hi_cached = self._torso_2x
                    if (
                        torso_hi_cached is not None
                        and torso_hi_cached.width == t_w * ss
                        and torso_hi_cached.height == t_h * ss
                    ):
                        torso_hi = torso_hi_cached
                        owns_torso_hi = False
                    else:
                        torso_src = torso_hi_cached if torso_hi_cached is not None else torso_base
                        torso_hi = torso_src.resize((t_w * ss, t_h * ss), Image.Resampling.BILINEAR)
                        owns_torso_hi = True
                    try:
                        torso_rot_hi, torso_rpiv_hi = rotate_around_pivot(
                            torso_hi,
                            rot_ang_q,
                            (t_w * ss * 0.5, float(t_h * ss)),
                            resample=Image.Resampling.BILINEAR,
                        )
                    finally:
                        if owns_torso_hi:
                            torso_hi.close()
                    if len(self._torso_rot_cache) >= 48:
                        old_tk = next(iter(self._torso_rot_cache))
                        old_rim, _ = self._torso_rot_cache.pop(old_tk)
                        old_rim.close()
                    self._torso_rot_cache[trot_key] = (torso_rot_hi, torso_rpiv_hi)
                    owns_torso_rot = False
                try:
                    hi_canvas.alpha_composite(
                        torso_rot_hi,
                        (
                            int(round(foot_center_x * ss - torso_rpiv_hi[0])),
                            int(round(foot_center_y * ss - torso_rpiv_hi[1])),
                        ),
                    )
                finally:
                    if owns_torso_rot:
                        torso_rot_hi.close()

                # Lớp 3: Tay phải Bézier mượt + găng tay bo tròn liền khối
                tan_r = _draw_bezier_arm(
                    dh,
                    (sh_r[0] * ss, sh_r[1] * ss),
                    (el_r[0] * ss, el_r[1] * ss),
                    (wr_r[0] * ss, wr_r[1] * ss),
                    w_ss,
                )
                self._composite_custom_or_vector_hand(
                    hi_canvas,
                    dh,
                    (wr_r[0] * ss, wr_r[1] * ss),
                    tan_r,
                    resolve_hand_shape(
                        self.pose, "right", self.interaction, board_type=self.board_type
                    ),
                    hand_r_ss=hand_r * ss,
                    outline_w_ss=outline_w_ss,
                    side="right",
                    ss=ss,
                )

                # Lớp 4: Đầu + Mắt + Miệng + Biểu cảm (scale 2x, chống rung nấc pixel)
                head_hi = head_local.resize(
                    (head_local.width * ss, head_local.height * ss), Image.Resampling.BILINEAR
                )
                try:
                    head_rot_hi, head_rpiv_hi = rotate_around_pivot(
                        head_hi,
                        eff_head_angle + eff_torso_angle,
                        (head_piv[0] * ss, head_piv[1] * ss),
                        resample=Image.Resampling.BILINEAR,
                    )
                    try:
                        hi_canvas.alpha_composite(
                            head_rot_hi,
                            (
                                int(round((neck_world[0] + st.head_dx) * ss - head_rpiv_hi[0])),
                                int(round(neck_world[1] * ss - head_rpiv_hi[1])),
                            ),
                        )
                    finally:
                        head_rot_hi.close()
                finally:
                    head_hi.close()

                # Downscale 1 lần duy nhất bằng LANCZOS trên đúng vùng có pixel (tight bbox)
                eff_out_scale = max(0.2, float(output_scale))
                out_w = max(32, int(round(cw * eff_out_scale)))
                out_h = max(32, int(round(ch * eff_out_scale)))
                bbox = hi_canvas.getbbox()
                if bbox is None:
                    return Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
                px0 = max(0, ((bbox[0] - 4) // ss) * ss)
                py0 = max(0, ((bbox[1] - 4) // ss) * ss)
                px1 = min(hi_canvas.width, ((bbox[2] + 4 + ss - 1) // ss) * ss)
                py1 = min(hi_canvas.height, ((bbox[3] + 4 + ss - 1) // ss) * ss)
                if px0 == 0 and py0 == 0 and px1 == hi_canvas.width and py1 == hi_canvas.height:
                    return hi_canvas.resize((out_w, out_h), Image.Resampling.LANCZOS)
                scale_x = out_w / float(hi_canvas.width)
                scale_y = out_h / float(hi_canvas.height)
                dx = int(round(px0 * scale_x))
                dy = int(round(py0 * scale_y))
                dw = max(2, int(round((px1 - px0) * scale_x)))
                dh_out = max(2, int(round((py1 - py0) * scale_y)))
                hi_crop = hi_canvas.crop((px0, py0, px1, py1))
                try:
                    scaled_crop = hi_crop.resize((dw, dh_out), Image.Resampling.LANCZOS)
                    try:
                        out_img = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
                        out_img.paste(scaled_crop, (dx, dy))
                        return out_img
                    finally:
                        scaled_crop.close()
                finally:
                    hi_crop.close()
            finally:
                hi_canvas.close()
        finally:
            head_local.close()

    def close(self) -> None:
        for im, _ in self._torso_rot_cache.values():
            im.close()
        self._torso_rot_cache.clear()
        for group in (self._eye_resize_cache, self._mouth_resize_cache):
            for im in group.values():
                im.close()
            group.clear()
        if not self._shared_assets:
            for group in (self.parts, self.eyes, self.mouths, self.custom_hands):
                for im in group.values():
                    im.close()
                group.clear()
            if self._torso_2x is not None:
                self._torso_2x.close()
                self._torso_2x = None
