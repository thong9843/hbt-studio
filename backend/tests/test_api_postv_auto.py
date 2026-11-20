"""Kiểm thử API Tạo tự động PVA và Dán JSON kịch bản PostV."""

import pytest

from tests.test_api import client  # noqa: F401


@pytest.fixture
def pv_project(client):  # noqa: F811
    r = client.post("/api/projects", json={"title": "Test PVA Auto", "kind": "postv"})
    assert r.status_code == 201
    slug = r.json()["slug"]
    # Điền một ít nội dung nguồn
    project = client.get(f"/api/projects/{slug}").json()
    project["post"]["text"] = "Hôm qua mình bỏ quên ví ở quán cà phê."
    project["comments"] = [
        {"id": "c1", "handle": "ban_a", "text": "Quán ở đâu vậy?", "likes": 10, "picked": True},
        {"id": "c2", "handle": "ban_b", "text": "May mắn quá nha!", "likes": 5, "picked": True},
    ]
    r_put = client.put(f"/api/projects/{slug}", json=project)
    assert r_put.status_code == 200, r_put.text
    return slug


def test_get_postv_styles(client):  # noqa: F811
    r = client.get("/api/postv/styles")
    assert r.status_code == 200
    styles = r.json()
    assert len(styles) == 5
    ids = [s["id"] for s in styles]
    assert "ke-chuyen" in ids
    assert "hai-huoc" in ids


def test_script_json_check_valid(client, pv_project):  # noqa: F811
    body = {
        "postv_script": 1,
        "style": "ke-chuyen",
        "hook": {"text": "Quên ví ở quán", "accent": "quên ví"},
        "segments": [
            {
                "role": "hook",
                "speaker": "narrator",
                "voice": "Quên ví ở quán cà phê.",
                "card": "hook",
            },
            {
                "role": "post",
                "speaker": "post",
                "voice": "Hôm qua mình để quên ví...",
                "card": "post",
            },
            {
                "role": "comment",
                "ref": "c1",
                "speaker": "narrator",
                "voice": "Có người hỏi ngay:",
                "card": "comment",
            },
            {
                "role": "comment",
                "ref": "c1",
                "speaker": "c1",
                "voice": "Quán ở đâu vậy?",
                "card": "comment",
            },
            {"role": "commentary", "speaker": "narrator", "voice": "Bạn thấy sao?", "card": "none"},
        ],
        "cast": {"narrator": "hai-dang"},
        "publish": {"hook": "Chuyện quên ví", "hashtags": ["chuyentute"]},
    }
    r = client.post(f"/api/projects/{pv_project}/postv/script-json/check", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["issues"] == []
    assert data["segments_count"] == 5


def test_script_json_check_invalid_fields(client, pv_project):  # noqa: F811
    # Thiếu postv_script: 1 và có trường lạ
    body = {
        "extra_field": "bị cấm",
        "segments": [
            {"role": "hook", "speaker": "narrator", "voice": "Chào"},
            {"role": "comment", "ref": "c99", "speaker": "ai_do", "voice": "Bình luận"},
        ],
    }
    r = client.post(f"/api/projects/{pv_project}/postv/script-json/check", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert any("postv_script" in s for s in data["issues"])
    assert any("extra_field" in s for s in data["issues"])
    assert any("c99" in s for s in data["issues"])


def test_script_json_apply_and_restore(client, pv_project):  # noqa: F811
    body = {
        "postv_script": 1,
        "hook": {"text": "Áp dụng mới", "accent": ""},
        "segments": [
            {"role": "hook", "speaker": "narrator", "voice": "Hook mới", "card": "hook"},
            {"role": "post", "speaker": "post", "voice": "Post mới", "card": "post"},
            {
                "role": "comment",
                "ref": "c1",
                "speaker": "c1",
                "voice": "Bình luận mới",
                "card": "comment",
            },
        ],
    }
    # 1. Áp dụng JSON
    r = client.post(f"/api/projects/{pv_project}/postv/script-json/apply", json=body)
    assert r.status_code == 200
    res = r.json()
    assert res["ok"] is True
    backup_id = res["backup_id"]
    assert backup_id

    # Đã cập nhật vào project
    p = client.get(f"/api/projects/{pv_project}").json()
    assert p["hook"]["text"] == "Áp dụng mới"
    assert len(p["segments"]) == 3

    # 2. Xem danh sách sao lưu
    b_res = client.get(f"/api/projects/{pv_project}/postv/backups")
    assert b_res.status_code == 200
    backups = b_res.json()
    assert len(backups) >= 1
    assert backups[0]["id"] == backup_id

    # 3. Khôi phục bản sao lưu
    rst = client.post(f"/api/projects/{pv_project}/postv/backups/{backup_id}/restore")
    assert rst.status_code == 200
    p_restored = client.get(f"/api/projects/{pv_project}").json()
    assert p_restored["hook"]["text"] == ""  # Giá trị trước khi áp


def test_postv_auto_job_stops_at_phase_6_when_vieneu_unavailable(client, pv_project):  # noqa: F811
    import time

    r = client.post(
        f"/api/projects/{pv_project}/postv/auto",
        json={"style": "ke-chuyen", "comments": 2, "seed": 99},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert job_id

    # Đợi job hoàn thành hoặc dừng lại ở pha 6
    job = {}
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)

    # Nếu máy không có VieNeu thật (như CI): job kết thúc FAILED ở pha 6
    # Nhưng các pha 1–5 đã hoàn tất và kịch bản đã được lưu vào project
    p = client.get(f"/api/projects/{pv_project}").json()
    assert len(p["segments"]) >= 4  # Kịch bản pha 2-3 đã được lưu
    assert p["auto"]["style"] == "ke-chuyen"
    assert p["auto"]["seed"] == 99
