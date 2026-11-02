"""API giọng VieNeu cho HBT: preferences, thông tin, job sinh giọng (G3)."""

import json
import time

import pytest

from hbt.postv.voice import FakeVoice
from tests.test_api import upload_wav
from tests.test_api_voice import make_client, new_postv, wait_job

VOICES = ["Adam bựa", "Trúc Ly"]


@pytest.fixture
def fake():
    return FakeVoice()


@pytest.fixture
def client(tmp_path, fake):
    with make_client(tmp_path, fake) as c:
        yield c


def new_hbt(client, voices=("Một.", "Hai | ba {bốn}.", "")):
    slug = client.post("/api/projects", json={"title": "Muỗi", "scene_count": len(voices)}).json()[
        "slug"
    ]
    p = client.get(f"/api/projects/{slug}").json()
    for scene, v in zip(p["scenes"], voices, strict=True):
        scene["voice"] = v
    assert client.put(f"/api/projects/{slug}", json=p).status_code == 200
    return slug


def synth(client, slug, voice_id=None):
    body = {"voice_id": voice_id} if voice_id else {}
    r = client.post(f"/api/projects/{slug}/draft/voice", json=body)
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["job_id"])


def folder(client, slug):
    return client.tmp / "workspace" / "projects" / slug


# ------------------------------------------------------------------ giọng nhớ
def test_preferences_start_empty_then_remember_across_apps(tmp_path, fake):
    with make_client(tmp_path, fake) as c:
        assert c.get("/api/gd2/voice/preferences").json() == {"voice_id": None}
        r = c.put("/api/gd2/voice/preferences", json={"voice_id": "Trúc Ly"})
        assert r.status_code == 200 and r.json() == {"voice_id": "Trúc Ly"}
    with make_client(tmp_path, FakeVoice()) as c:  # mở app lần sau
        assert c.get("/api/gd2/voice/preferences").json() == {"voice_id": "Trúc Ly"}
        assert c.put("/api/gd2/voice/preferences", json={"voice_id": None}).json() == {
            "voice_id": None
        }
        assert c.get("/api/gd2/voice/preferences").json() == {"voice_id": None}


def test_preferences_reject_unknown_voice_when_voices_are_known(client):
    r = client.put("/api/gd2/voice/preferences", json={"voice_id": "Không có giọng này"})
    assert r.status_code == 422
    assert client.get("/api/gd2/voice/preferences").json() == {"voice_id": None}


def test_preferences_accept_anything_when_vieneu_is_not_installed(tmp_path):
    with make_client(tmp_path, FakeVoice(ok=False)) as c:
        assert c.put("/api/gd2/voice/preferences", json={"voice_id": "Adam bựa"}).status_code == 200


# ------------------------------------------------------------------ thông tin
def test_info_without_vieneu_still_answers_so_the_card_can_show_a_note(tmp_path):
    with make_client(tmp_path, FakeVoice(ok=False)) as c:
        slug = new_hbt(c)
        info = c.get(f"/api/projects/{slug}/draft/voice").json()
        assert info["available"] is False and "Chưa cài VieNeu" in info["note"]
        assert info["has_file"] is False and info["stale"] is None and info["scenes"] == 2
        r = c.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Adam bựa"})
        assert r.status_code == 503


def test_info_for_postv_project_is_rejected(client):
    pv = new_postv(client)
    assert client.get(f"/api/projects/{pv['slug']}/draft/voice").status_code == 400
    r = client.post(f"/api/projects/{pv['slug']}/draft/voice", json={"voice_id": "Adam bựa"})
    assert r.status_code == 400


def test_info_estimates_seconds_from_spoken_text(client):
    slug = new_hbt(client)
    info = client.get(f"/api/projects/{slug}/draft/voice").json()
    assert info["available"] is True and info["estimated_seconds"] > 0
    assert info["has_file"] is False and info["file"] is None


# ------------------------------------------------------------------ job
def test_synthesize_needs_a_chosen_voice(client, fake):
    slug = new_hbt(client)
    r = client.post(f"/api/projects/{slug}/draft/voice", json={})
    assert r.status_code == 422 and "Chưa chọn giọng" in r.json()["detail"]
    assert fake.calls == []


def test_synthesize_writes_voice_and_sets_project_voice_without_engine(client, fake):
    slug = new_hbt(client)
    job = synth(client, slug, "Adam bựa")
    assert job["status"] == "done", job
    out = job["output"]
    assert out["voice"] == f"/api/files/projects/{slug}/voice.wav"
    assert out["voice_id"] == "Adam bựa" and out["seconds"] > 1
    assert [s["scene"] for s in out["scenes"]] == [0, 1]  # cảnh 3 không có lời
    # chữ gửi VieNeu đã xử lý {} và |
    assert [t for t, _ in fake.calls] == ["Một.", "Hai", "ba bốn."]
    saved = client.get(f"/api/projects/{slug}").json()
    assert saved["voice"] == "voice.wav"  # HBT chỉ có file (không engine, không trim_end)
    assert client.get(out["voice"]).status_code == 200
    info = client.get(f"/api/projects/{slug}/draft/voice").json()
    assert info["has_file"] and info["from_vieneu"] and info["stale"] is False
    assert info["used_voice_id"] == "Adam bựa" and info["voice_id"] == "Adam bựa"


