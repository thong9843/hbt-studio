"""Shared FFmpeg pipeline helpers cho HBT Studio."""

from hbt.shared.pipeline.aspect import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    AspectMode,
    build_aspect_filter,
    build_simple_vf,
    default_aspect_mode_for_engine,
)
from hbt.shared.pipeline.watermark import (
    WatermarkSettings,
    build_watermark_overlay_filter,
    render_watermark_png,
    resolve_watermark_logo,
)

__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_WIDTH",
    "AspectMode",
    "WatermarkSettings",
    "build_aspect_filter",
    "build_simple_vf",
    "build_watermark_overlay_filter",
    "default_aspect_mode_for_engine",
    "render_watermark_png",
    "resolve_watermark_logo",
]
