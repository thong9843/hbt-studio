"""Kiểm thử khởi tạo 8 dáng người que chuẩn Stickman & Asset Hub category."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from hbt.config import Settings
from hbt.main import create_app
from hbt.stickv.poses_init import DEFAULT_POSES, ensure_default_poses


def test_ensure_default_poses_creates_8_rgba_pngs(tmp_path: Path) -> None:
    poses_dir = tmp_path / "stickman" / "poses"
    created = ensure_default_poses(poses_dir)
    assert len(created) == 8
    assert {p.stem for p in created} == set(DEFAULT_POSES)
    assert (poses_dir / "index.json").is_file()

    for png in created:
        with Image.open(png) as img:
            assert img.mode == "RGBA"
            assert img.size == (512, 640)


def test_asset_hub_stickman_category_lists_and_uploads(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    lib = tmp_path / "library"
    assets = tmp_path / "assets"
    ensure_default_poses(lib / "stickman" / "poses")

    app = create_app(
        Settings(
            workspace_dir=ws,
            library_dir=lib,
            assets_dir=assets,
            whisper_model="small",
            whisper_device="cpu",
            default_fps=50,
        ),
    )
    client = TestClient(app)

    res = client.get("/api/asset-hub/stickman")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 8
    assert any(it["name"] == "explain.png" and it["source"] == "library" for it in items)

    # Kiểm tra import thêm nhân vật PNG (ví dụ từ Google Flow / Imagen)
    custom_png = tmp_path / "custom_pose.png"
    with Image.new("RGBA", (256, 256), (245, 158, 11, 255)) as im:
        im.save(custom_png, format="PNG")

    with custom_png.open("rb") as fh:
        up = client.post(
            "/api/asset-hub/stickman",
            files={"file": ("flow_pose.png", fh, "image/png")},
        )
    assert up.status_code == 201
    res2 = client.get("/api/asset-hub/stickman")
    assert len(res2.json()["items"]) == 9
