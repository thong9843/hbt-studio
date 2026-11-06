"""Tests cho chuỗi tự động PostV (PV9)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hbt.main import app
from hbt.pipeline.cancel import CancelToken, RenderCancelled
from hbt.pipeline.render import RenderResult
from hbt.postv.auto import (
    STAGE_FETCH,
    STAGE_PICK,
    STAGE_SCRIPT,
    STAGE_VOICE,
    STAGE_RENDER,
    STAGE_DONE,
    find_existing_url,
    get_hook_text,
    run_auto_job,
)
from hbt.postv.models import PostvComment, PostvPost, PostvProject, PostvSegment
from hbt.postv.parse import ParsedComment, ParsedPost, ParseResult
from hbt.postv.threads import ThreadsFetchError


@pytest.fixture
def client(tmp_path: Path):
    from hbt.config import Settings
    from hbt.main import create_app

    brand = tmp_path / "brand"
    brand.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        workspace_dir=tmp_path / "workspace",
        library_dir=tmp_path / "library",
        whisper_model="small",
        whisper_device="cpu",
        default_fps=60,
    )
    app = create_app(settings, brand_dir=brand)
    with TestClient(app) as c:
        c.tmp = tmp_path
        yield c


def test_hook_text_extractor():
    text = "Đây là câu mở đầu rất cuốn hút! Tiếp theo là nội dung dài dòng hơn nhiều."
    hook = get_hook_text(text, max_len=160)
    assert hook == "Đây là câu mở đầu rất cuốn hút!"

    long_sentence = "Từ " * 100
    hook_long = get_hook_text(long_sentence, max_len=40)
    assert len(hook_long) <= 40


def test_find_existing_url(tmp_path: Path):
    from hbt.storage import Storage

    storage = Storage(tmp_path / "workspace")
    # Dự án chưa có
    assert find_existing_url(storage, "https://www.threads.net/@user/post/123") is None

    # Tạo dự án PostV có url
    p = PostvProject(version=1, kind="postv", slug="bai-1", title="Bài 1")
    p.source.url = "https://www.threads.net/@user/post/123"
    storage.save_any("bai-1", p)

    found = find_existing_url(storage, "https://www.threads.net/@user/post/123")
    assert found == "bai-1"


def test_postv_auto_api_validation(client: TestClient):
    # Rỗng
    resp = client.post("/api/postv/auto", json={"url": "   "})
    assert resp.status_code == 422
    assert "Gợi ý: Dán chữ bài vào khung" in resp.json()["detail"]


def test_postv_auto_api_existing_url(client: TestClient):
    storage = client.app.state.hbt.storage
    p = storage.create_postv("Bài cũ")
    url = "https://www.threads.net/@testuser/post/abcxyz"
    p.source.url = url
    storage.save_any(p.slug, p)

    # Gọi /api/postv/auto không force_new
    res = client.post("/api/postv/auto", json={"url": url, "force_new": False})
    assert res.status_code == 200
    data = res.json()
    assert data["existing_slug"] == p.slug
    assert data["job_id"] is None

    # Gọi với force_new=True
    with patch("hbt.jobs.JobManager.submit_postv_quick") as mock_submit:
        mock_job = MagicMock()
        mock_job.id = "job-new-123"
        mock_submit.return_value = mock_job

        res2 = client.post("/api/postv/auto", json={"url": url, "force_new": True})
        assert res2.status_code == 200
        assert res2.json()["existing_slug"] is None
        assert res2.json()["job_id"] == "job-new-123"


def test_postv_auto_retry_api(client: TestClient):
    # Retry job không tồn tại -> 404
    res = client.post("/api/postv/auto/non-exist/retry")
    assert res.status_code == 404

    # Tạo 1 job thất bại
    jm = client.app.state.hbt.jobs
    storage = client.app.state.hbt.storage
    proj = storage.create_postv("Bài Thử Lại")
    job = jm.submit_postv_quick(proj.slug, "Chữ test", start_stage="voice")
    job.last_stage = "voice"
    job._finish("failed", error="Voice unavailable")

    res = client.post(f"/api/postv/auto/{job.id}/retry")
    assert res.status_code == 200
    data = res.json()
    assert data["project_slug"] == proj.slug
    assert data["resumed_stage"] == "voice"
    assert data["job_id"] != job.id


def test_run_auto_job_full_stages(tmp_path: Path):
    from hbt.jobs import Job, JobManager
    from hbt.storage import Storage

    storage = Storage(tmp_path / "workspace")
    lib_dir = tmp_path / "library"
    lib_dir.mkdir(parents=True, exist_ok=True)
    jm = JobManager(storage, lib_dir)

    # Tạo dự án
    slug = "test-auto-run"
    proj = PostvProject(version=1, kind="postv", slug=slug, title="Auto Run")
    storage.save_any(slug, proj)

    job = Job("job1", slug, False, 60, True, False, kind="postv_quick")
    job.auto_input = "https://www.threads.net/@thong/post/999"
    job.auto_options = {"target_seconds": 60, "max_comments": 3}
    job.start_stage = STAGE_FETCH

    parsed_post = ParsedPost(
        handle="thong",
        age="2h",
        text="Đây là bài viết đầy cảm hứng. Cuộc sống luôn có những bất ngờ.",
    )
    comments = [
        ParsedComment(
            id="c1", handle="b1", age="1h", text="Bình luận số một rất dài.", picked=False
        ),
        ParsedComment(id="c2", handle="b2", age="1h", text="Bình luận số hai.", picked=False),
        ParsedComment(id="c3", handle="b3", age="1h", text="Bình luận số ba ngắn.", picked=False),
    ]
    parse_res = ParseResult(guess="threads_text", post=parsed_post, comments=comments)

    render_result = RenderResult(
        job_dir=tmp_path,
        video=tmp_path / "output.mp4",
        srt=None,
        publish=tmp_path / "publish.txt",
        log=tmp_path / "log.txt",
        cover=tmp_path / "cover.jpg",
        youtube_cover=tmp_path / "youtube.jpg",
        fps=60,
        width=1080,
        height=1920,
        duration=62.5,
        lufs=-14.0,
        aligner="silence",
        seconds=10.0,
    )

    with (
        patch("hbt.postv.auto.extract_threads_post", return_value=parse_res),
        patch("hbt.postv.auto.build_plan", return_value=([], {})),
        patch("hbt.postv.auto.synthesize_plan"),
        patch.object(jm, "_render_postv", return_value=render_result),
    ):
        fake_voice = MagicMock()
        fake_voice.status.return_value = MagicMock(ok=True)
        fake_voice.list_voices.return_value = []
        jm.voice = fake_voice

        run_auto_job(jm, job)

    assert job.status == "done"
    assert job.output is not None
    assert job.output["duration"] == 62.5

    # Kiểm tra các sự kiện SSE đã phát
    events = [ev[1] for ev in job._events if ev[0] == "progress"]
    stages_fired = [e.get("stage") for e in events]
    assert STAGE_FETCH in stages_fired
    assert STAGE_PICK in stages_fired
    assert STAGE_SCRIPT in stages_fired
    assert STAGE_VOICE in stages_fired
    assert STAGE_RENDER in stages_fired
    assert STAGE_DONE in stages_fired


def test_run_auto_job_fetch_error_handling(tmp_path: Path):
    from hbt.jobs import Job, JobManager
    from hbt.storage import Storage

    storage = Storage(tmp_path / "workspace")
    lib_dir = tmp_path / "library"
    lib_dir.mkdir(parents=True, exist_ok=True)
    jm = JobManager(storage, lib_dir)

    slug = "test-fetch-err"
    proj = PostvProject(version=1, kind="postv", slug=slug, title="Fetch Err")
    storage.save_any(slug, proj)

    job = Job("job2", slug, False, 60, True, False, kind="postv_quick")
    job.auto_input = "https://www.threads.net/@nonuser/post/404"
    job.start_stage = STAGE_FETCH

    with patch(
        "hbt.postv.auto.extract_threads_post",
        side_effect=ThreadsFetchError("Bài viết Threads không tồn tại (HTTP 404)."),
    ):
        run_auto_job(jm, job)

    assert job.status == "failed"
    assert "404" in job.error
    assert "Dán chữ bài vào khung" in job.error


def test_run_auto_job_raw_text_input(tmp_path: Path):
    from hbt.jobs import Job, JobManager
    from hbt.storage import Storage

    storage = Storage(tmp_path / "workspace")
    lib_dir = tmp_path / "library"
    lib_dir.mkdir(parents=True, exist_ok=True)
    jm = JobManager(storage, lib_dir)

    slug = "test-raw-text"
    proj = PostvProject(version=1, kind="postv", slug=slug, title="Raw Text")
    storage.save_any(slug, proj)

    raw_text = """user1
