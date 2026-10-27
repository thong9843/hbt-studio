"""`compose()` không để lại `video.part.mp4` khi bị huỷ hoặc lỗi giữa vòng ghi khung."""

import threading
import time

import pytest

from hbt.pipeline import render
from hbt.pipeline.cancel import CancelToken, RenderCancelled
from tests.helpers import needs_ffmpeg
from tests.test_render import make_project

pytestmark = needs_ffmpeg


def mp4_files(pdir):
    (job_dir,) = list((pdir / "renders").iterdir())
    return sorted(p.name for p in job_dir.glob("*.mp4"))


def test_cancel_between_frame_writes_leaves_no_partial_video(tmp_path):
    """Huỷ bật từ chính luồng dựng, đúng lúc luồng đang ở giữa hai lần ghi khung (check_current
    ném RenderCancelled trong vòng ghi, không qua BrokenPipe) — đường từng để lại file dở."""
    pdir, opts = make_project(tmp_path, n=8)
    token = CancelToken()

    def progress(pct, step, message):
        if step == "Ghép cuối" and pct > 80:  # compose đã mở bộ mã hoá và ghi khung đầu
            token.cancel()

    with pytest.raises(RenderCancelled):
        render.render_project(pdir, opts, progress=progress, cancel_token=token)
    assert mp4_files(pdir) == []


def test_cancel_with_slow_frame_production_leaves_no_partial_video(tmp_path, monkeypatch):
    """Máy chậm: mỗi khung tốn thêm thời gian nên luồng hầu như luôn ở giữa hai lần ghi."""
    real_get = render.FrameReader.get

    def slow_get(self, i):
        time.sleep(0.01)
        return real_get(self, i)

    monkeypatch.setattr(render.FrameReader, "get", slow_get)
    pdir, opts = make_project(tmp_path, n=8)
    token = CancelToken()
    reached = threading.Event()
    result: dict = {}

    def progress(pct, step, message):
        if step == "Ghép cuối" and pct > 80:
            reached.set()

    def work():
        try:
            render.render_project(pdir, opts, progress=progress, cancel_token=token)
        except BaseException as e:  # noqa: BLE001
            result["error"] = e

    t = threading.Thread(target=work)
    t.start()
    assert reached.wait(60)
    time.sleep(0.3)
    token.cancel()
    t.join(30)
    assert not t.is_alive()
    assert isinstance(result.get("error"), RenderCancelled), result
    assert mp4_files(pdir) == []


def test_real_error_mid_loop_removes_partial_and_keeps_original_error(tmp_path, monkeypatch):
    real_get = render.FrameReader.get
    calls = {"n": 0}

    def failing_get(self, i):
        calls["n"] += 1
        if calls["n"] == 5:
            raise RuntimeError("boom giữa vòng ghi")
        return real_get(self, i)

    monkeypatch.setattr(render.FrameReader, "get", failing_get)
    pdir, opts = make_project(tmp_path, n=8)
    with pytest.raises(RuntimeError, match="boom giữa vòng ghi"):
        render.render_project(pdir, opts)
    assert mp4_files(pdir) == []


def test_remove_partial_retries_then_only_warns(tmp_path, monkeypatch):
    partial = tmp_path / "video.part.mp4"
    partial.write_bytes(b"x")
    attempts = {"n": 0}
    real_unlink = type(partial).unlink

    def locked(self, missing_ok=False):
        attempts["n"] += 1
        raise PermissionError("đang bị giữ")

    monkeypatch.setattr(type(partial), "unlink", locked)
    monkeypatch.setattr(render.time, "sleep", lambda s: None)
    render._remove_partial(partial)  # không ném
    assert attempts["n"] == render.PARTIAL_UNLINK_TRIES

    attempts["n"] = 0

    def flaky(self, missing_ok=False):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise PermissionError("đang bị giữ")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(type(partial), "unlink", flaky)
    render._remove_partial(partial)
    assert attempts["n"] == 3 and not partial.exists()
