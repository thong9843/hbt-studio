import shutil
import threading
import time
from pathlib import Path

import pytest

from hbt import jobs as jobs_module
from hbt.jobs import CANCELLED, DONE, FAILED, QUEUED, RUNNING, JobManager
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.cancel import RenderCancelled
from hbt.pipeline.render import RenderError
from hbt.storage import Conflict, NotFound, Storage, Unprocessable
from tests.helpers import needs_ffmpeg
from tests.test_render import make_project


@pytest.fixture
def env(tmp_path):
    """Workspace có sẵn project hoàn chỉnh `demo` (3 cảnh, ảnh + giọng giả)."""
    pdir, opts = make_project(tmp_path / "src")
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    return store, opts


def manager(env, render_fn=None):
    store, opts = env
    kwargs = {"render_fn": render_fn, "tool_check": None} if render_fn else {}
    return JobManager(store, opts.library_dir, opts.brand_dir, **kwargs)


class FakeRender:
    """Render giả: chờ `gate` rồi trả về/ném lỗi; ghi lại các lần gọi."""

    def __init__(self, behaviour="ok"):
        self.gate = threading.Event()
        self.started = threading.Event()
        self.calls = []
        self.behaviour = behaviour

    def __call__(self, folder, opts, progress=None, cancel_token=None):
        self.calls.append((Path(folder).name, opts.job_id, opts.preview, opts.fps))
        progress(10, "Căn chữ", "đang căn")
        self.started.set()
        while not self.gate.wait(0.05):
            if cancel_token.cancelled:
                raise RenderCancelled
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        raise AssertionError("render giả không có kết quả thật")


def wait_for(predicate, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


# ---------------------------------------------------------------- kiểm tra đầu vào
def test_submit_unknown_project(env):
    with pytest.raises(NotFound):
        manager(env).submit("khong-co")


def test_submit_incomplete_project_lists_problems(env):
    store, _ = env
    store.create("Nháp")
    with pytest.raises(Unprocessable, match="Project chưa đủ để dựng.*Cảnh 1: chưa có ảnh"):
        manager(env).submit("nhap")


@pytest.mark.parametrize("fps", [45, 24])
def test_submit_rejects_odd_fps(env, fps):
    with pytest.raises(Unprocessable, match="fps"):
        manager(env).submit("demo", fps=fps)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"preview": False, "preview_seconds": 10}, "Xem nhanh"),
        ({"preview": True, "preview_seconds": 0}, "preview_seconds"),
        ({"preview": True, "preview_seconds": 61}, "preview_seconds"),
    ],
)
def test_submit_rejects_bad_preview_seconds(env, kwargs, message):
    m = manager(env)
    with pytest.raises(Unprocessable, match=message):
        m.submit("demo", **kwargs)
    assert m._jobs == {}


# ---------------------------------------------------------------- hàng đợi, huỷ, lỗi (render giả)
def test_second_job_waits_in_queue_and_can_be_cancelled_without_running(env):
    fake = FakeRender()
    m = manager(env, fake)
    a = m.submit("demo", preview=True, fps=30)
    assert fake.started.wait(5)
    b = m.submit("demo")
    assert (a.status, b.status) == (RUNNING, QUEUED)

    cancelled = m.cancel(b.id)
    assert cancelled.status == CANCELLED and cancelled.finished
    assert [e[0] for e in cancelled.events_since(0)] == ["end"]

    m.cancel(a.id)
    assert a.status == CANCELLED
    assert len(fake.calls) == 1  # job B chưa bao giờ chạy
    assert fake.calls[0] == ("demo", a.id, True, 30)
    m.shutdown()


def test_cancel_running_job_waits_until_it_really_stopped(env):
    fake = FakeRender()
    m = manager(env, fake)
    job = m.submit("demo")
    assert fake.started.wait(5)
    result = m.cancel(job.id)
    assert result.status == CANCELLED and result.finished_at is not None
    assert job.events_since(0)[-1] == (
        "end",
        {"status": "cancelled", "error": None, "output": None},
    )
    m.shutdown()


def test_cancel_unknown_and_finished_jobs(env):
    fake = FakeRender(RenderError("hỏng rồi"))
    m = manager(env, fake)
    with pytest.raises(NotFound):
        m.cancel("khong-co")
    job = m.submit("demo")
    assert fake.started.wait(5)
    fake.gate.set()
    assert job.wait(5) and job.status == FAILED
    with pytest.raises(Conflict, match="failed"):
        m.cancel(job.id)
    m.shutdown()


