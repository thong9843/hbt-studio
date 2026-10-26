"""Nạp DLL CUDA của pip (`site-packages/nvidia/*/bin`) cho tiến trình con Whisper trên Windows."""

import os
import sys

import pytest

from hbt.pipeline import whisper_worker


@pytest.fixture
def site(monkeypatch, tmp_path):
    """Giả lập site-packages; ghi lại các lần gọi add_dll_directory."""
    monkeypatch.setattr(whisper_worker.sysconfig, "get_paths", lambda: {"purelib": str(tmp_path)})
    monkeypatch.setattr(whisper_worker.site, "getsitepackages", lambda: [str(tmp_path)])
    monkeypatch.setenv("PATH", "C:/sys")
    calls: list[str] = []
    monkeypatch.setattr(os, "add_dll_directory", calls.append, raising=False)
    return tmp_path, calls


def test_windows_with_nvidia_dirs_adds_each_and_prepends_path(monkeypatch, site):
    root, calls = site
    monkeypatch.setattr(sys, "platform", "win32")
    for pkg in ("cublas", "cudnn"):
        (root / "nvidia" / pkg / "bin").mkdir(parents=True)
    (root / "nvidia" / "empty").mkdir()  # không có bin → bỏ qua
    added = whisper_worker.add_cuda_dll_dirs()
    want = [str(root / "nvidia" / "cublas" / "bin"), str(root / "nvidia" / "cudnn" / "bin")]
    assert added == want and calls == want
    assert os.environ["PATH"].split(os.pathsep)[:3] == [*want, "C:/sys"]


def test_windows_without_nvidia_does_nothing(monkeypatch, site):
    _, calls = site
    monkeypatch.setattr(sys, "platform", "win32")
    assert whisper_worker.add_cuda_dll_dirs() == []
    assert calls == [] and os.environ["PATH"] == "C:/sys"


def test_non_windows_does_nothing(monkeypatch, site):
    root, calls = site
    (root / "nvidia" / "cublas" / "bin").mkdir(parents=True)
    monkeypatch.setattr(sys, "platform", "linux")
    assert whisper_worker.add_cuda_dll_dirs() == []
    assert calls == [] and os.environ["PATH"] == "C:/sys"


def test_oserror_on_one_dir_is_logged_and_the_rest_still_added(monkeypatch, site, capsys):
    root, _ = site
    monkeypatch.setattr(sys, "platform", "win32")
    bad = str(root / "nvidia" / "cublas" / "bin")
    good = str(root / "nvidia" / "cudnn" / "bin")
    for d in (bad, good):
        os.makedirs(d)
    added: list[str] = []

    def add(d):
        if d == bad:
            raise OSError("không nạp được")
        added.append(d)

    monkeypatch.setattr(os, "add_dll_directory", add, raising=False)
    assert whisper_worker.add_cuda_dll_dirs() == [good]
    assert added == [good]
    assert os.environ["PATH"].split(os.pathsep)[:2] == [good, "C:/sys"]
    err = capsys.readouterr().err
    assert bad in err and "không nạp được" in err


def test_dirs_are_added_before_faster_whisper_is_imported(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(whisper_worker, "add_cuda_dll_dirs", lambda: order.append("dll") or [])

    class Boom(Exception):
        pass

    class FakeModule:
        def __getattr__(self, name):
            order.append("import")
            raise Boom

    monkeypatch.setitem(sys.modules, "faster_whisper", FakeModule())
    with pytest.raises(Boom):
        whisper_worker.run({})
    assert order[0] == "dll" and "import" in order
