"""HBT Studio - Trích xuất dữ liệu bài viết Threads trực tiếp qua URL.

Sử dụng giao thức Meta Bot SSR (facebookexternalhit) để lấy dữ liệu nhanh (< 1.5s),
không tốn RAM, không cần mở trình duyệt và không cần token API chính thức.
"""

from __future__ import annotations

import html
import io
import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from hbt.postv.parse import ParsedComment, ParsedPost, ParseResult

log = logging.getLogger(__name__)

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

    # 4. Trích xuất toàn bộ mảng ảnh/media đính kèm từ bài gốc Threads
    media_urls = _extract_post_media_urls(raw_html, og.get("og:image"))

    post = ParsedPost(
        handle=handle,
        age="vừa xong",
        text=caption,
    )

    # 5. Trích xuất bình luận (kèm cấu trúc reply) từ JSON nhúng trong HTML Threads
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
        media_urls=media_urls,
        hints=[],
        warnings=warnings,
    )


def _is_avatar_url(url: str) -> bool:
    low = url.lower()
    return "profile" in low or "t51.2885-19" in low or "s150x150" in low or "150x150" in low


def _best_candidate_url(image_versions2: Any) -> str | None:
    if not isinstance(image_versions2, dict):
        return None
    cands = image_versions2.get("candidates")
    if not isinstance(cands, list) or not cands:
        return None
    best_url: str | None = None
    best_area = -1
    for item in cands:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith("http") or _is_avatar_url(url):
            continue
        w = int(item.get("width") or 0)
        h = int(item.get("height") or 0)
        area = w * h
        if area > best_area or best_url is None:
            best_area = area
            best_url = url.replace("\\/", "/")
    return best_url


def _extract_post_media_urls(raw_html: str, og_img: str | None = None) -> list[str]:
    """Bóc tách toàn bộ mảng URL ảnh đính kèm của bài viết gốc từ JSON nhúng & OpenGraph."""
    urls: list[str] = []

    def _add(u: str | None) -> None:
        if not u or not isinstance(u, str):
            return
        clean = u.replace("\\/", "/").strip()
        if clean.startswith("http") and not _is_avatar_url(clean) and clean not in urls:
            urls.append(clean)

    def _walk_media(node: Any) -> None:
        if isinstance(node, dict):
            carousel = node.get("carousel_media")
            if isinstance(carousel, list) and carousel:
                for item in carousel:
                    if isinstance(item, dict):
                        _add(_best_candidate_url(item.get("image_versions2")))
                        if isinstance(item.get("display_url"), str):
                            _add(item.get("display_url"))
                return

            if "image_versions2" in node:
                _add(_best_candidate_url(node.get("image_versions2")))

            for k, v in node.items():
                if k in ("user", "owner", "profile_pic_url", "hd_profile_pic_url_info"):
                    continue
                if isinstance(v, (dict, list)):
                    _walk_media(v)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    _walk_media(item)

    cdn_pattern = re.compile(r'https://[^"\',\s\\]+(?:cdninstagram|fbcdn)[^"\',\s\\]+')
    for script in re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', raw_html, re.DOTALL
    ):
        if any(k in script for k in ("carousel_media", "image_versions2", "display_url")):
            try:
                _walk_media(json.loads(script))
            except Exception:
                for img_m in cdn_pattern.finditer(script):
                    u = img_m.group(0).replace("\\/", "/")
                    if "640x640" not in u:
                        _add(u)

    if not urls and og_img:
        _add(og_img)
    elif og_img and not _is_avatar_url(og_img):
        # Đưa og:image vào đầu nếu hợp lệ mà chưa có ảnh trùng
        if og_img not in urls and "640x640" not in og_img:
            urls.insert(0, og_img)

    return urls


