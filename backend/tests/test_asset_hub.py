"""Kiểm thử API Asset Hub (stickers, memes, backgrounds, renders)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from hbt.config import Settings
from hbt.main import create_app


def _make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        workspace_dir=tmp_path / "workspace",
        library_dir=tmp_path / "library",
        whisper_model="auto",
        whisper_device="cpu",
        default_fps=50,
        models_dir=tmp_path / "models",
        assets_dir=tmp_path / "assets",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_asset_hub_upload_list_serve_and_delete(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # Ban đầu danh sách rỗng và tự tạo thư mục
    res = client.get("/api/asset-hub/stickers")
    assert res.status_code == 200
    assert res.json() == {"category": "stickers", "items": []}
    assert (tmp_path / "assets" / "stickers").is_dir()

    # Tải lên một sticker PNG
    up = client.post(
        "/api/asset-hub/stickers",
        files={"file": ("shock_face.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert up.status_code == 201
    item = up.json()["item"]
    assert item["name"] == "shock_face.png"
    assert item["kind"] == "image"
    assert item["url"] == "/api/asset-hub/files/stickers/shock_face.png"

    # Liệt kê lại
    listed = client.get("/api/asset-hub/stickers").json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["name"] == "shock_face.png"

    # Truy cập trực tiếp file
    served = client.get(item["url"])
    assert served.status_code == 200
    assert served.content.startswith(b"\x89PNG")

    # Xoá file
    deleted = client.delete("/api/asset-hub/stickers/shock_face.png")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == "shock_face.png"
    assert client.get("/api/asset-hub/stickers").json()["items"] == []


def test_asset_hub_rejects_invalid_category_and_traversal(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    assert client.get("/api/asset-hub/unknown").status_code == 422
    assert client.get("/api/asset-hub/files/memes/..secret.mp4").status_code == 422
    assert client.delete("/api/asset-hub/backgrounds/missing.mp4").status_code == 404
