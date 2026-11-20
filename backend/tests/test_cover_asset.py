"""POST /assets kind=cover: lưu images/cover.<ext> và gắn vào thumbnail.image."""

import io

import pytest
from PIL import Image

from tests.test_api import client, png_bytes  # noqa: F401
from tests.test_api_m3 import with_thumbnail


def image_bytes(fmt="PNG", size=(1080, 1920), color=(30, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def upload_cover(client, slug, data, name="a.png"):  # noqa: F811
    return client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": "cover"},
        files={"file": (name, data, "application/octet-stream")},
    )


def folder_of(client, slug):  # noqa: F811
    return client.app.state.hbt.storage.project_dir(slug)


@pytest.mark.parametrize(("fmt", "ext"), [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
def test_cover_upload_stores_cover_file_and_sets_thumbnail_image(client, fmt, ext):  # noqa: F811
    slug = with_thumbnail(client)
    r = upload_cover(client, slug, image_bytes(fmt))
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "cover" and body["path"] == f"images/cover.{ext}"
    assert body["project"]["thumbnail"]["image"] == f"images/cover.{ext}"
    assert (folder_of(client, slug) / f"images/cover.{ext}").is_file()
    saved = client.get(f"/api/projects/{slug}").json()
    assert saved["thumbnail"]["image"] == f"images/cover.{ext}"
    assert saved["thumbnail"]["lines"] == ["bạn có phải", "người được", "muỗi yêu?"]  # không đổi


def test_cover_upload_does_not_touch_scene_images(client):  # noqa: F811
    slug = with_thumbnail(client)
    before = client.get(f"/api/projects/{slug}").json()["scenes"]
    upload_cover(client, slug, image_bytes())
    after = client.get(f"/api/projects/{slug}").json()["scenes"]
    assert [s["image"] for s in before] == [s["image"] for s in after]


def test_replacing_with_another_extension_removes_the_old_cover_file(client):  # noqa: F811
    slug = with_thumbnail(client)
    upload_cover(client, slug, image_bytes("PNG"))
    r = upload_cover(client, slug, image_bytes("JPEG", color=(250, 0, 0)))
    assert r.json()["project"]["thumbnail"]["image"] == "images/cover.jpg"
    images = folder_of(client, slug) / "images"
    assert not (images / "cover.png").exists() and (images / "cover.jpg").is_file()
    upload_cover(client, slug, image_bytes("JPEG", color=(0, 250, 0)))  # cùng đuôi → ghi đè
    px = Image.open(images / "cover.jpg").convert("RGB").getpixel((10, 10))
    assert px[1] > 200 and sorted(p.name for p in images.glob("cover.*")) == ["cover.jpg"]


def test_clearing_image_keeps_the_file_on_disk(client):  # noqa: F811
    slug = with_thumbnail(client)
    upload_cover(client, slug, image_bytes())
    p = client.get(f"/api/projects/{slug}").json()
    p["thumbnail"]["image"] = None
    assert client.put(f"/api/projects/{slug}", json=p).status_code == 200
    assert client.get(f"/api/projects/{slug}").json()["thumbnail"]["image"] is None
    assert (folder_of(client, slug) / "images/cover.png").is_file()


def test_cover_needs_the_thumbnail_block(client):  # noqa: F811
    slug = client.post("/api/projects", json={"title": "Chưa bật bìa"}).json()["slug"]
    r = upload_cover(client, slug, image_bytes())
    assert r.status_code == 422 and "bật ảnh bìa" in r.json()["detail"]
    assert not (folder_of(client, slug) / "images/cover.png").exists()


@pytest.mark.parametrize(
    ("size", "ok"),
    [((540, 960), True), ((960, 540), True), ((539, 2000), False), ((2000, 539), False)],
)
def test_cover_short_side_must_be_at_least_540(client, size, ok):  # noqa: F811
    slug = with_thumbnail(client)
    r = upload_cover(client, slug, image_bytes(size=size))
    assert r.status_code == (200 if ok else 400)
    if not ok:
        assert "540" in r.json()["detail"]
        assert not (folder_of(client, slug) / "images/cover.png").exists()


def test_cover_rejects_non_images_and_other_formats(client):  # noqa: F811
    slug = with_thumbnail(client)
    assert upload_cover(client, slug, b"khong phai anh").status_code == 400
    assert upload_cover(client, slug, image_bytes("GIF")).status_code == 400
    assert upload_cover(client, slug, b"").status_code == 400
    assert client.get(f"/api/projects/{slug}").json()["thumbnail"]["image"] is None


def test_cover_too_large_is_413(client, monkeypatch):  # noqa: F811
    from hbt.api import assets

    slug = with_thumbnail(client)
    monkeypatch.setitem(assets.MAX_BYTES, "cover", 1000)
    assert upload_cover(client, slug, image_bytes()).status_code == 413


def test_cover_upload_is_refused_while_rendering(client, monkeypatch):  # noqa: F811
    slug = with_thumbnail(client)
    monkeypatch.setattr(client.app.state.hbt.jobs, "is_busy", lambda s: True)
    assert upload_cover(client, slug, image_bytes()).status_code == 409


def test_cover_upload_unknown_project_is_404(client):  # noqa: F811
    assert upload_cover(client, "khong-co", image_bytes()).status_code == 404


def test_duplicate_copies_the_cover_file(client):  # noqa: F811
    slug = with_thumbnail(client)
    upload_cover(client, slug, image_bytes())
    new = client.post(f"/api/projects/{slug}/duplicate", json={}).json()
    assert new["thumbnail"]["image"] == "images/cover.png"
    assert (folder_of(client, new["slug"]) / "images/cover.png").is_file()


def test_build_clean_keeps_the_cover_file(client):  # noqa: F811
    slug = with_thumbnail(client)
    upload_cover(client, slug, image_bytes())
    assert client.post(f"/api/projects/{slug}/build/clean").status_code == 200
    assert (folder_of(client, slug) / "images/cover.png").is_file()


def test_uploaded_cover_is_served_and_used_by_the_preview(client):  # noqa: F811
    slug = with_thumbnail(client)
    upload_cover(client, slug, image_bytes(size=(1600, 900), color=(220, 0, 0)))
    url = f"/api/projects/{slug}/thumbnail/preview.jpg?w=270"
    r = client.post(url, json={})
    px = Image.open(io.BytesIO(r.content)).convert("RGB").getpixel((135, 20))
    assert r.status_code == 200 and px[0] > px[1] * 2
    f = client.get(f"/api/files/projects/{slug}/images/cover.png")
    assert f.status_code == 200 and f.headers["cache-control"] == "no-cache"
