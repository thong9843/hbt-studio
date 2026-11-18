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

SEGMENT_NAMES: tuple[str, ...] = ("body_torso", "head_blank", "arm_left", "arm_right")
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
JOINT_CAP_COLOR = (11, 14, 20, 255)  # #0B0E14

DEFAULT_RIG_CONFIG: dict[str, Any] = {
    "neck_pivot_head": [0.50, 0.94],
    "neck_anchor_torso": [0.50, 0.04],
    "shoulder_left_pivot": [0.88, 0.12],
    "shoulder_left_torso": [0.36, 0.14],
    "shoulder_right_pivot": [0.12, 0.12],
    "shoulder_right_torso": [0.64, 0.14],
    "eyes_center_head": [0.50, 0.44],
    "eyes_width_ratio": 0.58,
    "mouth_center_head": [0.50, 0.72],
    "mouth_width_ratio": 0.32,
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


def auto_segment_puppet(
    base_char_path: Path,
    cache_dir: Path,
    *,
    puppet_dir: Path | None = None,
) -> dict[str, Any]:
    """Tự tách `base_character.png` thành 4 lớp RGBA + vá khớp vai `#0B0E14` + cache SHA-256."""
    # Nếu người dùng đã upload sẵn 4 file rời trong puppet_dir thì dùng trực tiếp
    if puppet_dir is not None and all((puppet_dir / f"{s}.png").is_file() for s in SEGMENT_NAMES):
        cfg = dict(DEFAULT_RIG_CONFIG)
        cfg_file = puppet_dir / "rig_config.json"
        if cfg_file.is_file():
            try:
                cfg.update(json.loads(cfg_file.read_text(encoding="utf-8")))
            except Exception:
                pass
        return {
            "segments": {s: puppet_dir / f"{s}.png" for s in SEGMENT_NAMES},
            "rig_config": cfg,
            "cached": True,
        }

    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = _sha256_file(base_char_path)[:16]
    meta_file = cache_dir / f"segments_{digest}.json"
    seg_paths = {s: cache_dir / f"{s}_{digest}.png" for s in SEGMENT_NAMES}
    if meta_file.is_file() and all(p.is_file() for p in seg_paths.values()):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
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

    # 3. Tạo mask từng bộ phận
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

    def _mask_to_cropped(mask: np.ndarray, pad: int = 4) -> tuple[Image.Image, tuple[int, int]]:
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

    head_img, _head_off = _mask_to_cropped(head_mask)
    torso_img, torso_off = _mask_to_cropped(torso_mask)
    arm_l_img, arm_l_off = _mask_to_cropped(arm_left_mask)
    arm_r_img, arm_r_off = _mask_to_cropped(arm_right_mask)

    # 4. Tính tọa độ khớp giải phẫu thực tế trên bounding box từng mảnh & vá khớp `#0B0E14`
    cap_r = max(4, int(round(min(w, h) * 0.014)))
    rig_cfg = dict(DEFAULT_RIG_CONFIG)

    # Tọa độ vai trong ảnh gốc
    sh_l_global = (float(cut_l), float(shoulder_y))
    sh_r_global = (float(cut_r), float(shoulder_y))

    def _to_norm(pt: tuple[float, float], off: tuple[int, int], im: Image.Image) -> list[float]:
        nx = max(0.0, min(1.0, (pt[0] - off[0]) / max(1, im.width)))
        ny = max(0.0, min(1.0, (pt[1] - off[1]) / max(1, im.height)))
        return [round(nx, 4), round(ny, 4)]

    rig_cfg["neck_anchor_torso"] = _to_norm(
        (float(x_center), float(neck_y + 2)), torso_off, torso_img
    )
    rig_cfg["shoulder_left_torso"] = _to_norm(sh_l_global, torso_off, torso_img)
    rig_cfg["shoulder_right_torso"] = _to_norm(sh_r_global, torso_off, torso_img)

    if np.any(arm_left_mask):
        rig_cfg["shoulder_left_pivot"] = _to_norm(sh_l_global, arm_l_off, arm_l_img)
        _draw_joint_cap(
            arm_l_img,
            (
                rig_cfg["shoulder_left_pivot"][0] * arm_l_img.width,
                rig_cfg["shoulder_left_pivot"][1] * arm_l_img.height,
            ),
            cap_r,
        )
    if np.any(arm_right_mask):
        rig_cfg["shoulder_right_pivot"] = _to_norm(sh_r_global, arm_r_off, arm_r_img)
        _draw_joint_cap(
            arm_r_img,
            (
                rig_cfg["shoulder_right_pivot"][0] * arm_r_img.width,
                rig_cfg["shoulder_right_pivot"][1] * arm_r_img.height,
            ),
            cap_r,
        )

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

    try:
        torso_img.save(seg_paths["body_torso"], format="PNG")
        head_img.save(seg_paths["head_blank"], format="PNG")
        arm_l_img.save(seg_paths["arm_left"], format="PNG")
        arm_r_img.save(seg_paths["arm_right"], format="PNG")
        meta_file.write_text(
            json.dumps({"sha256": digest, "rig_config": rig_cfg}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        head_img.close()
        torso_img.close()
        arm_l_img.close()
        arm_r_img.close()

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


def smooth_rms_envelope(raw_rms: list[float]) -> list[float]:
    """Áp dụng bộ lọc mượt EMA `env[i] = 0.55 * rms_norm[i] + 0.45 * env[i-1]`."""
    if not raw_rms:
        return []
    out: list[float] = []
    prev = 0.0
    for val in raw_rms:
        clamped = max(0.0, min(1.0, float(val)))
        cur = 0.55 * clamped + 0.45 * prev
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
        return smooth_rms_envelope(rms_norm)
    except Exception:
        return [0.0] * n_frames


def compute_mouth_transform(env_val: float) -> tuple[str, float, float]:
    """Trả về `(mouth_slot, scale_x, scale_y)` qua 3 mức: closed -> half_open -> open."""
    if env_val < 0.14:
        return "mouth_closed", 1.0, 1.0
    if env_val < 0.40:
        # Mức mở vừa (half_open ~55%-78%) giúp không nhấp nháy ở âm lượng nhẹ
        u = (env_val - 0.14) / 0.26
        scale_y = 0.55 + 0.23 * u
        scale_x = 1.03 - 0.04 * u
        return "mouth_open", round(scale_x, 4), round(scale_y, 4)
    # Mức mở lớn (open 80%-128%) theo Squash & Stretch
    t = min(1.0, (env_val - 0.40) / 0.45)
    scale_y = 0.78 + 0.50 * t
    scale_x = 1.04 - 0.12 * (scale_y - 0.55)
    return "mouth_open", round(scale_x, 4), round(scale_y, 4)


class EyeController:
    """Điều khiển biểu cảm mắt, chớp mắt sinh học 3.2s và liếc mắt theo interaction."""

    _SHOCK_POSES = {"shock", "scared", "shock_jump", "confused"}
    _HAPPY_POSES = {"happy", "laugh", "winner", "love", "idea", "idea_bulb", "celebrate", "rich"}
    _ANGRY_POSES = {"angry", "evil_grin", "run", "stop", "stop_hand"}

    def __init__(
        self,
        *,
        pose: str,
        anim_oneshot: str | None = None,
        interaction: str = "none",
        beat_id: str = "b001",
        fps: int = 30,
    ) -> None:
        self.fps = max(15, int(fps))
        self.interaction = (interaction or "none").strip().lower()
        self.eye_slot = self._resolve_slot(pose, anim_oneshot)
        # Hạt giống lệch pha ±0.4s theo beat_id
        seed_num = sum(ord(ch) for ch in (beat_id or "b001")) % 25
        jitter_s = ((seed_num / 24.0) - 0.5) * 0.8
        self.blink_period_frames = max(30, int(round((3.2 + jitter_s) * self.fps)))

    @classmethod
    def _resolve_slot(cls, pose: str, anim_oneshot: str | None) -> str:
        for raw in (anim_oneshot or "", pose or ""):
            key = raw.strip().lower()
            if key in cls._SHOCK_POSES:
                return "eyes_shock"
            if key in cls._HAPPY_POSES:
                return "eyes_happy"
            if key in cls._ANGRY_POSES:
                return "eyes_angry"
        return "eyes_neutral"

    def state_at(self, frame_idx: int) -> tuple[str, float, float, float]:
        """Trả về `(eye_slot, eye_scale_y, offset_x_px, offset_y_px)`."""
        eye_scale_y = 1.0
        if self.eye_slot != "eyes_happy":
            pos = frame_idx % self.blink_period_frames
            if pos == 0:
                eye_scale_y = 0.45
            elif pos == 1:
                eye_scale_y = 0.12
            elif pos == 2:
                eye_scale_y = 0.50

        ox, oy = 0.0, 0.0
        if self.interaction == "hold_prop":
            ox, oy = 4.0, -2.0
        elif self.interaction == "point_chart":
            ox, oy = 3.0, -4.0

        return self.eye_slot, eye_scale_y, ox, oy


@dataclass(frozen=True)
class PuppetPoseState:
    head_angle: float = 0.0
    head_dx: float = 0.0
    arm_l_angle: float = 0.0
    arm_r_angle: float = 0.0
    torso_angle: float = 0.0
    torso_dy: float = 0.0
    torso_scale_y: float = 1.0


def _hermite_smoothstep(t: float) -> float:
    u = max(0.0, min(1.0, float(t)))
    return u * u * (3.0 - 2.0 * u)


class _SpringChannel:
    """Bộ lọc giảm chấn lò xo tới hạn (critically damped spring) ổn định mọi fps."""

    def __init__(self, initial: float = 0.0) -> None:
        self.pos = float(initial)
        self.vel = 0.0

    def step(self, target: float, dt: float, omega: float = 12.0) -> float:
        f = 1.0 + 2.0 * omega * dt
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
        arm_r_angle=a.arm_r_angle + (b.arm_r_angle - a.arm_r_angle) * t,
        torso_angle=a.torso_angle + (b.torso_angle - a.torso_angle) * t,
        torso_dy=a.torso_dy + (b.torso_dy - a.torso_dy) * t,
        torso_scale_y=a.torso_scale_y + (b.torso_scale_y - a.torso_scale_y) * t,
    )


def evaluate_action_curve(action: str, t_sec: float, env_val: float) -> PuppetPoseState:
    """Tính góc xoay & dịch chuyển theo 9 đường cong hành động chuẩn (§4)."""
    act = (action or "talk_explain").strip().lower()
    env = max(0.0, min(1.0, float(env_val)))
    t = max(0.0, float(t_sec))

    if act == "idle_breathe":
        return PuppetPoseState(
            head_angle=2.0 * math.sin(1.8 * t),
            arm_l_angle=4.0 * math.sin(1.8 * t),
            arm_r_angle=-4.0 * math.sin(1.8 * t),
            torso_scale_y=1.0 + 0.012 * math.sin(2.2 * t),
        )
    if act in ("point_board", "point_chart"):
        phrase = math.sin(2.4 * t) * (0.4 + 0.6 * env)
        return PuppetPoseState(
            head_angle=-6.0 - 3.0 * env + 1.5 * math.sin(2.0 * t),
            arm_l_angle=10.0 + 4.0 * phrase,
            arm_r_angle=-52.0 + 9.0 * phrase,
            torso_angle=2.0 + 0.6 * math.sin(1.8 * t),
        )
    if act == "hold_prop":
        phrase = math.sin(2.6 * t) * (0.4 + 0.6 * env)
        return PuppetPoseState(
            head_angle=5.0 - 2.0 * env + 1.2 * math.sin(2.0 * t),
            arm_l_angle=10.0 + 3.5 * phrase,
            arm_r_angle=-42.0 + 7.5 * phrase,
            torso_dy=-2.5 * env,
        )
    if act in ("talk_excited", "celebrate"):
        return PuppetPoseState(
            head_angle=-7.0 * env + 2.0 * math.sin(5.0 * t),
            arm_l_angle=-45.0 + 18.0 * math.sin(6.0 * t),
            arm_r_angle=45.0 - 18.0 * math.sin(6.0 * t),
            torso_dy=-8.0 * abs(math.sin(5.0 * t)),
        )
    if act == "think_loop":
        return PuppetPoseState(
            head_angle=9.0 + 1.5 * math.sin(1.5 * t),
            arm_l_angle=-18.0,
            arm_r_angle=-62.0 + 3.0 * math.sin(2.0 * t),
            torso_scale_y=1.0 + 0.01 * math.sin(1.5 * math.pi * 2.0 * t),
        )
    if act == "shock_jump":
        damp = max(0.0, 1.0 - t / 0.65)
        jump_dy = -26.0 * math.sin(math.pi * t / 0.45) if t < 0.45 else 0.0
        return PuppetPoseState(
            head_angle=-8.0 * damp,
            head_dx=4.0 * math.sin(32.0 * t) * damp,
            arm_l_angle=-48.0 * damp,
            arm_r_angle=48.0 * damp,
            torso_dy=jump_dy,
        )
    if act == "nod_agree":
        return PuppetPoseState(
            head_angle=-12.0 * math.sin(2.0 * math.pi * t / 0.6),
            arm_l_angle=5.0,
            arm_r_angle=-5.0,
            torso_dy=-2.0 * abs(math.sin(2.0 * math.pi * t / 0.6)),
        )
    if act == "shake_head":
        return PuppetPoseState(
            head_dx=7.0 * math.sin(3.0 * math.pi * t / 0.7),
            arm_l_angle=6.0,
            arm_r_angle=-6.0,
        )
    # Mặc định: talk_explain
    return PuppetPoseState(
        head_angle=-5.5 * env + 2.0 * math.sin(3.0 * t),
        arm_l_angle=8.0 + 5.0 * math.sin(2.5 * t),
        arm_r_angle=-28.0 + 14.0 * math.sin(4.2 * t) * env,
        torso_dy=-3.0 * env,
    )


def _load_rgba_scaled(path: Path, scale: float) -> Image.Image:
    with Image.open(path) as raw:
        rgba = raw.convert("RGBA")
        if abs(scale - 1.0) < 0.005:
            return rgba.copy()
        nw = max(4, int(round(rgba.width * scale)))
        nh = max(4, int(round(rgba.height * scale)))
        return rgba.resize((nw, nh), Image.Resampling.LANCZOS)


class PuppetRig:
    """Bộ diễn hoạt Puppet 2D hoàn chỉnh cho 1 beat (tách khớp + hierarchical bone tree)."""

    def __init__(
        self,
        *,
        library_dir: Path,
        assets_dir: Path,
        target_height: int,
        pose: str = "explain",
        anim_oneshot: str | None = None,
        anim_loop: str = "talk_explain",
        interaction: str = "none",
        facing: str = "right",
        beat_id: str = "b001",
        fps: int = 30,
        speech_start: float = 0.0,
        speech_end: float = 2.0,
        rms_env: list[float] | None = None,
        prev_pose_state: PuppetPoseState | None = None,
        global_t_offset: float = 0.0,
    ) -> None:
        self.target_height = max(120, int(target_height))
        self.pose = pose
        self.anim_oneshot = (anim_oneshot or "").strip() or None
        self.anim_loop = (anim_loop or "talk_explain").strip() or "talk_explain"
        self.interaction = (interaction or "none").strip().lower()
        self.facing = facing
        self.fps = max(15, int(fps))
        self.speech_start = max(0.0, float(speech_start))
        self.speech_end = max(self.speech_start, float(speech_end))
        self.env = smooth_rms_envelope(rms_env or [])
        self.prev_pose_state = prev_pose_state
        self.global_t_offset = max(0.0, float(global_t_offset))
        self.tween_dur = 0.40 if prev_pose_state is not None else 0.0
        init_st = prev_pose_state or PuppetPoseState()
        self._springs = {
            "head_angle": _SpringChannel(init_st.head_angle),
            "head_dx": _SpringChannel(init_st.head_dx),
            "arm_l_angle": _SpringChannel(init_st.arm_l_angle),
            "arm_r_angle": _SpringChannel(init_st.arm_r_angle),
            "torso_angle": _SpringChannel(init_st.torso_angle),
            "torso_dy": _SpringChannel(init_st.torso_dy),
            "torso_scale_y": _SpringChannel(init_st.torso_scale_y),
        }
        self._follow_history: list[PuppetPoseState] = [init_st, init_st, init_st]
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

        # Tính hệ số scale sao cho tổng chiều cao (đầu + thân) khớp `target_height`
        with Image.open(seg_paths["body_torso"]) as bt, Image.open(seg_paths["head_blank"]) as hb:
            raw_total_h = max(1, bt.height + int(hb.height * 0.85))
        scale = (self.target_height * 0.88) / raw_total_h

        self.parts: dict[str, Image.Image] = {
            name: _load_rgba_scaled(seg_paths[name], scale) for name in SEGMENT_NAMES
        }

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
            anim_oneshot=self.anim_oneshot,
            interaction=self.interaction,
            beat_id=beat_id,
            fps=self.fps,
        )
        self.oneshot_dur = 0.65 if self.anim_oneshot else 0.0
        self.blend_dur = 0.15  # 5 frames @ 30fps

    def _select_loop_action(self) -> str:
        if self.interaction == "point_chart":
            return "point_board"
        if self.interaction == "hold_prop":
            return "hold_prop"
        return self.anim_loop

    def _raw_pose_state_at(self, t_sec: float, env_val: float) -> PuppetPoseState:
        loop_action = self._select_loop_action()
        gt = self.global_t_offset + t_sec

        if t_sec > self.speech_end:
            idle_state = evaluate_action_curve("idle_breathe", gt, 0.0)
            dt_idle = t_sec - self.speech_end
            if dt_idle < self.blend_dur:
                prev_state = evaluate_action_curve(loop_action, gt, env_val)
                return lerp_pose_state(prev_state, idle_state, dt_idle / self.blend_dur)
            return idle_state

        if self.anim_oneshot and t_sec < self.oneshot_dur:
            target_st = evaluate_action_curve(self.anim_oneshot, t_sec, env_val)
        else:
            loop_state = evaluate_action_curve(loop_action, gt, env_val)
            if self.anim_oneshot and t_sec < (self.oneshot_dur + self.blend_dur):
                alpha = (t_sec - self.oneshot_dur) / self.blend_dur
                oneshot_tail = evaluate_action_curve(self.anim_oneshot, t_sec, env_val)
                target_st = lerp_pose_state(oneshot_tail, loop_state, alpha)
            else:
                target_st = loop_state

        if self.prev_pose_state is not None and t_sec < self.tween_dur:
            return lerp_pose_state(self.prev_pose_state, target_st, t_sec / self.tween_dur)
        return target_st

    def _pose_state_at(self, t_sec: float, env_val: float) -> PuppetPoseState:
        raw_target = self._raw_pose_state_at(t_sec, env_val)
        dt = 1.0 / self.fps
        # Follow-through (~2-3 frames lag): thân dẫn -> đầu trễ 2 frame -> tay trễ 3 frame
        self._follow_history.append(raw_target)
        if len(self._follow_history) > 4:
            self._follow_history.pop(0)
        head_lag = self._follow_history[-2] if len(self._follow_history) >= 2 else raw_target
        arm_lag = self._follow_history[0]

        smoothed = PuppetPoseState(
            head_angle=self._springs["head_angle"].step(head_lag.head_angle, dt, omega=11.0),
            head_dx=self._springs["head_dx"].step(head_lag.head_dx, dt, omega=12.0),
            arm_l_angle=self._springs["arm_l_angle"].step(arm_lag.arm_l_angle, dt, omega=9.5),
            arm_r_angle=self._springs["arm_r_angle"].step(arm_lag.arm_r_angle, dt, omega=9.5),
            torso_angle=self._springs["torso_angle"].step(raw_target.torso_angle, dt, omega=14.0),
            torso_dy=self._springs["torso_dy"].step(raw_target.torso_dy, dt, omega=14.0),
            torso_scale_y=self._springs["torso_scale_y"].step(
                raw_target.torso_scale_y, dt, omega=13.0
            ),
        )
        self.last_pose_state = smoothed
        return smoothed

    def _build_head_layer(self, frame_idx: int, env_val: float) -> Image.Image:
        """Lắp Eyes & Mouth vào hệ tọa độ cục bộ của Head trước khi xoay khối đầu."""
        head = self.parts["head_blank"].copy()
        hw, hh = head.size

        # 1. Eyes layer
        eslot, eye_sy, eox, eoy = self.eye_ctrl.state_at(frame_idx)
        eye_src = self.eyes.get(eslot) or self.eyes.get("eyes_neutral")
        if eye_src is not None:
            ew = max(8, int(round(hw * float(self.rig_cfg["eyes_width_ratio"]))))
            eh = max(2, int(round((ew * eye_src.height / max(1, eye_src.width)) * eye_sy)))
            eye_resized = eye_src.resize((ew, eh), Image.Resampling.LANCZOS)
            ecx = hw * float(self.rig_cfg["eyes_center_head"][0]) + eox
            ecy = hh * float(self.rig_cfg["eyes_center_head"][1]) + eoy
            ex = max(2, min(hw - ew - 2, int(round(ecx - ew / 2))))
            ey = max(2, min(hh - eh - 2, int(round(ecy - eh / 2))))
            head.alpha_composite(eye_resized, (ex, ey))
            eye_resized.close()

        # 2. Mouth layer (3 mức closed -> half_open -> open + làm mượt EMA chống nhấp nháy)
        mslot, msx, msy_target = compute_mouth_transform(env_val)
        self._mouth_sy_smooth = 0.60 * msy_target + 0.40 * self._mouth_sy_smooth
        msy = self._mouth_sy_smooth if mslot == "mouth_open" else 1.0
        mouth_src = self.mouths.get(mslot) or self.mouths.get("mouth_closed")
        if mouth_src is not None:
            base_mw = max(8, int(round(hw * float(self.rig_cfg["mouth_width_ratio"]))))
            base_mh = max(4, int(round(base_mw * mouth_src.height / max(1, mouth_src.width))))
            mw = max(4, min(int(hw * 0.65), int(round(base_mw * msx))))
            mh = max(3, min(int(hh * 0.40), int(round(base_mh * msy))))
            mouth_resized = mouth_src.resize((mw, mh), Image.Resampling.LANCZOS)
            mcx = hw * float(self.rig_cfg["mouth_center_head"][0])
            mcy = hh * float(self.rig_cfg["mouth_center_head"][1])
            mx = max(2, min(hw - mw - 2, int(round(mcx - mw / 2))))
            my = max(2, min(hh - mh - 2, int(round(mcy - mh / 2))))
            head.alpha_composite(mouth_resized, (mx, my))
            mouth_resized.close()

        return head

    def render_frame(self, frame_idx: int, t_sec: float) -> Image.Image:
        """Dựng 1 frame Puppet RGBA theo cây khớp Cha–Con, chân bám đáy canvas."""
        env_val = self.env[frame_idx] if 0 <= frame_idx < len(self.env) else 0.0
        st = self._pose_state_at(t_sec, env_val)

        torso_base = self.parts["body_torso"]
        head_local = self._build_head_layer(frame_idx, env_val)
        arm_l_src = self.parts["arm_left"]
        arm_r_src = self.parts["arm_right"]

        # Kích thước canvas cố định đủ rộng cho đầu & tay vung, chân bám đáy
        cw = max(
            int(self.target_height * 0.85),
            torso_base.width + arm_l_src.width + arm_r_src.width + 40,
        )
        ch = self.target_height
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

        try:
            # [2] BODY_TORSO (bám Root đáy chân)
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

            root_world_x = cw * 0.5
            root_world_y = float(ch - 8) + st.torso_dy
            torso_tl_x = int(round(root_world_x - torso_rot_pivot[0]))
            torso_tl_y = int(round(root_world_y - torso_rot_pivot[1]))

            # Hàm ánh xạ điểm cục bộ của torso sang tọa độ world sau biến đổi của torso
            theta_t = math.radians(st.torso_angle)
            cos_t, sin_t = math.cos(theta_t), math.sin(theta_t)

            def _torso_anchor_world(norm_xy: list[float]) -> tuple[float, float]:
                lx = float(norm_xy[0]) * t_w - torso_pivot_local[0]
                ly = float(norm_xy[1]) * t_h - torso_pivot_local[1]
                wx = root_world_x + (lx * cos_t + ly * sin_t)
                wy = root_world_y + (-lx * sin_t + ly * cos_t)
                return wx, wy

            # [3] ARM_LEFT
            sh_l_world = _torso_anchor_world(self.rig_cfg["shoulder_left_torso"])
            arm_l_piv = (
                float(self.rig_cfg["shoulder_left_pivot"][0]) * arm_l_src.width,
                float(self.rig_cfg["shoulder_left_pivot"][1]) * arm_l_src.height,
            )
            arm_l_rot, arm_l_rpiv = rotate_around_pivot(
                arm_l_src, st.arm_l_angle + st.torso_angle, arm_l_piv
            )
            canvas.alpha_composite(
                arm_l_rot,
                (
                    int(round(sh_l_world[0] - arm_l_rpiv[0])),
                    int(round(sh_l_world[1] - arm_l_rpiv[1])),
                ),
            )
            arm_l_rot.close()

            # [4] ARM_RIGHT
            sh_r_world = _torso_anchor_world(self.rig_cfg["shoulder_right_torso"])
            arm_r_piv = (
                float(self.rig_cfg["shoulder_right_pivot"][0]) * arm_r_src.width,
                float(self.rig_cfg["shoulder_right_pivot"][1]) * arm_r_src.height,
            )
            arm_r_rot, arm_r_rpiv = rotate_around_pivot(
                arm_r_src, st.arm_r_angle + st.torso_angle, arm_r_piv
            )
            canvas.alpha_composite(
                arm_r_rot,
                (
                    int(round(sh_r_world[0] - arm_r_rpiv[0])),
                    int(round(sh_r_world[1] - arm_r_rpiv[1])),
                ),
            )
            arm_r_rot.close()

            # Composite Torso (che đẹp phần giao vai nhờ joint cap)
            canvas.alpha_composite(torso_rot, (torso_tl_x, torso_tl_y))
            torso_rot.close()

            # [5] HEAD_BLANK + [6] EYES + [7] MOUTH (xoay nguyên khối quanh neck_pivot)
            neck_world = _torso_anchor_world(self.rig_cfg["neck_anchor_torso"])
            head_piv = (
                float(self.rig_cfg["neck_pivot_head"][0]) * head_local.width,
                float(self.rig_cfg["neck_pivot_head"][1]) * head_local.height,
            )
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
