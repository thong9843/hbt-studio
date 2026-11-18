"""Unit test cho Freesound API, Pixabay Audio fallback, live API key reload & auto-pick BGM."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from hbt.api.asset_hub import _ONLINE_SEARCH_CACHE
from hbt.app_settings import AppSettings, AppSettingsStore, resolve_online_api_key
from hbt.config import Settings
from hbt.main import create_app
from hbt.shared.online_sources.freesound_audio import import_freesound_audio, search_freesound_audio
from hbt.shared.online_sources.pixabay_audio import search_pixabay_audio
from hbt.stickv.audio import auto_resolve_mood_bgm


def test_freesound_search_and_import(tmp_path: Path) -> None:
    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {
        "results": [
            {
                "id": 9988,
                "name": "Clock Tick Ambience",
                "username": "soundsmith",
                "duration": 18.5,
                "previews": {"preview-hq-mp3": "https://cdn.freesound.org/previews/9988-hq.mp3"},
                "tags": ["clock", "tense"],
                "license": "http://creativecommons.org/publicdomain/zero/1.0/",
            }
        ]
    }
    search_resp.raise_for_status.return_value = None

    dl_resp = MagicMock()
    dl_resp.content = b"ID3-freesound-bytes"
    dl_resp.raise_for_status.return_value = None

    client = AsyncMock()
    client.get.side_effect = [search_resp, dl_resp]

    hits = asyncio.run(search_freesound_audio("clock", kind="sfx", api_key="fs-key", client=client))
    assert len(hits) == 1
    assert hits[0]["source"] == "freesound"

    with patch("hbt.shared.online_sources.freesound_audio._normalize_mp3_lufs"):
        res = asyncio.run(
            import_freesound_audio(
                item_id=hits[0]["id"],
                title=hits[0]["title"],
                artist=hits[0]["artist"],
                download_url=hits[0]["download_url"],
                kind="sfx",
                tags=hits[0]["tags"],
                license_url=hits[0]["license"],
                library_dir=tmp_path,
                client=client,
            )
        )
    assert res["ok"] is True
    assert (tmp_path / "sfx" / "freesound-9988.mp3").is_file()


def test_freesound_and_pixabay_http_errors_raise_clear_value_error() -> None:
    req = httpx.Request("GET", "https://example.com")

    bad_fs_resp = MagicMock()
    bad_fs_resp.status_code = 401
    bad_fs_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=req, response=bad_fs_resp
    )
    client_fs = AsyncMock()
    client_fs.get.return_value = bad_fs_resp
    with pytest.raises(ValueError, match="FREESOUND_API_KEY"):
        asyncio.run(search_freesound_audio("piano", kind="music", api_key="bad", client=client_fs))

    bad_px_resp = MagicMock()
    bad_px_resp.status_code = 400
    bad_px_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400", request=req, response=bad_px_resp
    )
    client_px = AsyncMock()
    client_px.get.return_value = bad_px_resp
    with pytest.raises(ValueError, match="Pixabay Public REST API"):
        asyncio.run(search_pixabay_audio("piano", kind="music", api_key="px-key", client=client_px))


def test_resolve_online_api_key_overrides_empty_env_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("FREESOUND_API_KEY", "")
    monkeypatch.setenv("PIXABAY_API_KEY", "")

    AppSettingsStore(ws).save(
        AppSettings(freesound_api_key="live-fs-key", pixabay_api_key="live-px-key")
    )
    assert resolve_online_api_key("FREESOUND_API_KEY", ws) == "live-fs-key"
    assert resolve_online_api_key("PIXABAY_API_KEY", ws) == "live-px-key"


def test_unified_online_search_freesound_and_ttl_cache_cleared_on_settings_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ONLINE_SEARCH_CACHE.clear()
    monkeypatch.setenv("FREESOUND_API_KEY", "demo-fs")

    settings = Settings(
        workspace_dir=tmp_path / "ws",
        assets_dir=tmp_path / "assets",
        library_dir=tmp_path / "lib",
        whisper_model="small",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings)
    client = TestClient(app)

    fake_items = [
        {
            "id": "fs1",
            "title": "Science Ambient",
            "artist": "HBT",
            "duration": 60.0,
            "tags": ["ambient"],
            "preview_url": "https://example.com/fs1.mp3",
            "download_url": "https://example.com/fs1.mp3",
            "source": "freesound",
            "kind": "music",
        }
    ]
    with patch(
        "hbt.api.asset_hub.search_freesound_audio", new=AsyncMock(return_value=fake_items)
    ) as m_fs:
        r1 = client.get("/api/asset-hub/online/search?category=music&source=freesound&q=science")
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert r1.json()["items"][0]["id"] == "fs1"

        r2 = client.get("/api/asset-hub/online/search?category=music&source=freesound&q=science")
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert m_fs.await_count == 1

        # Lưu Cài đặt xóa cache tìm kiếm online ngay lập tức
        put_res = client.put("/api/settings/app", json={"freesound_api_key": "new-fs-key"})
        assert put_res.status_code == 200
        assert len(_ONLINE_SEARCH_CACHE) == 0


def test_auto_resolve_mood_bgm_downloads_from_freesound_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FREESOUND_API_KEY", "demo-fs")
    lib = tmp_path / "lib"
    (lib / "music").mkdir(parents=True, exist_ok=True)
    downloaded_file = lib / "music" / "freesound-auto1.mp3"

    async def _fake_import(**kwargs: object) -> dict[str, object]:
        downloaded_file.write_bytes(b"mp3")
        return {"ok": True, "path": str(downloaded_file)}

    with (
        patch(
            "hbt.stickv.audio.search_freesound_audio",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "auto1",
                        "title": "Auto Ambient Track",
                        "artist": "FreesoundCreator",
                        "download_url": "https://example.com/auto1.mp3",
                        "tags": ["ambient"],
                    }
                ]
            ),
        ),
        patch("hbt.stickv.audio.import_freesound_audio", side_effect=_fake_import),
    ):
        tracks = auto_resolve_mood_bgm(lib, 12.0, "curious_science")
        assert tracks == [downloaded_file]
