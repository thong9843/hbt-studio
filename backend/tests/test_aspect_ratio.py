"""Tests cho bộ chuẩn hóa khung hình 9:16 Smart Fit / Fill."""

from __future__ import annotations

import pytest

from hbt.shared.pipeline.aspect import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    build_aspect_filter,
    build_simple_vf,
    default_aspect_mode_for_engine,
)


def test_aspect_defaults_are_1080x1920() -> None:
    assert DEFAULT_WIDTH == 1080
    assert DEFAULT_HEIGHT == 1920
    assert default_aspect_mode_for_engine("core") == "fill"
    assert default_aspect_mode_for_engine("postv") == "fit"
    assert default_aspect_mode_for_engine("chatting") == "fit"


def test_build_aspect_filter_fill() -> None:
    flt = build_aspect_filter("fill", input_label="0:v", output_label="bg")
    assert "[0:v]scale=1080:1920:force_original_aspect_ratio=increase" in flt
    assert "crop=1080:1920,setsar=1[bg]" in flt


def test_build_aspect_filter_fit_with_boxblur() -> None:
    flt = build_aspect_filter("fit", input_label="1:v", output_label="out")
    assert "split=2[out_bg_src][out_fg_src]" in flt
    assert "boxblur=25:5" in flt
    assert "overlay=(W-w)/2:(H-h)/2[out]" in flt


def test_build_simple_vf_and_invalid_mode() -> None:
    assert "crop=1080:1920" in build_simple_vf("fill")
    assert "boxblur=25:5" in build_simple_vf("fit")
    with pytest.raises(ValueError, match="aspect_mode"):
        build_aspect_filter("stretch")  # type: ignore[arg-type]


def test_engines_support_aspect_mode(tmp_path, monkeypatch) -> None:
    from PIL import Image

    from hbt.chatting.models import Character, ChatDoc, Message
    from hbt.core.render import build_core_scene_layers_safe, render_core_segment_clip
    from hbt.postv import bgbuild
    from hbt.postv.models import PostvSettings

    # 1. HBT Core: build_core_scene_layers_safe + render_core_segment_clip với fit/fill
    src_img = tmp_path / "src.png"
    Image.new("RGB", (1920, 1080), (10, 120, 200)).save(src_img)
    base_fit = tmp_path / "base_fit.png"
    card_fit = tmp_path / "card_fit.png"
    build_core_scene_layers_safe(
        {"card": {"y": "top", "lines": [{"text": "Test", "size": "m", "color": "ink"}]}},
        src_img,
        base_fit,
        card_fit,
        {"primary": "#e11d48", "ink": "#111827"},
        aspect_mode="fit",
    )
    with Image.open(base_fit) as im:
        assert im.size == (1080, 1920)

    captured_cmds: list[list[str]] = []

    def fake_run_ffmpeg(cmd, **_kwargs):
        captured_cmds.append([str(x) for x in cmd])
        # Tạo file đích giả để publish_atomic hoạt động
        out_p = tmp_path / "seg.tmp.mp4"
        out_p.write_bytes(b"mp4")

    monkeypatch.setattr("hbt.core.render.run_ffmpeg", fake_run_ffmpeg)
    render_core_segment_clip(base_fit, card_fit, 1.0, 1, tmp_path / "seg.mp4", aspect_mode="fit")
    assert any("boxblur=25:5" in " ".join(c) for c in captured_cmds)

    # 2. PostV: PostvSettings + bgbuild.bg_key + bgbuild.build_background mặc định fit
    assert PostvSettings().aspect_mode == "fit"
    assert PostvSettings(aspect_mode="fill").aspect_mode == "fill"

    clip = tmp_path / "bg_clip.mp4"
    clip.write_bytes(b"clip")
    pieces = [bgbuild.Piece("c1", clip, 0.0, 2.0)]
    k_fill = bgbuild.bg_key(pieces, 1080, 1920, 60, "veryfast", 20, aspect_mode="fill")
    k_fit = bgbuild.bg_key(pieces, 1080, 1920, 60, "veryfast", 20, aspect_mode="fit")
    assert k_fill != k_fit

    pv_cmds: list[list[str]] = []

    def fake_pv_ffmpeg(cmd):
        pv_cmds.append([str(x) for x in cmd])
        (tmp_path / "bg.part.mp4").write_bytes(b"bg")

    monkeypatch.setattr(bgbuild, "run_ffmpeg", fake_pv_ffmpeg)
    bgbuild.build_background(
        pieces, 1080, 1920, 60, "veryfast", 20, tmp_path / "bg.mp4", aspect_mode="fit"
    )
    assert any("boxblur=25:5" in " ".join(c) for c in pv_cmds)

    # 3. Chatting: ChatDoc.aspect_mode mặc định fit
    doc = ChatDoc(
        title="Test",
        characters=[
            Character(id="me", name="A", side="right"),
            Character(id="o", name="B", side="left"),
        ],
        messages=[Message(from_="me", text=f"Tin {i}") for i in range(8)],
    )
    assert doc.aspect_mode == "fit"
