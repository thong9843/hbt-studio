import io
import json
import shutil
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hbt.api import assets as assets_api
from hbt.config import BRAND_DIR, Settings
from hbt.main import create_app
from hbt.pipeline.cancel import RenderCancelled
from tests.helpers import needs_ffmpeg, write_wav
from tests.test_render import SENTENCES, speech


@pytest.fixture
def client(tmp_path):
    brand = tmp_path / "brand"
    brand.mkdir()
    shutil.copy(BRAND_DIR / "hay-biet-tuot_avatar.png", brand)
    settings = Settings(
        workspace_dir=tmp_path / "workspace",
        library_dir=tmp_path / "library",
        whisper_model="large-v3",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings, brand_dir=brand)
    with TestClient(app) as c:
        c.tmp = tmp_path
        yield c


def png_bytes(color=(220, 90, 70), size=(540, 960)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def upload_image(client, slug, scene, color=(220, 90, 70)):
    return client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": "image", "scene_index": str(scene)},
        files={"file": ("a.png", png_bytes(color), "image/png")},
    )


def upload_wav(client, slug, kind, parts):
    path = client.tmp / f"{kind}.wav"
    write_wav(path, parts)
    return client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": kind},
        files={"file": (f"{kind}.wav", path.read_bytes(), "audio/wav")},
    )


def complete_project(client, n=3, title="Thử nghiệm"):
    """Tạo project qua API rồi tải đủ ảnh + giọng + lời đọc."""
    slug = client.post("/api/projects", json={"title": title, "scene_count": n}).json()["slug"]
    for i in range(n):
        assert upload_image(client, slug, i, (40 * i + 60, 90, 140)).status_code == 200
    assert upload_wav(client, slug, "voice", [*speech(n), ("gap", 0.3)]).status_code == 200
    project = client.get(f"/api/projects/{slug}").json()
    for i, scene in enumerate(project["scenes"]):
        scene["voice"] = SENTENCES[i % len(SENTENCES)]
        scene["card"] = {"y": "top", "lines": [{"text": f"Cảnh {i + 1}", "size": "l"}]}
    project["settings"].update(aligner="silence", outro=False)
    assert client.put(f"/api/projects/{slug}", json=project).status_code == 200
    return slug


def wait_job(client, job_id, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.2)
    raise AssertionError("job không kết thúc")


