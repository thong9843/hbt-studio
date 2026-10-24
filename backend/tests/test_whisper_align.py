"""Căn chữ bằng Whisper: so khớp, tích hợp vào bộ dựng, cache `timing.json`, rơi về khoảng lặng.

Whisper được giả bằng `render.run_whisper` (không cần model, không cần GPU)."""

import json
import shutil

import pytest

from hbt.app_settings import AppSettingsStore
from hbt.jobs import JobManager
from hbt.pipeline import align, render
from hbt.pipeline.render import RenderError, render_project
from hbt.pipeline.text import parse_voice
from hbt.pipeline.whisper import Step, WhisperFailed, WhisperRun
from hbt.storage import Storage
from tests.helpers import needs_ffmpeg, write_wav
from tests.test_jobs import FakeRender, wait_for
from tests.test_render import SENTENCES, make_project

CPU_SMALL = Step("cpu", "int8", "small")


# ---------------------------------------------------------------- so khớp
def heard_for(script, drop_last=False):
    tokens = parse_voice(script)
    sylls = [s for t in tokens for s in t["syl"]]
    heard = [(s, 0.5 + i * 0.3, 0.8 + i * 0.3) for i, s in enumerate(sylls)]
    return tokens, heard[:-1] if drop_last else heard


def test_match_script_reports_ratio_and_last_token():
    tokens, heard = heard_for("Xin chào các bạn.")
    m = align.match_script(tokens, heard)
    assert m.matched_ratio == 1.0 and m.last_token_matched
    assert m.last_matched_end == pytest.approx(heard[-1][2]) == pytest.approx(m.heard_end)


def test_match_script_last_token_missing_is_not_matched():
    tokens, heard = heard_for("Xin chào các bạn.", drop_last=True)
    m = align.match_script(tokens, heard)
    assert m.matched_ratio == 0.75 and not m.last_token_matched
    assert m.last_matched_end == pytest.approx(heard[-1][2])
    assert m.times[-1][1] >= m.times[-1][0]  # vẫn có mốc (nội suy)


def test_match_script_counts_unmatched_syllables_in_the_ratio():
    tokens = parse_voice("Một hai ba bốn.")
    heard = [("mot", 0, 1), ("ba", 2, 3), ("bon", 3, 4), ("quang", 4, 5), ("cao", 5, 6)]
    m = align.match_script(tokens, heard)
    assert m.matched_ratio == 0.75 and m.last_token_matched is True
    assert m.heard_end == 6


def test_match_script_without_speech_raises():
    with pytest.raises(RuntimeError, match="Whisper"):
        align.match_script(parse_voice("Xin chào."), [])


# ---------------------------------------------------------------- dựng đầu-cuối
class FakeWhisper:
    """Thay `render.run_whisper`: nghe đúng kịch bản của make_project (mỗi câu 1,0 s)."""

    def __init__(self, extra=(), drop_last=False, fail=None):
        self.calls = []
        self.extra, self.drop_last, self.fail = extra, drop_last, fail

    def __call__(self, wav, prompt, cfg, log=print, *, steps=None):
        self.calls.append(cfg)
        if self.fail:
            raise self.fail
        syl = []
        for i, sentence in enumerate(SENTENCES):
            toks = [s for t in parse_voice(sentence) for s in t["syl"]]
            start = 0.5 + i * 1.8  # 0,3 lặng đầu + 0,2 trễ giọng
            n = len(toks)
            syl += [(s, start + k / n, start + (k + 1) / n) for k, s in enumerate(toks)]
        if self.drop_last:
            syl = syl[:-1]
        syl += list(self.extra)
        log(f"Whisper {CPU_SMALL.label}…")
        return WhisperRun(syl, CPU_SMALL, 3.2)


@pytest.fixture
def fake_whisper(monkeypatch):
    fake = FakeWhisper()
    monkeypatch.setattr(render, "run_whisper", fake)
    return fake


@needs_ffmpeg
def test_auto_uses_whisper_and_records_how(tmp_path, fake_whisper):
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    res = render_project(pdir, opts)
    assert res.aligner == "whisper" and res.aligner_info["model"] == "small"
    meta = json.loads((res.job_dir / "meta.json").read_text("utf-8"))
    assert meta["aligner"] == "whisper"
    assert meta["aligner_info"]["device"] == "cpu" and meta["aligner_info"]["match_ratio"] == 1.0
    assert meta["aligner_info"]["last_token_matched"] is True
    log = res.log.read_text("utf-8")
    assert "Căn phụ đề bằng Whisper small (cpu, int8): khớp 100,0% âm tiết" in log
    assert "Aligner đã dùng: whisper" in log
    timing = json.loads((pdir / "build" / "timing.json").read_text("utf-8"))
    assert timing["aligner"] == "whisper" and timing["info"]["model"] == "small"


@needs_ffmpeg
def test_whisper_failure_falls_back_to_silence_and_says_why(tmp_path, fake_whisper):
    fake_whisper.fail = WhisperFailed("large-v3 (cuda, int8_float16): lỗi lúc chạy: cublas")
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    res = render_project(pdir, opts)
    assert res.aligner == "silence"
    assert "cublas" in res.aligner_info["whisper_error"]
    log = res.log.read_text("utf-8")
    assert "Không dùng được Whisper (large-v3 (cuda, int8_float16): lỗi lúc chạy: cublas)" in log
    assert "Aligner đã dùng: silence" in log


