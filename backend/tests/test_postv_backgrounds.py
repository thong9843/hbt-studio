"""Thư viện nền gameplay của PostV (docs/postv/IMPLEMENT-POSTV.md mục 4)."""

import json
import subprocess

import pytest

from hbt.pipeline.ffutil import ffmpeg_exe
from hbt.postv.backgrounds import BackgroundLibrary, background_problems
from hbt.storage import BadRequest, NotFound, Unprocessable
from tests.helpers import needs_ffmpeg
from tests.test_api import client  # noqa: F401

pytestmark = needs_ffmpeg

META = {"title": "Parkour 01", "source": "Tự quay", "license": "Tự quay", "url": "", "tags": []}


def make_clip(path, w=720, h=1280, seconds=4, fps=30, extra=()):
    cmd = [
        ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi",
        "-i", f"testsrc=size={w}x{h}:rate={fps}:duration={seconds}",
        "-pix_fmt", "yuv420p", *extra, str(path),
    ]  # fmt: skip
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture
def lib(tmp_path):
    return BackgroundLibrary(tmp_path / "library")


@pytest.fixture
def clip(tmp_path):
    return make_clip(tmp_path / "in.mp4")


def test_add_reads_the_video_and_stores_file_thumb_and_index(lib, clip):
    entry = lib.add(clip, "in.mp4", META)
    assert (entry.id, entry.file) == ("parkour-01", "parkour-01.mp4")
    assert (entry.width, entry.height) == (720, 1280)
    assert entry.fps == pytest.approx(30, abs=0.1) and entry.duration == pytest.approx(4, abs=0.3)
    assert (lib.root / "parkour-01.mp4").is_file() and not clip.exists()  # file được chuyển vào
    assert lib.thumb_path("parkour-01").read_bytes()[:2] == b"\xff\xd8"  # JPEG
    assert [e.id for e in lib.list()] == ["parkour-01"]
    assert json.loads(lib.index_path.read_text(encoding="utf-8"))[0]["license"] == "Tự quay"

    # Test remove
    lib.remove("parkour-01")
    assert not (lib.root / "parkour-01.mp4").is_file()
    assert not (lib.thumbs_dir / "parkour-01.jpg").is_file()
    assert len(lib.list()) == 0


def test_delete_background_endpoint(client, tmp_path):  # noqa: F811
    in_clip = make_clip(tmp_path / "temp_in.mp4")
    with open(in_clip, "rb") as f:
        r = client.post(
            "/api/backgrounds",
            data={"title": "Test Delete", "source": "src", "license": "lic"},
            files={"file": ("test.mp4", f, "video/mp4")},
        )
    assert r.status_code == 201
    clip_id = r.json()["id"]

    # Tạo dự án PostV dùng clip_id này
    p_res = client.post("/api/projects", json={"title": "Dùng Clip", "kind": "postv"})
    slug = p_res.json()["slug"]
    p_data = client.get(f"/api/projects/{slug}").json()
    p_data["background"]["clip_ids"] = [clip_id]
    client.put(f"/api/projects/{slug}", json=p_data)

    # Xóa bị 409 do dự án đang dùng
    del_r = client.delete(f"/api/backgrounds/{clip_id}")
    assert del_r.status_code == 409
    assert "Dùng Clip" in del_r.text

    # Bỏ dùng clip
    p_data["background"]["clip_ids"] = []
    client.put(f"/api/projects/{slug}", json=p_data)

    # Giờ xóa thành công 204
    del_ok = client.delete(f"/api/backgrounds/{clip_id}")
    assert del_ok.status_code == 204


def test_same_title_gets_a_new_id(lib, tmp_path):
    a = lib.add(make_clip(tmp_path / "a.mp4"), "a.mp4", META)
    b = lib.add(make_clip(tmp_path / "b.mp4"), "b.mp4", META)
    assert (a.id, b.id) == ("parkour-01", "parkour-01-2")


@pytest.mark.parametrize("missing", ["title", "source", "license"])
def test_title_source_and_license_are_required(lib, clip, missing):
    with pytest.raises(BadRequest, match=missing):
        lib.add(clip, "in.mp4", {**META, missing: "  "})
    assert lib.list() == []


def test_landscape_video_is_refused(lib, tmp_path):
    with pytest.raises(BadRequest, match="dọc"):
        lib.add(make_clip(tmp_path / "w.mp4", w=1280, h=720), "w.mp4", META)
    assert lib.list() == []


def test_too_small_or_too_short_is_refused(lib, tmp_path):
    with pytest.raises(BadRequest, match="nhỏ quá"):
        lib.add(make_clip(tmp_path / "s.mp4", w=360, h=640), "s.mp4", META)
    with pytest.raises(BadRequest, match="ngắn quá"):
        lib.add(make_clip(tmp_path / "t.mp4", seconds=1), "t.mp4", META)


