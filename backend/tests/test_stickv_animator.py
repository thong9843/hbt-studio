"""Unit test cho StickmanAnimator (.webm alpha / PNG sequence / RMS fallback) & /library."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from hbt.config import Settings
from hbt.main import create_app
from hbt.stickv.animator import StickmanAnimator, list_available_animations


def _make_png(path: Path, color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (64, 64), color).save(path)


def test_list_available_animations_empty_dirs(tmp_path: Path) -> None:
    res = list_available_animations(tmp_path / "lib", tmp_path / "assets")
    assert res == {"oneshot": [], "loop": []}


def test_animator_three_phases_with_png_sequences(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"

    # Tạo chuỗi PNG cho oneshot (đỏ), loop (xanh dương) và idle_breathe (xanh lá)
    for i in range(6):
        _make_png(
            lib / "stickman" / "animations" / "oneshot" / "shock_jump" / f"{i:03d}.png",
            (220, 30, 30, 255),
        )
    for i in range(4):
        _make_png(
            lib / "stickman" / "animations" / "loop" / "talk_explain" / f"{i:03d}.png",
            (30, 90, 220, 255),
        )
    for i in range(4):
        _make_png(
            lib / "stickman" / "animations" / "loop" / "idle_breathe" / f"{i:03d}.png",
            (30, 180, 90, 255),
        )

    listed = list_available_animations(lib, assets)
    assert "shock_jump" in listed["oneshot"]
    assert "talk_explain" in listed["loop"]
    assert "idle_breathe" in listed["loop"]

    fps = 15
    rms = [0.6] * 45
    anim = StickmanAnimator(
        pose="explain",
        anim_oneshot="shock_jump",
        anim_loop="talk_explain",
        facing="right",
        duration_sec=3.0,
        speech_start=0.0,
        speech_end=2.0,
        fps=fps,
        rms_env=rms,
        library_dir=lib,
        assets_dir=assets,
        target_height=128,
    )
    try:
        # Pha 1: 0.1s -> oneshot
        f1, m1 = anim.frame_at(1, 0.1)
        assert f1 is not None and m1.phase == "oneshot" and not m1.used_fallback
        assert f1.getpixel((10, 10))[0] > 180
        f1.close()

        # Pha 2: 1.2s -> loop
        f2, m2 = anim.frame_at(18, 1.2)
        assert f2 is not None and m2.phase == "loop" and not m2.used_fallback
        assert f2.getpixel((10, 10))[2] > 180
        f2.close()

        # Pha 3: 2.5s (> speech_end) -> idle
        f3, m3 = anim.frame_at(38, 2.5)
        assert f3 is not None and m3.phase == "idle" and not m3.used_fallback
        assert f3.getpixel((10, 10))[1] > 150
        f3.close()
    finally:
        anim.close()


def test_animator_deterministic_png_fallback_with_rms(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_png(assets / "stickman" / "shock.png", (255, 200, 0, 255))

    fps = 15
    # Giây 0..1.5 nói to (rms=0.8), giây 1.5..2.5 im lặng (rms=0.0)
    rms = [0.8] * 23 + [0.0] * 15
    anim = StickmanAnimator(
        pose="explain",
        anim_oneshot="shock_jump",
        anim_loop="talk_explain",
        facing="left",
        duration_sec=2.5,
        speech_start=0.0,
        speech_end=1.5,
        fps=fps,
        rms_env=rms,
        library_dir=lib,
        assets_dir=assets,
        target_height=128,
    )
    try:
        f_talk, m_talk = anim.frame_at(5, 0.35)
        assert f_talk is not None
        assert m_talk.used_fallback is True
        assert m_talk.dy < 0.0
        assert m_talk.scale_y > 1.0
        f_talk.close()

        f_idle, m_idle = anim.frame_at(30, 2.0)
        assert f_idle is not None
        assert m_idle.used_fallback is True
        assert m_idle.phase == "idle"
        assert abs(m_idle.dy) <= 1.3
        f_idle.close()
    finally:
        anim.close()


def test_asset_hub_upload_stickman_animation_slots(tmp_path: Path) -> None:
    settings = Settings(
        workspace_dir=tmp_path / "ws",
        assets_dir=tmp_path / "assets",
        library_dir=tmp_path / "lib",
        whisper_model="small",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings)
    client = TestClient(app)

    res1 = client.post(
        "/api/asset-hub/stickman",
        data={"anim_group": "oneshot"},
        files={"file": ("shock_jump.webm", b"fake-webm-bytes", "video/webm")},
    )
    assert res1.status_code == 201
    item1 = res1.json()["item"]
    assert item1["anim_group"] == "oneshot"
    assert item1["source"] == "library"
    assert (
        settings.library_dir / "stickman" / "animations" / "oneshot" / "shock_jump.webm"
    ).is_file()

    res2 = client.post(
        "/api/asset-hub/stickman",
        data={"anim_group": "loop"},
        files={"file": ("talk_explain.webm", b"fake-webm-loop", "video/webm")},
    )
    assert res2.status_code == 201
    assert res2.json()["item"]["anim_group"] == "loop"
    assert (
        settings.library_dir / "stickman" / "animations" / "loop" / "talk_explain.webm"
    ).is_file()

    listed = client.get("/api/asset-hub/stickman").json()["items"]
    groups = {it["name"]: it["anim_group"] for it in listed}
    assert groups.get("shock_jump.webm") == "oneshot"
    assert groups.get("talk_explain.webm") == "loop"
