"""Kiểm thử API StickV: CRUD, sinh kịch bản Gemini, upload media beat & hàng đợi job."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from hbt.config import Settings
from hbt.main import create_app
from hbt.stickv.models import StickvBeat


def test_stickv_api_crud_generate_and_media_upload(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            workspace_dir=tmp_path / "workspace",
            library_dir=tmp_path / "library",
            assets_dir=tmp_path / "assets",
            whisper_model="small",
            whisper_device="cpu",
            default_fps=50,
        )
    )
    client = TestClient(app)

    # 1. List rỗng + danh sách model Gemini
    r_list = client.get("/api/stickv")
    assert r_list.status_code == 200
    assert r_list.json()["items"] == []
    assert len(r_list.json()["gemini_models"]) >= 1

    # 2. Generate với Gemini mock
    fake_beats = [
        StickvBeat(id="b001", narration="Chào mừng đến với StickV.", pose="explain"),
    ]
    with patch(
        "hbt.api.stickv.generate_stickv_script",
        return_value=("Video Stickman Đầu Tiên", fake_beats, {"chapters": 1}),
    ):
        r_gen = client.post(
            "/api/stickv/generate",
            json={"idea": "Giải thích hiệu ứng cánh bướm", "aspect": "16:9", "theme": "dark"},
        )
    assert r_gen.status_code == 200
    proj = r_gen.json()["project"]
    slug = proj["slug"]
    assert proj["aspect"] == "16:9"
    assert proj["theme"] == "dark"
    assert len(proj["beats"]) == 1

    # 3. Upload clip .mp4 cho beat b001
    r_up = client.post(
        f"/api/stickv/{slug}/beats/b001/media",
        files={"file": ("veo_clip.mp4", b"fake-mp4-data", "video/mp4")},
    )
    assert r_up.status_code == 200
    assert r_up.json()["media_path"].startswith("media/b001_")

    # 4. Enqueue render
    with patch("hbt.stickv.render.render_stickv") as mock_render:
        out_mp4 = tmp_path / "workspace" / "stickv" / slug / "renders" / "preview.mp4"
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(b"mp4")
        mock_render.return_value = {
            "file_path": str(out_mp4),
            "duration_sec": 3.0,
            "size_mb": 0.1,
            "aspect": "16:9",
            "fps": 24,
            "preview": True,
        }
        r_ren = client.post(f"/api/stickv/{slug}/render", json={"preview": True})
        assert r_ren.status_code == 202
        assert "job_id" in r_ren.json()

    # 5. Import JSON (0 Token) & Import Lời thoại (Không cần AI)
    r_imp_json = client.post(
        "/api/stickv/import-json",
        json={"raw_json": '{"title":"Từ Web Gemini","beats":[{"narration":"Xin chào"}]}'},
    )
    assert r_imp_json.status_code == 200
    assert r_imp_json.json()["project"]["title"] == "Từ Web Gemini"

    r_imp_script = client.post(
        "/api/stickv/import-script",
        json={"raw_text": "Câu một.\nCâu hai rất hay."},
    )
    assert r_imp_script.status_code == 200
    assert len(r_imp_script.json()["project"]["beats"]) == 2

    # 6. Xóa dự án
    r_del = client.delete(f"/api/stickv/{slug}")
    assert r_del.status_code == 200


def test_stickv_jobs_api_reports_live_metadata_and_recent_completed(tmp_path: Path) -> None:
    """GET /api/jobs phải trả đủ kind='stickv', slug, mode, stage, progress, beat & recent done."""
    import threading
    import time

    app = create_app(
        Settings(
            workspace_dir=tmp_path / "workspace",
            library_dir=tmp_path / "library",
            assets_dir=tmp_path / "assets",
            whisper_model="small",
            whisper_device="cpu",
            default_fps=30,
        )
    )
    app.state.hbt.jobs._tool_check = None
    client = TestClient(app)

    r_imp = client.post(
        "/api/stickv/import-script",
        json={"title": "Persist Demo", "raw_text": "Câu một.\nCâu hai.\nCâu ba."},
    )
    assert r_imp.status_code == 200
    slug = r_imp.json()["project"]["slug"]

    reached_mid = threading.Event()
    release_gate = threading.Event()
    out_mp4 = tmp_path / "workspace" / "stickv" / slug / "renders" / "final.mp4"

    def fake_render(project, project_dir, **kwargs):
        on_prog = kwargs.get("on_progress")
        if on_prog:
            on_prog(52.0, "Đang dựng cụm 2/3 (Chương 1)...")
        reached_mid.set()
        release_gate.wait(5.0)
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(b"fake-final-mp4")
        return {
            "file_path": str(out_mp4),
            "duration_sec": 6.4,
            "size_mb": 0.4,
            "aspect": project.aspect,
            "fps": 30,
            "preview": False,
        }

    with patch("hbt.stickv.render.render_stickv", side_effect=fake_render):
        r_ren = client.post(f"/api/stickv/{slug}/render", json={"preview": False})
        assert r_ren.status_code == 202
        job_id = r_ren.json()["job_id"]
        assert reached_mid.wait(5.0)

        active_rows = client.get("/api/jobs").json()
        assert len(active_rows) == 1
        row = active_rows[0]
        assert row["id"] == job_id
        assert row["kind"] == "stickv"
        assert row["slug"] == slug
        assert row["mode"] == "final"
        assert row["status"] == "running"
        assert row["progress"] == 52.0
        assert row["stage"] == "Dựng khung hình"
        assert row["current_beat"] == 2
        assert row["total_beats"] == 3
        assert row["started_at"] is not None

        release_gate.set()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if client.get(f"/api/jobs/{job_id}").json()["status"] == "done":
                break
            time.sleep(0.03)

    # Sau khi hoàn tất: GET /api/jobs mặc định rỗng; include_recent=true có bản done & URL đúng
    assert client.get("/api/jobs").json() == []
    recent_rows = client.get("/api/jobs?include_recent=true").json()
    done_row = next((r for r in recent_rows if r["id"] == job_id), None)
    assert done_row is not None
    assert done_row["kind"] == "stickv"
    assert done_row["status"] == "done"
    assert done_row["progress"] == 100.0
    assert done_row["output"]["video"] == f"/api/stickv/{slug}/renders/final.mp4"
