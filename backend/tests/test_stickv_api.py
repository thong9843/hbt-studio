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

    # 5. Xóa dự án
    r_del = client.delete(f"/api/stickv/{slug}")
    assert r_del.status_code == 200
