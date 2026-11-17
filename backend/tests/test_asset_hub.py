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


def test_unified_renders_lists_all_four_engines(tmp_path: Path) -> None:
    import json

    client = _make_client(tmp_path)

    # 1. Core
    core_dir = tmp_path / "workspace" / "projects" / "demo-core" / "renders" / "j1"
    core_dir.mkdir(parents=True)
    (core_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    (core_dir / "cover_9x16.jpg").write_bytes(b"\xff\xd8\xff\xe0cover")
    (core_dir / "meta.json").write_text(json.dumps({"duration": 31.2}), encoding="utf-8")

    # 2. Chatting
    chat_dir = tmp_path / "workspace" / "chatting" / "chat-1" / "renders"
    chat_dir.mkdir(parents=True)
    (chat_dir / "render_1.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

    # 3. StickV
    sv_dir = tmp_path / "workspace" / "stickv" / "sv-1" / "renders"
    sv_dir.mkdir(parents=True)
    (sv_dir / "final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

    # 4. PostV in assets/renders
    pv_dir = tmp_path / "assets" / "renders" / "postv" / "pv-1"
    pv_dir.mkdir(parents=True)
    (pv_dir / "video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

    res = client.get("/api/renders")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 4
    assert {it["engine"] for it in items} == {"core", "postv", "chatting", "stickv"}
    core_it = next(it for it in items if it["engine"] == "core")
    assert core_it["duration_sec"] == 31.2
    assert core_it["size_bytes"] > 0
    assert core_it["thumb_url"] == core_it["cover_url"]
    assert core_it["thumb_url"] is not None

    media_res = client.get(core_it["video_url"])
    assert media_res.status_code == 200
    assert media_res.content.startswith(b"\x00\x00\x00\x18ftypmp42")


def test_stickman_upload_priority_no_overwrite_and_pose_endpoint(tmp_path: Path) -> None:
    from PIL import Image

    from hbt.stickv.poses_init import ensure_default_poses

    client = _make_client(tmp_path)
    custom_png = tmp_path / "shock.png"
    with Image.new("RGBA", (64, 64), (255, 0, 0, 255)) as im:
        im.save(custom_png, format="PNG")
    custom_bytes = custom_png.read_bytes()

    with custom_png.open("rb") as fh:
        up = client.post(
            "/api/asset-hub/stickman",
            files={"file": ("shock.png", fh, "image/png")},
        )
    assert up.status_code == 201

    # Khởi tạo lại bộ mặc định không được ghi đè file người dùng
    ensure_default_poses(tmp_path / "library" / "stickman" / "poses")
    r_pose = client.get("/api/stickv/poses/shock")
    assert r_pose.status_code == 200
    assert r_pose.content == custom_bytes

    # Đặt làm mặc định cho tất cả dáng chưa có file riêng
    r_def = client.post("/api/asset-hub/stickman/shock.png/set-default")
    assert r_def.status_code == 200
    r_think = client.get("/api/stickv/poses/think")
    assert r_think.status_code == 200
    assert r_think.content == custom_bytes

    # Kiểm tra ensure_default_poses không tạo đè khi đã có file {pose}.* của người dùng
    flow_dir = tmp_path / "flow_poses"
    flow_dir.mkdir()
    flow_file = flow_dir / "explain.png_Same_stickman_mascot_123.png"
    flow_file.write_bytes(custom_bytes)
    ensured = ensure_default_poses(flow_dir)
    assert any(p.name == flow_file.name for p in ensured)
    assert not (flow_dir / "explain.png").exists()


def test_stickman_video_pose_upload_and_list(tmp_path: Path) -> None:
    from unittest.mock import patch

    client = _make_client(tmp_path)
    fake_thumb = tmp_path / "thumb.jpg"
    fake_thumb.write_bytes(b"\xff\xd8\xff\xe0fake-jpg")

    with patch(
        "hbt.api.asset_hub._probe_and_thumb_video_pose",
        return_value=(4.0, 1080, 1920, fake_thumb),
    ):
        up = client.post(
            "/api/asset-hub/stickman",
            files={"file": ("flow_dance.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")},
        )
        assert up.status_code == 201
        item = up.json()["item"]
        assert item["media_type"] == "video"
        assert item["duration_sec"] == 4.0
        assert item["thumb_url"]

        listed = client.get("/api/asset-hub/stickman").json()["items"]
        vid_items = [x for x in listed if x["name"] == "flow_dance.mp4"]
        assert len(vid_items) == 1
        assert vid_items[0]["media_type"] == "video"
        assert vid_items[0]["file_url"].endswith("flow_dance.mp4")


def test_tuna_sfx_search_fallback_and_import(tmp_path: Path) -> None:
    import asyncio
    from unittest.mock import patch

    import httpx

    from hbt.shared.online_sources.tuna_sfx import import_tuna_sfx, search_tuna_sfx

    # 1. Mock API thành công
    def ok_handler(request: httpx.Request) -> httpx.Response:
        if "api.tuna.voicemod.net" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "boom1",
                            "name": "Vine Boom",
                            "duration": 1500,
                            "mp3Path": "https://cdn.voicemod.net/boom.mp3",
                            "tags": ["meme", "boom"],
                        }
                    ]
                },
            )
        return httpx.Response(200, content=b"ID3fake-mp3-bytes")

    async def _run_ok():
        async with httpx.AsyncClient(transport=httpx.MockTransport(ok_handler)) as c:
            items = await search_tuna_sfx("vine boom", client=c)
            assert len(items) == 1
            assert items[0]["title"] == "Vine Boom"
            assert items[0]["duration_sec"] == 1.5

            with patch(
                "hbt.shared.online_sources.tuna_sfx.run_ffmpeg", side_effect=RuntimeError("skip")
            ):
                res = await import_tuna_sfx(
                    item_id="boom1",
                    title="Vine Boom",
                    preview_url=items[0]["preview_url"],
                    tags=items[0]["tags"],
                    library_dir=tmp_path / "library",
                    client=c,
                )
            assert res["ok"] is True
            assert Path(res["file_path"]).is_file()
            assert (tmp_path / "library" / "sfx" / "index.json").is_file()

    asyncio.run(_run_ok())

    # 2. Fallback an toàn khi 502 / Timeout
    def err_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    async def _run_err():
        async with httpx.AsyncClient(transport=httpx.MockTransport(err_handler)) as c:
            items = await search_tuna_sfx("bruh", client=c)
            assert items == []

    asyncio.run(_run_err())

    # 3. Kiểm tra endpoint /api/asset-hub/online/search mặc định tuna cho sfx + TTL Cache
    client = _make_client(tmp_path)
    calls = {"n": 0}

    async def fake_search(q: str = "meme", **kwargs):
        calls["n"] += 1
        return [
            {
                "id": "t1",
                "title": "Bruh Sound",
                "duration_sec": 1.1,
                "preview_url": "https://cdn.voicemod.net/bruh.mp3",
                "source": "tuna",
                "tags": ["meme"],
            }
        ]

    with patch("hbt.api.asset_hub.search_tuna_sfx", side_effect=fake_search):
        r1 = client.get("/api/asset-hub/online/search?category=sfx&q=bruh-cache-test")
        assert r1.status_code == 200
        assert r1.json()["source"] == "tuna"
        assert r1.json()["cached"] is False
        r2 = client.get("/api/asset-hub/online/search?category=sfx&q=bruh-cache-test")
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert calls["n"] == 1


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