def test_wrong_extension_and_not_a_video_are_refused(lib, tmp_path, clip):
    with pytest.raises(BadRequest, match="Đuôi file"):
        lib.add(clip, "in.avi", META)
    fake = tmp_path / "fake.mp4"
    fake.write_text("đây không phải video", encoding="utf-8")
    with pytest.raises(BadRequest):
        lib.add(fake, "fake.mp4", META)
    assert lib.list() == []


def test_rotated_phone_video_counts_by_displayed_size(lib, tmp_path):
    """Video quay dọc ghi 1280×720 kèm cờ xoay 90° vẫn là video dọc."""
    src = make_clip(tmp_path / "land.mp4", w=1280, h=720)
    rotated = tmp_path / "rot.mp4"
    subprocess.run(
        [
            ffmpeg_exe(),
            "-v",
            "error",
            "-y",
            "-display_rotation",
            "90",
            "-i",
            str(src),
            "-c",
            "copy",
            str(rotated),
        ],
        check=True,
    )
    assert (lib.add(rotated, "rot.mp4", META).width,) == (720,)


def test_low_resolution_flag(lib, tmp_path):
    small = lib.add(make_clip(tmp_path / "a.mp4"), "a.mp4", META)
    full = lib.add(
        make_clip(tmp_path / "b.mp4", w=1080, h=1920, seconds=3), "b.mp4", {**META, "title": "Full"}
    )
    assert small.low_resolution is True and full.low_resolution is False


def test_find_errors(lib, clip):
    lib.add(clip, "in.mp4", META)
    with pytest.raises(Unprocessable):
        lib.find("Khong Hop Le")
    with pytest.raises(NotFound):
        lib.find("khong-co")
    (lib.root / "parkour-01.mp4").unlink()
    with pytest.raises(NotFound):
        lib.find("parkour-01")


def test_broken_index_is_a_clear_error(lib):
    lib.root.mkdir(parents=True)
    lib.index_path.write_text("{không phải json", encoding="utf-8")
    with pytest.raises(BadRequest, match="index.json"):
        lib.list()
    lib.index_path.write_text('[{"id": "a"}]', encoding="utf-8")
    with pytest.raises(BadRequest):
        lib.list()


def test_background_problems(lib, tmp_path):
    assert background_problems([], lib) == ["Chưa có clip nền nào trong thư viện"]
    lib.add(make_clip(tmp_path / "a.mp4"), "a.mp4", META)
    assert background_problems([], lib) == []
    assert background_problems(["parkour-01"], lib) == []
    assert background_problems(["khong-co"], lib) == [
        "Clip nền 'khong-co' không còn trong thư viện"
    ]
    (lib.root / "parkour-01.mp4").unlink()
    assert background_problems([], lib) == ["Thiếu file video của clip nền 'Parkour 01'"]


# ------------------------------------------------------------------ API
def upload(client, path, **over):  # noqa: F811
    data = {"title": "Parkour 01", "source": "Tự quay", "license": "Tự quay", **over}
    return client.post(
        "/api/backgrounds", data=data, files={"file": ("clip.mp4", path.read_bytes(), "video/mp4")}
    )


def test_api_add_list_play_and_thumb(client, clip):  # noqa: F811
    assert client.get("/api/backgrounds").json() == []
    r = upload(client, clip, tags="parkour, minecraft", url="https://example.com")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == "parkour-01" and body["tags"] == ["parkour", "minecraft"]
    assert [e["id"] for e in client.get("/api/backgrounds").json()] == ["parkour-01"]
    video = client.get("/api/backgrounds/parkour-01/video")
    assert video.status_code == 200 and len(video.content) > 1000
    thumb = client.get("/api/backgrounds/parkour-01/thumb")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"


def test_api_rejects_missing_license_and_landscape(client, clip, tmp_path):  # noqa: F811
    assert upload(client, clip, license="  ").status_code == 400
    wide = make_clip(tmp_path / "w.mp4", w=1280, h=720)
    assert upload(client, wide).status_code == 400
    assert client.get("/api/backgrounds").json() == []
    leftovers = list((client.tmp / "workspace" / ".uploads").glob("*"))
    assert leftovers == []  # không để file tạm


def test_api_unknown_clip_is_404(client):  # noqa: F811
    assert client.get("/api/backgrounds/khong-co/video").status_code == 404
    assert client.get("/api/backgrounds/khong-co/thumb").status_code == 404
    assert client.get("/api/backgrounds/KHONG HOP LE/video").status_code in (404, 422)
