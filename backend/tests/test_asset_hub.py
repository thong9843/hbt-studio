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
    assert client.get("/api/asset-hub/renders").status_code == 422
    assert client.get("/api/asset-hub/watermarks").status_code == 200
    assert client.get("/api/asset-hub/music").status_code == 200
    assert client.get("/api/asset-hub/files/memes/..secret.mp4").status_code == 422
    assert client.delete("/api/asset-hub/backgrounds/missing.mp4").status_code == 404


def test_unified_renders_sync_list_and_delete(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    job_dir = tmp_path / "workspace" / "projects" / "demo-core" / "renders" / "job1"
    job_dir.mkdir(parents=True)
    mp4 = job_dir / "video.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (job_dir / "publish.txt").write_text("Tiêu đề mẫu\n#HayBietTuot", encoding="utf-8")

    res = client.get("/api/renders")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["engine"] == "core"
    assert "Tiêu đề mẫu" in items[0]["publish_text"]

    del_res = client.delete(f"/api/renders/{items[0]['id']}")
    assert del_res.status_code == 200
    assert client.get("/api/renders").json()["items"] == []


def test_asset_hub_scans_library_with_index_json_and_brand_watermark(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    music_dir = tmp_path / "library" / "music"
    music_dir.mkdir(parents=True)
    (music_dir / "track1.mp3").write_bytes(b"ID3fake")
    (music_dir / "index.json").write_text(
        '[{"file": "track1.mp3", "title": "Nhạc kịch tính", "artist": "HBT", "moods": ["drama"]}]',
        encoding="utf-8",
    )

    bg_dir = tmp_path / "library" / "backgrounds"
    thumbs_dir = bg_dir / "thumbs"
    thumbs_dir.mkdir(parents=True)
    (bg_dir / "mc1.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (thumbs_dir / "mc1.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    res_music = client.get("/api/asset-hub/music")
    assert res_music.status_code == 200
    m_items = res_music.json()["items"]
    assert len(m_items) == 1
    assert m_items[0]["title"] == "Nhạc kịch tính"
    assert m_items[0]["artist"] == "HBT"
    assert m_items[0]["moods"] == ["drama"]
    assert client.get(m_items[0]["url"]).status_code == 200

    res_bg = client.get("/api/asset-hub/backgrounds")
    assert res_bg.status_code == 200
    bg_items = res_bg.json()["items"]
    assert len(bg_items) == 1
    assert bg_items[0]["thumb_url"] == "/api/asset-hub/file/library/backgrounds/thumbs/mc1.jpg"
    assert client.get(bg_items[0]["thumb_url"]).status_code == 200

    res_wm = client.get("/api/asset-hub/watermarks")
    assert res_wm.status_code == 200
    assert any(it["name"] == "hbt-logo-mark.png" for it in res_wm.json()["items"])
