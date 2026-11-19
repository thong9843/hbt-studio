"""Chuyển cảnh biên tập tốc độ cao: Editorial Cut, Paper Slide & Whip-Pan 1D motion blur."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

from hbt.cinema.motion import clamp01, ease_out_cubic
from hbt.cinema.schema import TransitionType


def _horizontal_motion_blur(arr: np.ndarray, radius: int) -> np.ndarray:
    """Làm mờ chuyển động ngang 1D tốc độ O(W*H) bằng tổng tích lũy NumPy."""
    if radius <= 1:
        return arr
    k = min(41, int(radius) * 2 + 1)
    pad_l = k // 2
    pad_r = k - 1 - pad_l
    padded = np.pad(arr.astype(np.float32), ((0, 0), (pad_l, pad_r), (0, 0)), mode="edge")
    cs = np.cumsum(padded, axis=1)
    zeros = np.zeros((arr.shape[0], 1, arr.shape[2]), dtype=np.float32)
    cs_full = np.concatenate([zeros, cs], axis=1)
    blurred = (cs_full[:, k:, :] - cs_full[:, :-k, :]) / float(k)
    return np.clip(blurred, 0, 255).astype(np.uint8)


def apply_transition(
    prev_rgb: Image.Image,
    next_rgb: Image.Image,
    progress: float,
    kind: TransitionType,
    *,
    direction: Literal["left", "right"] = "left",
) -> Image.Image:
    """Áp dụng hiệu ứng chuyển cảnh tại tiến độ `progress` in [0, 1] và trả về ảnh RGB mới."""
    p = clamp01(progress)
    if kind == "editorial_cut" or p >= 0.999:
        return next_rgb.convert("RGB")
    if p <= 0.001:
        return prev_rgb.convert("RGB")

    w, h = next_rgb.size
    prev_fit = prev_rgb.convert("RGB")
    if prev_fit.size != (w, h):
        resized = prev_fit.resize((w, h), Image.Resampling.BILINEAR)
        prev_fit.close()
        prev_fit = resized

    next_fit = next_rgb.convert("RGB")
    try:
        u = ease_out_cubic(p)
        sign = -1 if direction == "left" else 1

        if kind == "paper_slide":
            out = prev_fit.copy()
            offset_x = int(round((1.0 - u) * w * (-sign)))
            # Đổ bóng mép tờ giấy trượt lên nhau
            shadow_x = offset_x if offset_x > 0 else offset_x + w
            if 0 <= shadow_x < w:
                draw = ImageDraw.Draw(out, "RGBA")
                draw.rectangle(
                    (max(0, shadow_x - 16), 0, min(w, shadow_x + 16), h),
                    fill=(15, 23, 42, 72),
                )
            out.paste(next_fit, (offset_x, 0))
            return out

        # whip_pan: trượt ngang kèm 1D motion blur đỉnh ở giữa chuyển động
        blur_strength = math.sin(math.pi * p)
        blur_radius = max(1, int(round(blur_strength * max(6, w // 45))))
        prev_arr = _horizontal_motion_blur(np.asarray(prev_fit), blur_radius)
        next_arr = _horizontal_motion_blur(np.asarray(next_fit), blur_radius)

        shift = int(round(u * w))
        canvas = np.zeros_like(next_arr)
        if direction == "left":
            rem = w - shift
            if rem > 0:
                canvas[:, :rem, :] = prev_arr[:, shift:, :]
            if shift > 0:
                canvas[:, rem:, :] = next_arr[:, :shift, :]
        else:
            rem = w - shift
            if shift > 0:
                canvas[:, :shift, :] = next_arr[:, rem:, :]
            if rem > 0:
                canvas[:, shift:, :] = prev_arr[:, :rem, :]
        return Image.fromarray(canvas, mode="RGB")
    finally:
        prev_fit.close()
        next_fit.close()
