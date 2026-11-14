"""Tests cho bộ chuẩn hóa khung hình 9:16 Smart Fit / Fill."""

from __future__ import annotations

import pytest

from hbt.shared.pipeline.aspect import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    build_aspect_filter,
    build_simple_vf,
)


def test_aspect_defaults_are_1080x1920() -> None:
    assert DEFAULT_WIDTH == 1080
    assert DEFAULT_HEIGHT == 1920


def test_build_aspect_filter_fill() -> None:
    flt = build_aspect_filter("fill", input_label="0:v", output_label="bg")
    assert "[0:v]scale=1080:1920:force_original_aspect_ratio=increase" in flt
    assert "crop=1080:1920,setsar=1[bg]" in flt


def test_build_aspect_filter_fit_with_boxblur() -> None:
    flt = build_aspect_filter("fit", input_label="1:v", output_label="out")
    assert "split=2[bg_src][fg_src]" in flt
    assert "boxblur=25:5" in flt
    assert "overlay=(W-w)/2:(H-h)/2[out]" in flt


def test_build_simple_vf_and_invalid_mode() -> None:
    assert "crop=1080:1920" in build_simple_vf("fill")
    assert "boxblur=25:5" in build_simple_vf("fit")
    with pytest.raises(ValueError, match="aspect_mode"):
        build_aspect_filter("stretch")  # type: ignore[arg-type]
