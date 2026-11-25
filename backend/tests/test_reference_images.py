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


def test_pixabay_fallback_from_photo_to_illustration() -> None:
    seen_types: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        img_type = request.url.params.get("image_type", "")
        seen_types.append(img_type)
        assert request.url.params.get("safesearch") == "true"
        if img_type == "photo":
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

    assert seen_types == ["photo", "illustration"]
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


def test_resolve_reference_image_3tier_cloudflare_fallback_and_budget(tmp_path: Path) -> None:
    """Wikimedia/Pixabay rỗng -> rơi sang Cloudflare Flux (768x512, cache .jpg, budget)."""
    clear_reference_image_cache()
    lib = tmp_path / "library"
    cf_calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "api.cloudflare.com" in str(request.url):
            cf_calls.append({"url": str(request.url), "body": request.content.decode("utf-8")})
            return httpx.Response(
                200,
                content=_png_bytes((768, 512), color=(210, 120, 60)),
                headers={"content-type": "image/png"},
            )
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    budget = [1]
    try:
        p1, src1 = resolve_reference_image(
            "endurance muscle fiber structure",
            lib,
            illustration_prompt="Cross section of slow-twitch muscle fibers",
            cf_account_id="acc-test",
            cf_api_token="tok-test",
            ai_budget=budget,
            client=client,
        )
        # Gọi lại cùng query -> trúng cache .jpg, không gọi lại Cloudflare
        p2, src2 = resolve_reference_image(
            "endurance muscle fiber structure",
            lib,
            illustration_prompt="Cross section of slow-twitch muscle fibers",
            cf_account_id="acc-test",
            cf_api_token="tok-test",
            ai_budget=budget,
            client=client,
        )
    finally:
        client.close()

    assert src1 == "cloudflare_flux"
    assert p1.suffix == ".jpg" and p1.is_file()
    assert src2 == "cache" and p2 == p1
    assert len(cf_calls) == 1
    assert budget == [0]