def test_failed_job_keeps_the_error_message(env):
    fake = FakeRender(RenderError("Bộ mã hoá lỗi (mã 1)"))
    m = manager(env, fake)
    job = m.submit("demo")
    fake.gate.set()
    assert job.wait(5)
    assert job.status == FAILED and job.error == "Bộ mã hoá lỗi (mã 1)"
    assert job.output is None and not job.needs_confirmation
    assert job.events_since(0)[-1][1]["status"] == "failed"
    m.shutdown()


def test_long_trim_asks_for_confirmation(env):
    fake = FakeRender(TailTrimNeedsConfirmation("Đuôi thừa dài 9,50 giây"))
    m = manager(env, fake)
    job = m.submit("demo")
    fake.gate.set()
    assert job.wait(5)
    assert job.status == FAILED and job.needs_confirmation and "9,50" in job.error
    m.shutdown()


def test_unexpected_exception_becomes_a_failed_job(env):
    fake = FakeRender(ZeroDivisionError())
    m = manager(env, fake)
    job = m.submit("demo")
    fake.gate.set()
    assert job.wait(5) and job.status == FAILED and job.error == "ZeroDivisionError"
    m.shutdown()


def test_progress_and_log_tail_are_recorded(env):
    fake = FakeRender(RenderError("x"))
    m = manager(env, fake)
    job = m.submit("demo")
    assert fake.started.wait(5)
    assert (job.progress, job.step) == (10, "Căn chữ") and job.log_tail() == ["đang căn"]
    kinds = [e[0] for e in job.events_since(0)]
    assert kinds == ["progress"]
    assert job.events_since(0)[0][1] == {"progress": 10, "step": "Căn chữ", "message": "đang căn"}
    assert job.events_since(1) == []
    fake.gate.set()
    job.wait(5)
    m.shutdown()


def test_is_busy_follows_the_job_lifecycle(env):
    fake = FakeRender(RenderError("x"))
    m = manager(env, fake)
    assert not m.is_busy("demo")
    job = m.submit("demo")
    assert m.is_busy("demo") and not m.is_busy("khac")
    fake.gate.set()
    job.wait(5)
    assert wait_for(lambda: not m.is_busy("demo"))
    m.shutdown()


def test_old_finished_jobs_are_pruned(env, monkeypatch):
    monkeypatch.setattr(jobs_module, "MAX_JOBS", 3)
    fake = FakeRender(RenderError("x"))
    fake.gate.set()
    m = manager(env, fake)
    ids = []
    for _ in range(6):
        j = m.submit("demo")
        j.wait(5)
        ids.append(j.id)
    assert wait_for(lambda: len(m._jobs) <= 4)
    assert ids[-1] in m._jobs and ids[0] not in m._jobs
    with pytest.raises(NotFound):
        m.get(ids[0])
    m.shutdown()


def test_shutdown_cancels_running_work(env):
    fake = FakeRender()
    m = manager(env, fake)
    job = m.submit("demo")
    assert fake.started.wait(5)
    m.shutdown()
    assert job.status == CANCELLED


# ---------------------------------------------------------------- dựng thật
@needs_ffmpeg
@pytest.mark.slow
def test_real_preview_job_end_to_end(env):
    store, _ = env
    m = manager(env)
    job = m.submit("demo", preview=True, outro=False)
    assert job.wait(180)
    assert job.status == DONE, job.error
    out = job.output
    assert out["fps"] == 30 and (out["width"], out["height"]) == (540, 960)
    assert out["video"] == f"projects/demo/renders/{job.id}/video.mp4"
    for key in ("video", "srt", "publish", "log"):
        assert (store.workspace_dir / out[key]).is_file(), key
    events = job.events_since(0)
    kinds = [k for k, _ in events]
    assert kinds[-1] == "end" and set(kinds[:-1]) == {"progress"}
    percents = [d["progress"] for k, d in events if k == "progress"]
    assert percents == sorted(percents) and percents[0] == 0 and percents[-1] == 100
    assert events[-1][1]["output"]["video"] == out["video"] and job.progress == 100
    assert store.last_render("demo")["job_id"] == job.id
    m.shutdown()


@needs_ffmpeg
@pytest.mark.slow
def test_real_head_preview_job_reports_seconds_and_no_srt(tmp_path):
    pdir, opts = make_project(tmp_path / "src", n=8)
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    m = JobManager(store, opts.library_dir, opts.brand_dir)
    job = m.submit("demo", preview=True, preview_seconds=10)
    assert job.wait(180)
    assert job.status == DONE, job.error
    out = job.output
    assert out["preview_seconds"] == 10 and out["srt"] is None and out["lufs"] is None
    assert out["duration"] == pytest.approx(10.0, abs=0.2)
    assert store.last_render("demo")["job_id"] == job.id
    m.shutdown()
