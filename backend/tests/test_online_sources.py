"""Unit tests cho Tìm kiếm & Nhập Tài nguyên Trực tuyến + Tự gắn tag & Chọn Meme theo ngữ cảnh."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hbt.app_settings import AppSettings, AppSettingsStore, resolve_online_api_key
from hbt.chatting.llm import select_memes_for_chat
from hbt.shared.online_sources import (
    auto_tag_meme,
    batch_auto_tag_memes,
    import_giphy_sticker,
    import_greenmeme,
    import_pixabay_audio,
    import_sigstick_pack,
    match_meme_by_context,
    search_giphy_stickers,
    search_greenmeme,
    search_pixabay_audio,
    update_meme_metadata,
)


def test_resolve_online_api_key_from_env_and_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.delenv("GIPHY_API_KEY", raising=False)
    store = AppSettingsStore(tmp_path)
    store.save(AppSettings(pixabay_api_key="pb-from-settings", giphy_api_key="gp-from-settings"))

    assert resolve_online_api_key("PIXABAY_API_KEY", tmp_path) == "pb-from-settings"
    assert resolve_online_api_key("GIPHY_API_KEY", tmp_path) == "gp-from-settings"

    monkeypatch.setenv("PIXABAY_API_KEY", "pb-from-env")
    assert resolve_online_api_key("PIXABAY_API_KEY", tmp_path) == "pb-from-env"


@pytest.mark.anyio
async def test_pixabay_search_and_import(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "pixabay.com/api/" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "id": 12345,
                            "title": "Lofi Chill Beat",
                            "user": "BeatMaker",
                            "duration": 62,
                            "tags": "lofi, chill, study",
                            "previewURL": "https://cdn.pixabay.com/audio/preview.mp3",
                            "audio": "https://cdn.pixabay.com/audio/full.mp3",
                        }
                    ]
                },
            )
        return httpx.Response(200, content=b"FAKE_MP3_BYTES")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        items = await search_pixabay_audio("lofi", kind="music", api_key="test-key", client=client)
        assert len(items) == 1
        assert items[0]["title"] == "Lofi Chill Beat"
        assert items[0]["artist"] == "BeatMaker"

        res = await import_pixabay_audio(
            item_id=items[0]["id"],
            title=items[0]["title"],
            artist=items[0]["artist"],
            download_url=items[0]["download_url"],
            kind="music",
            tags=items[0]["tags"],
            library_dir=tmp_path,
            client=client,
        )
        assert res["ok"] is True
        assert (tmp_path / "music" / "pixabay-12345.mp3").is_file()
        idx = json.loads((tmp_path / "music" / "index.json").read_text(encoding="utf-8"))
        assert idx[0]["license"] == "Pixabay Content License"


@pytest.mark.anyio
async def test_greenmeme_search_and_import(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "wp-json/wp/v2/posts" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 99,
                        "slug": "ishowspeed-shocked",
                        "title": {"rendered": "IShowSpeed Shocked"},
                        "content": {
                            "rendered": (
                                '<video poster="https://greenscreenmemes.com/p.jpg">'
                                '<source src="https://greenscreenmemes.com/v.mp4"></video>'
                            )
                        },
                    }
                ],
            )
        if url.endswith(".mp4"):
            return httpx.Response(200, content=b"FAKE_MP4")
        if url.endswith(".jpg"):
            return httpx.Response(200, content=b"FAKE_JPG")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        items = await search_greenmeme("shocked", client=client)
        assert len(items) == 1
        assert items[0]["id"] == "ishowspeed-shocked"

        res = await import_greenmeme(
            meme_id=items[0]["id"],
            title=items[0]["title"],
            video_url=items[0]["video_url"],
            poster_url=items[0]["poster_url"],
            library_dir=tmp_path,
            client=client,
        )
        assert res["ok"] is True
        assert (tmp_path / "memes" / "ishowspeed-shocked.mp4").is_file()
        assert (tmp_path / "memes" / "ishowspeed-shocked_thumb.jpg").is_file()
        assert "bat_ngo" in res["item"]["tags"]


@pytest.mark.anyio
async def test_giphy_and_sigstick_import(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.giphy.com" in url:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "g123",
                            "title": "Happy Cat Laugh",
                            "images": {
                                "original": {
                                    "webp": "https://media.giphy.com/media/g123/giphy.webp",
                                    "url": "https://media.giphy.com/media/g123/giphy.gif",
                                }
                            },
                        }
                    ]
                },
            )
        if "sigstick.com/pack/" in url:
            return httpx.Response(
                200,
                text=(
                    '<html><img src="https://cdn.sigstick.com/pack/s1.webp">'
                    '<img src="https://cdn.sigstick.com/pack/s2.png"></html>'
                ),
            )
        return httpx.Response(200, content=b"STICKER_BYTES")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        g_items = await search_giphy_stickers("cat", api_key="gp-key", client=client)
        assert len(g_items) == 1
        g_res = await import_giphy_sticker(
            sticker_id=g_items[0]["id"],
            title=g_items[0]["title"],
            download_url=g_items[0]["download_url"],
            library_dir=tmp_path,
            client=client,
        )
        assert g_res["ok"] is True
        assert (tmp_path / "stickers" / "giphy-g123.webp").is_file()

        s_res = await import_sigstick_pack(
            "https://www.sigstick.com/pack/4apDIMb2XSMEjwwLRkRe-video-stickers",
            library_dir=tmp_path,
            client=client,
        )
        assert s_res["ok"] is True
        assert s_res["count"] == 2
        assert (
            tmp_path / "stickers" / "4apdimb2xsmejwwlrkre-video-stickers" / "stk_01.webp"
        ).is_file()


def test_meme_auto_tag_and_context_matching(tmp_path: Path) -> None:
    memes_dir = tmp_path / "memes"
    memes_dir.mkdir(parents=True)
    (memes_dir / "cat-laugh.mp4").write_bytes(b"mp4")
    (memes_dir / "shocked-omg.mp4").write_bytes(b"mp4")

    tags, topic = auto_tag_meme("Shocked OMG Face")
    assert "bat_ngo" in tags
    assert topic

    batch = batch_auto_tag_memes(memes_dir)
    assert batch["total"] == 2
    assert batch["updated"] == 2

    patched = update_meme_metadata(
        memes_dir,
        "cat-laugh",
        tags=["meo", "hai_huoc", "ca_khia"],
        topic="Mèo cười khẩy cà khịa",
    )
    assert patched is not None
    assert "ca_khia" in patched["tags"]

    # Khớp ngữ cảnh câu thoại
    matched = match_meme_by_context("Trời ơi sốc quá không tin nổi!", batch["items"])
    assert matched is not None
    assert matched["id"] == "shocked-omg"

    # AI / fallback chọn meme không trùng lặp trong kịch bản Chatting
    msgs = [
        {"from": "a", "text": "Sốc quá trời ơi!", "sticker": "soc"},
        {"from": "me", "text": "Cười xỉu với con mèo này", "sticker": "cuoi"},
        {"from": "a", "text": "Thật sự sốc luôn á", "sticker": "soc"},
    ]
    out_msgs = select_memes_for_chat(msgs, batch["items"])
    chosen_ids = [m["meme_id"] for m in out_msgs if m.get("meme_id")]
    assert len(chosen_ids) == len(set(chosen_ids))  # Không bao giờ chọn trùng meme_id
