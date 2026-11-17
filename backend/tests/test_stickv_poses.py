"""Kiểm thử khởi tạo 8 dáng người que chuẩn Stickman & Asset Hub category."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from hbt.config import Settings
from hbt.main import create_app
from hbt.stickv.poses_init import DEFAULT_POSES, ensure_default_poses, remove_white_background


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


def test_remove_white_background_preserves_interior_white_and_auto_strips_upload(
    tmp_path: Path,
) -> None:
    # Vẽ ảnh nền trắng (255,255,255) bên ngoài, vòng tròn đen ở giữa chứa màu trắng bên trong
    src = tmp_path / "stick_white_bg.jpg"
    im = Image.new("RGB", (120, 120), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.ellipse((30, 30, 90, 90), fill=(255, 255, 255), outline=(10, 10, 10), width=6)
    im.save(src, format="JPEG", quality=98)
    im.close()

    out_png, removed = remove_white_background(src, tmp_path / "stick_clean.png")
    assert removed is True
    assert out_png.is_file()
    with Image.open(out_png) as res_im:
        assert res_im.mode == "RGBA"
        # Góc ngoài phải trong suốt
        assert res_im.getpixel((2, 2))[3] == 0
        # Tâm đầu bên trong vòng tròn đen vẫn giữ nguyên màu trắng đục
        assert res_im.getpixel((60, 60))[3] == 255

    # Test API upload JPG có nền trắng tự động chuyển thành PNG trong suốt + endpoint remove-bg
    ws = tmp_path / "ws"
    lib = tmp_path / "lib"
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
        )
    )
    client = TestClient(app)
    with src.open("rb") as fh:
        up = client.post(
            "/api/asset-hub/stickman",
            files={"file": ("white_char.jpg", fh, "image/jpeg")},
        )
    assert up.status_code == 201
    item_name = up.json()["item"]["name"]
    assert item_name.endswith(".png")

    r_rm = client.post(f"/api/asset-hub/stickman/{item_name}/remove-bg?source=assets")
    assert r_rm.status_code == 200
    assert r_rm.json()["ok"] is True