def parse_sse(text):
    events, cur = [], {}
    for line in text.splitlines():
        if not line:
            if cur:
                events.append(cur)
                cur = {}
        elif line.startswith("event:"):
            cur["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            cur["data"] = json.loads(line.split(":", 1)[1].strip())
    if cur:
        events.append(cur)
    return [e for e in events if "event" in e]


class FakeRender:
    def __init__(self):
        self.started = threading.Event()
        self.gate = threading.Event()

    def __call__(self, folder, opts, progress=None, cancel_token=None):
        progress(5, "Căn chữ", "đang căn")
        self.started.set()
        while not self.gate.wait(0.05):
            if cancel_token.cancelled:
                raise RenderCancelled
        raise RuntimeError("không dùng")


# ---------------------------------------------------------------- project
def test_project_crud_roundtrip(client):
    r = client.post("/api/projects", json={"title": "Vì sao muỗi đốt?", "series": "VSVT"})
    assert r.status_code == 201
    created = r.json()
    assert created["slug"] == "vi-sao-muoi-dot" and len(created["scenes"]) == 8
    assert created["voice"] is None and created["series"] == "VSVT"

    assert client.get("/api/projects/vi-sao-muoi-dot").json() == created
    created["title"] = "Đã sửa"
    created["scenes"][0]["voice"] = "Xin chào | các bạn."
    r = client.put("/api/projects/vi-sao-muoi-dot", json=created)
    assert r.status_code == 200 and r.json()["title"] == "Đã sửa"
    assert (
        client.get("/api/projects/vi-sao-muoi-dot").json()["scenes"][0]["voice"].startswith("Xin")
    )

    assert client.delete("/api/projects/vi-sao-muoi-dot").status_code == 204
    r = client.get("/api/projects/vi-sao-muoi-dot")
    assert r.status_code == 404 and "detail" in r.json()


def test_list_projects(client):
    assert client.get("/api/projects").json() == []
    client.post("/api/projects", json={"title": "Một"})
    slug = client.post("/api/projects", json={"title": "Hai"}).json()["slug"]
    upload_image(client, slug, 0)
    items = {i["slug"]: i for i in client.get("/api/projects").json()}
    thumb = items["hai"]["thumb"]
    assert thumb.startswith("/api/files/projects/hai/images/") and thumb.endswith(".png")
    assert items["mot"]["thumb"] is None and items["mot"]["last_render"] is None
    assert items["hai"]["updated_at"].endswith("Z")
    assert client.get(items["hai"]["thumb"]).status_code == 200


@pytest.mark.parametrize(
    "body", [{"title": ""}, {"title": "X", "scene_count": 2}, {"title": "X", "scene_count": 13}, {}]
)
def test_create_validation(client, body):
    r = client.post("/api/projects", json=body)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_put_validation_and_mismatches(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    p = client.get(f"/api/projects/{slug}").json()
    bad_fps = {**p, "settings": {**p["settings"], "fps": 45}}
    r = client.put(f"/api/projects/{slug}", json=bad_fps)
    assert r.status_code == 422 and "fps" in r.json()["detail"]
    r = client.put(f"/api/projects/{slug}", json={**p, "slug": "khac"})
    assert r.status_code == 400 and "slug" in r.json()["detail"]
    assert client.put("/api/projects/khong-co", json={**p, "slug": "khong-co"}).status_code == 404
    assert (
        client.put(f"/api/projects/{slug}", json={**p, "scenes": p["scenes"][:2]}).status_code
        == 422
    )


@pytest.mark.parametrize("slug", ["Bad%20Slug", "UPPER", "a..b", "%2e%2e", "-a"])
def test_invalid_slugs_are_422_not_404(client, slug):
    r = client.get(f"/api/projects/{slug}")
    assert r.status_code == 422 and r.json()["detail"].startswith("Slug không hợp lệ")
    assert client.delete(f"/api/projects/{slug}").status_code == 422


def test_valid_but_missing_slug_is_still_404(client):
    assert client.get("/api/projects/khong-co").status_code == 404


def test_duplicate(client):
    slug = complete_project(client)
    r = client.post(f"/api/projects/{slug}/duplicate")
    assert r.status_code == 201 and r.json()["slug"] == f"{slug}-ban-sao"
    copy = r.json()
    assert (
        client.get(f"/api/files/projects/{copy['slug']}/{copy['scenes'][0]['image']}").status_code
        == 200
    )
    r = client.post(f"/api/projects/{slug}/duplicate", json={"title": "Mẫu series"})
    assert r.json()["slug"] == "mau-series" and r.json()["title"] == "Mẫu series"
    assert client.post("/api/projects/khong-co/duplicate").status_code == 404


def test_delete_refused_while_rendering(client, monkeypatch):
    slug = complete_project(client)
    monkeypatch.setattr(client.app.state.hbt.jobs, "is_busy", lambda s: True)
    r = client.delete(f"/api/projects/{slug}")
    assert r.status_code == 409 and "huỷ" in r.json()["detail"]
    assert client.get(f"/api/projects/{slug}").status_code == 200


# ---------------------------------------------------------------- tài sản
def test_image_upload_updates_the_project(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    r = upload_image(client, slug, 2)
    assert r.status_code == 200
    body = r.json()
    path = body["path"]
    assert body["kind"] == "image" and path.startswith("images/") and path.endswith(".png")
    assert body["project"]["scenes"][2]["image"] == path
    got = client.get(f"/api/files/projects/{slug}/{path}")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"


@pytest.mark.parametrize("scene_index", [None, 8, -1])
def test_image_upload_needs_a_valid_scene(client, scene_index):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    data = {"kind": "image"} | ({} if scene_index is None else {"scene_index": str(scene_index)})
    r = client.post(
        f"/api/projects/{slug}/assets",
        data=data,
        files={"file": ("a.png", png_bytes(), "image/png")},
    )
    assert r.status_code == 400 and "scene_index" in r.json()["detail"]


def test_asset_rejections(client, monkeypatch):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    url = f"/api/projects/{slug}/assets"
    r = client.post(
        url,
        data={"kind": "image", "scene_index": "0"},
        files={"file": ("a.png", b"khong phai anh", "image/png")},
    )
    assert r.status_code == 400 and "ảnh hợp lệ" in r.json()["detail"]
    r = client.post(url, data={"kind": "video"}, files={"file": ("a.mp4", b"x", "video/mp4")})
    assert r.status_code == 400 and "kind" in r.json()["detail"]
    r = client.post(
        url, data={"kind": "image", "scene_index": "0"}, files={"file": ("a.png", b"", "image/png")}
    )
    assert r.status_code == 400 and "rỗng" in r.json()["detail"]
    r = client.post(
        "/api/projects/khong-co/assets", data={"kind": "voice"}, files={"file": ("a.wav", b"x")}
    )
    assert r.status_code == 404
    monkeypatch.setitem(assets_api.MAX_BYTES, "image", 100)
    r = upload_image(client, slug, 0)
    assert r.status_code == 413 and "giới hạn" in r.json()["detail"]
    uploads = client.app.state.hbt.settings.workspace_dir / ".uploads"
    assert not list(uploads.glob("*")), "file tạm bị bỏ lại"
    monkeypatch.setattr(client.app.state.hbt.jobs, "is_busy", lambda s: True)
    assert upload_image(client, slug, 0).status_code == 409


@needs_ffmpeg
def test_voice_and_music_upload(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    r = upload_wav(client, slug, "voice", [("tone", 1.0)])
    assert r.status_code == 200 and r.json()["project"]["voice"] == "voice.wav"
    r = upload_wav(client, slug, "music", [("tone", 1.0)])
    assert r.json()["project"]["music"]["file"] == "music.wav"
    bad = client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": "voice"},
        files={"file": ("x.mp3", b"khong phai am thanh", "audio/mpeg")},
    )
    assert bad.status_code == 400


# ---------------------------------------------------------------- xem trước từng cảnh
def test_scene_preview_png(client):
    slug = complete_project(client)
    r = client.get(f"/api/projects/{slug}/scenes/0/preview.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (1080, 1920)
    small = Image.open(
        io.BytesIO(client.get(f"/api/projects/{slug}/scenes/0/preview.png?w=270").content)
    )
    assert small.size == (270, 480)
    cached = list(
        (client.app.state.hbt.storage.project_dir(slug) / "build" / "previews").glob("*.png")
    )
    assert len(cached) == 1
    assert client.get(f"/api/projects/{slug}/scenes/0/preview.png").content == r.content


def test_scene_preview_shows_card_and_sample_caption(client):
    slug = complete_project(client)
    plain = Image.open(io.BytesIO(client.get(f"/api/projects/{slug}/scenes/0/preview.png").content))
    p = client.get(f"/api/projects/{slug}").json()
    p["scenes"][0]["card"]["lines"] = []
    p["scenes"][0]["voice"] = "Một hai."
    client.put(f"/api/projects/{slug}", json=p)
    bare = Image.open(io.BytesIO(client.get(f"/api/projects/{slug}/scenes/0/preview.png").content))
    top = (0, 100, 1080, 700)  # vùng thẻ chữ (y=110) khác nhau khi có / không có thẻ
    assert plain.crop(top).tobytes() != bare.crop(top).tobytes()
    low = (0, 1300, 1080, 1600)  # vùng phụ đề (y≈1420): có chữ phụ đề trắng/vàng
    assert plain.crop(low).tobytes() != Image.new("RGB", plain.crop(low).size).tobytes()


def test_scene_preview_without_image_uses_the_hbt_avatar(client):
    slug = client.post("/api/projects", json={"title": "Trống"}).json()["slug"]
    r = client.get(f"/api/projects/{slug}/scenes/3/preview.png")
    assert r.status_code == 200
    im = Image.open(io.BytesIO(r.content)).convert("RGB")
    assert im.size == (1080, 1920)
    assert im.getpixel((540, 960))[0] > 120  # avatar nền đỏ của kênh


@pytest.mark.parametrize("index, code", [(8, 404), (-1, 404), (99, 404)])
def test_scene_preview_index_range(client, index, code):
    slug = client.post("/api/projects", json={"title": "Trống"}).json()["slug"]
    assert client.get(f"/api/projects/{slug}/scenes/{index}/preview.png").status_code == code


def test_scene_preview_params_validated(client):
    slug = client.post("/api/projects", json={"title": "Trống"}).json()["slug"]
    assert client.get(f"/api/projects/{slug}/scenes/abc/preview.png").status_code == 422
    assert client.get(f"/api/projects/{slug}/scenes/0/preview.png?w=5").status_code == 422
    assert client.get("/api/projects/khong-co/scenes/0/preview.png").status_code == 404


# ---------------------------------------------------------------- lint và từ nhạy cảm
def test_lint_endpoint(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    r = client.post(f"/api/projects/{slug}/lint").json()
    assert r["issues"] == [] and r["blocked"] is False
    assert r["counts"] == {"info": 0, "warn": 0, "block": 0}
    assert "Chưa có file giọng đọc" in r["problems"]
    p = client.get(f"/api/projects/{slug}").json()
    p["scenes"][0]["voice"] = "a" * 751
    client.put(f"/api/projects/{slug}", json=p)
    r = client.post(f"/api/projects/{slug}/lint").json()
    assert r["counts"]["warn"] == 1 and r["issues"][0]["category"] == "voice_length"
    assert r["issues"][0]["level"] == "warn" and r["blocked"] is False
    assert client.post("/api/projects/khong-co/lint").status_code == 404


def test_sensitive_words_default_edit_and_validation(client):
    default = client.get("/api/settings/sensitive-words").json()
    assert [c["id"] for c in default["categories"]][:2] == ["alcohol", "blood"]
    edited = {"categories": [{"id": "rieng", "level": "block", "words": ["từ cấm"], "hint": "x"}]}
    assert client.put("/api/settings/sensitive-words", json=edited).json() == edited
    assert client.get("/api/settings/sensitive-words").json() == edited
    r = client.put(
        "/api/settings/sensitive-words", json={"categories": [{"id": "A", "level": "warn"}]}
    )
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert (
        client.get("/api/settings/sensitive-words").json() == edited
    )  # lỗi không làm hỏng dữ liệu


# ---------------------------------------------------------------- thư viện nhạc
@needs_ffmpeg
def test_music_library(client):
    assert client.get("/api/music").json() == []
    path = client.tmp / "m.wav"
    write_wav(path, [("tone", 1.0)])
    form = {
        "title": "The Wacky Sprint",
        "artist": "nkbloom",
        "source": "Pixabay",
        "license": "Pixabay Content License",
        "moods": "vui, tinh nghịch",
        "bpm": "120",
    }
    r = client.post(
        "/api/music", data=form, files={"file": ("x.wav", path.read_bytes(), "audio/wav")}
    )
    assert r.status_code == 201
    assert r.json()["id"] == "the-wacky-sprint"
    assert r.json()["file"] == "the-wacky-sprint.wav" and r.json()["moods"] == [
        "vui",
        "tinh nghịch",
    ]
    assert [(e["id"], e["title"]) for e in client.get("/api/music").json()] == [
        ("the-wacky-sprint", "The Wacky Sprint")
    ]
    bad = client.post(
        "/api/music", data={**form, "title": "  "}, files={"file": ("x.wav", b"x", "audio/wav")}
    )
    assert bad.status_code == 400 and "title" in bad.json()["detail"]
    bad = client.post(
        "/api/music", data={**form, "bpm": "5"}, files={"file": ("x.wav", path.read_bytes())}
    )
    assert bad.status_code == 400 and "bpm" in bad.json()["detail"]
    assert len(client.get("/api/music").json()) == 1


# ---------------------------------------------------------------- file
def test_files_serving_and_range(client):
    slug = complete_project(client)
    img = client.get(f"/api/projects/{slug}").json()["scenes"][0]["image"]
    url = f"/api/files/projects/{slug}/{img}"
    full = client.get(url)
    assert full.status_code == 200 and len(full.content) > 100
    part = client.get(url, headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == full.content[:10]
    assert part.headers["content-range"].startswith("bytes 0-9/")


@pytest.mark.parametrize(
    "path",
    [
        "%2e%2e/%2e%2e/etc/passwd",
        "projects/../../outside.txt",
        "projects/%2e%2e/%2e%2e/outside.txt",
        "..%5C..%5Coutside.txt",
        ".uploads/x",
        "projects",
        "khong/co/file.png",
        "C%3A/Windows/win.ini",
    ],
)
def test_files_blocks_traversal_and_missing(client, path):
    (client.tmp / "outside.txt").write_text("bí mật", encoding="utf-8")
    client.post("/api/projects", json={"title": "Muỗi"})
    r = client.get(f"/api/files/{path}")
    assert r.status_code in (404, 422) and "bí mật" not in r.text


# ---------------------------------------------------------------- dựng và job
def test_render_validation(client):
    assert client.post("/api/projects/khong-co/render").status_code == 404
    slug = client.post("/api/projects", json={"title": "Nháp"}).json()["slug"]
    r = client.post(f"/api/projects/{slug}/render")
    assert r.status_code == 422 and "Project chưa đủ để dựng" in r.json()["detail"]
    assert "Cảnh 1: chưa có ảnh" in r.json()["detail"]
    good = complete_project(client)
    assert client.post(f"/api/projects/{good}/render", json={"fps": 45}).status_code == 422


def test_job_endpoints_unknown_ids(client):
    assert client.get("/api/jobs/khong-co").status_code == 404
    assert client.post("/api/jobs/khong-co/cancel").status_code == 404
    assert client.get("/api/jobs/khong-co/events").status_code == 404


def test_cancel_queued_and_running_jobs_via_api(client):
    fake = FakeRender()
    client.app.state.hbt.jobs._render = fake
    client.app.state.hbt.jobs._tool_check = None  # không phụ thuộc FFmpeg thật
    slug = complete_project(client)
    a = client.post(f"/api/projects/{slug}/render", json={"preview": True}).json()["job_id"]
    assert fake.started.wait(5)
    b = client.post(f"/api/projects/{slug}/render").json()["job_id"]
    assert client.get(f"/api/jobs/{a}").json()["status"] == "running"
    assert client.get(f"/api/jobs/{b}").json()["status"] == "queued"
    assert client.get(f"/api/jobs/{a}").json()["log_tail"] == ["đang căn"]

    assert client.delete(f"/api/projects/{slug}").status_code == 409  # đang dựng
    r = client.post(f"/api/jobs/{b}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = client.post(f"/api/jobs/{a}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    r = client.post(f"/api/jobs/{a}/cancel")
    assert r.status_code == 409 and "cancelled" in r.json()["detail"]
    assert client.delete(f"/api/projects/{slug}").status_code == 204  # hết bận


@needs_ffmpeg
def test_full_flow_render_sse_and_outputs(client):
    slug = complete_project(client)
    r = client.post(f"/api/projects/{slug}/render", json={"preview": True})
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        text = "".join(stream.iter_text())
    events = parse_sse(text)
    kinds = [e["event"] for e in events]
    assert kinds[-1] == "end" and set(kinds[:-1]) == {"progress"}
    progress = [e["data"] for e in events if e["event"] == "progress"]
    assert all(set(d) == {"progress", "step", "message"} for d in progress)
    pcts = [d["progress"] for d in progress]
    assert pcts == sorted(pcts) and pcts[-1] == 100
    end = events[-1]["data"]
    assert end["status"] == "done" and end["output"]["video"].startswith("/api/files/projects/")

    job = wait_job(client, job_id)
    assert job["status"] == "done" and job["progress"] == 100 and job["error"] is None
    out = job["output"]
    assert (out["width"], out["height"], out["fps"]) == (540, 960, 30)
    for key in ("video", "srt", "publish", "log"):
        assert client.get(out[key]).status_code == 200, key
    video = client.get(out["video"], headers={"Range": "bytes=0-99"})
    assert video.status_code == 206 and len(video.content) == 100
    assert job["log_tail"] and job["preview"] is True

    # người nối sau vẫn nhận lại toàn bộ sự kiện
    again = parse_sse(client.get(f"/api/jobs/{job_id}/events").text)
    assert [e["event"] for e in again] == kinds

    summary = {i["slug"]: i for i in client.get("/api/projects").json()}[slug]
    assert summary["last_render"]["job_id"] == job_id and summary["last_render"]["preview"] is True
    assert summary["last_render"]["video"] == out["video"]


@needs_ffmpeg
def test_real_render_can_be_cancelled_via_api(client):
    slug = complete_project(client, n=8)
    job_id = client.post(f"/api/projects/{slug}/render", json={"preview": True}).json()["job_id"]
    end = time.time() + 60
    while time.time() < end:
        if client.get(f"/api/jobs/{job_id}").json()["step"] == "Clip từng cảnh":
            break
        time.sleep(0.05)
    started = time.time()
    r = client.post(f"/api/jobs/{job_id}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert time.time() - started < 8
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "cancelled" and job["output"] is None
    renders = client.app.state.hbt.storage.project_dir(slug) / "renders" / job_id
    assert not list(renders.glob("*.mp4"))
    end_event = parse_sse(client.get(f"/api/jobs/{job_id}/events").text)[-1]
    assert end_event["event"] == "end" and end_event["data"]["status"] == "cancelled"


def test_every_error_is_a_detail_string(client):
    responses = [
        client.get("/api/projects/khong-co"),
        client.post("/api/projects", json={}),
        client.get("/api/jobs/khong-co"),
        client.get("/api/files/khong/co.png"),
    ]
    for r in responses:
        assert r.status_code >= 400 and isinstance(r.json()["detail"], str)


# ---------------------------------------------------------------- scene_index (từ 0)
def test_old_scene_field_is_no_longer_accepted(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    r = client.post(
        f"/api/projects/{slug}/assets",
        data={"kind": "image", "scene": "0"},  # tên cũ
        files={"file": ("a.png", png_bytes(), "image/png")},
    )
    assert r.status_code == 400 and "scene_index" in r.json()["detail"]


def test_openapi_names_the_zero_based_index_scene_index(client):
    spec = client.get("/openapi.json").json()
    assert "/api/projects/{slug}/scenes/{scene_index}/preview.png" in spec["paths"]
    body = next(
        s["properties"]
        for s in spec["components"]["schemas"].values()
        if "kind" in s.get("properties", {})
        and "file" in s["properties"]
        and "title" not in s["properties"]
    )
    assert "scene_index" in body and "scene" not in body


def test_scene_index_zero_is_the_first_scene_and_file_is_named_by_hash(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    first = upload_image(client, slug, 0).json()
    last = upload_image(client, slug, 7).json()
    assert first["path"].startswith("images/")
    assert first["project"]["scenes"][0]["image"] == first["path"]
    assert last["path"].startswith("images/")
    assert last["project"]["scenes"][7]["image"] == last["path"]
    assert client.get(f"/api/projects/{slug}/scenes/0/preview.png").status_code == 200
    assert client.get(f"/api/projects/{slug}/scenes/8/preview.png").status_code == 404


def test_lint_issue_uses_scene_index(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    p = client.get(f"/api/projects/{slug}").json()
    p["scenes"][0]["voice"] = "a" * 751
    client.put(f"/api/projects/{slug}", json=p)
    issue = client.post(f"/api/projects/{slug}/lint").json()["issues"][0]
    assert "scene_index" in issue and issue["scene_index"] is None and "scene" not in issue


# ---------------------------------------------------------- thiếu FFmpeg: lỗi rõ, server không sập
INSTALL = "winget install Gyan.FFmpeg"


def no_ffmpeg(monkeypatch, tmp_path):
    """Xoá FFmpeg khỏi PATH của chính tiến trình test (PATH chỉ còn một thư mục rỗng)."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert shutil.which("ffmpeg") is None and shutil.which("ffprobe") is None


def ready_without_ffmpeg(client, n=3):
    """Project đủ ảnh/lời/giọng mà KHÔNG cần FFmpeg (giọng được đặt thẳng vào thư mục project)."""
    slug = client.post("/api/projects", json={"title": "Không FFmpeg", "scene_count": n}).json()[
        "slug"
    ]
    for i in range(n):
        assert upload_image(client, slug, i).status_code == 200
    write_wav(client.app.state.hbt.storage.project_dir(slug) / "voice.wav", speech(n))
    p = client.get(f"/api/projects/{slug}").json()
    p["voice"] = "voice.wav"
    for i, scene in enumerate(p["scenes"]):
        scene["voice"] = SENTENCES[i % len(SENTENCES)]
    assert client.put(f"/api/projects/{slug}", json=p).status_code == 200
    return slug


def test_health_without_ffmpeg_reports_it_and_stays_up(client, monkeypatch, tmp_path):
    no_ffmpeg(monkeypatch, tmp_path)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["ffmpeg"] is False and body["missing"] == ["ffmpeg"]


def test_render_without_ffmpeg_is_a_clear_503_and_creates_no_job(client, monkeypatch, tmp_path):
    slug = ready_without_ffmpeg(client)
    no_ffmpeg(monkeypatch, tmp_path)
    r = client.post(f"/api/projects/{slug}/render", json={"preview": True})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "FFmpeg" in detail and INSTALL in detail and "README.md" in detail
    assert client.app.state.hbt.jobs._jobs == {}  # không tạo job treo
    # server vẫn sống và trả lời bình thường
    assert client.get("/api/health").status_code == 200
    assert client.get(f"/api/projects/{slug}").status_code == 200


def test_incomplete_project_still_gets_the_422_list_before_the_ffmpeg_check(
    client, monkeypatch, tmp_path
):
    slug = client.post("/api/projects", json={"title": "Nháp"}).json()["slug"]
    no_ffmpeg(monkeypatch, tmp_path)
    r = client.post(f"/api/projects/{slug}/render")
    assert r.status_code == 422 and "Project chưa đủ để dựng" in r.json()["detail"]


def test_features_that_do_not_need_ffmpeg_keep_working(client, monkeypatch, tmp_path):
    slug = ready_without_ffmpeg(client)
    no_ffmpeg(monkeypatch, tmp_path)
    up = upload_image(client, slug, 0, (10, 20, 30))
    assert up.status_code == 200
    img_path = up.json()["path"]
    assert client.get(f"/api/projects/{slug}/scenes/0/preview.png").status_code == 200
    assert client.post(f"/api/projects/{slug}/lint").status_code == 200
    assert client.get(f"/api/files/projects/{slug}/{img_path}").status_code == 200
    assert client.get("/api/music").status_code == 200
    assert client.get("/api/settings/sensitive-words").status_code == 200
    assert client.get("/api/projects").status_code == 200
    assert client.post(f"/api/projects/{slug}/duplicate").status_code == 201


def test_audio_uploads_without_ffprobe_say_so_with_503(client, monkeypatch, tmp_path):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    wav = tmp_path / "v.wav"
    write_wav(wav, [("tone", 1.0)])
    no_ffmpeg(monkeypatch, tmp_path)
    for kind in ("voice", "music"):
        r = client.post(
            f"/api/projects/{slug}/assets",
            data={"kind": kind},
            files={"file": ("a.wav", wav.read_bytes(), "audio/wav")},
        )
        assert r.status_code == 503 and INSTALL in r.json()["detail"], kind
    r = client.post(
        "/api/music",
        data={"title": "T", "artist": "A", "source": "S", "license": "L"},
        files={"file": ("a.wav", wav.read_bytes(), "audio/wav")},
    )
    assert r.status_code == 503 and INSTALL in r.json()["detail"]
    project = client.get(f"/api/projects/{slug}").json()
    assert project["voice"] is None and project["music"] is None  # không ghi dở
    assert not list((client.app.state.hbt.settings.workspace_dir / ".uploads").glob("*"))


def test_render_refused_when_ffmpeg_lacks_an_encoder_or_filter(client, monkeypatch):
    slug = ready_without_ffmpeg(client)
    from hbt.api import health

    listing = {
        "-version": "ffmpeg version 6.0",
        "-encoders": "Encoders:\n ------\n V....D libx265  HEVC\n",
        "-filters": "Filters:\n ------\n .. loudnorm  A->A  EBU R128\n",
    }
    monkeypatch.setattr(health, "_ffmpeg_stdout", lambda arg: listing[arg])
    r = client.post(f"/api/projects/{slug}/render")
    assert r.status_code == 503
    assert "libx264" in r.json()["detail"] and "xfade" in r.json()["detail"]


def test_render_refused_when_only_ffprobe_is_missing(client, monkeypatch):
    slug = ready_without_ffmpeg(client)
    from hbt import jobs

    real_which = shutil.which
    monkeypatch.setattr(jobs.shutil, "which", lambda n: None if n == "ffprobe" else real_which(n))
    r = client.post(f"/api/projects/{slug}/render")
    assert r.status_code == 503 and "ffprobe" in r.json()["detail"]


# ------------------------------------------------ slug: [a-z0-9-], tối đa 60, không tên Windows
BAD_ROUTE_SLUGS = ["a%20b", "UPPER", "%2e%2e", "con", "NUL", "com1", "lpt9", "-a", "a--b", "x" * 61]


@pytest.mark.parametrize("slug", BAD_ROUTE_SLUGS)
def test_every_project_endpoint_rejects_an_invalid_slug_with_422(client, slug):
    p = f"/api/projects/{slug}"
    body = {
        "slug": "x",
        "title": "T",
        "scenes": [{} for _ in range(3)],
    }
    calls = [
        client.get(p),
        client.put(p, json=body),
        client.delete(p),
        client.post(p + "/duplicate"),
        client.post(p + "/lint"),
        client.post(p + "/render"),
        client.get(p + "/scenes/0/preview.png"),
        client.post(
            p + "/assets",
            data={"kind": "image", "scene_index": "0"},
            files={"file": ("a.png", png_bytes(), "image/png")},
        ),
    ]
    for r in calls:
        assert r.status_code == 422, (slug, r.request.method, r.request.url.path, r.text)
        assert isinstance(r.json()["detail"], str)
    ws = client.app.state.hbt.settings.workspace_dir
    assert not (ws / "projects").exists() or not any((ws / "projects").iterdir())


def test_put_rejects_a_body_with_an_invalid_slug(client):
    slug = client.post("/api/projects", json={"title": "Muỗi"}).json()["slug"]
    p = client.get(f"/api/projects/{slug}").json()
    for bad in ("../x", "a/b", "con", "A b", "a" * 61, ""):
        r = client.put(f"/api/projects/{slug}", json={**p, "slug": bad})
        assert r.status_code == 422 and "slug" in r.json()["detail"], bad


@pytest.mark.parametrize(
    "path",
    [
        "projects/con/images/scene-01.png",
        "projects/NUL/x",
        "projects/a%20b/x",
        "projects/UPPER/x",
        "projects/" + "x" * 61 + "/x",
        "projects/-a/x",
        "projects/%2e%2e/x",
    ],
)
def test_files_rejects_an_invalid_project_slug_with_422(client, path):
    r = client.get(f"/api/files/{path}")
    assert r.status_code == 422 and "detail" in r.json()


@pytest.mark.parametrize(
    "path", ["projects/..%2Fx", "projects/a/%2e%2e/%2e%2e/x", "%2e%2e/x", ".uploads/x", "C%3A/x"]
)
def test_files_rejects_traversal_with_422(client, path):
    assert client.get(f"/api/files/{path}").status_code == 422


def test_files_valid_but_missing_is_404(client):
    assert client.get("/api/files/projects/khong-co/images/scene-01.png").status_code == 404
    assert client.get("/api/files/settings/khong-co.json").status_code == 404


@pytest.mark.parametrize("title", ["Con", "NUL", "com1", "Lpt9"])
def test_creating_a_project_whose_title_is_a_windows_device_name_works(client, title):
    r = client.post("/api/projects", json={"title": title})
    assert r.status_code == 201 and r.json()["slug"] == title.lower() + "-video"
    assert client.get(f"/api/projects/{r.json()['slug']}").status_code == 200


def test_slug_length_limit_holds_through_the_api(client):
    slugs = [
        client.post("/api/projects", json={"title": "muoi dot nguoi " * 12}).json()["slug"]
        for _ in range(3)
    ]
    assert len(set(slugs)) == 3 and all(len(s) <= 60 for s in slugs)
    assert all(client.get(f"/api/projects/{s}").status_code == 200 for s in slugs)


def test_lint_endpoint_reports_sensitive_words_and_blocks_on_block_level(client):
    slug = client.post("/api/projects", json={"title": "Từ nhạy cảm"}).json()["slug"]
    p = client.get(f"/api/projects/{slug}").json()
    p["scenes"][0]["voice"] = "Quán bia, còn bìa sách thì không."
    client.put(f"/api/projects/{slug}", json=p)
    r = client.post(f"/api/projects/{slug}/lint").json()
    assert [(i["word"], i["level"], i["scene_index"]) for i in r["issues"]] == [("bia", "warn", 0)]
    assert r["counts"] == {"info": 0, "warn": 1, "block": 0} and r["blocked"] is False

    p["scenes"][0]["voice"] = "Bàn về ma tuý."
    client.put(f"/api/projects/{slug}", json=p)
    r = client.post(f"/api/projects/{slug}/lint").json()
    assert r["counts"]["block"] == 1 and r["blocked"] is True


def test_lint_uses_the_users_own_word_list(client):
    slug = client.post("/api/projects", json={"title": "Danh sách riêng"}).json()["slug"]
    p = client.get(f"/api/projects/{slug}").json()
    p["scenes"][0]["voice"] = "Quán bia và con muỗi."
    client.put(f"/api/projects/{slug}", json=p)
    mine = {"categories": [{"id": "rieng", "level": "info", "words": ["muỗi"]}]}
    assert client.put("/api/settings/sensitive-words", json=mine).status_code == 200
    issues = client.post(f"/api/projects/{slug}/lint").json()["issues"]
    assert [(i["word"], i["level"]) for i in issues] == [("muỗi", "info")]
