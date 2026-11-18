"""Unit test cho Jamendo Music API, Freesound API, TTL cache & auto-pick BGM."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hbt.api.app import create_app
from hbt.api.asset_hub import _ONLINE_SEARCH_CACHE
from hbt.config import Settings
from hbt.shared.online_sources.freesound_audio import import_freesound_audio, search_freesound_audio
from hbt.shared.online_sources.jamendo_music import import_jamendo_music, search_jamendo_music
from hbt.stickv.audio import auto_resolve_mood_bgm


@pytest.mark.asyncio
async def test_jamendo_search_and_import(tmp_path: Path) -> None:
    search_resp = MagicMock()
    search_resp.json.return_value = {
        "results": [
            {
                "id": "12345",
                "name": "Quantum Pulse",
                "artist_name": "Lab Synth",
                "duration": 95,
                "audio": "https://mp3d.jamendo.com/track/12345.mp3",
                "audiodownload": "https://mp3d.jamendo.com/download/12345.mp3",
                "license_ccurl": "https://creativecommons.org/licenses/by/3.0/",
                "musicinfo": {"tags": {"genres": ["ambient", "electronic"]}},
            }
        ]
    }
    search_resp.raise_for_status.return_value = None

    dl_resp = MagicMock()
    dl_resp.content = b"ID3-fake-mp3-data"
    dl_resp.raise_for_status.return_value = None

    client = AsyncMock()
    client.get.side_effect = [search_resp, dl_resp]

    hits = await search_jamendo_music(mood="curious_science", client_id="cid-123", client=client)
    assert len(hits) == 1
    assert hits[0]["source"] == "jamendo"
    assert hits[0]["title"] == "Quantum Pulse"

    with patch("hbt.shared.online_sources.jamendo_music._normalize_mp3_lufs"):
        res = await import_jamendo_music(
            item_id=hits[0]["id"],
            title=hits[0]["title"],
            artist=hits[0]["artist"],
            download_url=hits[0]["download_url"],
            tags=hits[0]["tags"],
            moods=["curious_science"],
            license_url=hits[0]["license"],
            library_dir=tmp_path,
            client=client,
        )
    assert res["ok"] is True
    mp3_path = tmp_path / "music" / "jamendo-12345.mp3"
    assert mp3_path.is_file()
    idx = json.loads((tmp_path / "music" / "index.json").read_text(encoding="utf-8"))
    assert idx[0]["source"] == "jamendo"
    assert "curious_science" in idx[0]["moods"]


@pytest.mark.asyncio
async def test_freesound_search_and_import(tmp_path: Path) -> None:
    search_resp = MagicMock()
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

    hits = await search_freesound_audio("clock", kind="sfx", api_key="fs-key", client=client)
    assert len(hits) == 1
    assert hits[0]["source"] == "freesound"

    with patch("hbt.shared.online_sources.freesound_audio._normalize_mp3_lufs"):
        res = await import_freesound_audio(
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
    assert res["ok"] is True
    assert (tmp_path / "sfx" / "freesound-9988.mp3").is_file()


def test_unified_online_search_jamendo_and_ttl_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ONLINE_SEARCH_CACHE.clear()
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "demo-cid")
    monkeypatch.setenv("FREESOUND_API_KEY", "demo-fs")

    settings = Settings(
        workspace_dir=tmp_path / "ws",
        assets_dir=tmp_path / "assets",
        library_dir=tmp_path / "lib",
        out_dir=tmp_path / "out",
    )
    app = create_app(settings)
    client = TestClient(app)

    fake_items = [
        {
            "id": "j1",
            "title": "Science Beat",
            "artist": "HBT",
            "duration": 60.0,
            "tags": ["ambient"],
            "preview_url": "https://example.com/j1.mp3",
            "download_url": "https://example.com/j1.mp3",
            "source": "jamendo",
            "kind": "music",
        }
    ]
    with patch("hbt.api.asset_hub.search_jamendo_music", new=AsyncMock(return_value=fake_items)) as m_j:
        r1 = client.get("/api/asset-hub/online/search?category=music&source=jamendo&q=science")
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert r1.json()["items"][0]["id"] == "j1"

        r2 = client.get("/api/asset-hub/online/search?category=music&source=jamendo&q=science")
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert m_j.await_count == 1


def test_auto_resolve_mood_bgm_downloads_from_jamendo_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JAMENDO_CLIENT_ID", "demo-cid")
    lib = tmp_path / "lib"
    (lib / "music").mkdir(parents=True, exist_ok=True)
    downloaded_file = lib / "music" / "jamendo-auto1.mp3"

    async def _fake_import(**kwargs: object) -> dict[str, object]:
        downloaded_file.write_bytes(b"mp3")
        return {"ok": True, "path": str(downloaded_file)}

    with (
        patch(
            "hbt.stickv.audio.search_jamendo_music",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "auto1",
                        "title": "Auto Track",
                        "artist": "AI",
                        "download_url": "https://example.com/auto1.mp3",
                        "tags": ["ambient"],
                    }
                ]
            ),
        ),
        patch("hbt.stickv.audio.import_jamendo_music", side_effect=_fake_import),
    ):
        tracks = auto_resolve_mood_bgm(lib, 12.0, "curious_science")
        assert tracks == [downloaded_file]
