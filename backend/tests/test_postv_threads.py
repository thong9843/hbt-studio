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


SAMPLE_CAROUSEL_AND_TREE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta property="og:title" content="Chủ Bài (@host) on Threads" />
  <meta property="og:description" content="Ảnh đẹp cuối tuần nè mọi người." />
  <meta property="og:image" content="https://scontent.cdninstagram.com/t51.2885-19/avt.jpg" />
</head>
<body>
  <script type="application/json">
  {
    "carousel_media": [
      {
        "image_versions2": {
          "candidates": [
            {"url": "https://scontent.cdninstagram.com/v/p1_s.jpg", "width": 320, "height": 320},
            {"url": "https://scontent.cdninstagram.com/v/p1_hd.jpg", "width": 1080, "height": 1350}
          ]
        }
      },
      {
        "image_versions2": {
          "candidates": [
            {"url": "https://scontent.cdninstagram.com/v/p2_hd.jpg", "width": 1080, "height": 1080}
          ]
        }
      }
    ],
    "thread_items": [
      {
        "post": {
          "user": {"username": "parent_user"},
          "caption": {"text": "Bình luận gốc thu hút hàng nghìn tương tác."},
          "like_count": 320,
          "text_post_app_info": {"direct_reply_count": 12}
        }
      },
      {
        "post": {
          "user": {"username": "child_user"},
          "caption": {"text": "Reply nổi bật ngay bên dưới bình luận cha."},
          "like_count": 45
        }
      }
    ]
  }
  </script>
</body>
</html>
"""


def test_extract_threads_carousel_media_and_threaded_replies(tmp_path):
    import io

    from PIL import Image

    from hbt.postv.threads import download_post_media

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_CAROUSEL_AND_TREE_HTML

    with patch("httpx.Client.get", return_value=mock_resp):
        res = extract_threads_post("https://www.threads.net/@host/post/ABC123")

    assert res.media_urls == [
        "https://scontent.cdninstagram.com/v/p1_hd.jpg",
        "https://scontent.cdninstagram.com/v/p2_hd.jpg",
    ]
    assert len(res.comments) == 2
    assert res.comments[0].id == "c1"
    assert res.comments[0].replies == 12
    assert res.comments[0].parent is None
    assert res.comments[1].id == "c2"
    assert res.comments[1].parent == "c1"

    # Kiểm tra download_post_media tải và xác thực ảnh bằng Pillow
    buf = io.BytesIO()
    Image.new("RGB", (120, 120), (20, 150, 220)).save(buf, format="PNG")
    img_resp = MagicMock()
    img_resp.status_code = 200
    img_resp.content = buf.getvalue()

    with patch("httpx.Client.get", return_value=img_resp):
        saved = download_post_media(res.media_urls, tmp_path / "media")

    assert len(saved) == 2
    assert saved[0].is_file() and saved[0].suffix == ".png"


def test_extract_threads_nested_replies_key():
    nested_html = """
    <html><head>
      <meta property="og:title" content="TacGia (@tacgia) on Threads" />
      <meta property="og:description" content="Bài viết chính thu hút tranh luận." />
    </head><body><script type="application/json">
    {
      "thread_items": [
        {
          "post": {
            "user": {"username": "parent_vip"},
            "caption": {"text": "Comment cha siêu chất lượng mọi người ơi."},
            "like_count": 200
          },
          "replies": [
            {
              "user": {"username": "nested_child"},
              "caption": {"text": "Reply con nằm lồng trong mảng replies nè!"},
              "like_count": 35
            }
          ]
        }
      ]
    }
    </script></body></html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = nested_html
    with patch("httpx.Client.get", return_value=mock_resp):
        res = extract_threads_post("https://www.threads.net/@tacgia/post/XYZ999")
    assert len(res.comments) == 2
    assert res.comments[0].id == "c1" and res.comments[0].parent is None
    assert res.comments[1].id == "c2" and res.comments[1].parent == "c1"


