"""Tests cho chuỗi tự động PostV (PV9)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hbt.pipeline.render import RenderResult
from hbt.postv.auto import (
    STAGE_DONE,
    STAGE_FETCH,
    STAGE_PICK,
    STAGE_RENDER,
    STAGE_SCRIPT,
    STAGE_VOICE,
    find_existing_url,
    get_hook_text,
    run_auto_job,
)
from hbt.postv.models import PostvComment, PostvProject
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


def test_filter_comments_rules():
    import re

    from hbt.postv.auto import _filter_comments
    from hbt.postv.censor import CensorMatcher

    censor = [CensorMatcher(word="từcấm", category="block", pattern=re.compile(r"từcấm"))]

    raw_comments = [
        PostvComment(id="c1", handle="u1", text="Ngắn", age="1h"),
        PostvComment(id="c2", handle="u2", text="😂😂😂 !!! ???", age="1h"),
        PostvComment(
            id="c3",
            handle="u3",
            text="Bình luận này hợp lệ và có độ dài đủ chuẩn.",
            age="1h",
            likes=50,
        ),
        PostvComment(
            id="c4",
            handle="u4",
            text="Bình luận này hợp lệ và có độ dài đủ chuẩn.",
            age="1h",
            likes=20,
        ),
        PostvComment(id="c5", handle="u5", text="Nội dung có chứa từcấm này nhé bạn ơi.", age="1h"),
        PostvComment(
            id="c6",
            handle="u6",
            text="Một bình luận khác cũng rất hay và ý nghĩa.",
            age="1h",
            likes=100,
        ),
    ]

    filtered = _filter_comments(raw_comments, censor)
    assert len(filtered) == 2
    assert filtered[0].id == "c3"
    assert filtered[1].id == "c6"


def test_step_script_starts_with_post_without_hook():
    from hbt.jobs import Job
    from hbt.postv.auto import _step_script

    slug = "test-no-hook"
    proj = PostvProject(version=1, kind="postv", slug=slug, title="No Hook")
    proj.post.text = "Bài viết mở đầu bằng nội dung chính luôn. Không có hook thừa."
    proj.comments = [
        PostvComment(
            id="c1", handle="u1", text="Bình luận đầu tiên đủ dài và chuẩn.", age="1h", picked=True
        )
    ]

    jm = MagicMock()
    jm.storage.load_any.return_value = proj
    jm.voice = None

    job = Job("job5", slug, False, 60, True, False, kind="postv_quick")

    _step_script(jm, job, {}, MagicMock())

    saved = proj
    assert saved.hook.text == ""
    assert len(saved.segments) == 2
    assert saved.segments[0].role == "post"
    assert saved.segments[0].card == "post"
    assert saved.segments[0].voice == proj.post.text
    assert saved.segments[1].role == "comment"
    assert saved.segments[1].card == "comment"


def test_step_pick_accumulates_to_target_seconds():
    from hbt.jobs import Job
    from hbt.postv.auto import _step_pick

    comment_text = (
        "Đây là một bình luận rất chi tiết và sâu sắc có độ dài tương đương "
        "mười giây đọc để kiểm thử khả năng tích luỹ thời lượng tự động của hệ thống."
    )
    slug = "test-target-duration"

    post_text = (
        "Bài viết mở đầu có độ dài tương đương mười giây đọc "
        "để làm mốc tính thời lượng ban đầu của kịch bản video."
    )

    comments = [
        PostvComment(
            id=f"c{i}",
            handle=f"u{i}",
            text=f"{comment_text} (ý kiến {i})",
            age="1h",
            likes=100 - i,
        )
        for i in range(1, 10)
    ]

    from hbt.postv.timeline import compute_time_budget

    # Target 30s: Post (~8.2s) + comments (~11s mỗi cmt theo 3.2 từ/s + 0.4s) -> đạt >= 30s
    proj30 = PostvProject(version=1, kind="postv", slug=slug, title="Duration 30")
    proj30.post.text = post_text
    proj30.comments = [c.model_copy() for c in comments]

    jm = MagicMock()
    jm.storage.load_any.return_value = proj30
    jm.library_dir = None
    job30 = Job("job-30", slug, False, 60, True, False, kind="postv_quick")

    _step_pick(jm, job30, {"target_seconds": 30}, MagicMock())
    picked30 = [c for c in proj30.comments if c.picked]
    assert len(picked30) >= 2
    assert compute_time_budget(post_text, picked30, [], 30).total_seconds >= 30

    # Target 60s: gom thêm bình luận cho tới khi >= 60s
    proj60 = PostvProject(version=1, kind="postv", slug=slug, title="Duration 60")
    proj60.post.text = post_text
    proj60.comments = [c.model_copy() for c in comments]
    jm.storage.load_any.return_value = proj60
    job60 = Job("job-60", slug, False, 60, True, False, kind="postv_quick")

    _step_pick(jm, job60, {"target_seconds": 60}, MagicMock())
    picked60 = [c for c in proj60.comments if c.picked]
    assert len(picked60) > len(picked30)
    assert compute_time_budget(post_text, picked60, [], 60).total_seconds >= 60


def test_inspect_comment_filter_and_min_length_constant():
    import re

    from hbt.postv.auto import MIN_COMMENT_LENGTH, inspect_comment_filter
    from hbt.postv.censor import CensorMatcher

    assert MIN_COMMENT_LENGTH == 8

    censor = [CensorMatcher(word="từcấm", category="block", pattern=re.compile(r"từcấm"))]
    seen = set()

    # < 8 ký tự -> "ngắn"
    c_short = PostvComment(id="c1", handle="u1", text="Ngắn", age="1h")
    assert inspect_comment_filter(c_short, seen, censor) == "ngắn"

    # Chỉ emoji / ký hiệu -> "ngắn"
    c_emoji = PostvComment(id="c2", handle="u2", text="😂😂😂 !!! ???", age="1h")
    assert inspect_comment_filter(c_emoji, seen, censor) == "ngắn"

    # Bình luận hợp lệ >= 8 ký tự
    c_valid = PostvComment(id="c3", handle="u3", text="Bình luận này hợp lệ đủ chuẩn.", age="1h")
    assert inspect_comment_filter(c_valid, seen, censor) is None

    # Trùng lặp
    c_dup = PostvComment(id="c4", handle="u4", text="Bình luận này hợp lệ đủ chuẩn.", age="1h")
    assert inspect_comment_filter(c_dup, seen, censor) == "trùng"

    # Chứa từ nhạy cảm
    c_bad = PostvComment(id="c5", handle="u5", text="Có chứa từcấm ở đây nha bạn.", age="1h")
    assert inspect_comment_filter(c_bad, seen, censor) == "từ nhạy cảm"


def test_step_pick_manual_mode_pauses_and_sets_waiting_pick():
    import threading

    from hbt.jobs import Job
    from hbt.postv.auto import _step_pick

    slug = "test-manual-pick"
    proj = PostvProject(version=1, kind="postv", slug=slug, title="Manual Pick")
    proj.post.text = "Bài viết gốc của tác giả có nội dung đầy đủ."
    proj.comments = [
        PostvComment(
            id="c1", handle="u1", text="Bình luận 1 rất chất lượng và dài vừa đủ.", age="1h"
        ),
        PostvComment(id="c2", handle="u2", text="Ngắn", age="1h"),
    ]

    jm = MagicMock()
    jm.storage.load_any.return_value = proj
    job = Job("job-manual", slug, False, 60, True, False, kind="postv_quick")

    checked_waiting = False

    def fake_wait(self, timeout=None):
        nonlocal checked_waiting
        assert job.status == "waiting_pick"
        assert hasattr(job, "_pick_event")
        checked_waiting = True
        return True

    with (
        patch.object(threading.Event, "wait", fake_wait),
        patch("hbt.postv.auto.emit_stage_event") as emit_mock,
    ):
        _step_pick(jm, job, {"pick_mode": "manual", "target_seconds": 60}, MagicMock())

    assert checked_waiting is True
    assert job.status == "running"
    # Kiểm tra event waiting_pick đã được emit
    waiting_emits = [
        call for call in emit_mock.call_args_list if call.kwargs.get("status") == "waiting_pick"
    ]
    assert len(waiting_emits) == 1
    call_kwargs = waiting_emits[0].kwargs
    assert call_kwargs["stage"] == "pick"
    assert "comments" in call_kwargs["data"]
    comments_data = call_kwargs["data"]["comments"]
    assert len(comments_data) == 2
    assert comments_data[0]["id"] == "c1"
    assert comments_data[0]["filter_reason"] is None
    assert comments_data[1]["id"] == "c2"
    assert comments_data[1]["filter_reason"] == "ngắn"


def test_api_postv_settings_endpoint(client):
    # GET ban đầu trả về default (rỗng hoặc file chưa có)
    r_get = client.get("/api/postv/settings")
    assert r_get.status_code == 200

    # POST lưu giọng mới
    r_post = client.post("/api/postv/settings", json={"voice_id": "mai-anh"})
    assert r_post.status_code == 200
    assert r_post.json()["voice_id"] == "mai-anh"

    # GET lại kiểm tra đã nhớ
    r_get2 = client.get("/api/postv/settings")
    assert r_get2.status_code == 200
    assert r_get2.json()["voice_id"] == "mai-anh"


def test_api_postv_delete_endpoint(client):
    # Tạo một project PostV
    r_create = client.post("/api/projects", json={"title": "Video Cần Xoá", "kind": "postv"})
    assert r_create.status_code == 201
    slug = r_create.json()["slug"]

    # Kiểm tra project tồn tại
    assert client.get(f"/api/projects/{slug}").status_code == 200

    # Gọi DELETE /api/postv/{slug}
    r_del = client.delete(f"/api/postv/{slug}")
    assert r_del.status_code == 204

    # Kiểm tra project đã bị xoá
    assert client.get(f"/api/projects/{slug}").status_code == 404

    # Xoá project không tồn tại trả về 404
    assert client.delete(f"/api/postv/{slug}").status_code == 404


def test_api_voices_sample_endpoint(client):
    import wave

    cache_dir = client.tmp / "workspace" / "cache" / "voice_samples"
    cache_dir.mkdir(parents=True, exist_ok=True)
    sample_wav = cache_dir / "test-voice.wav"

    # Tạo một file wav dummy hợp lệ
    with wave.open(str(sample_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 2400)

    r = client.get("/api/voices/test-voice/sample")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert len(r.content) > 0


def test_api_postv_pick_endpoints(client):
    import threading

    from hbt.jobs import Job

    # Tạo project postv
    r_create = client.post("/api/projects", json={"title": "Pick API Test", "kind": "postv"})
    assert r_create.status_code == 201
    slug = r_create.json()["slug"]

    hbt_state = client.app.state.hbt
    proj = hbt_state.storage.load_any(slug)
    proj.post.text = "Bài viết gốc"
    proj.comments = [
        PostvComment(id="c1", handle="u1", text="Bình luận 1", age="1h"),
        PostvComment(id="c2", handle="u2", text="Bình luận 2", age="1h"),
    ]
    hbt_state.storage.save_any(slug, proj)

    # Đăng ký job đang ở waiting_pick
    job = Job("job-pick-test", slug, False, 60, True, False, kind="postv_quick")
    job.status = "waiting_pick"
    job._pick_event = threading.Event()
    hbt_state.jobs._jobs[job.id] = job

    # GET /api/postv/auto/{job_id}/pick
    r_get = client.get(f"/api/postv/auto/{job.id}/pick")
    assert r_get.status_code == 200
    data = r_get.json()
    assert data["job_id"] == job.id
    assert len(data["comments"]) == 2

    # POST /api/postv/auto/{job_id}/pick
    r_pick = client.post(
        f"/api/postv/auto/{job.id}/pick",
        json={"comment_ids": ["c2", "c1"]},
    )
    assert r_pick.status_code == 200
    assert r_pick.json()["ok"] is True
    assert job._pick_event.is_set()

    # Kiểm tra project comments đã được cập nhật thứ tự và picked
    updated_proj = hbt_state.storage.load_any(slug)
    assert updated_proj.comments[0].id == "c2" and updated_proj.comments[0].picked is True
    assert updated_proj.comments[1].id == "c1" and updated_proj.comments[1].picked is True


def test_smart_comment_ranking_up_to_30_and_spam_filter(tmp_path):
    from hbt.jobs import Job
    from hbt.postv.auto import _step_pick, inspect_comment_filter

    # Lọc spam / rác
    seen = set()
    spam = PostvComment(id="s1", handle="bot", text="Inbox check bio zalo 09123", age="1m")
    assert inspect_comment_filter(spam, seen) == "rác"

    # Tạo 25 bình luận + reply để thử bóc tách vượt ngưỡng 7-8 cũ cho mục tiêu 180s
    proj = PostvProject(version=1, kind="postv", slug="long-thread", title="Long Thread")
    proj.post.text = "Bài viết gốc ngắn mở màn câu chuyện."
    comments = []
    for i in range(1, 22):
        comments.append(
            PostvComment(
                id=f"c{i}",
                handle=f"user{i}",
                text=f"Bình luận thứ {i} chia sẻ câu chuyện rất dài và thú vị haha! 😂 " * 2,
                likes=500 if i == 21 else i * 15,
                replies=5 if i == 21 else (3 if i % 4 == 0 else 0),
            )
        )
    # Reply con cho c21 (comment có like cao nhất)
    comments.append(
        PostvComment(
            id="r1",
            handle="replier1",
            text="Đồng quan điểm luôn á trời ơi, đọc tới đây mà cười xỉu haha 😂",
            parent="c21",
            likes=80,
        )
    )
    proj.comments = comments

    jm = MagicMock()
    jm.storage.load_any.return_value = proj
    jm.postv_words = None
    job = Job("job-30", "long-thread", False, 60, True, False, kind="postv_quick")

    _step_pick(jm, job, {"pick_mode": "auto", "target_seconds": 180}, MagicMock())
    picked = [c for c in proj.comments if c.picked]
    assert len(picked) >= 15
    # c21 (nhiều like nhất) ở đầu, và r1 (reply của c21) bám ngay dưới nó
    assert picked[0].id == "c21"
    assert picked[1].id == "r1"


def test_climax_meme_assignment_non_repeating_and_playlist_bgm(tmp_path):
    import json

    from hbt.chatting.audio import build_bgm_playlist
    from hbt.postv.auto import _assign_climax_memes
    from hbt.postv.models import PostvSegment
    from tests.helpers import write_wav

    lib = tmp_path / "library"
    memes_dir = lib / "memes"
    music_dir = lib / "music"
    memes_dir.mkdir(parents=True)
    music_dir.mkdir(parents=True)

    (memes_dir / "cat1.mp4").write_bytes(b"mp4-1")
    (memes_dir / "cat2.mp4").write_bytes(b"mp4-2")
    (memes_dir / "index.json").write_text(
        json.dumps(
            {
                "memes": [
                    {
                        "file": "cat1.mp4",
                        "tags": ["cuoi"],
                        "emojis": ["😂"],
                        "start_time": 0.5,
                        "duration": 3.0,
                    },
                    {
                        "file": "cat2.mp4",
                        "tags": ["cuoi"],
                        "emojis": ["😂"],
                        "start_time": 0.0,
                        "duration": 2.5,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    comments = [
        PostvComment(
            id=f"c{i}",
            handle=f"u{i}",
            text=f"Bình luận hài hước quá trời 😂 số {i}",
            likes=100 - i,
        )
        for i in range(1, 7)
    ]
    by_id = {c.id: c for c in comments}
    segs = [PostvSegment(role="post", card="post", voice="Post gốc", speaker="post")]
    for c in comments:
        segs.append(
            PostvSegment(role="comment", card="comment", voice=c.text, ref=c.id, speaker=c.id)
        )

    _assign_climax_memes(segs, by_id, lib)
    assigned_memes = [s.meme_id for s in segs if s.meme_id]
    assert len(assigned_memes) == 2
    assert len(set(assigned_memes)) == 2  # Xoay vòng không lặp lại

    # Kiểm tra Playlist BGM tạo đủ độ dài phủ kín 150s từ các bài ngắn hơn
    write_wav(music_dir / "track1.wav", [("tone", 2.0, 0.3)], freq=220)
    write_wav(music_dir / "track2.wav", [("tone", 2.0, 0.3)], freq=330)
    playlist = build_bgm_playlist(lib, "track1.wav", 5.0, crossfade_s=0.5)
    assert len(playlist) >= 2


def test_postv_audio_resolves_library_picks_default_and_attaches(tmp_path):
    from hbt.jobs import Job, JobManager
    from hbt.postv.audio import (
        list_available_bgm,
        pick_default_bgm,
        resolve_music_dir,
        resolve_project_music_src,
    )
    from hbt.postv.auto import _step_script
    from hbt.storage import Storage
    from tests.helpers import write_wav

    lib = tmp_path / "library"
    music_dir = lib / "music"
    music_dir.mkdir(parents=True)
    write_wav(music_dir / "quirky.wav", [("tone", 1.5, 0.2)], freq=250)
    (music_dir / "index.json").write_text("[]", encoding="utf-8")

    assert resolve_music_dir(lib).is_absolute()
    avail = list_available_bgm(lib)
    assert len(avail) == 1
    track = pick_default_bgm(lib)
    assert track is not None and track.path.is_file()

    # Kiểm tra _step_script tự chọn và chép file nhạc vào thư mục dự án, không mở đầu bằng hook
    storage = Storage(tmp_path / "workspace")
    jm = JobManager(storage, lib)
    proj = storage.create_postv("BGM & No Hook Test")
    proj.post.text = "Bài gốc mở đầu ngay tại giây 0 https://example.com 😂"
    proj.comments = [
        PostvComment(
            id="c1",
            handle="u1",
            text="Bình luận một khá dài và rất hay!",
            likes=50,
            picked=True,
        )
    ]
    storage.save_any(proj.slug, proj)

    job = Job("job-bgm", proj.slug, False, 60, True, False, kind="postv_quick")
    _step_script(jm, job, {"music": "auto"}, MagicMock())

    saved = storage.load_any(proj.slug)
    assert saved.segments[0].role == "post" and saved.segments[0].card == "post"
    assert "https://" not in saved.segments[0].voice
    assert saved.music is not None
    pdir = storage.project_dir(proj.slug)
    assert (pdir / saved.music.file).is_file()
    assert resolve_project_music_src(saved, pdir, lib) is not None


def test_time_budgeting_replaces_fixed_limits_for_1m_2m_3m():
    from hbt.jobs import Job
    from hbt.postv.auto import _step_pick
    from hbt.postv.timeline import compute_time_budget, estimate_tts_seconds

    assert estimate_tts_seconds("Một hai ba bốn năm sáu bảy tám.") == pytest.approx(
        8 / 3.2 + 0.4, abs=0.05
    )

    def run_budget_for(target_sec: float) -> tuple[int, float]:
        proj = PostvProject(version=1, kind="postv", slug="budget", title="Budget")
        proj.post.text = "Bài viết mở đầu ngắn gọn đọc nhanh trong ba giây thôi."
        # Tạo kho 65 bình luận ngắn + reply con (~4.5s mỗi mục), không bị kẹp limit 10/15/30
        comments = []
        for i in range(1, 56):
            comments.append(
                PostvComment(
                    id=f"c{i}",
                    handle=f"u{i}",
                    text=f"Bình luận ngắn số {i} cực thú vị luôn nha bạn!",
                    likes=200 - i,
                )
            )
            if i % 5 == 0:
                comments.append(
                    PostvComment(
                        id=f"r{i}",
                        handle=f"rep{i}",
                        text=f"Reply con nổi bật bám theo bình luận {i} nè!",
                        parent=f"c{i}",
                        likes=80,
                    )
                )
        proj.comments = comments
        jm = MagicMock()
        jm.storage.load_any.return_value = proj
        jm.library_dir = None
        jm.postv_words = None
        job = Job("j", "budget", False, 60, True, False, kind="postv_quick")
        _step_pick(jm, job, {"pick_mode": "auto", "target_seconds": target_sec}, MagicMock())
        picked = [c for c in proj.comments if c.picked]
        summary = compute_time_budget(proj.post.text, picked, [], target_seconds=target_sec)
        return len(picked), summary.total_seconds

    n_1m, sec_1m = run_budget_for(60)
    n_2m, sec_2m = run_budget_for(120)
    n_3m, sec_3m = run_budget_for(180)
    # Tuyệt đối không ngắn hơn mục tiêu và vượt khỏi mọi kẹp cứng 30 thẻ ở mốc 3m
    assert sec_1m >= 60 and sec_1m <= 66
    assert sec_2m >= 120 and sec_2m <= 126
    assert sec_3m >= 180 and sec_3m <= 186
    assert n_3m > 30


def test_meme_cutin_pause_never_overlaps_tts_or_early_card_scroll(tmp_path):
    from hbt.postv.models import PostvSegment
    from hbt.postv.timeline import (
        estimate_meme_pause_slots,
        plan_meme_cutin_and_card_starts,
    )
    from hbt.postv.voice import join_wavs, wav_seconds
    from tests.helpers import write_wav

    p1 = tmp_path / "p1.wav"
    p2 = tmp_path / "p2.wav"
    p3 = tmp_path / "p3.wav"
    write_wav(p1, [("tone", 1.5, 0.3)], freq=200)
    write_wav(p2, [("tone", 1.5, 0.3)], freq=300)
    write_wav(p3, [("tone", 1.5, 0.3)], freq=400)

    segs = [
        PostvSegment(role="post", card="post", voice="Post", speaker="post"),
        PostvSegment(role="comment", card="comment", voice="C1", ref="c1", meme_id="cat.mp4"),
        PostvSegment(role="comment", card="comment", voice="C2", ref="c2"),
    ]
    gaps = estimate_meme_pause_slots(segs, None)
    assert gaps[0] == 0.25 and 2.8 <= gaps[1] <= 4.0

    joined = tmp_path / "voice.wav"
    spans = join_wavs([p1, p2, p3], joined, post_gaps=gaps)
    # Đoạn 2 (index 1) có meme cut-in: khoảng trống giữa hết đọc p2 và đầu đọc p3 phải >= 3.0s
    assert spans[2][0] - spans[1][1] >= 3.0
    assert wav_seconds(joined) >= 7.5

    first_start = [s[0] for s in spans]
    last_end = [s[1] for s in spans]
    offsets = [(last_end[k - 1] + first_start[k]) / 2 - 0.2 for k in range(1, 3)]
    base_starts = [0.0, *(o + 0.2 for o in offsets)]
    starts, windows = plan_meme_cutin_and_card_starts(
        segs, offsets, first_start, last_end, base_starts, {1: 3.0}, wav_seconds(joined) + 1.0
    )
    assert starts[0] == 0.0
    win = windows[1]
    # Meme chạy sau khi hết đọc đoạn 1 (TTS dừng hoàn toàn) và thẻ tiếp theo chỉ cuộn sau meme
    assert win.start >= last_end[1]
    assert win.end <= first_start[2]
    assert starts[2] >= win.end


def test_step_pick_debug_budget_log_and_low_comments_warning():
    import logging

    from hbt.jobs import Job
    from hbt.postv.auto import _step_pick

    proj = PostvProject(version=1, kind="postv", slug="low-cmt", title="Low")
    proj.post.text = "Bài viết gốc chỉ có vài bình luận ngắn ngủi."
    proj.comments = [
        PostvComment(
            id=f"c{i}",
            handle=f"u{i}",
            text=f"Bình luận hợp lệ thứ {i} dài hơn 8 ký tự nè.",
            likes=20 - i,
        )
        for i in range(1, 5)
    ]

    jm = MagicMock()
    jm.storage.load_any.return_value = proj
    jm.library_dir = None
    jm.postv_words = None
    job = Job("j-low", "low-cmt", False, 60, True, False, kind="postv_quick")
    mock_logger = MagicMock(spec=logging.Logger)

    _step_pick(jm, job, {"pick_mode": "auto", "target_seconds": 120}, mock_logger)

    info_msgs = [str(c.args[0]) for c in mock_logger.info.call_args_list if c.args]
    assert any("[DEBUG]" in m and "cào=4" in m and "tích_lũy=" in m for m in info_msgs)

    pick_payloads = [payload for ev, payload in job._events if ev == "progress"]
    done_payload = pick_payloads[-1]["data"]
    assert done_payload["total_comments"] == 4
    assert done_payload["low_comments_warning"]
    assert "< 10" in done_payload["low_comments_warning"]


def test_step_voice_emits_sentence_progress_and_releases_lock(tmp_path):
    import logging

    from hbt.jobs import Job, JobManager
    from hbt.postv.auto import _step_voice
    from hbt.postv.models import PostvSegment
    from hbt.postv.voice import FakeVoice
    from hbt.storage import Storage

    store = Storage(tmp_path / "ws")
    proj = store.create_postv("Progress Voice")
    proj.comments = [
        PostvComment(id="c1", handle="u1", text="Bình luận một"),
        PostvComment(id="c2", handle="u2", text="Bình luận hai"),
    ]
    proj.segments = [
        PostvSegment(role="post", card="post", voice="Bài mở đầu ngắn", speaker="post"),
        PostvSegment(role="comment", card="comment", voice="Bình luận một", ref="c1", speaker="c1"),
        PostvSegment(role="comment", card="comment", voice="Bình luận hai", ref="c2", speaker="c2"),
    ]
    store.save_any(proj.slug, proj)

    jm = JobManager(store, tmp_path / "lib", voice=FakeVoice(), tool_check=None)
    job = Job("j-voice-prog", proj.slug, False, 60, True, False, kind="postv_quick")
    _step_voice(jm, job, {}, logging.getLogger("test"))

    voice_events = [
        payload
        for ev, payload in job._events
        if ev == "progress" and payload.get("step") == "voice"
    ]
    assert any(
        e.get("current") == 1 and e.get("total") == 3 and "1/3" in e.get("message", "")
        for e in voice_events
    )
    assert any(e.get("current") == 3 and e.get("percent") == 100 for e in voice_events)
    assert jm.is_generating_voice.get(proj.slug) is False
    jm.shutdown()
