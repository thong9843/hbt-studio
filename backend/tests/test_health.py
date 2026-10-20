import subprocess

import pytest
from fastapi.testclient import TestClient

from hbt.api import health
from hbt.main import app

client = TestClient(app)


def test_health_shape():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"ok", "ffmpeg", "whisper", "gpu"}
    assert all(isinstance(v, bool) for v in body.values())


@pytest.mark.parametrize("ffmpeg", [True, False])
def test_ok_follows_ffmpeg(monkeypatch, ffmpeg):
    monkeypatch.setattr(health, "check_ffmpeg", lambda: ffmpeg)
    monkeypatch.setattr(health, "check_whisper", lambda: False)
    monkeypatch.setattr(health, "check_gpu", lambda: False)
    assert client.get("/api/health").json() == {
        "ok": ffmpeg,
        "ffmpeg": ffmpeg,
        "whisper": False,
        "gpu": False,
    }


def test_check_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda _: None)
    assert health.check_ffmpeg() is False


def test_check_ffmpeg_nonzero_exit(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        health.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=1),
    )
    assert health.check_ffmpeg() is False


def test_check_whisper_not_installed(monkeypatch):
    def fail(name):
        raise ImportError(name)

    monkeypatch.setattr(health.importlib, "import_module", fail)
    assert health.check_whisper() is False
    assert health.check_gpu() is False


def test_cors_allows_vite_only():
    ok = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