def download_post_media(
    urls: Sequence[str],
    media_dir: Path,
    timeout: float = 15.0,
    max_items: int = 8,
) -> list[Path]:
    """Tải danh sách ảnh đính kèm bài gốc về `media_dir` và xác thực bằng Pillow."""
    if not urls:
        return []
    media_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    fmt_ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=BOT_HEADERS) as client:
            for idx, url in enumerate(urls[:max_items], 1):
                try:
                    resp = client.get(url)
                    if resp.status_code != 200 or not resp.content:
                        continue
                    with Image.open(io.BytesIO(resp.content)) as im:
                        im.verify()
                    with Image.open(io.BytesIO(resp.content)) as im2:
                        ext = fmt_ext.get((im2.format or "").upper(), ".jpg")
                    target = media_dir / f"img_{idx:02d}{ext}"
                    target.write_bytes(resp.content)
                    saved.append(target)
                except Exception as exc:
                    log.debug("Không tải được ảnh bài viết (%s): %s", url, exc)
                    continue
    except Exception as exc:
        log.warning("Lỗi tải media bài viết: %s", exc)
    return saved


def _extract_post_node_fields(node: dict[str, Any]) -> tuple[str, str, int, int] | None:
    """Trích xuất (username, clean_text, likes, reply_count) từ 1 node JSON của Threads."""
    user = node.get("user")
    caption = node.get("caption")
    username = None
    text = None

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

    if not username or not isinstance(text, str):
        return None
    clean_text = unicodedata.normalize("NFC", text).strip()
    if not clean_text:
        return None

    likes = int(node.get("like_count") or 0) if isinstance(node.get("like_count"), int) else 0
    rep_info = node.get("text_post_app_info") or {}
    replies = 0
    if isinstance(rep_info, dict) and isinstance(rep_info.get("direct_reply_count"), int):
        replies = rep_info["direct_reply_count"]
    elif isinstance(node.get("reply_count"), int):
        replies = node["reply_count"]

    return str(username).lstrip("@"), clean_text, likes, replies


def _extract_comments_from_html(
    raw_html: str, main_handle: str, main_text: str
) -> list[ParsedComment]:
    """Trích xuất bình luận công khai (kèm cây reply 1 cấp) từ thẻ script application/json."""
    comments: list[ParsedComment] = []
    seen_texts: set[str] = set()
    norm_main = unicodedata.normalize("NFC", main_text).strip().casefold()
    if norm_main:
        seen_texts.add(norm_main)

    def _add_comment(
        clean_user: str,
        clean_text: str,
        likes: int,
        replies: int,
        parent_id: str | None = None,
    ) -> str | None:
        norm_text = clean_text.casefold()
        if norm_text in seen_texts:
            return None
        seen_texts.add(norm_text)
        cid = f"c{len(comments) + 1}"
        comments.append(
            ParsedComment(
                id=cid,
                handle=clean_user,
                age="vừa xong",
                text=clean_text,
                likes=likes,
                replies=replies,
                parent=parent_id,
                same_author=(clean_user.casefold() == main_handle.lstrip("@").casefold()),
                picked=False,
            )
        )
        return cid

    def _walk(node: Any, current_parent: str | None = None) -> None:
        if isinstance(node, dict):
            fields = _extract_post_node_fields(node)
            added_id = None
            if fields:
                clean_user, clean_text, likes, replies = fields
                added_id = _add_comment(clean_user, clean_text, likes, replies, current_parent)

            # Kiểm tra các chuỗi lồng (thread_items / direct_replies)
            nested_parent = added_id or current_parent
            for key, v in node.items():
                if not isinstance(v, (dict, list)):
                    continue
                if key in ("direct_replies", "reply_posts") and nested_parent:
                    _walk(v, current_parent=nested_parent)
                elif key == "thread_items" and isinstance(v, list) and v:
                    # Trong thread_items: phần tử đầu là cha, phần tử sau là reply nối tiếp
                    first_parent: str | None = current_parent
                    for idx, item in enumerate(v):
                        if not isinstance(item, dict):
                            continue
                        post_obj = item.get("post") if isinstance(item.get("post"), dict) else item
                        f2 = _extract_post_node_fields(post_obj)
                        if f2:
                            cid = _add_comment(
                                f2[0],
                                f2[1],
                                f2[2],
                                f2[3],
                                parent_id=first_parent if idx > 0 else current_parent,
                            )
                            if idx == 0 and cid:
                                first_parent = cid
                        else:
                            _walk(item, current_parent=first_parent if idx > 0 else current_parent)
                else:
                    _walk(v, current_parent=current_parent)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    _walk(item, current_parent=current_parent)

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
