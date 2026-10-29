"""API cho project PostV: tạo, đọc, lưu, nhân bản, tài sản; project HBT không đổi (PV1)."""

import json

import pytest

from tests.test_api import client, png_bytes, upload_wav  # noqa: F401


def folder(client, slug):  # noqa: F811
    return client.tmp / "workspace" / "projects" / slug


@pytest.fixture
def pv(client):  # noqa: F811
    r = client.post("/api/projects", json={"title": "Bài đêm khuya", "kind": "postv"})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_postv_returns_postv_project(client, pv):  # noqa: F811
    assert pv["kind"] == "postv" and pv["slug"] == "bai-dem-khuya"
    assert pv["settings"]["fps"] == 60 and pv["segments"] == []
    saved = json.loads((folder(client, pv["slug"]) / "project.json").read_text(encoding="utf-8"))
    assert saved["kind"] == "postv" and "scenes" not in saved
    assert (folder(client, pv["slug"]) / "images").is_dir()


def test_create_default_kind_is_video(client):  # noqa: F811
    r = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 4})
    assert r.status_code == 201
    body = r.json()
    assert "kind" not in body and len(body["scenes"]) == 4


def test_create_postv_ignores_scene_count_and_rejects_empty_title(client):  # noqa: F811
    r = client.post("/api/projects", json={"title": "X", "kind": "postv", "scene_count": 12})
    assert r.status_code == 201 and "scenes" not in r.json()
    assert client.post("/api/projects", json={"title": "", "kind": "postv"}).status_code == 422
    assert client.post("/api/projects", json={"title": "X", "kind": "khac"}).status_code == 422


def test_list_shows_kind_for_both(client, pv):  # noqa: F811
    client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3})
    items = {i["slug"]: i for i in client.get("/api/projects").json()}
    assert items["bai-dem-khuya"]["kind"] == "postv"
    assert items["bai-dem-khuya"]["thumb"] is None and items["bai-dem-khuya"]["title"]
    assert items["muoi"]["kind"] == "video"
    assert "error" not in items["bai-dem-khuya"] or items["bai-dem-khuya"]["error"] is None


def test_get_and_put_postv_roundtrip(client, pv):  # noqa: F811
    slug = pv["slug"]
    got = client.get(f"/api/projects/{slug}").json()
    assert got["kind"] == "postv"
    got["post"]["handle"] = "wangxuan334"
    got["post"]["likes"] = 27600
    got["comments"] = [{"id": "c1", "handle": "cozy_bear41", "age": "14h", "text": "Hi"}]
    got["segments"] = [{"role": "comment", "ref": "c1", "voice": "Xin chào"}]
    r = client.put(f"/api/projects/{slug}", json=got)
    assert r.status_code == 200, r.text
    again = client.get(f"/api/projects/{slug}").json()
    assert again["post"]["likes"] == 27600 and again["segments"][0]["ref"] == "c1"


def test_put_invalid_postv_is_422(client, pv):  # noqa: F811
    body = client.get(f"/api/projects/{pv['slug']}").json()
    body["settings"]["fps"] = 25
    assert client.put(f"/api/projects/{pv['slug']}", json=body).status_code == 422
    body["settings"]["fps"] = 60
    body["segments"] = [{"role": "comment", "ref": "khong-co"}]
    assert client.put(f"/api/projects/{pv['slug']}", json=body).status_code == 422


def test_put_cannot_change_kind(client, pv):  # noqa: F811
    video = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3}).json()
    # đẩy nội dung video vào slug PostV
    wrong = {**video, "slug": pv["slug"]}
    assert client.put(f"/api/projects/{pv['slug']}", json=wrong).status_code == 422
    # đẩy nội dung PostV vào slug video
    wrong2 = {**pv, "slug": video["slug"]}
    assert client.put(f"/api/projects/{video['slug']}", json=wrong2).status_code == 422
    assert client.get(f"/api/projects/{pv['slug']}").json()["kind"] == "postv"


def test_put_unknown_slug_is_404(client):  # noqa: F811
    body = {"kind": "postv", "slug": "khong-co", "title": "X"}
    assert client.put("/api/projects/khong-co", json=body).status_code == 404


