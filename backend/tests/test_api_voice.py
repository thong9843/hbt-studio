"""API giọng PostV: /voices, /voice, job sinh giọng, /health, cache (PV4)."""

import json
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from hbt.config import BRAND_DIR, Settings
from hbt.main import create_app
from hbt.postv.voice import FakeVoice
from tests.test_api import upload_wav

SEGMENTS = [
    {"role": "hook", "voice": "Quên ví ở quán cà phê."},
    {"role": "post", "voice": "Hôm qua mình để quên ví trên bàn."},
    {"role": "comment", "ref": "c1", "voice": "Có người hỏi ngay:", "speaker": "narrator"},
    {"role": "comment", "ref": "c1", "voice": "Quán ở đâu vậy bạn?"},
    {"role": "commentary", "voice": ""},
]


def make_client(tmp_path, voice):
    brand = tmp_path / "brand"
    brand.mkdir(parents=True, exist_ok=True)
    shutil.copy(BRAND_DIR / "hay-biet-tuot_avatar.png", brand)
    settings = Settings(
        workspace_dir=tmp_path / "workspace",
        library_dir=tmp_path / "library",
        whisper_model="large-v3",
        whisper_device="cpu",
        default_fps=50,
    )
    c = TestClient(create_app(settings, brand_dir=brand, voice=voice))
    c.tmp = tmp_path
    return c


@pytest.fixture
def fake():
    return FakeVoice()


@pytest.fixture
def client(tmp_path, fake):
    with make_client(tmp_path, fake) as c:
        yield c


def new_postv(client, segments=SEGMENTS, **extra):
    p = client.post("/api/projects", json={"title": "Bài đêm khuya", "kind": "postv"}).json()
    p["comments"] = [{"id": "c1", "handle": "an", "text": "Quán ở đâu vậy bạn?"}]
    p["post"] = {"handle": "linh", "text": "Hôm qua mình để quên ví trên bàn."}
    p["segments"] = segments
    p.update(extra)
    r = client.put(f"/api/projects/{p['slug']}", json=p)
    assert r.status_code == 200, r.text
    return r.json()


def wait_job(client, job_id, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job không kết thúc")


def synth(client, slug):
    r = client.post(f"/api/projects/{slug}/voice/synthesize")
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["job_id"])


# ---------------------------------------------------------------- /voices và /health
def test_voices_lists_with_gender(client):
    body = client.get("/api/voices").json()
    assert body["default"] == "Adam bựa"
    assert {"id": "Trúc Ly", "gender": "Nữ"}.items() <= next(
        v for v in body["voices"] if v["id"] == "Trúc Ly"
    ).items()


def test_voices_503_when_not_installed(tmp_path):
    with make_client(tmp_path, FakeVoice(ok=False)) as c:
        r = c.get("/api/voices")
        assert r.status_code == 503 and "VieNeu" in r.json()["detail"]


def test_health_reports_vieneu(tmp_path):
    with make_client(tmp_path, FakeVoice()) as c:
        body = c.get("/api/health").json()
        assert body["vieneu"] is True and body["vieneu_note"] is None
    with make_client(tmp_path, FakeVoice(ok=False)) as c:
        body = c.get("/api/health").json()
        assert body["vieneu"] is False and "VieNeu" in body["vieneu_note"]
        assert body["ok"] == (not body["missing"])  # VieNeu không làm đổi `ok`


# ---------------------------------------------------------------- job sinh giọng
def test_synthesize_job_writes_voice_and_updates_project(client, fake):
    pv = new_postv(client)
    job = synth(client, pv["slug"])
    assert job["status"] == "done", job
    out = job["output"]
    assert out["voice"] == "/api/files/" + f"projects/{pv['slug']}/voice.wav"
    assert out["generated"] == 4 and out["cached"] == 0 and out["seconds"] > 3
    assert [s["speaker"] for s in out["segments"]] == ["narrator", "post", "narrator", "c1"]
    assert out["cast"]["narrator"] == "Adam bựa" and len(set(out["cast"].values())) == 3
    saved = client.get(f"/api/projects/{pv['slug']}").json()
    assert saved["voice"]["engine"] == "vieneu" and saved["voice"]["file"] == "voice.wav"
    assert client.get(out["voice"]).status_code == 200
    assert saved["segments"] == pv["segments"]  # chỉ đổi voice, không đụng kịch bản


def test_synthesize_progress_events_mention_segment(client):
    pv = new_postv(client)
    job_id = client.post(f"/api/projects/{pv['slug']}/voice/synthesize").json()["job_id"]
    wait_job(client, job_id)
    log = client.get(f"/api/jobs/{job_id}").json()["log_tail"]
    assert any("Đang đọc đoạn 1/4" in m for m in log) and any("Xong đoạn 4/4" in m for m in log)


def test_synthesize_uses_cache_and_only_redoes_changed_segment(client, fake):
    pv = new_postv(client)
    synth(client, pv["slug"])
    assert len(fake.calls) == 4
    again = synth(client, pv["slug"])
    assert again["output"]["generated"] == 0 and again["output"]["cached"] == 4
    assert len(fake.calls) == 4  # không gọi VieNeu lại
    pv["segments"][1]["voice"] = "Câu đã đổi hoàn toàn."
    client.put(f"/api/projects/{pv['slug']}", json=pv)
    third = synth(client, pv["slug"])
    assert (third["output"]["generated"], third["output"]["cached"]) == (1, 3)


