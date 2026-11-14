"""Tests cho bộ tạo & phủ lớp Watermark bản quyền (shared/pipeline/watermark.py)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from hbt.app_settings import AppSettings, AppSettingsStore
from hbt.shared.pipeline.watermark import (
    WatermarkSettings,
    build_watermark_overlay_filter,
    render_watermark_png,
    resolve_watermark_logo,
)


def test_watermark_settings_defaults_and_persistence(tmp_path: Path) -> None:
    store = AppSettingsStore(tmp_path)
    loaded = store.load()
    assert loaded.watermark.enabled is True
    assert loaded.watermark.mode == "both"
    assert loaded.watermark.text == "@HayBietTuot"
    assert loaded.watermark.position == "top-right"
    assert loaded.watermark.opacity == 0.35

    updated = AppSettings(
        watermark=WatermarkSettings(
            enabled=True,
            mode="text",
            text="@HBTChannel",
            position="top-left",
            opacity=0.5,
        )
    )
    store.save(updated)
    reloaded = store.load()
    assert reloaded.watermark.mode == "text"
    assert reloaded.watermark.text == "@HBTChannel"
    assert reloaded.watermark.position == "top-left"
    assert reloaded.watermark.opacity == 0.5


def test_render_watermark_png_modes_and_positions(tmp_path: Path) -> None:
    logo_path = resolve_watermark_logo("brand/hbt-logo-mark.png")
    assert logo_path is not None and logo_path.is_file()

    for mode in ("both", "text", "logo"):
        for pos in ("top-right", "top-left", "center-subtle"):
            out_png = tmp_path / f"wm_{mode}_{pos}.png"
            cfg = WatermarkSettings(enabled=True, mode=mode, position=pos, opacity=0.40)
            res = render_watermark_png(out_png, cfg, width=540, height=960)
            assert res.is_file()
            with Image.open(res) as im:
                assert im.size == (540, 960)
                assert im.mode == "RGBA"
                # Phải có pixel không trong suốt ở vùng vẽ watermark
                alpha_extrema = im.getchannel("A").getextrema()
                assert alpha_extrema is not None and alpha_extrema[1] > 0

    # Khi disabled -> ảnh hoàn toàn trong suốt
    disabled_png = tmp_path / "wm_disabled.png"
    render_watermark_png(disabled_png, WatermarkSettings(enabled=False), width=540, height=960)
    with Image.open(disabled_png) as im:
        assert im.getchannel("A").getextrema() == (0, 0)


def test_build_watermark_overlay_filter_hides_on_outro() -> None:
    flt = build_watermark_overlay_filter(
        input_video="ov", input_wm="wm", output_label="ov_wm", visible_until_s=26.0
    )
    assert "[ov][wm]overlay=0:0:eof_action=pass:enable='between(t,0,26.000)'" in flt
    assert "[ov_wm]" in flt