def test_video_project_json_is_not_rewritten_by_listing_or_reading(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3}).json()["slug"]
    path = folder(client, slug) / "project.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    client.get("/api/projects")
    client.get(f"/api/projects/{slug}")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_duplicate_postv(client, pv):  # noqa: F811
    r = client.post(f"/api/projects/{pv['slug']}/duplicate", json={"title": "Bản nhân đôi"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "postv" and body["slug"] == "ban-nhan-doi"
    assert client.get("/api/projects/ban-nhan-doi").json()["title"] == "Bản nhân đôi"


def test_delete_postv(client, pv):  # noqa: F811
    assert client.delete(f"/api/projects/{pv['slug']}").status_code == 204
    assert client.get(f"/api/projects/{pv['slug']}").status_code == 404


def test_upload_voice_sets_file_engine(client, pv):  # noqa: F811
    r = upload_wav(client, pv["slug"], "voice", [("tone", 1.0)])
    assert r.status_code == 200, r.text
    voice = client.get(f"/api/projects/{pv['slug']}").json()["voice"]
    assert voice["engine"] == "file" and voice["file"].startswith("voice.")


def test_upload_music_for_postv(client, pv):  # noqa: F811
    r = upload_wav(client, pv["slug"], "music", [("tone", 1.0)])
    assert r.status_code == 200, r.text
    assert client.get(f"/api/projects/{pv['slug']}").json()["music"]["file"].startswith("music.")


def test_upload_image_is_rejected_and_cover_needs_thumbnail(client, pv):  # noqa: F811
    slug = pv["slug"]
    img = {"file": ("a.png", png_bytes(), "image/png")}
    assert (
        client.post(
            f"/api/projects/{slug}/assets", data={"kind": "image", "scene_index": "0"}, files=img
        ).status_code
        == 400
    )
    assert (
        client.post(f"/api/projects/{slug}/assets", data={"kind": "cover"}, files=img).status_code
        == 422
    )


def test_upload_cover_after_enabling_thumbnail(client, pv):  # noqa: F811
    slug = pv["slug"]
    body = client.get(f"/api/projects/{slug}").json()
    body["thumbnail"] = {"scene": 1, "lines": ["Dòng một", "Dòng hai"]}
    assert client.put(f"/api/projects/{slug}", json=body).status_code == 200
    r = client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": "cover"},
        files={"file": ("c.png", png_bytes(size=(1080, 1920)), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert client.get(f"/api/projects/{slug}").json()["thumbnail"]["image"] == "images/cover.png"


def test_render_postv_is_422_not_500(client, pv):  # noqa: F811
    r = client.post(f"/api/projects/{pv['slug']}/render", json={})
    assert r.status_code == 422 and "PostV" in r.json()["detail"]


def test_renders_and_clean_work_for_postv(client, pv):  # noqa: F811
    assert client.get(f"/api/projects/{pv['slug']}/renders").json() == []
    assert client.post(f"/api/projects/{pv['slug']}/build/clean").status_code == 200


# Mọi router của video HBT gặp slug PostV phải trả 4xx rõ ràng, không bao giờ 500.
VIDEO_ONLY = [
    ("get", "/api/projects/{s}/scenes/0/preview.png", None),
    ("post", "/api/projects/{s}/scenes/0/preview.png", {"scene": {}}),
    ("post", "/api/projects/{s}/scenes/reorder", {"order": [0]}),
    ("delete", "/api/projects/{s}/scenes/0", None),
    ("post", "/api/projects/{s}/thumbnail/preview.jpg", {}),
    ("post", "/api/projects/{s}/lint", None),
    ("post", "/api/projects/{s}/script/check", {"script": "[]"}),
    ("post", "/api/projects/{s}/script/apply", {"script": "[]", "base_hash": "x"}),
    ("post", "/api/projects/{s}/backups/abc/restore", None),
]


def test_backups_list_is_harmless_for_postv(client, pv):  # noqa: F811
    r = client.get(f"/api/projects/{pv['slug']}/backups")
    assert r.status_code < 500


@pytest.mark.parametrize(("method", "url", "body"), VIDEO_ONLY)
def test_video_routes_reject_postv_without_500(client, pv, method, url, body):  # noqa: F811
    kw = {"json": body} if body is not None else {}
    r = getattr(client, method)(url.format(s=pv["slug"]), **kw)
    assert 400 <= r.status_code < 500, (url, r.status_code, r.text)


def test_music_from_library_for_postv(client, pv):  # noqa: F811
    lib = client.tmp / "library" / "music"
    lib.mkdir(parents=True, exist_ok=True)
    from tests.helpers import write_wav

    write_wav(lib / "bai.wav", [("tone", 1.0)])
    (lib / "index.json").write_text(
        json.dumps(
            [
                {
                    "id": "bai",
                    "file": "bai.wav",
                    "title": "Bài",
                    "artist": "A",
                    "source": "S",
                    "license": "L",
                }
            ]
        ),
        encoding="utf-8",
    )
    r = client.post(f"/api/projects/{pv['slug']}/music/from-library", json={"id": "bai"})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "postv" and r.json()["music"]["credit"].startswith("Bài")