def test_manual_cast_and_seed_are_used(client):
    pv = new_postv(client, voice={"engine": "vieneu", "cast": {"post": "Mai Anh"}, "seed": 4})
    out = synth(client, pv["slug"])["output"]
    assert out["cast"]["post"] == "Mai Anh"
    assert out["segments"][1]["voice_id"] == "Mai Anh"


def test_synthesize_errors(client, tmp_path, fake):
    assert client.post("/api/projects/khong-co/voice/synthesize").status_code == 404
    muoi = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3}).json()
    assert client.post(f"/api/projects/{muoi['slug']}/voice/synthesize").status_code == 422
    empty = client.post("/api/projects", json={"title": "Rỗng", "kind": "postv"}).json()
    r = client.post(f"/api/projects/{empty['slug']}/voice/synthesize")
    assert r.status_code == 422 and "lời đọc" in r.json()["detail"]
    with make_client(tmp_path / "b", FakeVoice(ok=False)) as c:
        pv = new_postv(c)
        r = c.post(f"/api/projects/{pv['slug']}/voice/synthesize")
        assert r.status_code == 503 and "VieNeu" in r.json()["detail"]


def test_synthesize_conflict_while_busy_and_cancel(tmp_path):
    slow = FakeVoice(delay=2.0)
    with make_client(tmp_path, slow) as c:
        pv = new_postv(c)
        job_id = c.post(f"/api/projects/{pv['slug']}/voice/synthesize").json()["job_id"]
        assert c.post(f"/api/projects/{pv['slug']}/voice/synthesize").status_code == 409
        active = c.get("/api/jobs").json()
        assert active[0]["kind"] == "voice" and active[0]["slug"] == pv["slug"]
        job = c.post(f"/api/jobs/{job_id}/cancel").json()
        assert job["status"] == "cancelled"
        assert not (c.tmp / "workspace" / "projects" / pv["slug"] / "voice.wav").exists()
        assert c.get(f"/api/projects/{pv['slug']}").json()["voice"]["file"] is None


def test_synthesize_failure_keeps_project_untouched(tmp_path):
    with make_client(tmp_path, FakeVoice(fail_on="Quán ở đâu")) as c:
        pv = new_postv(c)
        job = synth(c, pv["slug"])
        assert job["status"] == "failed" and "Giọng giả lỗi" in job["error"]
        assert c.get(f"/api/projects/{pv['slug']}").json()["voice"]["file"] is None


def test_unknown_manual_voice_fails_with_clear_message(client):
    pv = new_postv(client, voice={"engine": "vieneu", "cast": {"post": "Giọng lạ"}})
    job = synth(client, pv["slug"])
    assert job["status"] == "failed" and "Giọng lạ" in job["error"]


# ---------------------------------------------------------------- /voice (hiện trạng)
def test_voice_info_before_and_after(client):
    pv = new_postv(client)
    info = client.get(f"/api/projects/{pv['slug']}/voice").json()
    assert info["available"] and info["url"] is None and info["stale"] is None
    assert [s["speaker"] for s in info["speakers"]] == ["narrator", "post", "c1"]
    assert info["speakers"][0] == {"speaker": "narrator", "voice_id": "Adam bựa", "manual": False}
    assert info["estimated_seconds"] > 0
    synth(client, pv["slug"])
    info = client.get(f"/api/projects/{pv['slug']}/voice").json()
    assert info["url"].endswith("/voice.wav") and info["stale"] is False
    assert info["seconds"] > 3 and len(info["segments"]) == 4
    pv["segments"][3]["voice"] = "Câu khác hẳn."
    client.put(f"/api/projects/{pv['slug']}", json=pv)
    assert client.get(f"/api/projects/{pv['slug']}/voice").json()["stale"] is True


def test_voice_info_without_vieneu_still_works(tmp_path):
    with make_client(tmp_path, FakeVoice(ok=False)) as c:
        pv = new_postv(c)
        info = c.get(f"/api/projects/{pv['slug']}/voice").json()
        assert info["available"] is False and info["speakers"] == [] and "VieNeu" in info["note"]
        assert info["estimated_seconds"] > 0


def test_voice_info_rejects_video_project(client):
    muoi = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3}).json()
    assert client.get(f"/api/projects/{muoi['slug']}/voice").status_code == 400
    assert client.get("/api/projects/khong-co/voice").status_code == 404


def test_file_voice_still_works_and_keeps_cast(client):
    pv = new_postv(client, voice={"engine": "vieneu", "cast": {"post": "Mai Anh"}, "seed": 9})
    r = upload_wav(client, pv["slug"], "voice", [("tone", 0.5)])
    assert r.status_code == 200, r.text
    voice = client.get(f"/api/projects/{pv['slug']}").json()["voice"]
    assert voice["engine"] == "file" and voice["file"].startswith("voice.")
    assert voice["cast"] == {"post": "Mai Anh"} and voice["seed"] == 9


def test_synthesized_voice_files_are_saved(client):
    pv = new_postv(client)
    synth(client, pv["slug"])
    folder = client.tmp / "workspace" / "projects" / pv["slug"]
    meta = json.loads((folder / "build" / "voice_segments.json").read_text(encoding="utf-8"))
    assert meta["seconds"] > 0 and len(list((folder / "build" / "voice").glob("*.wav"))) == 4
