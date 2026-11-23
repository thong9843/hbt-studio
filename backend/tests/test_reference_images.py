"""Unit tests cho kho ảnh tư liệu StickV: Wikimedia Commons -> Pixabay -> Iconify fallback."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from hbt.config import Settings
from hbt.main import create_app
from hbt.shared.online_sources.reference_images import (
    WIKIMEDIA_USER_AGENT,
    clear_reference_image_cache,
    resolve_reference_image,
    search_pixabay_images,
    search_reference_images,
    search_wikimedia_images,
)
from hbt.stickv.models import StickvBeat
from hbt.stickv.storage import create_stickv_project


def _png_bytes(
    size: tuple[int, int] = (480, 360), color: tuple[int, int, int] = (90, 140, 200)
) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    try:
        img.save(buf, format="PNG")
    finally:
        img.close()
    return buf.getvalue()


def test_wikimedia_search_filters_svg_and_small_images_with_user_agent() -> None:
    captured_ua: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_ua.append(request.headers.get("user-agent", ""))
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {
                            "pageid": 1,
                            "title": "File:Vector.svg",
                            "imageinfo": [
                                {
                                    "url": "https://img/v.svg",
                                    "width": 800,
                                    "height": 800,
                                    "mime": "image/svg+xml",
                                }
                            ],
                        },
                        "2": {
                            "pageid": 2,
                            "title": "File:Tiny.png",
                            "imageinfo": [
                                {
                                    "url": "https://img/tiny.png",
                                    "width": 120,
                                    "height": 120,
                                    "mime": "image/png",
                                }
                            ],
                        },
                        "3": {
                            "pageid": 3,
                            "title": "File:Easter_Island_Moai.jpg",
                            "imageinfo": [
                                {
                                    "url": "https://img/moai.jpg",
                                    "thumburl": "https://img/moai_1024.jpg",
                                    "width": 1600,
                                    "height": 1200,
                                    "mime": "image/jpeg",
                                }
                            ],
                        },
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        items = search_wikimedia_images("Easter Island", limit=6, client=client)
    finally:
        client.close()

    assert captured_ua == [WIKIMEDIA_USER_AGENT]
    assert len(items) == 1
    assert items[0]["source"] == "wikimedia"
    assert items[0]["url"] == "https://img/moai_1024.jpg"
    assert items[0]["title"] == "Easter_Island_Moai.jpg"


def test_pixabay_fallback_from_illustration_to_all() -> None:
    seen_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        img_type = request.url.params.get("image_type", "")
        seen_types.append(img_type)
        assert request.url.params.get("safesearch") == "true"
        if img_type == "illustration":
            return httpx.Response(200, json={"hits": []})
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": 99,
                        "tags": "brain, synapse",
                        "webformatURL": "https://pixabay.test/brain.jpg",
                        "previewURL": "https://pixabay.test/brain_sm.jpg",
                        "imageWidth": 1280,
                        "imageHeight": 720,
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        items = search_pixabay_images("brain", api_key="pix-key", limit=4, client=client)
    finally:
        client.close()

    assert seen_types == ["illustration", "all"]
    assert len(items) == 1
    assert items[0]["source"] == "pixabay"
    assert items[0]["url"] == "https://pixabay.test/brain.jpg"


def test_resolve_reference_image_downloads_caches_and_falls_back_to_iconify(
    tmp_path: Path, monkeypatch
) -> None:
    clear_reference_image_cache()
    lib = tmp_path / "library"

    # 1. Tải ảnh từ Wikimedia và cache vào library/reference_images/
    def handler_ok(request: httpx.Request) -> httpx.Response:
        if "commons.wikimedia.org" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "10": {
                                "pageid": 10,
                                "title": "File:Pyramid.jpg",
                                "imageinfo": [
                                    {
                                        "url": "https://upload.test/pyramid.png",
                                        "width": 640,
                                        "height": 480,
                                        "mime": "image/png",
                                    }
                                ],
                            }
                        }
                    }
                },
            )
        return httpx.Response(200, content=_png_bytes((480, 360)))

    client_ok = httpx.Client(transport=httpx.MockTransport(handler_ok))
    try:
        p1, src1 = resolve_reference_image("pyramid giza", lib, client=client_ok)
        p2, src2 = resolve_reference_image("pyramid giza", lib, client=client_ok)
    finally:
        client_ok.close()

    assert p1.is_file()
    assert p1.parent == lib / "reference_images"
    assert src1 == "wikimedia"
    assert p2 == p1 and src2 == "cache"

    # 2. Khi cả Wikimedia và Pixabay đều rỗng -> fallback sang iconify_props
    fallback_file = lib / "props" / "unknown-item.png"
    fallback_file.parent.mkdir(parents=True, exist_ok=True)
    fallback_file.write_bytes(_png_bytes((200, 200)))
    monkeypatch.setattr(
        "hbt.shared.online_sources.reference_images.resolve_prop_png",
        lambda *_a, **_kw: fallback_file,
    )

    client_empty = httpx.Client(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={}))
    )
    try:
        p3, src3 = resolve_reference_image(
            "unknown rare concept", lib, pixabay_key="", client=client_empty
        )
    finally:
        client_empty.close()

    assert p3 == fallback_file
    assert src3 == "iconify"


def test_stickv_reference_images_api_search_and_apply(tmp_path: Path, monkeypatch) -> None:
    ws = tmp_path / "workspace"
    lib = tmp_path / "library"
    ws.mkdir()
    lib.mkdir()
    settings = Settings(
        workspace_dir=ws,
        library_dir=lib,
        whisper_model="auto",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings)
    proj = create_stickv_project(
        ws,
        title="Bí ẩn Kim Tự Tháp",
        beats=[StickvBeat(id="b001", narration="Sự thật gây sốc.", board_title="Kim Tự Tháp")],
    )

    monkeypatch.setattr(
        "hbt.api.stickv.search_reference_images",
        lambda q, **_kw: [
            {
                "id": "wiki:1",
                "title": "Giza.jpg",
                "url": "https://img.test/giza.png",
                "thumb_url": "https://img.test/giza.png",
                "width": 800,
                "height": 600,
                "source": "wikimedia",
            }
        ],
    )

    def fake_download(url: str, dest_dir: Path, **_kw) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / "b001_giza.png"
        out.write_bytes(_png_bytes((400, 300)))
        return out

    monkeypatch.setattr("hbt.api.stickv.download_reference_image_url", fake_download)

    with TestClient(app) as client:
        r_search = client.get("/api/stickv/reference-images/search?q=giza")
        assert r_search.status_code == 200
        assert len(r_search.json()["items"]) == 1

        r_apply = client.post(
            f"/api/stickv/{proj.slug}/beats/b001/reference-image",
            json={
                "url": "https://img.test/giza.png",
                "query": "giza",
                "caption": "Kim Tự Tháp Giza",
            },
        )
        assert r_apply.status_code == 200
        body = r_apply.json()
        assert body["ok"] is True
        beat0 = body["project"]["beats"][0]
        assert beat0["board_type"] == "pinned_photo"
        assert beat0["media_path"].startswith("media/")
        assert beat0["board_data"]["caption"] == "Kim Tự Tháp Giza"

    # Xác nhận hàm search_reference_images không crash khi query rỗng
    assert search_reference_images("") == []
