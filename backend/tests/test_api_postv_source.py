"""API nhập nguồn PostV: tách chữ dán, kiểm tra kịch bản, danh sách từ che (PV2)."""

import json

import pytest

from hbt.postv.parse import MAX_TEXT
from tests.test_api import client  # noqa: F401

PASTE = "user_a\n17h\nBài gốc có chữ\nuser_b\n14h\nBình luận 1\nuser_c\n13h\nBình luận 2\n"


@pytest.fixture
def pv(client):  # noqa: F811
    return client.post("/api/projects", json={"title": "Bài thử", "kind": "postv"}).json()


def put_segments(client, pv, voices, **over):  # noqa: F811
    body = client.get(f"/api/projects/{pv['slug']}").json()
    body["segments"] = [{"role": "commentary", "voice": v} for v in voices]
    body.update(over)
    r = client.put(f"/api/projects/{pv['slug']}", json=body)
    assert r.status_code == 200, r.text


def test_parse_returns_post_and_comments(client):  # noqa: F811
    r = client.post("/api/postv/parse", json={"text": PASTE})
    assert r.status_code == 200
    body = r.json()
    assert body["guess"] == "threads_text"
    assert body["post"] == {"handle": "user_a", "age": "17 giờ", "text": "Bài gốc có chữ"}
    assert [c["id"] for c in body["comments"]] == ["c1", "c2"]
    assert body["comments"][0]["picked"] is True


def test_parse_writes_nothing(client, tmp_path):  # noqa: F811
    before = sorted(p.name for p in (client.tmp / "workspace").rglob("*"))
    client.post("/api/postv/parse", json={"text": PASTE})
    assert sorted(p.name for p in (client.tmp / "workspace").rglob("*")) == before


def test_parse_rejects_empty_and_oversized(client):  # noqa: F811
    assert client.post("/api/postv/parse", json={"text": "   \n"}).status_code == 422
    assert client.post("/api/postv/parse", json={"text": "x" * (MAX_TEXT + 1)}).status_code == 422
    assert client.post("/api/postv/parse", json={}).status_code == 422


def test_parse_embed_code_does_not_fetch_the_link(client):  # noqa: F811
    embed = (
        '<blockquote data-text-post-permalink="https://www.threads.com/@u/post/X">v</blockquote>'
    )
    body = client.post("/api/postv/parse", json={"text": embed}).json()
    assert body["guess"] == "embed" and body["source_url"].endswith("/post/X")


def test_script_check_estimates_and_reports_censor(client, pv):  # noqa: F811
    put_segments(client, pv, ["x" * 165, "peak vcl"], post={"text": "ok"})
    r = client.post(f"/api/projects/{pv['slug']}/postv/script/check")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chars"] == 165 + 8 and body["long"] is False
    assert body["censored"] == 1
    assert [(i["where"], i["word"]) for i in body["issues"]] == [("Đoạn 2", "vcl")]


def test_script_check_on_empty_project_is_fine(client, pv):  # noqa: F811
    body = client.post(f"/api/projects/{pv['slug']}/postv/script/check").json()
    assert body["seconds"] == 0 and body["issues"] == [] and body["segments"] == []


def test_script_check_errors(client):  # noqa: F811
    assert client.post("/api/projects/khong-co/postv/script/check").status_code == 404
    video = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3}).json()
    assert client.post(f"/api/projects/{video['slug']}/postv/script/check").status_code == 400


def test_script_check_does_not_modify_the_project(client, pv):  # noqa: F811
    path = client.tmp / "workspace" / "projects" / pv["slug"] / "project.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    client.post(f"/api/projects/{pv['slug']}/postv/script/check")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_postv_words_default_and_update(client, pv):  # noqa: F811
    words = client.get("/api/settings/postv-words").json()
    assert words["categories"][0]["id"] == "tuc"
    words["categories"][0]["words"].append("xyzzy")
    assert client.put("/api/settings/postv-words", json=words).status_code == 200
    put_segments(client, pv, ["nói xyzzy đi"])
    body = client.post(f"/api/projects/{pv['slug']}/postv/script/check").json()
    assert [i["word"] for i in body["issues"]] == ["xyzzy"]
    saved = client.tmp / "workspace" / "settings" / "postv_censor_words.json"
    assert "xyzzy" in json.loads(saved.read_text(encoding="utf-8"))["categories"][0]["words"]


def test_hbt_sensitive_words_list_is_untouched_by_postv_words(client):  # noqa: F811
    before = client.get("/api/settings/sensitive-words").json()
    client.put("/api/settings/postv-words", json=client.get("/api/settings/postv-words").json())
    assert client.get("/api/settings/sensitive-words").json() == before
    assert "tuc" not in [c["id"] for c in before["categories"]]  # video HBT không đổi hành vi
