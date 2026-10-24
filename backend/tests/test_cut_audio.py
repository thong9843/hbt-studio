"""Nghe lại phần giọng đã cắt (IMPLEMENT.md 4d.4): file nằm ở renders/<job_id>/, không ở build/."""

import json
import shutil

import pytest

from hbt.api.render import job_view
from hbt.jobs import FAILED, JobManager
from hbt.pipeline import audio, render
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.ffutil import media_duration
from hbt.pipeline.render import render_project
from hbt.storage import Storage
from tests.helpers import needs_ffmpeg, write_wav
from tests.test_jobs import FakeRender, manager, wait_for
from tests.test_render import make_project
from tests.test_whisper_align import FakeWhisper
from tests.test_whisper_tail import AD, LAST_END, LONG_AD, LONG_TAIL, TAIL_AUDIO


@needs_ffmpeg
def test_save_cut_part_keeps_only_the_cut_span(tmp_path):
    src = tmp_path / "v.wav"
    write_wav(src, [("tone", 2.0), ("gap", 1.0), ("tone", 3.0)])
    out = audio.save_cut_part(src, 3.0, 6.0, tmp_path / "cut.wav")
    assert media_duration(out) == pytest.approx(3.0, abs=0.05)


@pytest.fixture
def whisper(monkeypatch):
    def install(**kw):
        monkeypatch.setattr(render, "run_whisper", FakeWhisper(**kw))

    return install


def meta_of(res):
    return json.loads((res.job_dir / "meta.json").read_text("utf-8"))


@needs_ffmpeg
def test_whisper_cut_is_saved_in_the_job_dir_and_recorded(tmp_path, whisper):
    whisper(extra=AD)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False, tail=TAIL_AUDIO)
    res = render_project(pdir, opts)
    assert res.trimmed_tail == res.job_dir / "trimmed_tail.wav" and res.trimmed_tail.is_file()
    # phần cắt chạy từ chữ cuối + 0,35 s đến hết giọng thật (trước đệm 1,6 s)
    assert media_duration(res.trimmed_tail) == pytest.approx(res.trimmed_tail_seconds, abs=0.05)
    assert res.trimmed_tail_seconds == pytest.approx(9.2 - (LAST_END + 0.35), abs=0.3)
    meta = meta_of(res)
    assert meta["trimmed_tail"] == "trimmed_tail.wav"
    assert meta["trimmed_tail_seconds"] == pytest.approx(res.trimmed_tail_seconds, abs=0.01)
    assert not (pdir / "build" / "trimmed_tail.wav").exists()  # nút Dọn file tạm không được xoá nó


@needs_ffmpeg
def test_nothing_cut_means_no_file(tmp_path, whisper):
    whisper()
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    res = render_project(pdir, opts)
    assert res.trimmed_tail is None and not (res.job_dir / "trimmed_tail.wav").exists()
    assert meta_of(res)["trimmed_tail"] is None


@needs_ffmpeg
def test_silence_aligner_cut_is_saved_too(tmp_path):
    pdir, opts = make_project(tmp_path, n=8, tail=[("gap", 0.8), ("tone", 3.0)], outro=False)
    res = render_project(pdir, opts)
    assert res.aligner == "silence" and res.trimmed_tail.is_file()
    assert media_duration(res.trimmed_tail) == pytest.approx(res.trimmed_tail_seconds, abs=0.05)
    assert res.trimmed_tail_seconds > 2.5


@needs_ffmpeg
def test_manual_trim_end_cut_is_saved_too(tmp_path):
    pdir, opts = make_project(
        tmp_path,
        outro=False,
        tail=TAIL_AUDIO,
        voice={"file": "voice.wav", "trim_end": 4.9 + 0.4},
    )
    res = render_project(pdir, opts)
    assert res.trimmed_tail.is_file()
    assert media_duration(res.trimmed_tail) == pytest.approx(res.trimmed_tail_seconds, abs=0.05)
    assert res.trimmed_tail_seconds == pytest.approx(9.2 - (5.3 + 0.2), abs=0.1)


@needs_ffmpeg
def test_unconfirmed_long_cut_still_saves_the_file_to_listen_to(tmp_path, whisper):
    whisper(extra=LONG_AD)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False, tail=LONG_TAIL)
    opts.job_id = "j-long"
    with pytest.raises(TailTrimNeedsConfirmation) as err:
        render_project(pdir, opts)
    cut = err.value.cut_file
    assert cut == pdir / "renders" / "j-long" / "trimmed_tail.wav" and cut.is_file()
    assert media_duration(cut) == pytest.approx(
        err.value.content_end - err.value.voice_end, abs=0.05
    )
    assert media_duration(cut) > 8


# ---------------------------------------------------------------- job và API
def test_needs_confirmation_job_carries_the_audio_url(tmp_path):
    pdir, opts = make_project(tmp_path / "src")
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    cut = store.project_dir("demo") / "renders" / "x" / "trimmed_tail.wav"
    cut.parent.mkdir(parents=True)
    write_wav(cut, [("tone", 1.0)])

    def raising(folder, o, progress=None, cancel_token=None):
        e = TailTrimNeedsConfirmation("Đuôi thừa dài 9,50 giây")
        e.cut_file = cut
        raise e

    m = JobManager(store, opts.library_dir, opts.brand_dir, render_fn=raising, tool_check=None)
    job = m.submit("demo")
    assert wait_for(lambda: job.finished)
    assert job.status == FAILED and job.needs_confirmation
    view = job_view(job)
    assert view["cut_audio"] == "/api/files/projects/demo/renders/x/trimmed_tail.wav"
    m.shutdown()


def test_job_without_a_cut_file_has_no_audio_url(tmp_path):
    pdir, opts = make_project(tmp_path / "src")
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    fake = FakeRender(TailTrimNeedsConfirmation("Đuôi thừa dài 9,50 giây"))
    m = manager((store, opts), fake)
    job = m.submit("demo")
    fake.gate.set()
    assert wait_for(lambda: job.finished)
    assert job_view(job)["cut_audio"] is None
    m.shutdown()


def test_renders_listing_exposes_the_cut_file(tmp_path):
    store = Storage(tmp_path / "workspace")
    pdir, _ = make_project(tmp_path / "src")
    shutil.copytree(pdir, store.projects_dir / "demo")
    d = store.project_dir("demo") / "renders" / "j1"
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(b"x")
    (d / "trimmed_tail.wav").write_bytes(b"x")
    (item,) = store.list_renders("demo")
    assert item["trimmed_tail"] == "projects/demo/renders/j1/trimmed_tail.wav"
    (d / "trimmed_tail.wav").unlink()
    assert store.list_renders("demo")[0]["trimmed_tail"] is None
