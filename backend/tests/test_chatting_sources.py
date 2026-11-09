"""Tests cho xử lý nguồn Reddit, Threads và dán chữ (CH1)."""

from unittest.mock import patch

import httpx
import pytest

from hbt.chatting.sources import (
    extract_reddit_id,
    fetch_reddit,
    parse_link,
)


def test_parse_link_reddit():
    urls = [
        ("https://www.reddit.com/r/VietNam/comments/1abc23/sample_post/", "1abc23"),
        ("https://reddit.com/r/test/comments/xyz123", "xyz123"),
        ("https://old.reddit.com/comments/abc789", "abc789"),
        ("https://redd.it/post123", "post123"),
        ("http://www.reddit.com/comments/def456/title", "def456"),
    ]
    for url, expected_id in urls:
        kind, link = parse_link(url)
        assert kind == "reddit"
        assert link == url
        assert extract_reddit_id(url) == expected_id


def test_parse_link_threads():
    urls = [
        "https://www.threads.net/@user/post/C123abc",
        "https://threads.net/@another_user/post/D456",
        "https://www.threads.com/@user/post/xyz",
    ]
    for url in urls:
        kind, link = parse_link(url)
        assert kind == "threads"
        assert link == url


def test_parse_link_pasted_and_unknown():
    samples = [
        "Chỉ là một câu chuyện dán tay bình thường",
        "https://facebook.com/groups/123/posts/456",
        "https://voz.vn/t/cau-chuyen-nua-dem.12345/",
        "ftp://example.com/file",
    ]
    for s in samples:
        kind, link = parse_link(s)
        assert kind == "pasted"
        assert link is None


def test_fetch_reddit_success():
    post_id = "test123"

    fake_response = [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Bỏ quên ví ở quán cà phê",
                            "selftext": "Hôm qua mình đi uống nước và bỏ quên ví...",
                        }
                    }
                ]
            }
        },
        {
            "data": {
                "children": [
                    {"data": {"author": "user1", "body": "Quán ở đâu vậy bạn?"}},
                    {"data": {"author": "user2", "body": "May mắn quá!"}},
                    {"data": {"author": "AutoModerator", "body": "Rule reminder"}},
                    {"data": {"author": "user3", "body": "[deleted]"}},
                ]
            }
        },
    ]

    mock_resp = httpx.Response(
        200, json=fake_response, request=httpx.Request("GET", "https://reddit.com")
    )
    with patch("httpx.Client.get", return_value=mock_resp):
        data = fetch_reddit(f"https://redd.it/{post_id}")
        assert data["title"] == "Bỏ quên ví ở quán cà phê"
        assert "bỏ quên ví" in data["body"]
        assert len(data["comments"]) == 2  # user1, user2 (bỏ qua bot và [deleted])
        assert data["comments"][0] == "Quán ở đâu vậy bạn?"


def test_fetch_reddit_403_or_429():
    post_id = "blocked"
    mock_resp = httpx.Response(403, request=httpx.Request("GET", "https://reddit.com"))

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(ValueError, match="Không lấy được bài, dán nội dung vào ô chat"):
            fetch_reddit(f"https://redd.it/{post_id}")


def test_fetch_threads_success():
    from unittest.mock import MagicMock

    from hbt.chatting.sources import fetch_threads

    fake_parse = MagicMock()
    fake_parse.post.handle = "testuser"
    fake_parse.post.text = "Hôm nay trời đẹp đi uống cà phê"
    comment_mock = MagicMock()
    comment_mock.text = "Quán cà phê view đẹp quá"
    fake_parse.comments = [comment_mock]

    with patch("hbt.postv.threads.extract_threads_post", return_value=fake_parse):
        res = fetch_threads("https://www.threads.net/@testuser/post/123")
        assert res["title"] == "Bài viết Threads của @testuser"
        assert res["body"] == "Hôm nay trời đẹp đi uống cà phê"
        assert res["comments"] == ["Quán cà phê view đẹp quá"]
