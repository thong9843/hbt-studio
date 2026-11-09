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
    assert "ollama_running" in data
    assert "stickers" in data
    assert isinstance(data["stickers"], dict)


def test_create_threads_link_returns_422(client):
    res = client.post(
        "/api/chatting",
        json={
            "input": "https://www.threads.net/@user/post/C12345",
            "platform": "messenger",
        },
    )
    assert res.status_code == 422
    assert "Chưa lấy được bài Threads, dán nội dung vào ô chat" in res.json()["detail"]


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
        if get_res.status_code == 200:
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

    # 5. Xoá dự án
    del_res = client.delete(f"/api/chatting/{slug}")
    assert del_res.status_code == 200

    # Kiểm tra đã xoá
    get_after_del = client.get(f"/api/chatting/{slug}")
    assert get_after_del.status_code == 404
