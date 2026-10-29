"""Job dựng PostV: jobs.py rẽ theo `kind`, job HBT giữ nguyên (IMPLEMENT-POSTV.md, PV5)."""

import json
import shutil
from types import SimpleNamespace

import pytest

from hbt.jobs import DONE, FAILED, JobManager
from hbt.pipeline.render import RenderError
from hbt.postv.backgrounds import BackgroundLibrary
from hbt.postv.censor import CensorStore
from hbt.postv.models import PostvProject
from hbt.storage import Storage, Unprocessable
from tests.helpers import needs_ffmpeg
from tests.test_jobs import FakeRender, wait_for
from tests.test_postv_backgrounds import make_clip
from tests.test_render import make_project


class FakePostvRender:
    """Dựng PostV giả: ghi lại lời gọi, trả kết quả như RenderResult."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, folder, opts, progress=None, cancel_token=None, censor_words=None):
        self.calls.append((folder.name, opts, censor_words))
        progress(50, "Ghép cuối", "đang ghép")
        if self.error:
            raise self.error
        job = folder / "renders" / opts.job_id
        job.mkdir(parents=True)
        for name in ("video.mp4", "publish.txt", "log.txt"):
            (job / name).write_bytes(b"x")
        (job / "meta.json").write_text(json.dumps({"fps": 60}), encoding="utf-8")
        return SimpleNamespace(
            job_dir=job, video=job / "video.mp4", srt=None, publish=job / "publish.txt",
            log=job / "log.txt", fps=60, width=1080, height=1920, duration=9.0, lufs=-14.0,
            aligner="silence", aligner_info={}, seconds=1.0, warnings=["nhắc"],
            preview_seconds=None,
            cover=None, youtube_cover=None, trimmed_tail=None, trimmed_tail_seconds=None,
        )  # fmt: skip


@pytest.fixture
def env(tmp_path):
    pdir, opts = make_project(tmp_path / "src")
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    return store, opts


def ready_postv(store, library_dir, tmp_path, with_clip=True):
    pv = store.create_postv("Bài thử")
    data = pv.model_dump() | {
        "post": {"text": "Một bài viết"},
        "segments": [{"role": "post", "voice": "Xin chào các bạn"}],
        "voice": {"engine": "file", "file": "voice.wav"},
    }
    store.save_any(pv.slug, PostvProject.model_validate(data))
    (store.project_dir(pv.slug) / "voice.wav").write_bytes(b"x")
    if with_clip:
        clip = make_clip(tmp_path / "c.mp4", seconds=4)
        BackgroundLibrary(library_dir).add(
            clip, "c.mp4", {"title": "A", "source": "s", "license": "l"}
        )
    return pv.slug


def manager(env, postv_fn, words=None):
    store, opts = env
    return JobManager(
        store, opts.library_dir, opts.brand_dir, render_fn=FakeRender(), tool_check=None,
        postv_render_fn=postv_fn, postv_words=words,
    )  # fmt: skip


@needs_ffmpeg
def test_postv_job_runs_the_postv_renderer_with_censor_words(env, tmp_path):
    store, opts = env
    slug = ready_postv(store, opts.library_dir, tmp_path)
    fake = FakePostvRender()
    m = manager(env, fake, CensorStore(tmp_path / "workspace"))
    job = m.submit(slug, preview=True, preview_seconds=10)
    assert job.wait(10) and job.status == DONE
    name, passed, words = fake.calls[0]
    assert name == slug and passed.preview and passed.preview_seconds == 10 and words is not None
    assert job.output["video"].endswith("video.mp4") and job.output["warnings"] == ["nhắc"]
    assert job.output["fps"] == 60 and job.output["aligner"] == "silence"
    assert (store.project_dir(slug) / "renders" / job.id / "meta.json").is_file()
    m.shutdown()


@needs_ffmpeg
def test_postv_render_error_fails_the_job(env, tmp_path):
    store, opts = env
    slug = ready_postv(store, opts.library_dir, tmp_path)
    m = manager(env, FakePostvRender(RenderError("nền hỏng")))
    job = m.submit(slug)
    assert job.wait(10) and job.status == FAILED and job.error == "nền hỏng"
    m.shutdown()


@needs_ffmpeg
def test_hbt_project_still_uses_the_hbt_renderer(env, tmp_path):
    fake_postv = FakePostvRender()
    m = manager(env, fake_postv)
    job = m.submit("demo", preview=True, fps=30)
    assert wait_for(lambda: m._render.calls)  # noqa: SLF001
    assert fake_postv.calls == [] and m._render.calls[0][0] == "demo"  # noqa: SLF001
    m._render.gate.set()  # noqa: SLF001
    job.wait(10)
    m.shutdown()


def test_postv_submit_lists_what_is_missing_and_checks_background(env):
    store, opts = env
    pv = store.create_postv("Trống")
    with pytest.raises(Unprocessable, match="Chưa có chữ bài gốc"):
        manager(env, FakePostvRender()).submit(pv.slug)


@needs_ffmpeg
def test_postv_submit_reports_missing_background(env, tmp_path):
    store, opts = env
    slug = ready_postv(store, opts.library_dir, tmp_path, with_clip=False)
    with pytest.raises(Unprocessable, match="Chưa có clip nền"):
        manager(env, FakePostvRender()).submit(slug)


@needs_ffmpeg
def test_postv_submit_validates_options_like_hbt(env, tmp_path):
    store, opts = env
    slug = ready_postv(store, opts.library_dir, tmp_path)
    m = manager(env, FakePostvRender())
    with pytest.raises(Unprocessable, match="fps"):
        m.submit(slug, fps=45)
    with pytest.raises(Unprocessable, match="preview_seconds"):
        m.submit(slug, preview=False, preview_seconds=5)
