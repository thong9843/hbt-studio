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
    assert is_threads_url("https://www.threads.com/share/EAZtg3gKD/")

    assert not is_threads_url("https://facebook.com/post/123")
    assert not is_threads_url("https://threads.net/")
    assert not is_threads_url("https://threads.net/@user")
    assert not is_threads_url("chữ thường không phải link")
    assert not is_threads_url("https://www.threads.com/@user/post/123\nuser_a\n17h\nBài gốc")


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
        assert any("Copy cả trang bài" in w for w in res.warnings)


SAMPLE_WITH_COMMENTS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Tác Giả (@author) on Threads" />
  <meta property="og:description" content="Nội dung bài viết rất hấp dẫn và lôi cuốn." />
</head>
<body>
  <script type="application/json">
  {
    "data": {
      "reply_threads": [
        {
          "post": {
            "user": {"username": "commenter_1"},
            "caption": {"text": "Bình luận đầu tiên với nhiều góc nhìn mới mẻ."},
            "like_count": 88
          }
        },
        {
          "post": {
            "user": {"username": "commenter_2"},
            "caption": {"text": "Bình luận thứ hai đóng góp ý kiến xây dựng."},
            "like_count": 12
          }
        }
      ]
    }
  }
  </script>
</body>
</html>
"""


def test_extract_threads_post_with_json_comments():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_WITH_COMMENTS_HTML

    with patch("httpx.Client.get", return_value=mock_resp):
        res = extract_threads_post("https://www.threads.net/@author/post/123456")

        assert res.post.handle == "author"
        assert res.post.text == "Nội dung bài viết rất hấp dẫn và lôi cuốn."
        assert len(res.comments) == 2
        assert res.comments[0].handle == "commenter_1"
        assert res.comments[0].text == "Bình luận đầu tiên với nhiều góc nhìn mới mẻ."
        assert res.comments[0].likes == 88
        assert res.comments[1].handle == "commenter_2"
        assert res.comments[1].text == "Bình luận thứ hai đóng góp ý kiến xây dựng."
        assert res.comments[1].likes == 12


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