def test_synthesize_remembers_the_voice_and_reuses_it(client, fake):
    slug = new_hbt(client)
    synth(client, slug, "Trúc Ly")
    assert client.get("/api/gd2/voice/preferences").json() == {"voice_id": "Trúc Ly"}
    job = synth(client, slug)  # không gửi giọng: dùng giọng đã nhớ
    assert job["status"] == "done" and job["output"]["voice_id"] == "Trúc Ly"
    assert job["output"]["cached"] == 3 and job["output"]["generated"] == 0


def test_progress_log_says_scene_x_of_n(client):
    slug = new_hbt(client)
    r = client.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Adam bựa"})
    job_id = r.json()["job_id"]
    wait_job(client, job_id)
    log = client.get(f"/api/jobs/{job_id}").json()["log_tail"]
    assert any("Đang đọc cảnh 1/2" in m for m in log) and any("Xong cảnh 2/2" in m for m in log)


def test_changed_text_reports_stale_but_does_not_regenerate(client, fake):
    slug = new_hbt(client)
    synth(client, slug, "Adam bựa")
    n = len(fake.calls)
    p = client.get(f"/api/projects/{slug}").json()
    p["scenes"][0]["voice"] = "Một khác."
    client.put(f"/api/projects/{slug}", json=p)
    info = client.get(f"/api/projects/{slug}/draft/voice").json()
    assert info["stale"] is True and len(fake.calls) == n


def test_missing_meta_means_unknown_not_stale(client):
    slug = new_hbt(client)
    synth(client, slug, "Adam bựa")
    (folder(client, slug) / "build" / "hbt_voice.json").unlink()
    info = client.get(f"/api/projects/{slug}/draft/voice").json()
    assert info["has_file"] is True and info["stale"] is None and info["from_vieneu"] is False


def test_vbee_upload_after_vieneu_replaces_it_and_info_follows(client):
    slug = new_hbt(client)
    synth(client, slug, "Adam bựa")
    assert upload_wav(client, slug, "voice", [("tone", 1.0)]).status_code == 200
    info = client.get(f"/api/projects/{slug}/draft/voice").json()
    assert info["has_file"] is True and info["from_vieneu"] is False and info["stale"] is None


def test_synthesize_replaces_old_voice_files(client):
    slug = new_hbt(client)
    assert upload_wav(client, slug, "voice", [("tone", 1.0)]).status_code == 200
    info = client.get(f"/api/projects/{slug}/draft/voice").json()
    assert info["has_file"] is True  # đã có giọng: thẻ sẽ nhắc "Sẽ thay giọng hiện có"
    (folder(client, slug) / "voice.mp3").write_bytes(b"ID3")
    synth(client, slug, "Adam bựa")
    assert not (folder(client, slug) / "voice.mp3").exists()
    assert (folder(client, slug) / "voice.wav").stat().st_size > 1000


def test_no_spoken_scene_is_422(client):
    slug = new_hbt(client, voices=("", "|", "{}"))
    r = client.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Adam bựa"})
    assert r.status_code == 422 and "lời đọc" in r.json()["detail"]


def test_unknown_voice_is_422(client):
    slug = new_hbt(client)
    r = client.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Giọng ma"})
    assert r.status_code == 422


def test_busy_project_is_409_and_cancel_keeps_things_clean(tmp_path):
    with make_client(tmp_path, FakeVoice(delay=0.3)) as c:
        slug = new_hbt(c)
        first = c.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Adam bựa"})
        assert first.status_code == 202
        second = c.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Adam bựa"})
        assert second.status_code == 409
        job_id = first.json()["job_id"]
        time.sleep(0.1)
        assert c.post(f"/api/jobs/{job_id}/cancel").json()["status"] == "cancelled"
        assert not (folder(c, slug) / "voice.wav").exists()
        assert c.get(f"/api/projects/{slug}").json()["voice"] is None


def test_voice_job_is_not_listed_as_a_render(client):
    slug = new_hbt(client)
    r = client.post(f"/api/projects/{slug}/draft/voice", json={"voice_id": "Adam bựa"})
    wait_job(client, r.json()["job_id"])
    rows = client.get("/api/jobs").json()
    mine = [j for j in rows if j["slug"] == slug]
    assert all(j["kind"] == "voice" for j in mine)


def test_prefs_file_lives_in_workspace_settings(client):
    client.put("/api/gd2/voice/preferences", json={"voice_id": "Trúc Ly"})
    path = client.tmp / "workspace" / "settings" / "gd2.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"voice": {"id": "Trúc Ly"}}
