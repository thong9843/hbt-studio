"""Kiểm chứng tích hợp thực tế (Real Integration Test): FastAPI + FFmpeg thật xuất MP4 StickV.

Không mock `render_stickv` hay FFmpeg:
1. `POST /api/stickv/{slug}/render` (Xuất bản đẹp `preview=False`).
2. Tiến độ SSE tăng mượt `2% -> 100%`, kết thúc bằng `status == "done"`.
3. Tạo ra tệp `final.mp4` thật trên đĩa, kiểm định qua `ffprobe` đạt `h264`, `yuv420p`, `48000 Hz`.
4. Nếu luồng dựng gặp ngoại lệ (`BaseException`), job luôn chuyển sang `failed` và mở khóa ngay.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hbt.config import Settings
from hbt.main import create_app


@pytest.mark.slow
def test_stickv_real_final_render_produces_valid_mp4_and_sse_progress(tmp_path: Path) -> None:
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
    # Dùng đường sinh WAV PCM chuẩn nội bộ để test tích hợp FFmpeg chạy nhanh < 2.5s trên mọi máy/CI
    app.state.hbt.jobs.voice = None
    client = TestClient(app)

    create_res = client.post(
        "/api/stickv",
        json={
            "title": "Kiểm Chứng Xuất Bản Đẹp StickV",
            "topic": "science",
            "domain": "paper_classic",
            "aspect": "9:16",
            "theme": "cream",
            "beats": [
                {
                    "id": "b01",
                    "chapter": 1,
                    "chapter_title": "Cơ chế thật",
                    "narration": "Não bộ tiêu thụ hai mươi phần trăm năng lượng cơ thể.",
                    "pose": "present_board",
                    "emotion": "curious",
                    "camera_shot": "focus_board",
                    "board_type": "myth_vs_fact",
                    "board_title": "Năng lượng não bộ",
                    "board_items": [
                        "Lầm tưởng: Não nghỉ khi ngủ",
                        "Sự thật: Tiêu thụ **20% ATP** liên tục",
                    ],
                    "duration_sec": 1.2,
                },
                {
                    "id": "b02",
                    "chapter": 1,
                    "chapter_title": "Tổng kết",
                    "narration": "Ngủ đủ giúp hệ thần kinh phục hồi tối ưu.",
                    "pose": "celebrate",
                    "emotion": "excited",
                    "camera_shot": "wide_stage",
                    "board_type": "recap_card",
                    "board_title": "Tóm tắt cốt lõi",
                    "board_items": [
                        "Não dùng **20% năng lượng**",
                        "Ngủ sâu giúp dọn sạch độc tố thần kinh",
                    ],
                    "duration_sec": 1.2,
                },
            ],
        },
    )
    assert create_res.status_code == 201
    proj = create_res.json()["project"]
    slug = proj["slug"]

    # Tắt outro để test tập trung vào luồng stream RGB24 + mix 48kHz + mux MP4 thật
    proj["outro"] = False
    put_res = client.put(f"/api/stickv/{slug}", json=proj)
    assert put_res.status_code == 200

    render_res = client.post(f"/api/stickv/{slug}/render", json={"preview": False})
    assert render_res.status_code == 202
    job_id = render_res.json()["job_id"]
    assert job_id

    # Chờ worker hoàn tất (tối đa 45s)
    job = app.state.hbt.jobs.get(job_id)
    assert job.wait(timeout=45.0), "Job dựng StickV thật bị quá thời gian 45s"

    status_res = client.get(f"/api/jobs/{job_id}")
    assert status_res.status_code == 200
    body = status_res.json()
    assert body["status"] == "done", f"Job thất bại: {body.get('error')}"
    assert body["progress"] == 100.0
    assert body["kind"] == "stickv"
    assert body["mode"] == "final"
    assert body["output"]["video"] == f"/api/stickv/{slug}/renders/final.mp4"

    # Kiểm tra chuỗi sự kiện SSE phát ra từ 2% -> 100%
    events = job.events_since(0)
    progress_vals = [
        float(payload.get("progress", 0.0)) for kind, payload in events if kind == "progress"
    ]
    assert len(progress_vals) >= 4
    assert progress_vals[0] == 2.0
    assert max(progress_vals) >= 85.0
    end_events = [payload for kind, payload in events if kind == "end"]
    assert len(end_events) == 1
    assert end_events[0]["status"] == "done"

    # Kiểm tra file MP4 thật trên đĩa và qua endpoint HTTP
    mp4_path = tmp_path / "workspace" / "stickv" / slug / "renders" / "final.mp4"
    assert mp4_path.is_file()
    assert mp4_path.stat().st_size > 10_000

    dl_res = client.get(body["output"]["video"])
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"].startswith("video/mp4")

    # Kiểm định luồng video + audio bằng ffprobe thật
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    probe_proc = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,pix_fmt,sample_rate,width,height",
            "-of",
            "json",
            str(mp4_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(probe_proc.stdout).get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    assert v_stream is not None
    assert v_stream.get("codec_name") == "h264"
    assert v_stream.get("pix_fmt") == "yuv420p"
    assert int(v_stream.get("width", 0)) == 1080
    assert int(v_stream.get("height", 0)) == 1920
    assert a_stream is not None
    assert a_stream.get("codec_name") == "aac"
    assert int(a_stream.get("sample_rate", 0)) == 48000


def test_stickv_worker_base_exception_always_transitions_to_failed_and_unlocks(
    tmp_path: Path,
) -> None:
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
    client = TestClient(app)

    create_res = client.post(
        "/api/stickv",
        json={
            "title": "Test Lỗi Không Treo Running",
            "beats": [{"id": "b01", "narration": "Câu thử lỗi.", "pose": "explain"}],
        },
    )
    slug = create_res.json()["project"]["slug"]

    class FatalWorkerFault(BaseException):
        pass

    with patch("hbt.stickv.render.render_stickv", side_effect=FatalWorkerFault("Crash tầng C")):
        res = client.post(f"/api/stickv/{slug}/render", json={"preview": False})
        assert res.status_code == 202
        job_id = res.json()["job_id"]
        job = app.state.hbt.jobs.get(job_id)
        assert job.wait(timeout=10.0)

    view = client.get(f"/api/jobs/{job_id}").json()
    assert view["status"] == "failed"
    assert "Crash tầng C" in (view["error"] or "")
    # Đảm bảo cờ khóa dự án đã được giải phóng hoàn toàn, không bị kẹt 409
    time.sleep(0.05)
    assert app.state.hbt.jobs.is_busy(slug) is False