@needs_ffmpeg
def test_aligner_whisper_does_not_fall_back(tmp_path, fake_whisper):
    fake_whisper.fail = WhisperFailed("hết giờ")
    pdir, opts = make_project(tmp_path, aligner="whisper", outro=False)
    with pytest.raises(RenderError, match="Whisper không chạy được: hết giờ"):
        render_project(pdir, opts)


@needs_ffmpeg
def test_aligner_silence_never_calls_whisper(tmp_path, fake_whisper):
    pdir, opts = make_project(tmp_path, aligner="silence", outro=False)
    assert render_project(pdir, opts).aligner == "silence"
    assert fake_whisper.calls == []


@needs_ffmpeg
def test_timing_cache_hit_skips_whisper(tmp_path, fake_whisper):
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    render_project(pdir, opts)
    res = render_project(pdir, opts)
    assert len(fake_whisper.calls) == 1
    assert "Mốc thời gian chữ: dùng bản đã có (aligner: whisper)" in res.log.read_text("utf-8")
    assert res.aligner == "whisper" and res.aligner_info["model"] == "small"


@needs_ffmpeg
@pytest.mark.parametrize("change", ["script", "model", "timeout", "aligner"])
def test_timing_cache_miss(tmp_path, fake_whisper, change):
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    render_project(pdir, opts)
    p = pdir / "project.json"
    data = json.loads(p.read_text("utf-8"))
    if change == "script":
        data["scenes"][0]["voice"] = "Xin chào tất cả các bạn."
        p.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    elif change == "model":
        opts.whisper_model = "medium"
    elif change == "timeout":
        opts.whisper_timeout = 300
    else:
        data["settings"]["aligner"] = "whisper"
        p.write_text(json.dumps(data), "utf-8")
    render_project(pdir, opts)
    assert len(fake_whisper.calls) == 2


@needs_ffmpeg
def test_timing_cache_miss_when_voice_changes(tmp_path, fake_whisper):
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    render_project(pdir, opts)
    write_wav(pdir / "voice.wav", [("gap", 0.3), ("tone", 1.0), ("gap", 0.8)] * 3, freq=500)
    render_project(pdir, opts)
    assert len(fake_whisper.calls) == 2


@needs_ffmpeg
@pytest.mark.parametrize(
    ("app", "env", "expected"),
    [("auto", "auto", "auto"), ("auto", "medium", "medium"), ("small", "medium", "small")],
)
def test_model_setting_precedence_reaches_whisper(
    tmp_path, fake_whisper, monkeypatch, app, env, expected
):
    monkeypatch.setenv("WHISPER_MODEL", env)
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    opts.whisper_model, opts.whisper_timeout = app, 123
    render_project(pdir, opts)
    cfg = fake_whisper.calls[0]
    assert (cfg.model, cfg.device, cfg.timeout) == (expected, "cpu", 123)


# ---------------------------------------------------------------- Cài đặt → job
def test_job_passes_whisper_settings_from_app_settings(tmp_path):
    pdir, opts = make_project(tmp_path / "src")
    store = Storage(tmp_path / "workspace")
    shutil.copytree(pdir, store.projects_dir / "demo")
    app = AppSettingsStore(tmp_path / "workspace")
    app.save(
        app.load().model_copy(update={"whisper_model": "medium", "whisper_timeout_seconds": 321})
    )
    seen = []
    fake = FakeRender()
    fake.gate.set()

    def render_fn(folder, o, progress=None, cancel_token=None):
        seen.append((o.whisper_model, o.whisper_timeout))
        return fake(folder, o, progress, cancel_token)

    mgr = JobManager(
        store,
        opts.library_dir,
        opts.brand_dir,
        render_fn=render_fn,
        tool_check=None,
        app_settings=app,
    )
    job = mgr.submit("demo", preview=True)
    assert wait_for(lambda: job.finished)
    assert seen == [("medium", 321)]


# ---------------------------------------------------------------- mốc cảnh không dùng được
@pytest.mark.parametrize(
    ("offsets", "ok"),
    [
        ([1.0, 2.0], True),
        ([0.0, 2.0], False),
        ([1.0, 1.0], False),
        ([2.0, 1.0], False),
        ([], False),
    ],
)
def test_offsets_valid(offsets, ok):
    assert render.offsets_valid(offsets) is ok


class ZeroWidthWhisper(FakeWhisper):
    """Whisper cho mọi âm tiết ở mốc 0,0 (như small CPU bỏ sót nửa đầu kịch bản)."""

    def __call__(self, wav, prompt, cfg, log=print, *, steps=None):
        run = super().__call__(wav, prompt, cfg, log, steps=steps)
        run.syllables = [(s, 0.0, 0.0) for s, _, _ in run.syllables]
        return run


@needs_ffmpeg
def test_unusable_scene_marks_fall_back_to_silence_instead_of_failing(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "run_whisper", ZeroWidthWhisper())
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    res = render_project(pdir, opts)
    assert res.aligner == "silence"
    assert "mốc chuyển cảnh từ Whisper không hợp lệ" in res.aligner_info["whisper_error"]
    assert "khớp" in res.log.read_text("utf-8")


@needs_ffmpeg
def test_unusable_scene_marks_fail_when_whisper_is_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "run_whisper", ZeroWidthWhisper())
    pdir, opts = make_project(tmp_path, aligner="whisper", outro=False)
    with pytest.raises(RenderError, match="mốc chuyển cảnh từ Whisper không hợp lệ"):
        render_project(pdir, opts)
