"""Giọng PostV: chia giọng, cache, nối đoạn, provider giả, tiến trình con (POSTV 6c, 6d)."""

import json
import sys
import threading
import wave
from pathlib import Path

import pytest

from hbt.pipeline.cancel import CancelToken, RenderCancelled, use_token
from hbt.postv import voice as V
from hbt.postv.voice import (
    FAKE_VOICES,
    FakeVoice,
    FileVoice,
    SynthItem,
    VieNeuProvider,
    VoiceError,
    VoicePlanItem,
    VoiceUnavailable,
    cache_key,
    join_wavs,
    parse_voice_label,
    resolve_cast,
    segment_speaker,
    synthesize_plan,
    wav_seconds,
)


def test_parse_voice_label():
    v = parse_voice_label("⭐ Adam bựa — Nam · Bắc · Phong cách tự nhiên", "Adam bựa")
    assert (v.id, v.label, v.gender, v.region, v.style) == (
        "Adam bựa",
        "Adam bựa — Nam · Bắc · Phong cách tự nhiên",
        "Nam",
        "Bắc",
        "Phong cách tự nhiên",
    )
    assert parse_voice_label("Chỉ tên", "x").gender == ""


@pytest.mark.parametrize(
    ("role", "ref", "speaker", "expect"),
    [
        ("post", None, None, "post"),
        ("comment", "c1", None, "c1"),
        ("hook", None, None, "narrator"),
        ("commentary", None, None, "narrator"),
        ("comment", "c1", "narrator", "narrator"),
    ],
)
def test_segment_speaker_default(role, ref, speaker, expect):
    assert segment_speaker(role, ref, speaker) == expect


def test_resolve_cast_narrator_default_and_no_duplicates():
    speakers = ["narrator", "post", "c1", "c2", "c3"]
    cast = resolve_cast(speakers, {}, 1, FAKE_VOICES)
    assert cast["narrator"] == "Adam bựa"
    assert len(set(cast.values())) == 5
    assert resolve_cast(speakers, {}, 1, FAKE_VOICES) == cast  # lặp lại được theo seed
    assert any(resolve_cast(speakers, {}, s, FAKE_VOICES) != cast for s in range(2, 8))


def test_resolve_cast_alternates_gender_and_respects_manual():
    by = {v.id: v.gender for v in FAKE_VOICES}
    cast = resolve_cast(["narrator", "post", "c1"], {"post": "Mai Anh"}, 3, FAKE_VOICES)
    assert cast["post"] == "Mai Anh"
    assert by[cast["narrator"]] != by[cast["post"]]
    assert by[cast["c1"]] != by[cast["post"]]  # xen nam/nữ so với người liền trước


def test_resolve_cast_reuses_when_out_of_voices_and_rejects_unknown():
    many = [f"c{i}" for i in range(1, 9)]
    cast = resolve_cast(many, {}, 1, FAKE_VOICES)
    assert set(cast) == set(many) and len(set(cast.values())) == len(FAKE_VOICES)
    with pytest.raises(VoiceError, match="không có trong danh sách"):
        resolve_cast(["post"], {"post": "Giọng lạ"}, 1, FAKE_VOICES)


def test_cache_key_depends_on_text_and_voice():
    assert cache_key("a", "x") == cache_key("a", "x")
    assert cache_key("a", "x") != cache_key("b", "x")
    assert cache_key("a", "x") != cache_key("a", "y")


def tone(path: Path, seconds: float, rate: int = 48000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * int(seconds * rate))
    return path


def test_join_wavs_gap_and_spans(tmp_path):
    a, b = tone(tmp_path / "a.wav", 1.0), tone(tmp_path / "b.wav", 0.5)
    spans = join_wavs([a, b], tmp_path / "out.wav")
    assert spans == [(0.0, 1.0), (1.25, 1.75)]
    assert wav_seconds(tmp_path / "out.wav") == pytest.approx(1.75)
    assert not (tmp_path / "out.wav.tmp").exists()


def test_join_wavs_rejects_mixed_formats(tmp_path):
    a, b = tone(tmp_path / "a.wav", 0.2), tone(tmp_path / "b.wav", 0.2, rate=24000)
    with pytest.raises(VoiceError, match="khác định dạng"):
        join_wavs([a, b], tmp_path / "out.wav")


def plan(*texts):
    return [
        VoicePlanItem(i, "narrator" if i % 2 == 0 else "post", "Adam bựa", t)
        for i, t in enumerate(texts)
    ]


