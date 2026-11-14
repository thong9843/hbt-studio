"""Bộ chuẩn hóa khung hình FFmpeg 9:16 (1080x1920) Smart Fit / Fill dùng chung."""

from __future__ import annotations

from typing import Literal

DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920

AspectMode = Literal["fill", "fit"]


def build_simple_vf(
    mode: AspectMode = "fill",
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """Trả về chuỗi -vf cho chế độ fill (1 luồng) hoặc filter_complex rút gọn."""
    if mode not in ("fill", "fit"):
        raise ValueError(f"aspect_mode không hợp lệ: {mode}")
    if mode == "fill":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )
    return (
        f"split=2[bg_src][fg_src];"
        f"[bg_src]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=25:5,setsar=1[bg_blur];"
        f"[fg_src]scale={width}:-2:force_original_aspect_ratio=decrease,setsar=1[fg_fit];"
        f"[bg_blur][fg_fit]overlay=(W-w)/2:(H-h)/2"
    )


def build_aspect_filter(
    mode: AspectMode = "fill",
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    input_label: str = "0:v",
    output_label: str = "vout",
) -> str:
    """Tạo đoạn filter_complex chuẩn hóa 9:16 (1080x1920) cho cả fill và fit."""
    if mode not in ("fill", "fit"):
        raise ValueError(f"aspect_mode không hợp lệ: {mode}")
    if mode == "fill":
        return (
            f"[{input_label}]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1[{output_label}]"
        )
    return (
        f"[{input_label}]split=2[bg_src][fg_src];"
        f"[bg_src]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=25:5,setsar=1[bg_blur];"
        f"[fg_src]scale={width}:-2:force_original_aspect_ratio=decrease,setsar=1[fg_fit];"
        f"[bg_blur][fg_fit]overlay=(W-w)/2:(H-h)/2[{output_label}]"
    )
