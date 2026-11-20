"""Job sinh giọng dùng chung JobManager với job dựng: job dựng HBT phải giữ nguyên hành vi (PV4)."""

import shutil
import time

import pytest

from hbt.jobs import CANCELLED, DONE, FAILED, Job, JobManager
from hbt.pipeline.render import RenderError
from hbt.postv.models import PostvProject
from hbt.postv.voice import FakeVoice
from hbt.storage import Storage, Unprocessable
from tests.test_jobs import FakeRender, wait_for
from tests.test_render import make_project


@pytest.fixture
def env(tmp_path):
    pdir, opts = make_project(tmp_path / "src")
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    return store, opts


def new_postv(store, text="Xin chào các bạn"):
    pv = store.create_postv("Bài thử")
    data = pv.model_dump() | {"segments": [{"role": "post", "voice": text}]}
    store.save_any(pv.slug, PostvProject.model_validate(data))
    return pv.slug


def manager(env, render_fn, voice=None):
    store, opts = env
    return JobManager(
        store, opts.library_dir, opts.brand_dir, render_fn=render_fn, tool_check=None, voice=voice
    )


def test_job_defaults_are_render_kind():
    job = Job("a", "demo", True, 30, None, False)
    assert job.kind == "render" and job.status == "queued" and job.preview_seconds is None


def test_hbt_render_job_unchanged_failure_path(env):
    fake = FakeRender(RenderError("hỏng giữa chừng"))
    m = manager(env, fake)
    job = m.submit("demo", preview=True, fps=30)
    assert job.kind == "render" and fake.started.wait(5)
    assert job.progress == 10 and job.step == "Căn chữ" and m.is_busy("demo")
    fake.gate.set()
    assert job.wait(5) and job.status == FAILED and job.error == "hỏng giữa chừng"
    kinds = [k for k, _ in job.events_since(0)]
    assert kinds == ["progress", "end"] and not m.is_busy("demo")
    assert fake.calls == [("demo", job.id, True, 30)]
    m.shutdown()


def test_hbt_render_job_unchanged_cancel_path(env):
    fake = FakeRender()
    m = manager(env, fake)
    job = m.submit("demo")
    assert fake.started.wait(5)
    assert m.cancel(job.id).status == CANCELLED
    assert [k for k, _ in job.events_since(0)][-1] == "end"
    m.shutdown()


def test_hbt_project_cannot_use_voice_job(env):
    m = manager(env, FakeRender(), voice=FakeVoice())
    with pytest.raises(Unprocessable, match="PostV"):
        m.submit_voice("demo")
    m.shutdown()


def test_voice_job_shares_single_queue_with_render_jobs(env):
    slug = new_postv(env[0])
    fake = FakeRender()
    m = manager(env, fake, voice=FakeVoice())
    render_job = m.submit("demo")
    assert fake.started.wait(5)
    voice_job = m.submit_voice(slug)
    time.sleep(0.2)
    assert voice_job.status == "queued"  # một luồng: chờ job dựng xong
    assert m.cancel(render_job.id).status == CANCELLED
    assert voice_job.wait(10) and voice_job.status == DONE
    assert voice_job.output["generated"] == 1 and voice_job.kind == "voice"
    m.shutdown()


def test_voice_job_cancelled_while_queued_does_not_run(env):
    slug = new_postv(env[0])
    fake, voice = FakeRender(), FakeVoice()
    m = manager(env, fake, voice=voice)
    m.submit("demo")
    assert fake.started.wait(5)
    job = m.submit_voice(slug)
    assert m.cancel(job.id).status == CANCELLED
    fake.gate.set()
    assert wait_for(lambda: not m.is_busy("demo"))
    assert voice.calls == []
    m.shutdown()


def test_voice_job_releases_lock_flags_on_error_and_stale_heartbeat(env):
    slug = new_postv(env[0], text="Câu một có chữ lỗi để kiểm thử try finally")
    failing_voice = FakeVoice(fail_on="lỗi")
    m = JobManager(
        env[0],
        env[1].library_dir,
        env[1].brand_dir,
        render_fn=FakeRender(),
        tool_check=None,
        voice=failing_voice,
        stale_timeout=0.05,
    )
    job = m.submit_voice(slug)
    assert job.wait(5) and job.status == FAILED
    assert not m.is_busy(slug)
    assert m.is_generating_voice.get(slug) is False
    assert m.is_rendering.get(slug) is False

    # Giả lập job treo kẹt không còn worker sống & hết hạn heartbeat
    stuck = Job("stuck1", slug, False, None, None, False, kind="voice", status="running")
    stuck.last_heartbeat = time.time() - 10.0
    m._jobs[stuck.id] = stuck
    m.is_generating_voice[slug] = True
    assert not m.is_busy(slug)
    assert stuck.status == FAILED
    assert m.is_generating_voice[slug] is False
    m.shutdown()


def test_api_unlock_project_endpoint(env, tmp_path):
    from fastapi.testclient import TestClient

    from hbt.config import Settings
    from hbt.main import create_app

    store, opts = env
    slug = new_postv(store, text="Dự án cần mở khoá")
    settings = Settings(
        workspace_dir=store.workspace_dir,
        library_dir=opts.library_dir,
        whisper_model="large-v3",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings, brand_dir=opts.brand_dir)
    with TestClient(app) as tc:
        jm = app.state.hbt.jobs
        stuck = Job("stuck-api", slug, False, None, None, False, kind="voice", status="running")
        jm._jobs[stuck.id] = stuck
        jm._active_workers.add(stuck.id)
        jm.is_generating_voice[slug] = True

        r = tc.post(f"/api/projects/{slug}/unlock")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["unlocked"] == 1
        assert not jm.is_busy(slug)
        assert jm.is_generating_voice[slug] is False
