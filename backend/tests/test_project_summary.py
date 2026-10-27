"""GET /projects: `cover` và `last_final` (IMPLEMENT 13.B6a)."""

import json

from tests.test_api import client  # noqa: F401


def make_render(folder, job_id, created_at, *, preview=False, cover=False, **meta):
    d = folder / "renders" / job_id
    d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(b"x")
    data = {"created_at": created_at, "preview": preview, "fps": 30 if preview else 50, **meta}
    (d / "meta.json").write_text(json.dumps(data), encoding="utf-8")
    if cover:
        (d / "cover_9x16.jpg").write_bytes(b"\xff\xd8\xff\xd9")


def new_project(client, title="Tóm tắt"):  # noqa: F811
    slug = client.post("/api/projects", json={"title": title}).json()["slug"]
    return slug, client.app.state.hbt.storage.project_dir(slug)


def summary(client, slug):  # noqa: F811
    return next(p for p in client.get("/api/projects").json() if p["slug"] == slug)


def test_project_without_renders_has_null_cover_and_last_final(client):  # noqa: F811
    slug, _ = new_project(client)
    item = summary(client, slug)
    assert item["cover"] is None and item["last_final"] is None and item["last_render"] is None


def test_summary_keys_keep_their_order_and_new_ones_come_last(client):  # noqa: F811
    slug, _ = new_project(client)
    assert list(summary(client, slug)) == [
        "slug",
        "title",
        "updated_at",
        "thumb",
        "last_render",
        "error",
        "cover",
        "last_final",
    ]


def test_only_quick_previews_means_no_last_final(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "p1", "2026-10-01T10:00:00Z", preview=True)
    make_render(folder, "p2", "2026-10-02T10:00:00Z", preview=True, preview_seconds=10)
    item = summary(client, slug)
    assert item["last_render"]["job_id"] == "p2" and item["last_render"]["preview"] is True
    assert item["last_final"] is None and item["cover"] is None


def test_last_final_is_the_newest_non_preview_with_the_same_fields_as_last_render(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "f1", "2026-10-01T10:00:00Z", render_seconds=140.0, align_cached=False)
    make_render(folder, "f2", "2026-10-02T10:00:00Z", render_seconds=60.5, align_cached=True)
    make_render(folder, "p3", "2026-10-03T10:00:00Z", preview=True)
    item = summary(client, slug)
    assert item["last_render"]["job_id"] == "p3"
    final = item["last_final"]
    assert final == {
        "job_id": "f2",
        "preview": False,
        "fps": 50,
        "duration": None,
        "render_seconds": 60.5,
        "align_cached": True,
        "created_at": "2026-10-02T10:00:00Z",
        "video": f"/api/files/projects/{slug}/renders/f2/video.mp4",
    }
    assert set(final) == set(item["last_render"])


def test_cover_skips_a_newer_final_whose_cover_failed(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "old", "2026-10-01T10:00:00Z", cover=True)
    make_render(folder, "new", "2026-10-02T10:00:00Z", cover=False)  # vẽ bìa lỗi chỉ cảnh báo
    make_render(folder, "quick", "2026-10-03T10:00:00Z", preview=True)
    item = summary(client, slug)
    assert item["last_final"]["job_id"] == "new"  # bản đẹp mới nhất vẫn là bản không có bìa
    assert item["cover"] == f"/api/files/projects/{slug}/renders/old/cover_9x16.jpg"
    served = client.get(item["cover"])  # URL dùng được ngay qua API files
    assert served.status_code == 200 and served.content == b"\xff\xd8\xff\xd9"


def test_cover_comes_from_the_newest_render_that_has_one(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "a", "2026-10-01T10:00:00Z", cover=True)
    make_render(folder, "b", "2026-10-02T10:00:00Z", cover=True)
    make_render(folder, "c", "2026-10-03T10:00:00Z")
    assert summary(client, slug)["cover"].endswith("/renders/b/cover_9x16.jpg")


def test_cover_is_never_a_path_outside_the_files_api(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "a", "2026-10-01T10:00:00Z", cover=True)
    cover = summary(client, slug)["cover"]
    assert cover.startswith("/api/files/projects/") and ":" not in cover and "\\" not in cover


def test_duplicate_does_not_carry_cover_or_last_final(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "a", "2026-10-01T10:00:00Z", cover=True)
    copy = client.post(f"/api/projects/{slug}/duplicate").json()["slug"]
    assert copy != slug
    dup = summary(client, copy)
    assert dup["cover"] is None and dup["last_final"] is None and dup["last_render"] is None
    original = summary(client, slug)
    assert original["cover"].endswith("/renders/a/cover_9x16.jpg")
    assert original["last_final"]["job_id"] == "a"


def test_broken_project_still_lists_with_null_new_fields(client):  # noqa: F811
    slug, folder = new_project(client)
    (folder / "project.json").write_text("{hỏng", encoding="utf-8")
    item = summary(client, slug)
    assert item["error"] and item["cover"] is None and item["last_final"] is None