1h
Bài viết chia sẻ kinh nghiệm làm video ngắn cực hay.

user2
30m
Hay quá bạn ơi!

user3
10m
Đồng ý kiến."""

    job = Job("job3", slug, False, 60, True, False, kind="postv_quick")
    job.auto_input = raw_text
    job.auto_options = {"target_seconds": 60}
    job.start_stage = STAGE_FETCH

    render_result = RenderResult(
        job_dir=tmp_path,
        video=tmp_path / "out.mp4",
        srt=None,
        publish=tmp_path / "pub.txt",
        log=tmp_path / "log.txt",
        fps=60,
        width=1080,
        height=1920,
        duration=45.0,
        lufs=-14.0,
        aligner="silence",
        seconds=5.0,
    )

    with (
        patch("hbt.postv.auto.build_plan", return_value=([], {})),
        patch("hbt.postv.auto.synthesize_plan"),
        patch.object(jm, "_render_postv", return_value=render_result),
    ):
        fake_voice = MagicMock()
        fake_voice.status.return_value = MagicMock(ok=True)
        fake_voice.list_voices.return_value = []
        jm.voice = fake_voice

        run_auto_job(jm, job)

    assert job.status == "done"
    saved = storage.load_any(slug)
    assert saved.post.text != ""


def test_run_auto_job_cancel(tmp_path: Path):
    from hbt.jobs import Job, JobManager
    from hbt.storage import Storage

    storage = Storage(tmp_path / "workspace")
    lib_dir = tmp_path / "library"
    lib_dir.mkdir(parents=True, exist_ok=True)
    jm = JobManager(storage, lib_dir)

    slug = "test-cancel"
    proj = PostvProject(version=1, kind="postv", slug=slug, title="Cancel Test")
    storage.save_any(slug, proj)

    job = Job("job4", slug, False, 60, True, False, kind="postv_quick")
    job.auto_input = "Một bài viết ngắn"
    job.start_stage = STAGE_FETCH

    # Huỷ ngay từ đầu
    job.token.cancel()
    run_auto_job(jm, job)

    assert job.status == "cancelled"
