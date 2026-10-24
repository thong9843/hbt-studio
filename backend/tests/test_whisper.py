"""Chạy Whisper trong tiến trình con: bậc rơi, hết giờ, huỷ job, nạp model có sẵn.

Không cần model hay GPU: `worker_command` được thay bằng một script giả hành xử theo biến môi trường
`FAKE_CUDA` / `FAKE_CPU` (ok | load_error | run_error | crash | hang | empty)."""

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from hbt.pipeline import whisper
from hbt.pipeline.cancel import CancelToken, RenderCancelled, use_token
from hbt.pipeline.whisper import Step, WhisperConfig, WhisperFailed, WhisperTimeout

FAKE_WORKER = r"""
import json, os, sys, time
req = json.load(open(sys.argv[1], encoding="utf-8"))
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(req) + "\n")
mode = os.environ.get("FAKE_" + req["device"].upper(), "ok")
def write(data):
    open(req["out"], "w", encoding="utf-8").write(json.dumps(data))
if mode == "ok":
    write({"ok": True, "syllables": [["xin", 0.5, 0.8], ["chao", 0.8, 1.1]]}); sys.exit(0)
if mode == "empty":
    write({"ok": True, "syllables": []}); sys.exit(0)
if mode in ("load_error", "run_error"):
    write({"ok": False, "stage": mode.split("_")[0], "error": "RuntimeError: cublas64_12.dll"})
    sys.exit(1)
if mode == "crash":
    sys.stderr.write("access violation"); sys.exit(3)
time.sleep(120)  # hang
"""


@pytest.fixture
def fake(monkeypatch, tmp_path):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setattr(
        whisper, "worker_command", lambda req: [sys.executable, "-c", FAKE_WORKER, str(req)]
    )
    procs: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def recording_popen(*a, **k):
        p = real_popen(*a, **k)
        procs.append(p)
        return p

    monkeypatch.setattr(whisper.subprocess, "Popen", recording_popen)

    class Fake:
        def requests(self):
            return (
                [json.loads(x) for x in log.read_text("utf-8").splitlines()] if log.exists() else []
            )

        processes = procs

    return Fake()


def cfg(tmp_path, **kw):
    return WhisperConfig(models_dir=tmp_path / "models", **{"timeout": 30, **kw})


CUDA = Step("cuda", "int8_float16", "large-v3")
CPU = Step("cpu", "int8", "small")


@pytest.mark.parametrize(
    ("model", "device", "gpu", "expected"),
    [
        ("auto", "auto", True, [CUDA, CPU]),
        ("auto", "auto", False, [CPU]),
        ("auto", "cpu", True, [CPU]),
        ("auto", "cuda", False, [CUDA, CPU]),
        ("medium", "auto", False, [Step("cpu", "int8", "medium")]),
        (
            "medium",
            "auto",
            True,
            [Step("cuda", "int8_float16", "medium"), Step("cpu", "int8", "medium")],
        ),
    ],
)
def test_plan_steps_follows_the_hardware(model, device, gpu, expected):
    assert whisper.plan_steps(model, device, gpu) == expected


@pytest.mark.parametrize(
    ("app", "env", "expected"),
    [("small", "large-v3", "small"), ("auto", "medium", "medium"), ("auto", "auto", "auto")],
)
def test_app_settings_override_env(app, env, expected):
    assert whisper.effective_model(app, env) == expected


def test_cuda_ok_does_not_touch_the_cpu_step(fake, tmp_path):
    run = whisper.run_whisper("v.wav", "p", cfg(tmp_path), steps=[CUDA, CPU])
    assert run.step == CUDA and run.skipped == []
    assert [r["device"] for r in fake.requests()] == ["cuda"]
    assert run.syllables[0] == ("xin", 0.5, 0.8)


@pytest.mark.parametrize(
    ("mode", "reason"), [("load_error", "lúc nạp model"), ("run_error", "lúc chạy")]
)
def test_cuda_failure_falls_back_to_cpu_and_logs_why(fake, tmp_path, monkeypatch, mode, reason):
    monkeypatch.setenv("FAKE_CUDA", mode)
    logs: list[str] = []
    run = whisper.run_whisper("v.wav", "p", cfg(tmp_path), logs.append, steps=[CUDA, CPU])
    assert run.step == CPU
    assert len(run.skipped) == 1 and reason in run.skipped[0] and "cublas64_12" in run.skipped[0]
    assert any(reason in line and "thử bậc kế" in line for line in logs)
    assert [r["device"] for r in fake.requests()] == ["cuda", "cpu"]