def test_stickv_generate_beat_ai_photo_endpoint(tmp_path: Path, monkeypatch) -> None:
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
        title="Nghịch lý thể hình cầu thủ",
        beats=[
            StickvBeat(
                id="b001",
                narration="Sợi cơ bền bỉ giúp chạy suốt 90 phút.",
                board_title="Sợi cơ bền bỉ",
                prop_query="soccer player sprint",
            )
        ],
    )
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc-demo")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-demo")

    def fake_gen(prompt: str, dest: Path, **_kw) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_png_bytes((768, 512)))
        return dest

    monkeypatch.setattr("hbt.api.stickv.generate_illustration_image", fake_gen)

    with TestClient(app) as client:
        r = client.post(
            f"/api/stickv/{proj.slug}/beats/b001/generate-photo",
            json={"prompt": "Slow-twitch muscle fibers diagram", "caption": "Sợi cơ bền bỉ"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        beat0 = body["project"]["beats"][0]
        assert beat0["board_type"] == "pinned_photo"
        assert beat0["media_path"].startswith("media/b001_ai_")
        assert beat0["board_data"]["caption"] == "Sợi cơ bền bỉ"


def test_wikimedia_junk_filter_and_entity_relevance_fallback_to_flux(tmp_path: Path) -> None:
    """Loại sạch ảnh rác (đồng xu, thước đo, cửa chớp, nhà kho) và chuyển thẳng Cloudflare Flux."""
    from hbt.shared.online_sources.reference_images import (
        DEFAULT_AI_IMAGE_BUDGET,
        REF_CACHE_VERSION,
        score_candidate_relevance,
    )

    clear_reference_image_cache()
    assert REF_CACHE_VERSION == "v3_beat_entity_real_first"
    assert DEFAULT_AI_IMAGE_BUDGET == 6

    junk_pages = {
        "1": {
            "pageid": 1,
            "title": "File:Roman_coin_Pisa.jpg",
            "imageinfo": [
                {
                    "url": "https://img/coin.jpg",
                    "width": 1000,
                    "height": 800,
                    "mime": "image/jpeg",
                }
            ],
        },
        "2": {
            "pageid": 2,
            "title": "File:Ruler_measurement_scale.jpg",
            "imageinfo": [
                {
                    "url": "https://img/ruler.jpg",
                    "width": 1000,
                    "height": 800,
                    "mime": "image/jpeg",
                }
            ],
        },
        "3": {
            "pageid": 3,
            "title": "File:Old_window_shutter.jpg",
            "imageinfo": [
                {
                    "url": "https://img/shutter.jpg",
                    "width": 1000,
                    "height": 800,
                    "mime": "image/jpeg",
                }
            ],
        },
        "4": {
            "pageid": 4,
            "title": "File:Abandoned_warehouse.jpg",
            "imageinfo": [
                {
                    "url": "https://img/warehouse.jpg",
                    "width": 1000,
                    "height": 800,
                    "mime": "image/jpeg",
                }
            ],
        },
        "5": {
            "pageid": 5,
            "title": "File:Leaning_Tower_of_Pisa_Tuscany.jpg",
            "imageinfo": [
                {
                    "url": "https://img/pisa_real.jpg",
                    "width": 1200,
                    "height": 900,
                    "mime": "image/jpeg",
                }
            ],
        },
    }

    client_filter = httpx.Client(
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"query": {"pages": junk_pages}})
        )
    )
    try:
        items = search_wikimedia_images("Leaning Tower of Pisa", limit=10, client=client_filter)
    finally:
        client_filter.close()

    # Cả 4 ảnh rác bị chặn, chỉ còn ảnh thật Tháp Nghiêng Pisa (không chặn nhầm "Tuscany")
    assert [it["title"] for it in items] == ["Leaning_Tower_of_Pisa_Tuscany.jpg"]
    assert (
        score_candidate_relevance(
            items[0],
            "Leaning Tower of Pisa",
            primary_entity_en="Leaning Tower of Pisa",
        )
        >= 0.7
    )
    # Nếu beat đòi bối cảnh cụ thể (cáp thép gia cố) mà ảnh chỉ là ảnh du lịch chung -> dưới ngưỡng
    assert (
        score_candidate_relevance(
            items[0],
            "Leaning Tower of Pisa modern scaffolding cables",
            primary_entity_en="Leaning Tower of Pisa",
        )
        < 0.45
    )

    # Khi Wikimedia chỉ trả ảnh lạc đề (không khớp thực thể chính) -> từ chối và gọi Cloudflare Flux
    off_topic_pages = {
        "9": {
            "pageid": 9,
            "title": "File:Medieval_stone_wall_France.jpg",
            "imageinfo": [
                {
                    "url": "https://img/france_wall.jpg",
                    "width": 1200,
                    "height": 900,
                    "mime": "image/jpeg",
                }
            ],
        }
    }
    flux_calls: list[str] = []

    def handler_fallback(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "commons.wikimedia.org" in url:
            return httpx.Response(200, json={"query": {"pages": off_topic_pages}})
        if "api.cloudflare.com" in url:
            flux_calls.append(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                content=_png_bytes((768, 512), color=(180, 140, 90)),
                headers={"content-type": "image/png"},
            )
        return httpx.Response(200, json={})

    lib = tmp_path / "library"
    budget = [DEFAULT_AI_IMAGE_BUDGET]
    client_fb = httpx.Client(transport=httpx.MockTransport(handler_fallback))
    try:
        out_p, src = resolve_reference_image(
            "Leaning Tower of Pisa soft clay foundation",
            lib,
            primary_entity_en="Leaning Tower of Pisa",
            illustration_prompt="Cross section of soft clay soil tilting the tower foundation",
            cf_account_id="acc-pisa",
            cf_api_token="tok-pisa",
            ai_budget=budget,
            client=client_fb,
        )
    finally:
        client_fb.close()

    assert src == "cloudflare_flux"
    assert out_p.is_file() and REF_CACHE_VERSION in out_p.name
    assert len(flux_calls) == 1
    assert "Leaning Tower of Pisa" in flux_calls[0]
    assert budget == [DEFAULT_AI_IMAGE_BUDGET - 1]


def test_v3_real_first_pass1b_entity_fallback_and_render_wiring(tmp_path: Path) -> None:
    """Nhịp 1a rỗng -> nhịp 1b tra đúng `beat_entity_en` lấy ảnh thật Wikimedia trước khi gọi AI."""
    from hbt.shared.online_sources.reference_images import (
        DEFAULT_AI_IMAGE_BUDGET,
        REF_CACHE_VERSION,
    )
    from hbt.stickv import render as stickv_render

    clear_reference_image_cache()
    seen_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "commons.wikimedia.org" in url:
            gsr = request.url.params.get("gsrsearch", "")
            seen_queries.append(gsr)
            # Nhịp 1a rỗng -> nhịp 1b ("Racetrack Playa") trả ảnh thật Wikimedia
            if "midnight" in gsr:
                return httpx.Response(200, json={"query": {"pages": {}}})
            return httpx.Response(
                200,
                json={
                    "query": {
                        "pages": {
                            "42": {
                                "pageid": 42,
                                "title": "File:Racetrack_Playa_Death_Valley.jpg",
                                "imageinfo": [
                                    {
                                        "url": "https://img/racetrack.jpg",
                                        "width": 1200,
                                        "height": 800,
                                        "mime": "image/jpeg",
                                    }
                                ],
                            }
                        }
                    }
                },
            )
        return httpx.Response(200, content=_png_bytes((600, 400), color=(190, 160, 120)))

    lib = tmp_path / "library"
    budget = [DEFAULT_AI_IMAGE_BUDGET]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        out_p, src = resolve_reference_image(
            "Racetrack Playa sailing stones midnight",
            lib,
            primary_entity_en="Racetrack Playa",
            cf_account_id="acc-test",
            cf_api_token="tok-test",
            ai_budget=budget,
            client=client,
        )
    finally:
        client.close()

    assert src == "wikimedia"
    assert out_p.is_file() and REF_CACHE_VERSION in out_p.name
    assert len(seen_queries) == 2
    assert "Racetrack Playa" in seen_queries[1]
    assert budget == [DEFAULT_AI_IMAGE_BUDGET]  # Không tốn lượt AI khi có ảnh thật Wikimedia
    assert stickv_render.DEFAULT_AI_IMAGE_BUDGET == 6
