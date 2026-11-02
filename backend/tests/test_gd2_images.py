"""Duyệt ảnh theo dấu ảnh từng cảnh và sửa prompt (G2, IMPLEMENT-GD2 mục 6)."""

import json

from tests.gd2_kit import sample
from tests.test_api import client, png_bytes  # noqa: F401


def make(client, **kw):  # noqa: F811
    r = client.post("/api/gd2/draft/create", json={"draft": sample(**kw)})
    assert r.status_code == 200, r.text
    return r.json()["slug"]


def put_image(client, slug, i, color):  # noqa: F811
    r = client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": "image", "scene_index": str(i)},
        files={"file": ("a.png", png_bytes(color), "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()["path"]


def draft(client, slug):  # noqa: F811
    return client.get(f"/api/projects/{slug}/draft").json()


def approve(client, slug, approved=True):  # noqa: F811
    return client.put(f"/api/projects/{slug}/draft/images-approved", json={"approved": approved})


def colour(i):
    return (40 * i + 20, 90, 70)


def fill(client, slug, n=3):  # noqa: F811
    return [put_image(client, slug, i, colour(i)) for i in range(n)]


def folder(client, slug):  # noqa: F811
    return client.tmp / "workspace" / "projects" / slug


def test_get_has_full_prompt_and_not_approved(client):  # noqa: F811
    slug = make(client)
    d = draft(client, slug)
    assert d["images_approved"] is False
    assert [s["image_approved"] for s in d["scenes"]] == [False] * 3
    assert d["scenes"][0]["full_prompt"].startswith("close-up of a mosquito")
    assert "no text" in d["scenes"][0]["full_prompt"]


def test_approve_needs_all_images(client):  # noqa: F811
    slug = make(client)
    put_image(client, slug, 0, (1, 2, 3))
    r = approve(client, slug)
    assert r.status_code == 422 and "2, 3" in r.json()["detail"]
    assert draft(client, slug)["images_approved"] is False


def test_approve_stores_marks_and_survives_reload(client):  # noqa: F811
    slug = make(client)
    images = fill(client, slug)
    r = approve(client, slug)
    assert r.status_code == 200 and r.json()["images_approved"] is True
    on_disk = json.loads((folder(client, slug) / "draft.json").read_text(encoding="utf-8"))
    assert on_disk["approved_marks"] == images and on_disk["images_approved"] is True
    d = draft(client, slug)
    assert d["images_approved"] is True and all(s["image_approved"] for s in d["scenes"])


def test_changing_one_image_unapproves_only_that_scene(client):  # noqa: F811
    slug = make(client)
    images = fill(client, slug)
    approve(client, slug)
    new = put_image(client, slug, 1, (250, 250, 10))
    assert new != images[1]
    d = draft(client, slug)
    assert [s["image_approved"] for s in d["scenes"]] == [True, False, True]
    assert d["images_approved"] is False
    # đưa về đúng ảnh cũ thì khớp dấu lại
    again = put_image(client, slug, 1, colour(1))
    assert again == images[1]
    assert draft(client, slug)["images_approved"] is True


def test_unapprove_clears_marks(client):  # noqa: F811
    slug = make(client)
    fill(client, slug)
    approve(client, slug)
    r = approve(client, slug, False)
    assert r.json()["images_approved"] is False
    on_disk = json.loads((folder(client, slug) / "draft.json").read_text(encoding="utf-8"))
    assert on_disk["approved_marks"] == [] and on_disk["images_approved"] is False


def test_get_does_not_write(client):  # noqa: F811
    slug = make(client)
    fill(client, slug)
    approve(client, slug)
    path = folder(client, slug) / "draft.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    put_image(client, slug, 0, (9, 9, 9))  # đổi ảnh: kết quả đọc đổi nhưng file nháp thì không
    assert draft(client, slug)["scenes"][0]["image_approved"] is False
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_prompt_edit_for_missing_prompt_keeps_approval(client):  # noqa: F811
    d = sample()
    del d["scenes"][2]["image_prompt"]
    slug = client.post("/api/gd2/draft/create", json={"draft": d}).json()["slug"]
    got = draft(client, slug)
    assert got["scenes"][2]["image_prompt_ok"] is False and got["scenes"][2]["full_prompt"] == ""
    fill(client, slug)
    approve(client, slug)
    r = client.put(
        f"/api/projects/{slug}/draft/scenes/2/prompt", json={"image_prompt": "  a pond at dusk  "}
    )
    assert r.status_code == 200
    s2 = r.json()["scenes"][2]
    assert s2["image_prompt"] == "a pond at dusk" and s2["image_prompt_ok"] is True
    assert s2["full_prompt"].startswith("a pond at dusk.")
    assert r.json()["images_approved"] is True  # dấu duyệt gắn với ảnh, không với prompt
    r = client.put(f"/api/projects/{slug}/draft/scenes/2/prompt", json={"image_prompt": " "})
    assert r.json()["scenes"][2]["image_prompt_ok"] is False


def test_prompt_index_out_of_range_and_no_draft(client):  # noqa: F811
    slug = make(client)
    r = client.put(f"/api/projects/{slug}/draft/scenes/9/prompt", json={"image_prompt": "x"})
    assert r.status_code == 404
    plain = client.post("/api/projects", json={"title": "Thường", "scene_count": 3}).json()["slug"]
    assert client.get(f"/api/projects/{plain}/draft").status_code == 404
    assert approve(client, plain).status_code == 404
    r = client.put(f"/api/projects/{plain}/draft/scenes/0/prompt", json={"image_prompt": "x"})
    assert r.status_code == 404


def test_draft_exists_answers_200_either_way(client):  # noqa: F811
    slug = make(client)
    plain = client.post("/api/projects", json={"title": "Thường", "scene_count": 3}).json()["slug"]
    assert client.get(f"/api/projects/{slug}/draft/exists").json() == {"exists": True}
    r = client.get(f"/api/projects/{plain}/draft/exists")
    assert r.status_code == 200 and r.json() == {"exists": False}
    assert client.get("/api/projects/khong-co/draft/exists").json() == {"exists": False}
