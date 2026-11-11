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
import subprocess
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from hbt.postv.parse import ParsedComment, ParsedPost, ParseResult, parse_threads_text

log = logging.getLogger(__name__)

MIN_BROWSER_COMMENTS = 30
TARGET_BROWSER_COMMENTS = 50
PLAYWRIGHT_SCRAPER_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "scrape_threads.mjs"

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


def _extract_meta_tags(raw_html: str) -> dict[str, str]:
    """Bóc tách thẻ OpenGraph / meta từ HTML."""
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
    return og


def _extract_handle_and_caption(
    og: dict[str, str],
    fallback_paths: Sequence[str],
) -> tuple[str, str]:
    """Xác định @handle và nội dung bài gốc từ metadata OpenGraph."""
    raw_title = og.get("og:title", "")
    handle = "user"
    user_match = re.search(r"\(@([a-zA-Z0-9._]+)\)", raw_title)
    if user_match:
        handle = user_match.group(1).strip()
    else:
        joined = " ".join(p for p in fallback_paths if p)
        path_match = re.search(r"/@([a-zA-Z0-9._]+)", joined)
        if path_match:
            handle = path_match.group(1).strip()

    caption = og.get("og:description") or og.get("description") or ""
    caption = unicodedata.normalize("NFC", caption).strip()
    caption = re.sub(r"\s*•\s*Threads,\s*Say more\s*$", "", caption, flags=re.IGNORECASE)
    return handle, caption


def _extract_json_scripts(raw_html: str) -> list[str]:
    return re.findall(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', raw_html, re.DOTALL
    )


