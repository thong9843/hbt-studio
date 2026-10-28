"""B′ (IMPLEMENT 13.B5): job ghi `render_seconds` và `align_cached` vào meta.json sau khi xong."""

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbt import jobs as jobs_module
from hbt.jobs import CANCELLED, DONE, FAILED, write_run_stats
from hbt.pipeline.cancel import RenderCancelled
from hbt.pipeline.render import RenderResult
from tests.test_api import client  # noqa: F401
from tests.test_jobs import env, manager  # noqa: F401

PIPELINE_META = {
    "fps": 50,
    "width": 1080,
    "height": 1920,
    "duration": 41.5,
    "preview": False,
    "aligner": "silence",
    "created_at": "2026-10-27T10:00:00Z",
}


class StatsRender:
    """Render giả ghi đủ file như pipeline: video, meta.json, và tuỳ ý `build/timing.json`."""

    def __init__(self, *, meta=True, timing="keep", error=None, seconds=12.34):
        self.meta, self.timing, self.error, self.seconds = meta, timing, error, seconds

    def __call__(self, folder, opts, progress=None, cancel_token=None):
        folder = Path(folder)
        job_dir = folder / "renders" / opts.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "video.mp4").write_bytes(b"x")
        (job_dir / "log.txt").write_text("log", encoding="utf-8")
        (job_dir / "publish.txt").write_text("p", encoding="utf-8")
        if self.meta:
            data = {**PIPELINE_META, "preview": opts.preview}
            (job_dir / "meta.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        timing = folder / "build" / "timing.json"
        if self.timing == "create":
            timing.parent.mkdir(exist_ok=True)
            timing.write_text("{}", encoding="utf-8")
        elif self.timing == "rewrite":
            timing.write_text("{}", encoding="utf-8")
            st = timing.stat()
            os.utime(timing, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        if self.error:
            raise self.error
        return RenderResult(
            job_dir=job_dir,
            video=job_dir / "video.mp4",
            srt=None,
            publish=job_dir / "publish.txt",
            log=job_dir / "log.txt",
            fps=50,
            width=1080,
            height=1920,
            duration=41.5,
            lufs=-14.0,
            aligner="silence",
            seconds=self.seconds,
        )


def seed_timing(store, slug="demo"):
    path = store.project_dir(slug) / "build" / "timing.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def run(env, fake, **kw):  # noqa: F811
    m = manager(env, fake)
    job = m.submit("demo", **kw)
    assert job.wait(30)
    m.shutdown()
    return job


def meta_of(env, job):  # noqa: F811
    store, _ = env
    path = store.project_dir("demo") / "renders" / job.id / "meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


@pytest.mark.parametrize("preview", [True, False])
def test_cached_alignment_and_seconds_are_recorded(env, preview):  # noqa: F811
    seed_timing(env[0])
    job = run(env, StatsRender(seconds=12.34), preview=preview)
    assert job.status == DONE, job.error
    meta = meta_of(env, job)
    assert meta["render_seconds"] == 12.3 and meta["align_cached"] is True
    pipeline_fields = {k: v for k, v in meta.items() if k not in ("render_seconds", "align_cached")}
    assert pipeline_fields == {**PIPELINE_META, "preview": preview}  # trường pipeline giữ nguyên


def test_rewritten_timing_means_not_cached(env):  # noqa: F811
    seed_timing(env[0])
    meta = meta_of(env, run(env, StatsRender(timing="rewrite")))
    assert meta["align_cached"] is False


def test_missing_timing_before_the_job_means_not_cached(env):  # noqa: F811
    job = run(env, StatsRender(timing="create"))  # job tự tạo timing.json: không phải dùng lại
    assert meta_of(env, job)["align_cached"] is False
    job = run(env, StatsRender(timing="keep"))  # lần này đã có sẵn và không đổi
    assert meta_of(env, job)["align_cached"] is True


def test_nothing_is_written_for_failed_or_cancelled_jobs(env):  # noqa: F811
    seed_timing(env[0])
    failed = run(env, StatsRender(error=RuntimeError("hỏng")))
    assert failed.status == FAILED
    assert meta_of(env, failed) == PIPELINE_META
    cancelled = run(env, StatsRender(error=RenderCancelled()))
    assert cancelled.status == CANCELLED
    assert meta_of(env, cancelled) == PIPELINE_META


def test_no_meta_json_means_nothing_is_created(env):  # noqa: F811
    store, _ = env
    job = run(env, StatsRender(meta=False))
    assert job.status == DONE, job.error
    folder = store.project_dir("demo") / "renders" / job.id
    assert not (folder / "meta.json").exists() and not (folder / "meta.json.tmp").exists()


def test_write_failure_is_only_logged_and_the_job_still_succeeds(env, monkeypatch, caplog):  # noqa: F811
    seed_timing(env[0])

    def boom(src, dst):
        raise OSError("đĩa đầy")

    monkeypatch.setattr(jobs_module, "os", SimpleNamespace(replace=boom))  # chỉ jobs.py
    with caplog.at_level(logging.WARNING, logger="hbt.jobs"):
        job = run(env, StatsRender())
    assert job.status == DONE and job.error is None
    assert meta_of(env, job) == PIPELINE_META  # meta.json nguyên vẹn
    folder = env[0].project_dir("demo") / "renders" / job.id
    assert not (folder / "meta.json.tmp").exists()
    assert "thống kê dựng" in caplog.text


def test_corrupt_meta_json_is_left_alone(tmp_path):
    (tmp_path / "meta.json").write_text("{hỏng", encoding="utf-8")
    write_run_stats(tmp_path, 3.0, True)
    assert (tmp_path / "meta.json").read_text(encoding="utf-8") == "{hỏng"
    assert not (tmp_path / "meta.json.tmp").exists()


def test_seconds_are_rounded_to_a_tenth(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps({"fps": 50}), encoding="utf-8")
    write_run_stats(tmp_path, 143.26, False)
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8")) == {
        "fps": 50,
        "render_seconds": 143.3,
        "align_cached": False,
    }


# ------------------------------------------------------------------ /renders và last_render
def write_render(folder, job_id, **meta):
    d = folder / "renders" / job_id
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(b"x")
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_storage_returns_the_two_fields_and_null_for_old_renders(env):  # noqa: F811
    store, _ = env
    folder = store.project_dir("demo")
    write_render(folder, "old", created_at="2026-10-01T10:00:00Z", fps=50)
    write_render(
        folder, "new", created_at="2026-10-02T10:00:00Z", render_seconds=143.3, align_cached=True
    )
    by_id = {r["job_id"]: r for r in store.list_renders("demo")}
    assert (by_id["new"]["render_seconds"], by_id["new"]["align_cached"]) == (143.3, True)
    assert (by_id["old"]["render_seconds"], by_id["old"]["align_cached"]) == (None, None)
    last = store.last_render("demo")
    assert last["job_id"] == "new" and last["render_seconds"] == 143.3
    assert last["align_cached"] is True
    (folder / "renders" / "new" / "video.mp4").unlink()
    last = store.last_render("demo")
    assert last["job_id"] == "old"
    assert last["render_seconds"] is None and last["align_cached"] is None


def test_renders_endpoint_exposes_the_fields(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Ước tính"}).json()["slug"]
    folder = client.app.state.hbt.storage.project_dir(slug)
    write_render(folder, "a", created_at="2026-10-01T10:00:00Z")
    write_render(
        folder, "b", created_at="2026-10-02T10:00:00Z", render_seconds=61.0, align_cached=False
    )
    items = client.get(f"/api/projects/{slug}/renders").json()
    assert [(i["job_id"], i["render_seconds"], i["align_cached"]) for i in items] == [
        ("b", 61.0, False),
        ("a", None, None),
    ]
    summary = next(p for p in client.get("/api/projects").json() if p["slug"] == slug)
    assert summary["last_render"]["render_seconds"] == 61.0