def test_process_crash_is_reported_with_exit_code(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CPU", "crash")
    with pytest.raises(WhisperFailed, match="thoát mã 3.*access violation"):
        whisper.run_whisper("v.wav", "p", cfg(tmp_path), steps=[CPU])


def test_every_step_failing_raises_with_all_reasons(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CUDA", "load_error")
    monkeypatch.setenv("FAKE_CPU", "empty")
    with pytest.raises(WhisperFailed) as err:
        whisper.run_whisper("v.wav", "p", cfg(tmp_path), steps=[CUDA, CPU])
    assert "large-v3 (cuda" in str(err.value) and "không nhận ra giọng nói" in str(err.value)


def test_timeout_kills_the_child_and_skips_remaining_steps(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CUDA", "hang")
    with pytest.raises(WhisperTimeout, match="quá giới hạn 1 giây"):
        whisper.run_whisper("v.wav", "p", cfg(tmp_path, timeout=1), steps=[CUDA, CPU])
    assert [r["device"] for r in fake.requests()] == ["cuda"]  # không sang bậc CPU: hết ngân sách
    assert fake.processes and all(p.poll() is not None for p in fake.processes)


def test_cancel_kills_the_child_and_raises(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CPU", "hang")
    token = CancelToken()
    threading.Timer(1.0, token.cancel).start()
    with use_token(token), pytest.raises(RenderCancelled):
        whisper.run_whisper("v.wav", "p", cfg(tmp_path), steps=[CPU])
    assert fake.processes and all(p.poll() is not None for p in fake.processes)


def make_model(models_dir, name):
    snap = models_dir / f"models--Systran--faster-whisper-{name}" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (snap / "model.bin").write_bytes(b"x")


def test_model_already_in_models_dir_is_loaded_locally(fake, tmp_path):
    make_model(tmp_path / "models", "small")
    assert whisper.model_cached(tmp_path / "models", "small")
    whisper.run_whisper("v.wav", "p", cfg(tmp_path), steps=[CPU])
    req = fake.requests()[0]
    assert req["local_only"] is True
    assert req["models_dir"] == str(tmp_path / "models") and req["model"] == "small"


def test_missing_model_is_allowed_to_download_into_models_dir(fake, tmp_path):
    assert not whisper.model_cached(tmp_path / "models", "small")
    whisper.run_whisper("v.wav", "p", cfg(tmp_path), steps=[CPU])
    assert fake.requests()[0]["local_only"] is False


def test_only_the_cached_model_counts(tmp_path):
    make_model(tmp_path / "models", "small")
    assert not whisper.model_cached(tmp_path / "models", "large-v3")
    assert not whisper.model_cached(tmp_path / "missing", "small")


def test_worker_turns_whisper_words_into_syllables():
    from types import SimpleNamespace as NS

    from hbt.pipeline.whisper_worker import syllables_of

    seg = NS(words=[NS(word=" Xin", start=0.0, end=0.4), NS(word=" chào các", start=0.4, end=1.0)])
    out = syllables_of([seg, NS(words=None)])
    assert [s for s, _, _ in out] == ["xin", "chao", "cac"]
    assert out[1][1:] == pytest.approx([0.4, 0.7]) and out[2][1:] == pytest.approx([0.7, 1.0])


def test_worker_reports_the_stage_of_a_failure(tmp_path, monkeypatch):
    """Worker thật, nhưng `faster_whisper` giả: lỗi lúc nạp và lỗi lúc chạy được phân biệt."""
    from types import ModuleType

    from hbt.pipeline import whisper_worker

    class Model:
        def __init__(self, *a, **k):
            if k["device"] == "cuda":
                raise RuntimeError("CUDA driver version is insufficient")

        def transcribe(self, *a, **k):
            raise RuntimeError("cublas64_12.dll not found")

    fake_mod = ModuleType("faster_whisper")
    fake_mod.WhisperModel = Model
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    base = {"model": "small", "compute_type": "int8", "models_dir": "m", "local_only": False,
            "wav": "v.wav", "prompt": "p"}  # fmt: skip
    results = {}
    for device in ("cuda", "cpu"):
        out = tmp_path / f"{device}.json"
        req = tmp_path / f"{device}-req.json"
        req.write_text(json.dumps({**base, "device": device, "out": str(out)}), "utf-8")
        assert whisper_worker.main(["w", str(req)]) == 1
        results[device] = json.loads(out.read_text("utf-8"))
    assert results["cuda"]["stage"] == "load" and "insufficient" in results["cuda"]["error"]
    assert results["cpu"]["stage"] == "run" and "cublas" in results["cpu"]["error"]


def test_relative_paths_are_made_absolute_for_the_child(fake, tmp_path, monkeypatch):
    """Tiến trình con chạy ở thư mục khác: đường dẫn tương đối của người gọi phải được đổi."""
    (tmp_path / "v.wav").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    whisper.run_whisper("v.wav", "p", WhisperConfig(models_dir=Path("models")), steps=[CPU])
    req = fake.requests()[0]
    assert Path(req["wav"]) == tmp_path / "v.wav"
    assert Path(req["models_dir"]) == tmp_path / "models"