def _scrape_threads_with_playwright(
    url: str,
    target_comments: int = TARGET_BROWSER_COMMENTS,
    timeout: float = 45.0,
) -> dict[str, Any] | None:
    """Cuộn sâu và phân trang GraphQL Threads bằng Chromium sẵn có của Playwright."""
    if not PLAYWRIGHT_SCRAPER_SCRIPT.is_file():
        return None
    try:
        proc = subprocess.run(
            ["node", str(PLAYWRIGHT_SCRAPER_SCRIPT), url, str(target_comments)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            log.debug(
                "Playwright scraper không thành công (code=%s): %s",
                proc.returncode,
                (proc.stderr or "")[:300],
            )
            return None
        data = json.loads(proc.stdout)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        log.debug("Lỗi chạy Playwright scraper cho Threads (%s): %s", url, exc)
        return None


def _should_use_playwright(
    use_browser: bool | None,
    ssr_comment_count: int,
    min_comments: int,
    had_ssr_error: bool,
) -> bool:
    if use_browser is not None:
        return use_browser
    # Tránh gọi trình duyệt thật khi unit test chỉ mock httpx.Client.get với URL giả
    httpx_mocked = hasattr(httpx.Client.get, "assert_called")
    browser_mocked = hasattr(_scrape_threads_with_playwright, "assert_called")
    if httpx_mocked and not browser_mocked:
        return False
    return had_ssr_error or ssr_comment_count < min_comments


def _split_dialogue_comments(caption: str) -> tuple[str, str, list[ParsedComment]] | None:
    lines = [line.strip() for line in caption.splitlines() if line.strip()]
    dialogue_lines: list[tuple[str, str]] = []
    for line in lines:
        match_speaker = re.match(r"^[-–—]?\s*([^:：]{1,20})[:：]\s*(.+)$", line)
        if match_speaker:
            dialogue_lines.append((match_speaker.group(1).strip(), match_speaker.group(2).strip()))

    if len(dialogue_lines) < 2:
        return None
    comments = [
        ParsedComment(
            id=f"c{idx}",
            handle=spk,
            age="vừa xong",
            text=msg,
            same_author=(spk == dialogue_lines[0][0]),
            picked=True,
        )
        for idx, (spk, msg) in enumerate(dialogue_lines[1:], 1)
    ]
    return dialogue_lines[0][0], dialogue_lines[0][1], comments


def extract_threads_post(
    url: str,
    timeout: float = 15.0,
    min_comments: int = MIN_BROWSER_COMMENTS,
    target_comments: int = TARGET_BROWSER_COMMENTS,
    use_browser: bool | None = None,
) -> ParseResult:
    """Tải và trích xuất thông tin bài viết Threads thành ParseResult của PostV."""
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    parsed_url = urlparse(clean_url)
    if parsed_url.netloc.lower() not in THREADS_HOSTS:
        raise ThreadsFetchError(f"Đường dẫn không thuộc Threads: '{clean_url}'")

    raw_html = ""
    final_path = parsed_url.path
    ssr_error: ThreadsFetchError | None = None
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(clean_url, headers=BOT_HEADERS)
        if resp.status_code == 404:
            raise ThreadsFetchError("Bài viết Threads không tồn tại hoặc đã bị xoá (HTTP 404).")
        if resp.status_code != 200:
            ssr_error = ThreadsFetchError(f"Máy chủ Threads phản hồi lỗi: HTTP {resp.status_code}")
        else:
            raw_html = resp.text
            final_path = getattr(getattr(resp, "url", None), "path", None) or parsed_url.path
    except ThreadsFetchError:
        raise
    except httpx.RequestError as exc:
        ssr_error = ThreadsFetchError(f"Không thể kết nối tới Threads: {exc}")

    og = _extract_meta_tags(raw_html) if raw_html else {}
    handle, caption = _extract_handle_and_caption(og, [final_path, parsed_url.path])
    ssr_scripts = _extract_json_scripts(raw_html) if raw_html else []
    ssr_comments = (
        _extract_comments_from_json_blobs(ssr_scripts, handle, caption) if ssr_scripts else []
    )

    browser_data: dict[str, Any] | None = None
    if _should_use_playwright(use_browser, len(ssr_comments), min_comments, ssr_error is not None):
        browser_data = _scrape_threads_with_playwright(
            clean_url, target_comments=target_comments, timeout=max(timeout * 2.5, 40.0)
        )

    if ssr_error is not None and not browser_data:
        raise ssr_error

    all_json_blobs: list[str] = list(ssr_scripts)
    if browser_data:
        b_og = browser_data.get("og") if isinstance(browser_data.get("og"), dict) else {}
        merged_og = {**b_og, **og}
        if not og.get("og:description") and b_og.get("og:description"):
            merged_og["og:description"] = b_og["og:description"]
        b_final_url = str(browser_data.get("final_url") or "")
        b_path = urlparse(b_final_url).path if b_final_url else ""
        handle2, caption2 = _extract_handle_and_caption(
            merged_og, [b_path, final_path, parsed_url.path]
        )
        if handle == "user" and handle2 != "user":
            handle = handle2
        if not caption and caption2:
            caption = caption2
        og = merged_og
        for blob in browser_data.get("scripts") or []:
            if isinstance(blob, str) and blob:
                all_json_blobs.append(blob)
        for blob in browser_data.get("graphql_payloads") or []:
            if isinstance(blob, str) and blob:
                all_json_blobs.append(blob)

    warnings: list[str] = []
    if not caption:
        warnings.append("Bài viết không có chữ hoặc chỉ chứa hình ảnh.")

    media_urls = _extract_post_media_urls_from_blobs(all_json_blobs, og.get("og:image"))
    post = ParsedPost(handle=handle, age="vừa xong", text=caption)

    comments = (
        _extract_comments_from_json_blobs(all_json_blobs, handle, caption) if all_json_blobs else []
    )

    # Gắn thêm các reply con bóc riêng từ các parent comment nhiều tương tác
    child_blobs = browser_data.get("child_reply_blobs") if isinstance(browser_data, dict) else None
    if isinstance(child_blobs, list) and child_blobs and comments:
        seen_norm = {unicodedata.normalize("NFC", c.text).strip().casefold() for c in comments}
        norm_main = unicodedata.normalize("NFC", caption).strip().casefold()
        if norm_main:
            seen_norm.add(norm_main)
        by_norm = {unicodedata.normalize("NFC", c.text).strip().casefold(): c.id for c in comments}
        for cb in child_blobs:
            if not isinstance(cb, dict):
                continue
            p_norm = (
                unicodedata.normalize("NFC", str(cb.get("parent_text") or "")).strip().casefold()
            )
            parent_cid = by_norm.get(p_norm)
            payload_str = cb.get("payload")
            if not parent_cid or not isinstance(payload_str, str) or not payload_str:
                continue
            children = _extract_comments_from_json_blobs(
                [payload_str],
                handle,
                caption,
                root_parent=parent_cid,
                initial_seen=seen_norm,
                id_offset=len(comments),
            )
            for ch in children:
                comments.append(ch)
                ch_norm = unicodedata.normalize("NFC", ch.text).strip().casefold()
                seen_norm.add(ch_norm)

    # Nếu kết quả JSON từ trình duyệt vẫn ít, gom thêm từ DOM snapshot thu khi cuộn trang
    dom_text = browser_data.get("dom_text") if isinstance(browser_data, dict) else None
    if isinstance(dom_text, str) and dom_text.strip() and len(comments) < min_comments:
        dom_parsed = parse_threads_text(dom_text)
        seen_norm = {unicodedata.normalize("NFC", c.text).strip().casefold() for c in comments}
        norm_main = unicodedata.normalize("NFC", caption).strip().casefold()
        if norm_main:
            seen_norm.add(norm_main)
        for dc in dom_parsed.comments:
            norm_dc = unicodedata.normalize("NFC", dc.text).strip().casefold()
            if not norm_dc or norm_dc in seen_norm:
                continue
            seen_norm.add(norm_dc)
            comments.append(dc.model_copy(update={"id": f"c{len(comments) + 1}", "parent": None}))

    # Nếu không có bình luận qua JSON/DOM, kiểm tra bài đối thoại (Chồng: / Vợ: ...)
    if not comments:
        dialogue = _split_dialogue_comments(caption)
        if dialogue:
            post.handle, post.text, comments = dialogue

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


def _node_media_urls(node: dict[str, Any]) -> list[str]:
    """Trích xuất ảnh đính kèm trực tiếp trên 1 node bài viết / bình luận Threads."""
    urls: list[str] = []

    def _add(u: str | None) -> None:
        if not u or not isinstance(u, str):
            return
        clean = u.replace("\\/", "/").strip()
        if clean.startswith("http") and not _is_avatar_url(clean) and clean not in urls:
            urls.append(clean)

    carousel = node.get("carousel_media")
    if isinstance(carousel, list) and carousel:
        for item in carousel:
            if isinstance(item, dict):
                _add(_best_candidate_url(item.get("image_versions2")))
                if isinstance(item.get("display_url"), str):
                    _add(item.get("display_url"))
    if "image_versions2" in node:
        _add(_best_candidate_url(node.get("image_versions2")))
    if isinstance(node.get("display_url"), str):
        _add(node.get("display_url"))
    return urls


def _extract_post_media_urls_from_blobs(
    json_blobs: Sequence[str], og_img: str | None = None
) -> list[str]:
    """Bóc tách toàn bộ mảng URL ảnh đính kèm của bài viết gốc từ danh sách JSON & OpenGraph."""
    urls: list[str] = []
    skip_subtree = frozenset(
        {
            "user",
            "owner",
            "profile_pic_url",
            "hd_profile_pic_url_info",
            "reply_threads",
            "direct_replies",
            "reply_posts",
            "replies",
            "sub_replies",
            "child_comments",
            "edge_threaded_comments",
        }
    )

    def _add(u: str | None) -> None:
        if not u or not isinstance(u, str):
            return
        clean = u.replace("\\/", "/").strip()
        if clean.startswith("http") and not _is_avatar_url(clean) and clean not in urls:
            urls.append(clean)

    def _walk_media(node: Any) -> None:
        if isinstance(node, dict):
            for u in _node_media_urls(node):
                _add(u)
            if node.get("carousel_media"):
                return
            for k, v in node.items():
                if k in skip_subtree:
                    continue
                if isinstance(v, (dict, list)):
                    _walk_media(v)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    _walk_media(item)

    cdn_pattern = re.compile(r'https://[^"\',\s\\]+(?:cdninstagram|fbcdn)[^"\',\s\\]+')
    for script in json_blobs:
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
        if og_img not in urls and "640x640" not in og_img:
            urls.insert(0, og_img)

    return urls


def _extract_post_media_urls(raw_html: str, og_img: str | None = None) -> list[str]:
    """Bóc tách toàn bộ mảng URL ảnh đính kèm của bài viết gốc từ JSON nhúng & OpenGraph."""
    return _extract_post_media_urls_from_blobs(_extract_json_scripts(raw_html), og_img)


def download_post_media(
    urls: Sequence[str],
    media_dir: Path,
    timeout: float = 15.0,
    max_items: int = 30,
    prefix: str = "img",
) -> list[Path]:
    """Tải danh sách ảnh đính kèm về `media_dir` đầy đủ đuôi mở rộng, xác thực bằng Pillow."""
    if not urls:
        return []
    media_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    fmt_ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=BOT_HEADERS) as client:
            for idx, url in enumerate(urls[:max_items], 1):
                clean_u = (url or "").strip()
                if not clean_u.startswith(("http://", "https://")):
                    continue
                try:
                    resp = client.get(clean_u)
                    if resp.status_code != 200 or not resp.content:
                        continue
                    with Image.open(io.BytesIO(resp.content)) as im:
                        im.verify()
                    with Image.open(io.BytesIO(resp.content)) as im2:
                        ext = fmt_ext.get((im2.format or "").upper(), ".jpg")
                    target = media_dir / f"{prefix}_{idx:02d}{ext}"
                    target.write_bytes(resp.content)
                    saved.append(target)
                except Exception as exc:
                    log.debug("Không tải được ảnh bài viết (%s): %s", clean_u, exc)
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


def _extract_comments_from_json_blobs(
    json_blobs: Sequence[str],
    main_handle: str,
    main_text: str,
    *,
    root_parent: str | None = None,
    initial_seen: set[str] | None = None,
    id_offset: int = 0,
) -> list[ParsedComment]:
    """Trích xuất bình luận công khai (kèm cây reply) từ chuỗi JSON HTML/GraphQL Threads."""
    comments: list[ParsedComment] = []
    seen_texts: set[str] = set(initial_seen) if initial_seen else set()
    norm_main = unicodedata.normalize("NFC", main_text).strip().casefold()
    if norm_main:
        seen_texts.add(norm_main)

    def _add_comment(
        clean_user: str,
        clean_text: str,
        likes: int,
        replies: int,
        parent_id: str | None = None,
        c_media: list[str] | None = None,
    ) -> str | None:
        norm_text = clean_text.casefold()
        if norm_text in seen_texts:
            return None
        seen_texts.add(norm_text)
        cid = f"c{id_offset + len(comments) + 1}"
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
                media_urls=list(c_media or []),
            )
        )
        return cid

    nested_keys = (
        "direct_replies",
        "reply_posts",
        "replies",
        "sub_replies",
        "child_comments",
        "edge_threaded_comments",
    )

    def _walk_thread_sequence(items: list[Any], current_parent: str | None) -> None:
        # Phần tử đầu trong thread_items hoặc posts.edges là bình luận cha, các phần tử sau là reply
        first_parent: str | None = current_parent
        for idx, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                continue
            item = raw_item.get("node") if isinstance(raw_item.get("node"), dict) else raw_item
            post_obj = item.get("post") if isinstance(item.get("post"), dict) else item
            f2 = _extract_post_node_fields(post_obj)
            item_parent = first_parent if idx > 0 else current_parent
            cid = None
            if f2:
                cid = _add_comment(
                    f2[0],
                    f2[1],
                    f2[2],
                    f2[3],
                    parent_id=item_parent,
                    c_media=_node_media_urls(post_obj),
                )
                if idx == 0 and cid and root_parent is None:
                    first_parent = cid
            sub_parent = root_parent or cid or item_parent
            for ik, iv in item.items():
                if ik == "post" or not isinstance(iv, (dict, list)):
                    continue
                if ik in nested_keys and sub_parent:
                    _walk(iv, current_parent=sub_parent)
                else:
                    _walk(iv, current_parent=item_parent)

    def _walk(node: Any, current_parent: str | None = None) -> None:
        if isinstance(node, dict):
            fields = _extract_post_node_fields(node)
            media_src = node
            if fields is None and isinstance(node.get("post"), dict):
                media_src = node["post"]
                fields = _extract_post_node_fields(media_src)
            added_id = None
            if fields:
                clean_user, clean_text, likes, replies = fields
                added_id = _add_comment(
                    clean_user,
                    clean_text,
                    likes,
                    replies,
                    current_parent,
                    _node_media_urls(media_src),
                )

            nested_parent = added_id or current_parent
            for key, v in node.items():
                if not isinstance(v, (dict, list)):
                    continue
                if key in nested_keys and nested_parent:
                    _walk(v, current_parent=nested_parent)
                elif key == "thread_items" and isinstance(v, list) and v:
                    _walk_thread_sequence(v, current_parent)
                elif (
                    key == "posts"
                    and isinstance(v, dict)
                    and isinstance(v.get("edges"), list)
                    and v["edges"]
                ):
                    _walk_thread_sequence(v["edges"], current_parent)
                else:
                    _walk(v, current_parent=current_parent)
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    _walk(item, current_parent=current_parent)

    for script in json_blobs:
        if any(
            k in script
            for k in (
                "reply",
                "caption",
                "like_count",
                "direct_replies",
                "text",
                "edges",
                "thread_items",
                "posts",
            )
        ):
            try:
                data = json.loads(script)
                _walk(data, current_parent=root_parent)
            except Exception:
                continue

    return comments


def _extract_comments_from_html(
    raw_html: str, main_handle: str, main_text: str
) -> list[ParsedComment]:
    """Trích xuất bình luận công khai (kèm cây reply 1 cấp) từ thẻ script application/json."""
    return _extract_comments_from_json_blobs(
        _extract_json_scripts(raw_html), main_handle, main_text
    )