def test_synthesize_plan_caches_by_text_and_voice(tmp_path):
    fake = FakeVoice()
    steps = []
    r1 = synthesize_plan(
        plan("Xin chào các bạn", "Hôm nay thế nào"),
        tmp_path,
        fake,
        {"narrator": "Adam bựa"},
        lambda p, s, m: steps.append((p, m)),
    )
    assert (r1.generated, r1.cached) == (2, 0) and len(fake.calls) == 2
    assert r1.file == tmp_path / "voice.wav" and r1.seconds == pytest.approx(
        wav_seconds(r1.file), abs=2e-3
    )
    assert [s["index"] for s in r1.segments] == [0, 1]
    assert r1.segments[1]["start"] == pytest.approx(r1.segments[0]["end"] + 0.25, abs=2e-3)
    assert steps[0][0] >= 3 and steps[-1][0] < 100
    assert any("Đang đọc đoạn 1/2" in m for _, m in steps)
    # lần hai: đổi đúng một đoạn → chỉ sinh đoạn đó
    r2 = synthesize_plan(plan("Xin chào các bạn", "Câu mới hoàn toàn"), tmp_path, fake, {})
    assert (r2.generated, r2.cached) == (1, 1) and len(fake.calls) == 3
    assert r2.signature != r1.signature
    meta = json.loads((tmp_path / "build" / "voice_segments.json").read_text(encoding="utf-8"))
    assert meta["signature"] == r2.signature and len(meta["segments"]) == 2


def test_synthesize_plan_no_partial_file_on_error(tmp_path):
    fake = FakeVoice(fail_on="hỏng")
    with pytest.raises(VoiceError):
        synthesize_plan(plan("tốt", "đoạn hỏng"), tmp_path, fake, {})
    assert not (tmp_path / "voice.wav").exists()


def test_synthesize_plan_cancel_stops(tmp_path):
    token = CancelToken()
    fake = FakeVoice(delay=1.0)
    token.cancel()
    with use_token(token), pytest.raises(RenderCancelled):
        synthesize_plan(plan("một", "hai"), tmp_path, fake, {})
    assert not (tmp_path / "voice.wav").exists()


def test_synthesize_plan_removes_stale_voice_with_other_extension(tmp_path):
    (tmp_path / "voice.mp3").write_bytes(b"x")
    synthesize_plan(plan("một"), tmp_path, FakeVoice(), {})
    assert not (tmp_path / "voice.mp3").exists() and (tmp_path / "voice.wav").is_file()


def test_fake_voice_single_synthesize_returns_wav_bytes():
    data = FakeVoice().synthesize("Xin chào", "Adam bựa")
    assert data[:4] == b"RIFF"


def test_file_voice_cannot_synthesize():
    fv = FileVoice()
    assert fv.list_voices() == [] and fv.status().ok
    with pytest.raises(VoiceError):
        fv.synthesize("x", "y")


def test_fake_voice_unavailable():
    fv = FakeVoice(ok=False)
    assert not fv.status().ok
    with pytest.raises(VoiceUnavailable):
        fv.list_voices()


# ------------------------------------------------------------ VieNeuProvider (tiến trình con giả)
def fake_env(tmp_path, monkeypatch, worker_body):
    """venv-tts giả: python thật của máy chạy một worker giả thay cho voice_worker.py."""
    venv = tmp_path / "venv"
    (venv / "Lib" / "site-packages" / "vieneu").mkdir(parents=True)
    models = tmp_path / "models"
    (models / "hf_vieneu" / "hub" / V.WEIGHTS_REPO / "snapshots" / "abc").mkdir(parents=True)
    worker = tmp_path / "worker.py"
    worker.write_text(worker_body, encoding="utf-8")
    monkeypatch.setattr(V, "WORKER", worker)
    monkeypatch.setattr(V, "venv_python", lambda _v: Path(sys.executable))
    return VieNeuProvider(models, venv, cache_file=tmp_path / "voices.json", timeout_base=20)


WORKER_OK = """
import json, sys, wave, os
req = json.load(open(sys.argv[1], encoding="utf-8"))
assert os.environ["HF_HUB_OFFLINE"] == "1" and req["hf_home"].endswith("hf_vieneu")
if req["mode"] == "voices":
    voices = [["⭐ A — Nam · Bắc · X", "A"], ["B — Nữ · Nam · Y", "B"]]
    json.dump({"ok": True, "voices": voices}, open(req["out"], "w", encoding="utf-8"))
else:
    for i, it in enumerate(req["items"]):
        open(req["progress"], "a").write(f"begin {i}\\n")
        with wave.open(it["out"], "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
            w.writeframes(b"\\x00\\x00" * 4800)
        open(req["progress"], "a").write(f"done {i}\\n")
    json.dump({"ok": True, "files": []}, open(req["out"], "w"))
"""