def test_extract_threads_45_items_with_comment_media(tmp_path):
    import json

    items = []
    for i in range(1, 31):
        items.append(
            {
                "post": {
                    "user": {"username": f"u_{i}"},
                    "caption": {"text": f"Bình luận thứ {i} cực mặn mà từ cộng đồng Threads!"},
                    "like_count": 100 - i,
                    **(
                        {
                            "image_versions2": {
                                "candidates": [
                                    {
                                        "url": f"https://scontent.cdninstagram.com/v/c{i}.jpg",
                                        "width": 720,
                                        "height": 720,
                                    }
                                ]
                            }
                        }
                        if i == 1
                        else {}
                    ),
                },
                "direct_replies": (
                    [
                        {
                            "user": {"username": f"rep_{i}"},
                            "caption": {"text": f"Reply con nối đuôi ngay dưới u_{i}!"},
                            "like_count": 30,
                        }
                    ]
                    if i <= 15
                    else []
                ),
            }
        )
    payload_json = json.dumps({"edges": [{"node": x} for x in items]})
    html_45 = (
        '<html><head><meta property="og:title" content="Host (@host) on Threads" />'
        '<meta property="og:description" content="Bài viết gốc nhiều tương tác." />'
        f'</head><body><script type="application/json">{payload_json}</script>'
        "</body></html>"
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_45
    with patch("httpx.Client.get", return_value=mock_resp):
        res = extract_threads_post("https://www.threads.net/@host/post/DEEP45")
    assert len(res.comments) == 45
    assert res.comments[0].media_urls == ["https://scontent.cdninstagram.com/v/c1.jpg"]
    assert res.comments[1].parent == "c1"


def test_extract_threads_playwright_graphql_posts_edges_and_child_blobs():
    import json

    ssr_html = """
    <html><head>
      <meta property="og:title" content="Host (@host) on Threads" />
      <meta property="og:description" content="Bài viết gốc nhiều tương tác thực tế." />
    </head><body>
      <script type="application/json">
      {
        "thread_items": [
          {
            "post": {
              "user": {"username": "top_vip"},
              "caption": {"text": "Bình luận đầu bảng siêu hot!"},
              "like_count": 500,
              "text_post_app_info": {"direct_reply_count": 10}
            }
          }
        ]
      }
      </script>
    </body></html>
    """
    gql_edges = []
    for i in range(1, 36):
        posts_edges = [
            {
                "node": {
                    "user": {"username": f"user_{i}"},
                    "caption": {"text": f"Bình luận GraphQL trang sâu số {i} rất dài và hay."},
                    "like_count": 100 - i,
                }
            }
        ]
        if i == 1:
            posts_edges.append(
                {
                    "node": {
                        "user": {"username": "inline_child"},
                        "caption": {"text": "Reply nối đuôi nằm sẵn trong posts.edges nè!"},
                        "like_count": 25,
                    }
                }
            )
        gql_edges.append({"node": {"posts": {"edges": posts_edges}}})

    child_node = {
        "node": {
            "user": {"username": "vip_replier"},
            "caption": {"text": "Reply con bóc qua fetchChildReplies!"},
            "like_count": 88,
        }
    }
    child_blob = json.dumps(
        {
            "data": {
                "media": {
                    "text_post_app_info": {
                        "direct_replies": {"edges": [{"node": {"posts": {"edges": [child_node]}}}]}
                    }
                }
            }
        }
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ssr_html

    browser_payload = {
        "final_url": "https://www.threads.com/@host/post/DEEP99",
        "og": {},
        "scripts": [],
        "graphql_payloads": [
            json.dumps(
                {
                    "data": {
                        "media": {"text_post_app_info": {"direct_replies": {"edges": gql_edges}}}
                    }
                }
            )
        ],
        "child_reply_blobs": [
            {"parent_text": "Bình luận đầu bảng siêu hot!", "payload": child_blob}
        ],
        "dom_text": "",
    }

    with (
        patch("httpx.Client.get", return_value=mock_resp),
        patch("hbt.postv.threads._scrape_threads_with_playwright", return_value=browser_payload),
    ):
        res = extract_threads_post("https://www.threads.com/@host/post/DEEP99")

    assert len(res.comments) == 38
    assert res.comments[0].id == "c1"
    # Reply con của c1 (từ child_blobs) phải đứng ngay sau c1 theo cây hội thoại tuần tự
    assert res.comments[1].handle == "vip_replier" and res.comments[1].parent == "c1"
    c2_idx = next(i for i, c in enumerate(res.comments) if c.id == "c2")
    assert res.comments[c2_idx].parent is None
    assert (
        res.comments[c2_idx + 1].handle == "inline_child"
        and res.comments[c2_idx + 1].parent == "c2"
    )


def test_extract_threads_playwright_rescues_http_error():
    import json

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"

    browser_payload = {
        "final_url": "https://www.threads.com/@tacgia/post/OK123",
        "og": {
            "og:title": "Tác Giả (@tacgia) on Threads",
            "og:description": "Bài viết bị chặn SSR bot nhưng Chromium đọc được.",
        },
        "scripts": [
            json.dumps(
                {
                    "thread_items": [
                        {
                            "post": {
                                "user": {"username": "reader_1"},
                                "caption": {"text": "Chromium cứu thành công bài bị chặn SSR!"},
                                "like_count": 42,
                            }
                        }
                    ]
                }
            )
        ],
        "graphql_payloads": [],
        "child_reply_blobs": [],
        "dom_text": "",
    }

    with (
        patch("httpx.Client.get", return_value=mock_resp),
        patch("hbt.postv.threads._scrape_threads_with_playwright", return_value=browser_payload),
    ):
        res = extract_threads_post("https://www.threads.com/@tacgia/post/OK123")

    assert res.post.handle == "tacgia"
    assert len(res.comments) == 1
    assert res.comments[0].handle == "reader_1"
