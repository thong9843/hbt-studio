"""HBT Studio - Trích xuất dữ liệu bài viết Threads trực tiếp qua URL.

Sử dụng giao thức Meta Bot SSR (facebookexternalhit) để lấy dữ liệu nhanh (< 1.5s),
không tốn RAM, không cần mở trình duyệt và không cần token API chính thức.
"""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import urlparse

import httpx

from hbt.postv.parse import ParsedComment, ParsedPost, ParseResult

BOT_HEADERS = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

THREADS_HOSTS = frozenset({"threads.net", "www.threads.net", "threads.com", "www.threads.com"})


class ThreadsFetchError(Exception):
    """Lỗi khi tải hoặc bóc tách dữ liệu từ Threads."""

    pass


def is_threads_url(url: str) -> bool:
    """Kiểm tra một chuỗi có phải là đường dẫn bài viết Threads hợp lệ không."""
    s = url.strip()
    if not s or any(c.isspace() for c in s):
        return False
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    try:
        parsed = urlparse(s)
        return parsed.netloc.lower() in THREADS_HOSTS and bool(
            re.search(r"/(?:post|t|share)/[A-Za-z0-9_-]+", parsed.path)
        )
    except Exception:
        return False


def extract_threads_post(url: str, timeout: float = 15.0) -> ParseResult:
    """Tải và trích xuất thông tin bài viết Threads thành ParseResult của PostV."""
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    parsed_url = urlparse(clean_url)
    if parsed_url.netloc.lower() not in THREADS_HOSTS:
        raise ThreadsFetchError(f"Đường dẫn không thuộc Threads: '{clean_url}'")

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(clean_url, headers=BOT_HEADERS)
    except httpx.RequestError as exc:
        raise ThreadsFetchError(f"Không thể kết nối tới Threads: {exc}") from exc

    if resp.status_code == 404:
        raise ThreadsFetchError("Bài viết Threads không tồn tại hoặc đã bị xoá (HTTP 404).")
    if resp.status_code != 200:
        raise ThreadsFetchError(f"Máy chủ Threads phản hồi lỗi: HTTP {resp.status_code}")

    raw_html = resp.text

    # 1. Bóc tách thẻ Meta (OpenGraph)
    og: dict[str, str] = {}
    for m in re.finditer(
        r'<meta\s+(?:property|name)=["\']([^"\']+)["\']\s+content=["\']([^"\']*)["\']',
        raw_html,
    ):
        og[m.group(1)] = html.unescape(m.group(2))

    for m in re.finditer(
        r'<meta\s+content=["\']([^"\']*)["\']\s+(?:property|name)=["\']([^"\']+)["\']',
        raw_html,
    ):
        prop = m.group(2)
        if prop not in og:
            og[prop] = html.unescape(m.group(1))

    # 2. Xác định Handle (@username)
    raw_title = og.get("og:title", "")
    final_path = getattr(getattr(resp, "url", None), "path", None) or parsed_url.path
    handle = "user"
    user_match = re.search(r"\(@([a-zA-Z0-9._]+)\)", raw_title)
    if user_match:
        handle = user_match.group(1).strip()
    else:
        path_match = re.search(r"/@([a-zA-Z0-9._]+)", f"{final_path} {parsed_url.path}")
        if path_match:
            handle = path_match.group(1).strip()

    # 3. Lấy nội dung chữ bài viết
    caption = og.get("og:description") or og.get("description") or ""
    caption = unicodedata.normalize("NFC", caption).strip()

    # Bỏ hậu tố trang chia sẻ nếu có
    caption = re.sub(r"\s*•\s*Threads,\s*Say more\s*$", "", caption, flags=re.IGNORECASE)

    warnings: list[str] = []
    if not caption:
        warnings.append("Bài viết không có chữ hoặc chỉ chứa hình ảnh.")

    # 4. Trích xuất ảnh gốc từ CDN
    media_urls: list[str] = []
    og_img = og.get("og:image")
    if og_img:
        media_urls.append(og_img)

    cdn_pattern = re.compile(r'https://[^"\',\s\\]+(?:cdninstagram|fbcdn)[^"\',\s\\]+')
    for script in re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', raw_html, re.DOTALL
    ):
        if "carousel_media" in script or "image_versions2" in script:
            for img_m in cdn_pattern.finditer(script):
                u = img_m.group(0).replace("\\/", "/")
                if u not in media_urls and "640x640" not in u and "profile" not in u:
                    media_urls.append(u)

    post = ParsedPost(
        handle=handle,
        age="vừa xong",
        text=caption,
    )

    # 5. Trích xuất bình luận từ dữ liệu JSON nhúng trong HTML của Threads
    comments = _extract_comments_from_html(raw_html, handle, caption)

    # Nếu không có bình luận qua JSON, kiểm tra bài đối thoại (Chồng: / Vợ: ...)
    if not comments:
        lines = [line.strip() for line in caption.splitlines() if line.strip()]
        dialogue_lines: list[tuple[str, str]] = []

        for line in lines:
            match_speaker = re.match(r"^[-–—]?\s*([^:：]{1,20})[:：]\s*(.+)$", line)
            if match_speaker:
                spk = match_speaker.group(1).strip()
                msg = match_speaker.group(2).strip()
                dialogue_lines.append((spk, msg))

        # Nếu bài viết là một chuỗi đối thoại từ 2 câu trở lên, tự tạo bình luận cho từng lượt
        if len(dialogue_lines) >= 2:
            post.handle = dialogue_lines[0][0]
            post.text = dialogue_lines[0][1]
            for idx, (spk, msg) in enumerate(dialogue_lines[1:], 1):
                comments.append(
                    ParsedComment(
                        id=f"c{idx}",
                        handle=spk,
                        age="vừa xong",
                        text=msg,
                        same_author=(spk == post.handle),
                        picked=True,
                    )
                )

    # Nếu vẫn không có bình luận, thêm gợi ý người dùng dán chữ cả trang
    if not comments:
        warnings.append("Copy cả trang bài (Ctrl+A) rồi dán vào đây để thêm bình luận")

    return ParseResult(
        guess="threads_text",
        source_url=clean_url,
        post=post,
        comments=comments,
        hints=[],
        warnings=warnings,
    )


