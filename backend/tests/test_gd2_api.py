"""API GĐ2: kiểm và tạo dự án từ JSON nháp (IMPLEMENT-GD2 mục 4)."""

import json

from tests.gd2_kit import codes, sample
from tests.test_api import client  # noqa: F401


def projects_dir(client):  # noqa: F811
    return client.tmp / "workspace" / "projects"


def check(client, draft):  # noqa: F811
    return client.post("/api/gd2/draft/check", json={"draft": draft})


def create(client, draft, **kw):  # noqa: F811
    return client.post("/api/gd2/draft/create", json={"draft": draft, **kw})


def test_check_writes_nothing(client):  # noqa: F811
    r = check(client, sample())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["errors"] == [] and body["scenes"] == 3
    assert body["music_match"] is None
    assert not projects_dir(client).exists() or list(projects_dir(client).iterdir()) == []


def test_check_reports_errors_with_200(client):  # noqa: F811
    r = check(client, sample(hbt_draft=2))
    assert r.status_code == 200 and r.json()["ok"] is False
    assert codes(r.json()["errors"]) == ["K13"]


def test_check_accepts_json_string(client):  # noqa: F811
    r = check(client, json.dumps(sample(), ensure_ascii=False))
    assert r.json()["ok"] is True
    r = check(client, "{")
    assert codes(r.json()["errors"]) == ["K1"]


def test_create_builds_project_and_draft_json(client):  # noqa: F811
    r = create(client, sample())
    assert r.status_code == 200, r.text
    body = r.json()
    slug = body["slug"]
    p = body["project"]
    assert p["title"].startswith("Vì sao muỗi") and p["series"] == "Vì sao…"
    assert len(p["scenes"]) == 3
    assert p["scenes"][0]["punch"] is True
    assert p["scenes"][1]["voice"] == "Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét."
    assert p["scenes"][0]["card"]["lines"][1]["text"] == "CHỌN BẠN?"
    assert p["publish"]["hashtags"] == ["haybiettuot", "muoi", "visao"]
    assert p["thumbnail"]["scene"] == 1
    assert "image_prompt" not in json.dumps(p)  # trường nháp không rò vào project.json
    folder = projects_dir(client) / slug
    on_disk = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    assert on_disk["slug"] == slug and "topic" not in on_disk
    d = json.loads((folder / "draft.json").read_text(encoding="utf-8"))
    assert d["topic"].startswith("Vì sao muỗi") and d["music_mood"] == "tò mò"
    assert d["sources"][0]["id"] == "s1"
    assert [s["image_prompt_ok"] for s in d["scenes"]] == [True, True, True]
    assert d["scenes"][1]["image_prompt"].startswith("person breathing")
    assert d["images_approved"] is False
    assert not (folder / "draft.json.tmp").exists()
    got = client.get(f"/api/projects/{slug}/draft").json()
    assert all(got[k] == v for k, v in d.items() if k != "scenes")
    assert [(x["image_prompt"], x["image_prompt_ok"]) for x in got["scenes"]] == [
        (x["image_prompt"], x["image_prompt_ok"]) for x in d["scenes"]
    ]
    assert all(not x["image_approved"] and x["full_prompt"] for x in got["scenes"])


def test_create_title_override_and_unique_slug(client):  # noqa: F811
    a = create(client, sample(), title="Muỗi một").json()["slug"]
    b = create(client, sample(), title="Muỗi một").json()
    assert b["project"]["title"] == "Muỗi một" and b["slug"] != a


def test_create_with_errors_creates_nothing(client):  # noqa: F811
    d = sample()
    d["scenes"][0]["card"]["lines"][0]["size"] = "huge"  # K3
    r = create(client, d)
    assert r.status_code == 422
    assert "K3" in codes(r.json()["errors"])
    r = create(client, sample(topic=""))
    assert r.status_code == 422 and "K13" in codes(r.json()["errors"])
    assert not projects_dir(client).exists() or list(projects_dir(client).iterdir()) == []


def test_create_with_warnings_still_creates(client):  # noqa: F811
    d = sample()
    del d["scenes"][1]["image_prompt"]  # K18
    d["scenes"][0]["image_prompt"] = "a map"  # K17
    d["scenes"][2]["voice"] = "Chạy 99 vòng."  # K16
    r = create(client, d)
    assert r.status_code == 200
    assert {"K16", "K17", "K18"} <= set(codes(r.json()["warnings"]))
    draft = client.get(f"/api/projects/{r.json()['slug']}/draft").json()
    assert [s["image_prompt_ok"] for s in draft["scenes"]] == [True, False, True]


def test_create_attaches_music_by_mood_without_touching_index(client):  # noqa: F811
    root = client.tmp / "library" / "music"
    root.mkdir(parents=True)
    (root / "curious.mp3").write_bytes(b"ID3")
    index = root / "index.json"
    index.write_text(
        json.dumps(
            [
                {
                    "id": "curious",
                    "file": "curious.mp3",
                    "title": "Curious",
                    "artist": "A",
                    "source": "Pixabay",
                    "license": "Pixabay",
                    "moods": ["Tò mò"],
                }
            ]
        ),
        encoding="utf-8",
    )
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    chk = check(client, sample()).json()
    assert chk["music_match"] == {"id": "curious", "title": "Curious"}
    r = create(client, sample())
    assert r.status_code == 200
    music = r.json()["project"]["music"]
    assert music["file"] == "music.mp3" and "Curious" in music["credit"]
    assert (projects_dir(client) / r.json()["slug"] / "music.mp3").is_file()
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_create_without_matching_mood_leaves_music_blank(client):  # noqa: F811
    r = create(client, sample(music_mood="không có bài nào"))
    assert r.status_code == 200 and r.json()["project"]["music"] is None


def test_get_draft_404_for_normal_project(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Thường", "scene_count": 3}).json()["slug"]
    assert client.get(f"/api/projects/{slug}/draft").status_code == 404
