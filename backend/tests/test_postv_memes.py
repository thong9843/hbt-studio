"""Kiểm thử Thư viện Meme & Sticker greenscreen (hbt.postv.memes)."""

from unittest.mock import MagicMock, patch

import pytest

from hbt.postv.memes import MemeLibrary
from hbt.postv.models import PostvSegment
from tests.test_api import client  # noqa: F401


@pytest.fixture
def meme_lib(tmp_path):
    return MemeLibrary(tmp_path)


def test_meme_library_empty_init(meme_lib):
    assert meme_lib.list() == []


def test_postv_segment_meme_fields():
    seg = PostvSegment(
        role="comment", voice="Xin chào", meme_id="cat-dance", meme_pos="bottom_center"
    )
    assert seg.meme_id == "cat-dance"
    assert seg.meme_pos == "bottom_center"

    default_seg = PostvSegment(role="post", voice="Bài gốc")
    assert default_seg.meme_id is None
    assert default_seg.meme_pos == "bottom_right"


def test_meme_library_download_and_find(meme_lib, monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake mp4 video bytes"

    # Mock probe
    monkeypatch.setattr(
        "hbt.postv.memes.probe",
        lambda _: {
            "format": {"duration": "4.5"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
        },
    )

    with patch("httpx.Client.get", return_value=mock_resp):
        entry = meme_lib.download(
            meme_id="cat-1",
            video_url="https://media.greenscreenmemes.com/sample.mp4",
            title="Mèo nhảy",
            poster_url="https://media.greenscreenmemes.com/sample.webp",
        )
        assert entry.id == "cat-1"
        assert entry.title == "Mèo nhảy"
        assert entry.duration == 4.5
        assert entry.downloaded is True
        assert entry.source == "https://media.greenscreenmemes.com/sample.mp4"
        assert entry.license == "chưa rõ"

        found, path = meme_lib.find("cat-1")
        assert found.id == "cat-1"
        assert path.is_file()

        # Delete
        meme_lib.delete("cat-1")
        assert meme_lib.list() == []


@pytest.mark.anyio
async def test_search_online_with_mock(meme_lib):
    mock_posts = [
        {
            "id": 1234,
            "title": {"rendered": "Funny Cat Meme Green Screen"},
            "link": "https://greenscreenmemes.com/cat/",
        }
    ]
    mock_page = '<video src="https://media.greenscreenmemes.com/cat.mp4" poster="https://greenscreenmemes.com/cat.webp"></video>'

    class MockAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "wp-json" in url:
                resp.json = lambda: mock_posts
            else:
                resp.text = mock_page
            return resp

    with patch("httpx.AsyncClient", return_value=MockAsyncClient()):
        results = await meme_lib.search_online("cat", count=5)
        assert len(results) == 1
        assert results[0].id == "1234"
        assert results[0].title == "Funny Cat"
        assert results[0].video_url == "https://media.greenscreenmemes.com/cat.mp4"


def test_api_memes_endpoints(client, monkeypatch):  # noqa: F811
    # Mock probe & download
    monkeypatch.setattr(
        "hbt.postv.memes.probe",
        lambda _: {
            "format": {"duration": "3.0"},
            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
        },
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake mp4 video bytes"

    with patch("httpx.Client.get", return_value=mock_resp):
        # 1. Download
        r_down = client.post(
            "/api/memes/download",
            json={
                "meme_id": "test-cat",
                "video_url": "https://media.greenscreenmemes.com/test.mp4",
                "title": "Mèo hài",
            },
        )
        assert r_down.status_code == 200
        assert r_down.json()["id"] == "test-cat"

        # 2. List library
        r_list = client.get("/api/memes/library")
        assert r_list.status_code == 200
        items = r_list.json()
        assert any(i["id"] == "test-cat" for i in items)

        # 3. Delete
        r_del = client.delete("/api/memes/test-cat")
        assert r_del.status_code == 200