def _extract_comments_from_html(
    raw_html: str, main_handle: str, main_text: str
) -> list[ParsedComment]:
    """Trích xuất bình luận công khai từ các thẻ script application/json trong HTML của Threads."""
    import json
    from typing import Any

    comments: list[ParsedComment] = []
    seen_texts: set[str] = set()
    norm_main = unicodedata.normalize("NFC", main_text).strip().casefold()
    if norm_main:
        seen_texts.add(norm_main)

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            user = node.get("user")
            caption = node.get("caption")
            username = None
            text = None
            likes = 0

            if isinstance(user, dict):
                username = user.get("username")
            elif isinstance(node.get("username"), str):
                username = node.get("username")

            if isinstance(caption, dict):
                text = caption.get("text")
            elif isinstance(caption, str):
                text = caption
            elif isinstance(node.get("text"), str) and username:
                text = node.get("text")

            if isinstance(node.get("like_count"), int):
                likes = node.get("like_count")

            if username and text and isinstance(text, str):
                clean_text = unicodedata.normalize("NFC", text).strip()
                norm_text = clean_text.casefold()
                if clean_text and norm_text not in seen_texts:
                    seen_texts.add(norm_text)
                    cid = f"c{len(comments) + 1}"
                    clean_user = str(username).lstrip("@")
                    comments.append(
                        ParsedComment(
                            id=cid,
                            handle=clean_user,
                            age="vừa xong",
                            text=clean_text,
                            likes=likes,
                            same_author=(
                                clean_user.casefold() == main_handle.lstrip("@").casefold()
                            ),
                            picked=False,
                        )
                    )

            for v in node.values():
                if isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    _walk(item)

    for script in re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', raw_html, re.DOTALL
    ):
        if any(k in script for k in ("reply", "caption", "like_count", "direct_replies", "text")):
            try:
                data = json.loads(script)
                _walk(data)
            except Exception:
                continue

    return comments
