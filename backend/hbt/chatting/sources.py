"""Xử lý nguồn vào cho Chatting (link Reddit, nhận diện Threads, dán chữ) theo §1, §4."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

REDDIT_DOMAINS = {"www.reddit.com", "reddit.com", "old.reddit.com", "redd.it"}
REDDIT_PATH_PATTERN = re.compile(r"/(?:r/[^/]+/)?comments/([a-z0-9]+)", re.IGNORECASE)
REDDIT_SHORT_PATTERN = re.compile(r"^/([a-z0-9]+)$", re.IGNORECASE)
THREADS_DOMAINS = {"www.threads.net", "threads.net", "www.threads.com", "threads.com"}

USER_AGENT = "hbt-studio/0.1.0 (local)"
MAX_INPUT_CHARS = 6000


def parse_link(raw_input: str) -> tuple[str, str | None]:
    """Phân loại đầu vào thành: ('reddit', url), ('threads', url), hoặc ('pasted', None)."""
    text = raw_input.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        return "pasted", None

    try:
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
    except Exception:
        return "pasted", None

    if host in REDDIT_DOMAINS:
        return "reddit", text
    if host in THREADS_DOMAINS:
        return "threads", text

    return "pasted", None


def extract_reddit_id(url: str) -> str:
    """Trích xuất post id từ link Reddit."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in REDDIT_DOMAINS:
        raise ValueError(f"Domain không được phép: {host}")

    if host == "redd.it":
        m = REDDIT_SHORT_PATTERN.match(parsed.path)
        if m:
            return m.group(1)
    else:
        m = REDDIT_PATH_PATTERN.search(parsed.path)
        if m:
            return m.group(1)

    raise ValueError("Không tìm thấy ID bài viết Reddit từ đường dẫn")


def fetch_reddit(url_or_id: str, timeout: float = 15.0) -> dict[str, str | list[str]]:
    """Lấy bài viết Reddit qua GET .json công khai."""
    is_url = "http://" in url_or_id or "https://" in url_or_id
    post_id = extract_reddit_id(url_or_id) if is_url else url_or_id
    endpoint = f"https://www.reddit.com/comments/{post_id}.json?raw_json=1&limit=5&sort=top"

    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(timeout=timeout, headers=headers) as client:
            resp = client.get(endpoint)
            if resp.status_code in (403, 429):
                raise ValueError("Không lấy được bài, dán nội dung vào ô chat")
            resp.raise_for_status()
            data = resp.json()
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Không lấy được bài Reddit: {e}") from e

    if not isinstance(data, list) or len(data) < 1:
        raise ValueError("Dữ liệu phản hồi từ Reddit không đúng cấu trúc")

    # Dữ liệu bài chính
    post_info = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
    title = (post_info.get("title") or "").strip()
    selftext = (post_info.get("selftext") or "").strip()

    # Dữ liệu bình luận
    comments: list[str] = []
    if len(data) > 1:
        comment_children = data[1].get("data", {}).get("children", [])
        for c in comment_children:
            c_data = c.get("data", {})
            body = (c_data.get("body") or "").strip()
            # Bỏ qua [deleted], [removed], AutoModerator
            author = (c_data.get("author") or "").lower()
            if body and body not in ("[deleted]", "[removed]") and author != "automoderator":
                comments.append(body)
                if len(comments) >= 5:
                    break

    # Cắt tổng đầu vào <= 6000 ký tự
    total_len = len(title) + len(selftext) + sum(len(c) for c in comments)
    if total_len > MAX_INPUT_CHARS:
        excess = total_len - MAX_INPUT_CHARS
        if len(selftext) > excess + 200:
            selftext = selftext[: len(selftext) - excess] + "..."
        else:
            comments = comments[:2]

    return {
        "title": title,
        "body": selftext,
        "comments": comments,
        "source_url": url_or_id,
    }


def fetch_threads(url: str, timeout: float = 15.0) -> dict[str, str | list[str]]:
    """Lấy bài viết Threads qua hbt.postv.threads.extract_threads_post."""
    try:
        from hbt.postv.threads import extract_threads_post

        parsed = extract_threads_post(url, timeout=timeout)
        handle = ""
        selftext = ""
        if parsed.post:
            handle = getattr(parsed.post, "handle", "") or ""
            selftext = getattr(parsed.post, "text", "") or ""
        title = f"Bài viết Threads của @{handle}" if handle else "Bài viết Threads"
        comments = [c.text for c in (parsed.comments or []) if getattr(c, "text", "").strip()]
        if len(comments) > 5:
            comments = comments[:5]

        total_len = len(title) + len(selftext) + sum(len(c) for c in comments)
        if total_len > MAX_INPUT_CHARS:
            excess = total_len - MAX_INPUT_CHARS
            if len(selftext) > excess + 200:
                selftext = selftext[: len(selftext) - excess] + "..."
            else:
                comments = comments[:2]

        return {
            "title": title,
            "body": selftext,
            "comments": comments,
            "source_url": url,
        }
    except Exception as e:
        raise ValueError(f"Không lấy được bài Threads: {e}") from e
