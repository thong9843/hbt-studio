"""Xử lý nguồn vào cho Chatting (link Reddit, nhận diện Threads, dán chữ) theo §1, §4."""

from __future__ import annotations

import re
from typing import Any
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


def parse_direct_script(text: str) -> dict[str, Any]:
    """Bóc tách kịch bản dán trực tiếp (Bypass LLM) thành danh sách nhân vật và lời thoại."""
    from hbt.chatting.models import VALID_STICKER_TAGS

    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("Văn bản kịch bản trống")

    # Mẫu nhận diện: "Tên: Lời thoại", "[Tên]: Lời thoại", hoặc "Tên - Lời thoại"
    dialogue_pattern = re.compile(
        r"^(?:\[(?P<b_name>[^\]]{1,24})\]|(?P<p_name>[^:\-–—]{1,24}))\s*[:\-–—]\s*(?P<speech>.*)$"
    )
    sticker_bracket_pat = re.compile(r"\[(?:sticker:\s*|nhãn dán:\s*)?([^\]]+)\]", re.IGNORECASE)
    sticker_paren_pat = re.compile(r"\(([^)]+)\)$", re.IGNORECASE)

    tag_map = {
        "cuoi": "cuoi",
        "cười": "cuoi",
        "haha": "cuoi",
        "khoc": "khoc",
        "khóc": "khoc",
        "gian": "gian",
        "giận": "gian",
        "ngai": "ngai",
        "ngại": "ngai",
        "yeu": "yeu",
        "yêu": "yeu",
        "tim": "yeu",
        "soc": "soc",
        "sốc": "soc",
        "nghi": "nghi",
        "nghĩ": "nghi",
        "can": "can",
        "cạn": "can",
        "cang": "can",
        "bat_luc": "bat_luc",
        "bất lực": "bat_luc",
        "batluc": "bat_luc",
        "ok": "ok",
    }

    raw_dialogues: list[tuple[str, str, str | None]] = []
    char_names: list[str] = []

    last_speaker = "Người 1"

    for line in lines:
        m = dialogue_pattern.match(line)
        if m:
            speaker = (m.group("b_name") or m.group("p_name") or "").strip()
            speech = (m.group("speech") or "").strip()
        else:
            speaker = last_speaker
            speech = line

        last_speaker = speaker
        if speaker not in char_names:
            char_names.append(speaker)

        # Kiểm tra sticker
        sticker: str | None = None
        sm = sticker_bracket_pat.search(speech)
        if sm:
            raw_tag = sm.group(1).strip().lower()
            normalized_tag = tag_map.get(raw_tag)
            if normalized_tag and normalized_tag in VALID_STICKER_TAGS:
                sticker = normalized_tag
                speech = sticker_bracket_pat.sub("", speech).strip()
        if not sticker:
            spm = sticker_paren_pat.search(speech)
            if spm:
                raw_tag = spm.group(1).strip().lower()
                normalized_tag = tag_map.get(raw_tag)
                if normalized_tag and normalized_tag in VALID_STICKER_TAGS:
                    sticker = normalized_tag
                    speech = sticker_paren_pat.sub("", speech).strip()

        if speech or sticker:
            raw_dialogues.append((speaker, speech, sticker))

    if not raw_dialogues:
        raise ValueError("Không tìm thấy câu thoại nào hợp lệ trong kịch bản")

    # Phân vai: người đầu tiên bên phải ("me"), những người sau bên trái
    default_voices = ["Adam bựa", "Trúc Ly", "Thiện Minh", "Mai Anh", "Hải Đăng"]
    characters: list[dict[str, Any]] = []
    char_id_map: dict[str, str] = {}

    for idx, name in enumerate(char_names):
        cid = f"c{idx + 1}" if idx > 0 else "me"
        side = "right" if idx == 0 else "left"
        voice = default_voices[idx % len(default_voices)]
        char_id_map[name] = cid
        characters.append(
            {
                "id": cid,
                "name": name,
                "side": side,
                "voice": voice,
                "avatar": None,
            }
        )

    messages: list[dict[str, Any]] = []
    for speaker, speech, sticker in raw_dialogues:
        cid = char_id_map.get(speaker, "me")
        messages.append(
            {
                "from": cid,
                "text": speech or "...",
                "sticker": sticker,
            }
        )

    title = f"Đoạn chat của {char_names[0]}" if char_names else "Kịch bản trực tiếp"
    return {
        "title": title,
        "characters": characters,
        "messages": messages,
        "warnings": [],
    }
