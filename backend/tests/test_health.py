import pytest
from fastapi.testclient import TestClient

from hbt.api import health
from hbt.main import create_app
from hbt.postv.voice import FakeVoice

client = TestClient(create_app(voice=FakeVoice(ok=False)))  # VieNeu: không phụ thuộc máy

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
    assert set(body) == {"ok", "ffmpeg", "whisper", "gpu", "vieneu", "vieneu_note", "missing"}
    assert all(isinstance(body[k], bool) for k in ("ok", "ffmpeg", "whisper", "gpu", "vieneu"))
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
        "vieneu": False,
        "vieneu_note": "Chưa cài VieNeu (giả)",
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


# Đầu ra thật của FFmpeg 6.1.1 (Ubuntu 24.04, lấy từ CI): `-filters` KHÔNG có dòng `------`,
# cờ có 3 ký tự. Bản 9.0 (Windows) có dòng đó và cờ 2 ký tự.
FILTERS_61 = """Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
  A = Audio input/output
  V = Video input/output
  N = Dynamic number and/or type of input/output
  | = Source or sink filter
 ... abench            A->A       Benchmark part of a filtergraph.
 ..C acompressor       A->A       Audio compressor.
 ... acrossfade        AA->A      Cross fade two input audio streams.
 T.C loudnorm          A->A       EBU R128 loudness normalization
 ..C sidechaincompress AA->A      Sidechain compressor.
 ... silencedetect     A->A       Detect silence.
 .S. xfade             VV->V      Cross fade one video with another video.
 .SC zoompan           V->V       Apply Zoom & Pan effect.
 ... anullsrc          |->A       Null audio source.
"""
ENCODERS_61 = """Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ------
 V....D a64multi             Multicolor charset for Commodore 64 (codec a64_multi)
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
"""


def test_parse_names_handles_ffmpeg_61_filters_without_a_separator():
    names = health.parse_names(FILTERS_61)
    assert {"zoompan", "xfade", "sidechaincompress", "loudnorm", "silencedetect"} <= names
    assert {"abench", "acompressor", "anullsrc"} <= names
    assert "=" not in names and "Filters:" not in names and "A" not in names and "|" not in names


def test_parse_names_ignores_legend_lines_of_both_tables():
    assert health.parse_names(ENCODERS_61) == {"a64multi", "libx264"}


def test_parse_names_handles_two_and_three_character_flags():
    assert health.parse_names(
        " .. loudnorm  A->A  x\n TS aap  AA->A  y\n ..C xfade  VV->V  z\n"
    ) == {
        "loudnorm",
        "aap",
        "xfade",
    }


def test_check_ffmpeg_with_the_real_61_listings_finds_nothing_missing(monkeypatch):
    outputs = {"-version": "ffmpeg version 6.1.1", "-encoders": ENCODERS_61, "-filters": FILTERS_61}
    monkeypatch.setattr(health, "_ffmpeg_stdout", lambda arg: outputs[arg])
    assert health.check_ffmpeg() == []


def test_check_ffmpeg_still_reports_a_missing_filter_in_the_61_format(monkeypatch):
    outputs = {
        "-version": "ffmpeg version 6.1.1",
        "-encoders": ENCODERS_61,
        "-filters": FILTERS_61.replace(" xfade ", " xfadx "),
    }
    monkeypatch.setattr(health, "_ffmpeg_stdout", lambda arg: outputs[arg])
    assert health.check_ffmpeg() == ["xfade"]