def test_provider_status_messages(tmp_path):
    p = VieNeuProvider(tmp_path / "models", tmp_path / "khong-co")
    st = p.status()
    assert not st.installed and "requirements-tts.txt" in st.note
    with pytest.raises(VoiceUnavailable):
        p.list_voices()


def test_provider_status_missing_weights(tmp_path, monkeypatch):
    p = fake_env(tmp_path, monkeypatch, WORKER_OK)
    for d in (p.home / "hub" / V.WEIGHTS_REPO / "snapshots").glob("*"):
        d.rmdir()
    st = p.status()
    assert st.installed and not st.weights and "không tự tải" in st.note
    with pytest.raises(VoiceUnavailable, match="trọng số"):
        p.synthesize_many([SynthItem("x", "A", tmp_path / "o.wav")])


def test_provider_lists_voices_and_caches_on_disk(tmp_path, monkeypatch):
    p = fake_env(tmp_path, monkeypatch, WORKER_OK)
    assert p.status().ok
    voices = p.list_voices()
    assert [(v.id, v.gender) for v in voices] == [("A", "Nam"), ("B", "Nữ")]
    (tmp_path / "worker.py").write_text("raise SystemExit(3)", encoding="utf-8")
    again = VieNeuProvider(p.home.parent, p.venv, cache_file=p.cache_file)  # đọc từ đĩa
    assert [v.id for v in again.list_voices()] == ["A", "B"]


def test_provider_synthesizes_and_reports_progress(tmp_path, monkeypatch):
    p = fake_env(tmp_path, monkeypatch, WORKER_OK)
    events = []
    items = [SynthItem("a", "A", tmp_path / "x" / "1.wav"), SynthItem("b", "B", tmp_path / "2.wav")]
    p.synthesize_many(items, lambda i, s: events.append((i, s)))
    assert all(i.out.is_file() for i in items)
    assert events == [(0, "begin"), (0, "done"), (1, "begin"), (1, "done")]


def test_provider_worker_error_is_clear(tmp_path, monkeypatch):
    body = (
        "import json, sys\n"
        "req = json.load(open(sys.argv[1]))\n"
        'err = {"ok": False, "stage": "load", "error": "OSError: offline"}\n'
        'json.dump(err, open(req["out"], "w"))\n'
    )
    p = fake_env(tmp_path, monkeypatch, body)
    with pytest.raises(VoiceError, match="nạp mô hình: OSError: offline"):
        p.synthesize_many([SynthItem("a", "A", tmp_path / "o.wav")])


def test_provider_worker_crash_reports_stderr(tmp_path, monkeypatch):
    p = fake_env(tmp_path, monkeypatch, 'import sys\nsys.stderr.write("boom")\nsys.exit(5)\n')
    with pytest.raises(VoiceError, match="thoát mã 5 boom"):
        p.synthesize_many([SynthItem("a", "A", tmp_path / "o.wav")])


def test_provider_timeout_and_cancel_kill_child(tmp_path, monkeypatch):
    p = fake_env(tmp_path, monkeypatch, "import time\ntime.sleep(60)\n")
    p.timeout_base = 0.5
    with pytest.raises(VoiceError, match="quá giới hạn"):
        p.synthesize_many([SynthItem("a", "A", tmp_path / "o.wav")])
    token = CancelToken()
    p.timeout_base = 30
    threading.Timer(0.5, token.cancel).start()
    with use_token(token), pytest.raises(RenderCancelled):
        p.synthesize_many([SynthItem("a", "A", tmp_path / "o.wav")])


def test_worker_never_imports_hbt_and_forces_offline():
    src = V.WORKER.read_text(encoding="utf-8")
    assert "import hbt" not in src and "from hbt" not in src
    assert 'HF_HUB_OFFLINE"] = "1"' in src


def test_worker_turns_off_watermark():
    src = V.WORKER.read_text(encoding="utf-8")
    assert "apply_watermark=False" in src


def test_cache_key_changes_with_worker_rev(monkeypatch):
    before = cache_key("a", "x")
    monkeypatch.setattr(V, "WORKER_REV", V.WORKER_REV + 1)
    assert cache_key("a", "x") != before
