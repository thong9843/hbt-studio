import shutil
import subprocess
import sys
import threading
import time

import pytest

from hbt.pipeline import cancel
from hbt.pipeline.cancel import CancelToken, RenderCancelled, use_token
from hbt.pipeline.ffutil import run_ffmpeg
from hbt.pipeline.render import render_project
from tests.helpers import needs_ffmpeg
from tests.test_render import make_project

SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


def ffmpeg_process_count() -> int:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
        ).stdout
        return sum(1 for line in out.splitlines() if line.lower().startswith('"ffmpeg.exe"'))
    pgrep = shutil.which("pgrep")
    if pgrep is None:
        return 0
    out = subprocess.run([pgrep, "-c", "-x", "ffmpeg"], capture_output=True, text=True).stdout
    return int(out.strip() or 0)


def describe_ffmpeg_processes() -> str:
    """Danh sách tiến trình ffmpeg kèm trạng thái (Z = zombie), để chẩn đoán khi test fail."""
    if sys.platform == "win32":
        cmd = ["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe"]
    else:
        cmd = ["ps", "-eo", "pid,ppid,stat,etime,args"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    lines = [x for x in out.splitlines() if "ffmpeg" in x.lower() or x.lstrip().startswith("PID")]
    return "tiến trình ffmpeg còn sót:\n" + "\n".join(lines)


def record_subprocesses(monkeypatch) -> list:
    """Ghi lại mọi tiến trình con được tạo trong test (kể cả do thư viện khác tạo)."""
    made: list = []

    class Recording(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            made.append(self)

    monkeypatch.setattr(subprocess, "Popen", Recording)
    return made


def wait_until(predicate, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


# ---------------------------------------------------------------- token
def test_cancel_sets_flag_and_check_raises():
    token = CancelToken()
    token.check()  # chưa huỷ thì không làm gì
    assert not token.cancelled
    token.cancel()
    assert token.cancelled
    with pytest.raises(RenderCancelled):
        token.check()


def test_cancel_kills_tracked_processes():
    token = CancelToken()
    proc = subprocess.Popen(SLEEPER)
    token.track(proc)
    token.cancel()
    assert wait_until(lambda: proc.poll() is not None, 5)


def test_untracked_process_is_left_alone():
    token = CancelToken()
    proc = subprocess.Popen(SLEEPER)
    try:
        token.track(proc)
        token.untrack(proc)
        token.cancel()
        time.sleep(0.3)
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait()


def test_process_started_after_cancel_is_killed_at_once():
    token = CancelToken()
    token.cancel()
    proc = subprocess.Popen(SLEEPER)
    token.track(proc)
    assert wait_until(lambda: proc.poll() is not None, 5)


def test_use_token_scopes_and_restores():
    assert cancel.current() is None
    a, b = CancelToken(), CancelToken()
    with use_token(a):
        assert cancel.current() is a
        with use_token(b):
            assert cancel.current() is b
        assert cancel.current() is a
    assert cancel.current() is None
    cancel.check_current()  # không có token: bỏ qua


def test_check_current_raises_when_the_active_token_is_cancelled():
    token = CancelToken()
    with use_token(token):
        token.cancel()
        with pytest.raises(RenderCancelled):
            cancel.check_current()


# ---------------------------------------------------------------- ffmpeg thật
@needs_ffmpeg
def test_run_ffmpeg_does_not_start_when_already_cancelled():
    token = CancelToken()
    token.cancel()
    before = ffmpeg_process_count()
    with use_token(token), pytest.raises(RenderCancelled):
        run_ffmpeg(["-f", "lavfi", "-i", "anullsrc", "-t", "1", "-f", "null", "-"])
    assert ffmpeg_process_count() <= before


@needs_ffmpeg
def test_run_ffmpeg_is_interrupted_by_cancel():
    token = CancelToken()
    result: dict = {}

    def work():
        try:
            with use_token(token):
                # ~50 phút video giả: nếu không bị huỷ sẽ chạy rất lâu
                run_ffmpeg(
                    ["-f", "lavfi", "-i", "testsrc=s=1280x720:r=60:d=3000", "-f", "null", "-"]
                )
            result["ok"] = True
        except BaseException as e:  # noqa: BLE001
            result["error"] = e

    before = ffmpeg_process_count()
    t = threading.Thread(target=work)
    t.start()
    assert wait_until(lambda: ffmpeg_process_count() > before, 10)  # ffmpeg đã thật sự chạy
    started = time.time()
    token.cancel()
    t.join(15)
    assert not t.is_alive()
    assert isinstance(result.get("error"), RenderCancelled)
    assert time.time() - started < 5
    assert wait_until(lambda: ffmpeg_process_count() <= before, 5)


# ---------------------------------------------------------------- dựng đầu-cuối bị huỷ
@needs_ffmpeg
@pytest.mark.parametrize("step", ["Clip từng cảnh", "Ghép cuối"])
@pytest.mark.slow
def test_render_cancelled_midway_leaves_nothing_running(tmp_path, step, monkeypatch):
    recorder = record_subprocesses(monkeypatch)
    pdir, opts = make_project(tmp_path, n=8)
    token = CancelToken()
    reached = threading.Event()
    result: dict = {}

    def progress(pct, current_step, message):
        if current_step == step:
            reached.set()

    def work():
        try:
            render_project(pdir, opts, progress=progress, cancel_token=token)
            result["ok"] = True
        except BaseException as e:  # noqa: BLE001
            result["error"] = e

    before = ffmpeg_process_count()
    t = threading.Thread(target=work)
    t.start()
    assert reached.wait(60), f"không tới bước {step}"
    time.sleep(0.2)
    token.cancel()
    t.join(30)
    assert not t.is_alive()
    assert isinstance(result.get("error"), RenderCancelled), result
    renders = list((pdir / "renders").iterdir())
    assert len(renders) == 1
    assert not (renders[0] / "meta.json").exists()
    assert not list(renders[0].glob("*.mp4")), "để lại video dang dở"
    assert wait_until(lambda: ffmpeg_process_count() <= before, 10), describe_ffmpeg_processes()
    # Mọi tiến trình con đã được thu dọn (wait): chưa wait thì trên Linux thành zombie "<defunct>".
    # `returncode` chỉ được đặt khi wait()/poll() đã chạy, nên kiểm tra được trên cả Windows.
    unreaped = [p.args[:1] for p in recorder if p.returncode is None]
    assert not unreaped, f"tiến trình con chưa được thu dọn: {unreaped}"


@needs_ffmpeg
@pytest.mark.slow
def test_render_without_token_is_unaffected(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    res = render_project(pdir, opts)
    assert res.video.is_file() and (res.job_dir / "meta.json").is_file()
    assert cancel.current() is None


@needs_ffmpeg
@pytest.mark.slow
def test_job_id_names_the_render_folder_and_meta_is_written(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    opts.job_id = "abc123"
    res = render_project(pdir, opts)
    assert res.job_dir.name == "abc123"
    import json

    meta = json.loads((res.job_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["job_id"] == "abc123" and meta["preview"] is True and meta["fps"] == 30
    assert meta["created_at"].endswith("Z") and meta["duration"] == pytest.approx(
        res.duration, abs=0.01
    )
