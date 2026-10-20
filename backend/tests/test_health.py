import pytest
from fastapi.testclient import TestClient

from hbt.api import health
from hbt.main import app

client = TestClient(app)

ENCODERS = """Encoders:
 V..... = Video
 ------
 V....D a64multi             Multicolor charset for Commodore 64 (codec a64_multi)
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC (codec h264)
 A....D aac                  AAC (Advanced Audio Coding)
"""

FILTERS = """Filters:
  T.. = Timeline support
  | = Source or sink filter
  ------
 .. loudnorm          A->A       EBU R128 loudness normalization
 .. sidechaincompress AA->A      Sidechain compressor.
 .. silencedetect     A->A       Detect silence.
 .S xfade             VV->V      Cross fade one video with another video.
 .. zoompan           V->V       Apply Zoom & Pan effect.
"""


def fake_ffmpeg(monkeypatch, encoders=ENCODERS, filters=FILTERS, runs=True):
    outputs = {"-version": "ffmpeg version 9.0", "-encoders": encoders, "-filters": filters}
    monkeypatch.setattr(health, "_ffmpeg_stdout", lambda arg: outputs[arg] if runs else None)
    monkeypatch.setattr(health, "check_whisper", lambda: False)
    monkeypatch.setattr(health, "check_gpu", lambda: False)


def test_health_shape():
    body = client.get("/api/health").json()
    assert set(body) == {"ok", "ffmpeg", "whisper", "gpu", "missing"}
    assert all(isinstance(body[k], bool) for k in ("ok", "ffmpeg", "whisper", "gpu"))
    assert isinstance(body["missing"], list)


def test_parse_names_skips_header_legend():
    assert health.parse_names(ENCODERS) == {"a64multi", "libx264", "aac"}
    names = health.parse_names(FILTERS)
    assert "zoompan" in names and "=" not in names and "Source" not in names


def test_ok_when_everything_present(monkeypatch):
    fake_ffmpeg(monkeypatch)
    assert client.get("/api/health").json() == {
        "ok": True,
        "ffmpeg": True,
        "whisper": False,
        "gpu": False,
        "missing": [],
    }


def test_missing_encoder_and_filter(monkeypatch):
    fake_ffmpeg(
        monkeypatch,
        encoders=ENCODERS.replace("libx264 ", "libx265 "),
        filters=FILTERS.replace(" xfade ", " blend "),
    )
    body = client.get("/api/health").json()
    assert body["ok"] is False
    assert body["ffmpeg"] is True
    assert body["missing"] == ["libx264", "xfade"]


def test_ffmpeg_not_runnable(monkeypatch):
    fake_ffmpeg(monkeypatch, runs=False)
    body = client.get("/api/health").json()
    assert body["ok"] is False
    assert body["ffmpeg"] is False
    assert body["missing"] == ["ffmpeg"]


def test_ffmpeg_stdout_missing_binary(monkeypatch):
    monkeypatch.setattr(health.shutil, "which", lambda _: None)
    assert health._ffmpeg_stdout("-version") is None


@pytest.mark.parametrize("returncode", [1, 255])
def test_ffmpeg_stdout_nonzero_exit(monkeypatch, returncode):
    monkeypatch.setattr(health.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(
        health.subprocess,
        "run",
        lambda *a, **k: health.subprocess.CompletedProcess(a, returncode, stdout="x"),
    )
    assert health._ffmpeg_stdout("-version") is None


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
