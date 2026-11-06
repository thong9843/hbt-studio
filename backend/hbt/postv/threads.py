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
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    try:
        parsed = urlparse(s)
        return parsed.netloc.lower() in THREADS_HOSTS and bool(
            re.search(r"/(?:post|t)/[A-Za-z0-9_-]+", parsed.path)
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
    handle = "user"
    user_match = re.search(r"\(@([a-zA-Z0-9._]+)\)", raw_title)
    if user_match:
        handle = user_match.group(1).strip()
    else:
        path_match = re.search(r"/@([a-zA-Z0-9._]+)", parsed_url.path)
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

    # 5. Phân tách đối thoại nếu bài viết có dạng chat (Chồng: / Vợ: / Nam: / Nữ: ...)
    comments: list[ParsedComment] = []
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
        # Câu đầu giữ làm post text
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

    return ParseResult(
        guess="threads_text",
        source_url=clean_url,
        post=post,
        comments=comments,
        hints=[],
        warnings=warnings,
    )
