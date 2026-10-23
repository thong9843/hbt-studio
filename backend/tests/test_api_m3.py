"""API bổ sung cho giao diện M3: sắp xếp cảnh, xem trước bản nháp, nhạc thư viện, cài đặt app."""

import io
import json

from PIL import Image

from hbt.models import Music
from tests.helpers import write_wav
from tests.test_api import client, complete_project, upload_image, upload_wav  # noqa: F401


def test_reorder_scenes_preserves_image_names_and_content(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Sắp xếp", "scene_count": 3}).json()["slug"]
    for i, color in enumerate([(200, 0, 0), (0, 200, 0), (0, 0, 200)]):
        assert upload_image(client, slug, i, color).status_code == 200
    p = client.get(f"/api/projects/{slug}").json()
    for i, s in enumerate(p["scenes"]):
        s["voice"] = f"Câu {i}"
    client.put(f"/api/projects/{slug}", json=p)
    orig_images = [s["image"] for s in p["scenes"]]

    r = client.post(f"/api/projects/{slug}/scenes/reorder", json={"order": [2, 0, 1]})
    assert r.status_code == 200
    scenes = r.json()["scenes"]
    assert [s["voice"] for s in scenes] == ["Câu 2", "Câu 0", "Câu 1"]
    assert [s["image"] for s in scenes] == [orig_images[2], orig_images[0], orig_images[1]]
    folder = client.app.state.hbt.storage.project_dir(slug)
    reds = [Image.open(folder / s["image"]).convert("RGB").getpixel((5, 5)) for s in scenes]
    assert reds == [(0, 0, 200), (200, 0, 0), (0, 200, 0)]


def test_delete_scene_api(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Xoá cảnh", "scene_count": 4}).json()["slug"]
    for i, color in enumerate([(10, 0, 0), (20, 0, 0), (30, 0, 0), (40, 0, 0)]):
        upload_image(client, slug, i, color)
    p = client.get(f"/api/projects/{slug}").json()
    deleted_img = p["scenes"][1]["image"]

    r = client.delete(f"/api/projects/{slug}/scenes/1")
    assert r.status_code == 200
    p_after = r.json()
    assert len(p_after["scenes"]) == 3

    folder = client.app.state.hbt.storage.project_dir(slug)
    assert not (folder / deleted_img).exists()

    # Chỉ còn 3 cảnh -> xoá tiếp sẽ báo 400
    r_bad = client.delete(f"/api/projects/{slug}/scenes/0")
    assert r_bad.status_code == 400 and "ít nhất 3 cảnh" in r_bad.json()["detail"]

    # Sai scene_index -> 404
    assert client.delete(f"/api/projects/{slug}/scenes/99").status_code == 404


def test_reorder_rejects_non_permutations(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Sắp xếp", "scene_count": 3}).json()["slug"]
    for order in ([0, 1], [0, 0, 1], [0, 1, 3]):
        r = client.post(f"/api/projects/{slug}/scenes/reorder", json={"order": order})
        assert r.status_code == 400 and "hoán vị" in r.json()["detail"]
    assert (
        client.post("/api/projects/khong-co/scenes/reorder", json={"order": [0]}).status_code == 404
    )


def test_draft_preview_uses_unsaved_text(client):  # noqa: F811
    slug = complete_project(client)
    p = client.get(f"/api/projects/{slug}").json()
    saved = client.get(f"/api/projects/{slug}/scenes/0/preview.png").content
    draft = p["scenes"][0]
    draft["card"]["lines"] = [{"text": "Bản nháp chưa lưu", "size": "xl"}]
    r = client.post(f"/api/projects/{slug}/scenes/0/preview.png?w=270", json={"scene": draft})
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.content)).size == (270, 480)
    full = client.post(f"/api/projects/{slug}/scenes/0/preview.png", json={"scene": draft}).content
    assert full != saved
    # chưa lưu gì vào project
    assert (
        client.get(f"/api/projects/{slug}").json()["scenes"][0]["card"]["lines"][0]["text"]
        == "Cảnh 1"
    )


def test_draft_preview_rejects_paths_outside_the_project(client):  # noqa: F811
    slug = complete_project(client)
    scene = client.get(f"/api/projects/{slug}").json()["scenes"][0]
    for bad in ("../../x.png", "..", "/etc/passwd"):
        scene["image"] = bad
        r = client.post(f"/api/projects/{slug}/scenes/0/preview.png", json={"scene": scene})
        assert r.status_code == 422, bad
    assert (
        client.post(
            "/api/projects/khong-co/scenes/0/preview.png", json={"scene": scene}
        ).status_code
        == 404
    )


def seed_library(client):  # noqa: F811
    lib = client.app.state.hbt.library
    src = client.tmp / "t.wav"
    write_wav(src, [("tone", 1.0)])
    meta = {"title": "Bài thử", "artist": "Ai Đó", "source": "Pixabay", "license": "CC0"}
    lib.add(src, "t.wav", meta)
    return lib.list()[0].id


def test_library_audio_and_attach(client):  # noqa: F811
    music_id = seed_library(client)
    assert music_id == "bai-thu"
    got = client.get(f"/api/music/{music_id}/audio")
    assert got.status_code == 200
    part = client.get(f"/api/music/{music_id}/audio", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"].startswith("bytes 0-99/")
    assert client.get("/api/music/khong-co/audio").status_code == 404

    slug = client.post("/api/projects", json={"title": "Nhạc"}).json()["slug"]
    r = client.post(f"/api/projects/{slug}/music/from-library", json={"id": music_id})
    assert r.status_code == 200
    music = r.json()["music"]
    assert music["file"].startswith("music.") and music["credit"] == "Bài thử – Ai Đó (Pixabay)"
    folder = client.app.state.hbt.storage.project_dir(slug)
    assert (folder / music["file"]).is_file()
    missing = client.post(f"/api/projects/{slug}/music/from-library", json={"id": "khong-co"})
    assert missing.status_code == 404
    bad = client.post(f"/api/projects/{slug}/music/from-library", json={"id": "Bad_Id"})
    assert bad.status_code == 422
    gone = client.post("/api/projects/khong-co/music/from-library", json={"id": music_id})
    assert gone.status_code == 404


def set_old_music(client, slug):  # noqa: F811
    store = client.app.state.hbt.storage
    project = store.load(slug)
    project.music = Music(file="old.wav", start=5.0, credit="Cũ")
    store.save(slug, project)


def test_from_library_resets_start_and_sets_credit(client):  # noqa: F811
    music_id = seed_library(client)
    slug = client.post("/api/projects", json={"title": "Đặt lại"}).json()["slug"]
    set_old_music(client, slug)
    music = client.post(f"/api/projects/{slug}/music/from-library", json={"id": music_id}).json()[
        "music"
    ]
    assert music["start"] is None and music["credit"] == "Bài thử – Ai Đó (Pixabay)"


def test_new_music_upload_resets_start_and_credit(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Tải mới"}).json()["slug"]
    set_old_music(client, slug)
    music = upload_wav(client, slug, "music", [("tone", 1.0)]).json()["project"]["music"]
    assert music["file"] == "music.wav" and music["start"] is None and music["credit"] == ""


def test_library_audio_rejects_bad_ids_and_old_file_route(client):  # noqa: F811
    seed_library(client)
    # Route cũ theo tên file đã bỏ: tên file không phải id hợp lệ → 422
    assert client.get("/api/music/bai-thu.wav/audio").status_code == 422
    for bad in ("Bai_Thu", "bai thu", "-bai", "bai--thu", "C:", "x.mp3"):
        assert client.get(f"/api/music/{bad}/audio").status_code == 422, bad
    # Không khớp route (có dấu '/') → không bao giờ phát file ngoài thư viện
    for bad in ("..%2Findex.json", "sub%2Ftest", "%2Fetc%2Fx"):
        assert client.get(f"/api/music/{bad}/audio").status_code in (404, 422), bad


def test_library_audio_dotdot_never_serves(client):  # noqa: F811
    seed_library(client)
    for bad in ("%2e%2e", "..", "%2e%2e%2findex.json"):
        assert client.get(f"/api/music/{bad}/audio").status_code != 200, bad


def test_renders_history_lists_newest_first(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Lịch sử"}).json()["slug"]
    assert client.get(f"/api/projects/{slug}/renders").json() == []
    folder = client.app.state.hbt.storage.project_dir(slug)
    for job, created in (("a1", "2026-10-01T10:00:00+00:00"), ("b2", "2026-10-02T10:00:00+00:00")):
        d = folder / "renders" / job
        d.mkdir(parents=True)
        (d / "video.mp4").write_bytes(b"x")
        if job == "b2":
            (d / "cover_9x16.jpg").write_bytes(b"x")
            (d / "youtube_3x2.jpg").write_bytes(b"x")
        meta = json.dumps(
            {
                "created_at": created,
                "fps": 50,
                "music_start": 4.5,
                "music_start_source": "auto",
                "preview_seconds": 10,
            }
        )
        (d / "meta.json").write_text(meta, encoding="utf-8")
    items = client.get(f"/api/projects/{slug}/renders").json()
    assert [i["job_id"] for i in items] == ["b2", "a1"]
    assert items[0]["video"] == f"/api/files/projects/{slug}/renders/b2/video.mp4"
    assert items[0]["srt"] is None
    assert items[0]["music_start"] == 4.5 and items[0]["music_start_source"] == "auto"
    assert items[0]["preview_seconds"] == 10
    assert items[0]["cover"] == f"/api/files/projects/{slug}/renders/b2/cover_9x16.jpg"
    assert items[0]["youtube_cover"].endswith("/renders/b2/youtube_3x2.jpg")
    assert items[1]["cover"] is None and items[1]["youtube_cover"] is None
    assert client.get("/api/projects/khong-co/renders").status_code == 404


def test_renders_flag_whether_music_is_still_the_one_used(client):  # noqa: F811
    import hashlib

    slug = client.post("/api/projects", json={"title": "Nhạc đổi"}).json()["slug"]
    store = client.app.state.hbt.storage
    folder = store.project_dir(slug)
    (folder / "music.wav").write_bytes(b"nhac-cu")
    project = store.load(slug)
    project.music = Music(file="music.wav")
    store.save(slug, project)
    for job, sha in (
        ("a1", hashlib.sha256(b"nhac-cu").hexdigest()),
        ("b2", hashlib.sha256(b"nhac-khac").hexdigest()),
        ("c3", None),
    ):
        d = folder / "renders" / job
        d.mkdir(parents=True)
        (d / "video.mp4").write_bytes(b"x")
        meta = {"created_at": f"2026-10-0{ord(job[0]) - 96}T10:00:00+00:00", "music_sha256": sha}
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    flags = {
        i["job_id"]: i["music_matches_current"]
        for i in client.get(f"/api/projects/{slug}/renders").json()
    }
    assert flags == {"a1": True, "b2": False, "c3": False}
    (folder / "music.wav").write_bytes(b"nhac-khac")  # đổi nhạc → cờ đổi theo
    flags = {
        i["job_id"]: i["music_matches_current"]
        for i in client.get(f"/api/projects/{slug}/renders").json()
    }
    assert flags == {"a1": False, "b2": True, "c3": False}
    project = store.load(slug)
    project.music = None
    store.save(slug, project)
    assert not any(
        i["music_matches_current"] for i in client.get(f"/api/projects/{slug}/renders").json()
    )


def test_app_settings_roundtrip_and_defaults_for_new_projects(client):  # noqa: F811
    first = client.get("/api/settings/app").json()
    assert first["default_fps"] == 50 and first["whisper_model"] == "auto"
    body = {**first, "default_fps": 30, "theme": {"primary": "#112233", "accent": "#445566"}}
    assert client.put("/api/settings/app", json=body).json() == body
    assert client.get("/api/settings/app").json() == body
    p = client.post("/api/projects", json={"title": "Mặc định"}).json()
    assert p["settings"]["fps"] == 30 and p["theme"] == {"primary": "#112233", "accent": "#445566"}


def test_app_settings_validation_and_corrupt_file(client):  # noqa: F811
    bad = {"default_fps": 45}
    assert client.put("/api/settings/app", json=bad).status_code == 422
    assert client.put("/api/settings/app", json={"theme": {"primary": "đỏ"}}).status_code == 422
    path = client.app.state.hbt.app_settings.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{hỏng", encoding="utf-8")
    assert client.get("/api/settings/app").json()["default_fps"] == 50
