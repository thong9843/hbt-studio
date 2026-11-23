"""Tests cho API Chatting (/api/chatting/...) (CH1)."""

import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hbt.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("CHATTING_FAKE_LLM", "1")
    app = create_app()
    return TestClient(app)


def test_get_chatting_status(client):
    res = client.get("/api/chatting/status")
    assert res.status_code == 200
    data = res.json()
    assert "gemini_configured" in data
    assert "stickers" in data
    assert isinstance(data["stickers"], dict)


def test_create_threads_link_accepted(client):
    res = client.post(
        "/api/chatting",
        json={
            "input": "https://www.threads.net/@user/post/C12345",
            "platform": "messenger",
        },
    )
    assert res.status_code == 200
    assert "slug" in res.json()
    assert "job_id" in res.json()


def test_create_and_manage_chatting_project(client):
    # 1. Tạo dự án với dán chữ
    create_res = client.post(
        "/api/chatting",
        json={
            "input": "Người yêu cũ nhắn tin lúc 2h sáng\nEm còn nhớ anh không?",
            "platform": "messenger",
            "background": "minecraft4-1080p60",
        },
    )
    assert create_res.status_code == 200
    res_data = create_res.json()
    slug = res_data["slug"]
    job_id = res_data["job_id"]
    assert slug
    assert job_id

    # 2. Đọc dự án (đợi job hoàn tất tạo file chat.json)
    get_res = None
    for _ in range(50):
        get_res = client.get(f"/api/chatting/{slug}")
        if get_res.status_code == 200 and get_res.json().get("doc") is not None:
            break
        time.sleep(0.1)
    assert get_res is not None and get_res.status_code == 200
    project_data = get_res.json()
    assert project_data["slug"] == slug
    assert "doc" in project_data

    # 3. Liệt kê dự án
    list_res = client.get("/api/chatting/projects")
    assert list_res.status_code == 200
    projects = list_res.json()
    assert any(p["slug"] == slug for p in projects)

    # 4. Tải avatar
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    avatar_res = client.post(
        f"/api/chatting/{slug}/avatar/me",
        files={"file": ("avatar.png", buf, "image/png")},
    )
    assert avatar_res.status_code == 200
    assert avatar_res.json()["ok"] is True
    assert "avatars/me.png" in avatar_res.json()["avatar"]

    # 5. Xoá dự án (đợi job chạy xong để nhả file lock)
    for _ in range(50):
        job = client.app.state.hbt.jobs.get(job_id)
        if job.finished:
            break
        time.sleep(0.1)

    del_res = client.delete(f"/api/chatting/{slug}")
    assert del_res.status_code == 200

    # Kiểm tra đã xoá
    get_after_del = client.get(f"/api/chatting/{slug}")
    assert get_after_del.status_code == 404


def test_reroll_asset_endpoint_updates_message_and_avoids_duplicates(tmp_path, monkeypatch):
    import json

    from hbt.chatting.models import Character, ChatDoc, Message
    from hbt.chatting.store import save_chat

    ws = tmp_path / "workspace"
    lib = tmp_path / "library"
    (lib / "memes").mkdir(parents=True)
    (lib / "memes" / "m1.mp4").write_bytes(b"mp4-1")
    (lib / "memes" / "m2.mp4").write_bytes(b"mp4-2")
    (lib / "memes" / "index.json").write_text(
        json.dumps(
            [
                {"id": "m1", "file": "m1.mp4", "title": "Cat Shocked 1", "tags": ["shock", "cat"]},
                {"id": "m2", "file": "m2.mp4", "title": "Cat Shocked 2", "tags": ["shock", "cat"]},
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("LIBRARY_DIR", str(lib))
    monkeypatch.setenv("CHATTING_FAKE_LLM", "1")
    app = create_app()
    c = TestClient(app)

    slug = "chat-reroll-test"
    doc = ChatDoc(
        title="Test Reroll",
        auto_fetch_online=False,
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Nam", side="left"),
        ],
        messages=[
            Message(
                from_="me" if i % 2 == 0 else "a",
                text=f"Tin nhắn {i}",
                sticker="soc" if i == 4 else None,
                meme_id="m1" if i == 4 else None,
                meme_query="cat shocked" if i == 4 else None,
                intensity=5 if i == 4 else 2,
            )
            for i in range(8)
        ],
    )
    save_chat(ws, slug, doc)

    res = c.post(
        f"/api/chatting/{slug}/messages/4/reroll-asset",
        json={"kind": "meme", "auto_fetch_online": False},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert payload["message"]["meme_id"] == "m2"
    assert payload["doc"]["messages"][4]["meme_id"] == "m2"
