"""Kiểm thử trích xuất bài viết Threads trực tiếp từ URL (hbt.postv.threads)."""

from unittest.mock import MagicMock, patch

import pytest

from hbt.postv.threads import (
    ThreadsFetchError,
    extract_threads_post,
    is_threads_url,
)
from tests.test_api import client  # noqa: F401

SAMPLE_THREAD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta property="og:site_name" content="Threads" />
  <meta property="og:title" content="Trần Văn A (@tranvana) on Threads" />
  <meta property="og:description" content="Hôm nay trời đẹp quá mọi người ơi!" />
  <meta property="og:image" content="https://scontent.cdninstagram.com/v/sample_image.jpg" />
  <meta property="og:url" content="https://www.threads.net/@tranvana/post/DfXrs6RGonx" />
</head>
<body></body>
</html>
"""

SAMPLE_DIALOGUE_DESC = "Chồng: Em ơi tối nay ăn gì?&#10;Vợ: Ăn gì cũng được.&#10;Chồng: Ăn phở nhé?"
SAMPLE_DIALOGUE_HTML = f"""
<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Chuyện Vợ Chồng (@giadinh) on Threads" />
  <meta property="og:description" content="{SAMPLE_DIALOGUE_DESC}" />
  <meta property="og:image" content="https://scontent.cdninstagram.com/v/chat.jpg" />
</head>
<body></body>
</html>
"""


def test_is_threads_url():
    assert is_threads_url("https://www.threads.net/@zuck/post/DfXrs6RGonx")
    assert is_threads_url("https://threads.net/@user/post/12345")
    assert is_threads_url("http://threads.net/t/abc_123")
    assert is_threads_url("www.threads.net/@abc/post/xyz")

    assert not is_threads_url("https://facebook.com/post/123")
    assert not is_threads_url("https://threads.net/")
    assert not is_threads_url("https://threads.net/@user")
    assert not is_threads_url("chữ thường không phải link")


def test_extract_threads_post_success(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_THREAD_HTML

    with patch("httpx.Client.get", return_value=mock_resp):
        res = extract_threads_post("https://www.threads.net/@tranvana/post/DfXrs6RGonx")

        assert res.guess == "threads_text"
        assert res.source_url == "https://www.threads.net/@tranvana/post/DfXrs6RGonx"
        assert res.post.handle == "tranvana"
        assert res.post.text == "Hôm nay trời đẹp quá mọi người ơi!"
        assert res.post.age == "vừa xong"
        assert res.comments == []


def test_extract_threads_post_dialogue_splitting():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_DIALOGUE_HTML

    with patch("httpx.Client.get", return_value=mock_resp):
        res = extract_threads_post("https://www.threads.net/@giadinh/post/123")

        assert res.post.handle == "Chồng"
        assert res.post.text == "Em ơi tối nay ăn gì?"
        assert len(res.comments) == 2
        assert res.comments[0].handle == "Vợ"
        assert res.comments[0].text == "Ăn gì cũng được."
        assert res.comments[1].handle == "Chồng"
        assert res.comments[1].text == "Ăn phở nhé?"


def test_extract_threads_post_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(ThreadsFetchError, match="không tồn tại"):
            extract_threads_post("https://www.threads.net/@user/post/notfound")


def test_api_fetch_threads_endpoint(client):  # noqa: F811
    # Invalid URL
    r_bad = client.post("/api/postv/fetch-threads", json={"url": "https://facebook.com/123"})
    assert r_bad.status_code == 422

    # Valid URL with mock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_THREAD_HTML

    with patch("httpx.Client.get", return_value=mock_resp):
        r_ok = client.post(
            "/api/postv/fetch-threads",
            json={"url": "https://www.threads.net/@tranvana/post/DfXrs6RGonx"},
        )
        assert r_ok.status_code == 200
        data = r_ok.json()
        assert data["guess"] == "threads_text"
        assert data["post"]["handle"] == "tranvana"
        assert data["post"]["text"] == "Hôm nay trời đẹp quá mọi người ơi!"


def test_api_parse_auto_detects_threads_url(client):  # noqa: F811
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_THREAD_HTML

    with patch("httpx.Client.get", return_value=mock_resp):
        r = client.post(
            "/api/postv/parse",
            json={"text": "https://www.threads.net/@tranvana/post/DfXrs6RGonx"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["guess"] == "threads_text"
        assert data["post"]["handle"] == "tranvana"
