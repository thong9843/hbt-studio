"""Thư viện Meme & Sticker phông xanh (Green Screen Memes) cho PostV.

Kết nối với kho greenscreenmemes.com qua REST API công khai và quản lý bộ nhớ đệm
cục bộ tại `library/memes/index.json`.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from hbt.pipeline.ffutil import FFmpegError, probe
from hbt.storage import BadRequest, NotFound, Unprocessable

logger = logging.getLogger("hbt.postv.memes")

GREENSCREEN_API = "https://greenscreenmemes.com/wp-json/wp/v2/posts"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


class MemeEntry(BaseModel):
    id: str  # mã id duy nhất (slug hoặc post_id)
    title: str = Field(min_length=1)
    file: str = ""  # tên file cục bộ trong library/memes/ (vd: 68061.mp4)
    video_url: str = ""  # link CDN gốc
    poster_url: str = ""  # link ảnh bìa webp
    duration: float = 0.0  # thời lượng tính bằng giây
    width: int = 0
    height: int = 0
    downloaded: bool = False


class MemeLibrary:
    """Quản lý danh mục meme cục bộ và tìm kiếm trực tuyến."""

    def __init__(self, library_dir: str | Path) -> None:
        self.root = Path(library_dir).resolve() / "memes"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_file = self.root / "index.json"
        if not self.index_file.is_file():
            self._save_index([])

    def _read_index(self) -> list[MemeEntry]:
        if not self.index_file.is_file():
            return []
        try:
            raw = json.loads(self.index_file.read_text(encoding="utf-8"))
            return [MemeEntry.model_validate(item) for item in raw]
        except (OSError, ValueError):
            return []

    def _save_index(self, entries: list[MemeEntry]) -> None:
        # Ghi an toàn qua file tạm rồi replace
        payload = [e.model_dump() for e in entries]
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp = self.root / f".tmp_{os.getpid()}_{id(self)}.json"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.index_file)

    def list(self) -> list[MemeEntry]:
        """Danh sách meme đã tải về máy cục bộ."""
        entries = self._read_index()
        # Xác thực file có tồn tại trên đĩa thật
        valid = []
        for e in entries:
            if e.file and (self.root / e.file).is_file():
                e.downloaded = True
                valid.append(e)
        return valid

    def find(self, meme_id: str) -> tuple[MemeEntry, Path]:
        """Tìm meme theo ID. Trả về (MemeEntry, đường dẫn file)."""
        entries = self._read_index()
        for e in entries:
            if e.id == meme_id:
                path = self.root / e.file
                if path.is_file():
                    e.downloaded = True
                    return e, path
        raise NotFound(f"Không tìm thấy meme '{meme_id}' trong thư viện")

    async def search_online(self, query: str = "", count: int = 12) -> list[MemeEntry]:
        """Tìm kiếm meme từ greenscreenmemes.com qua REST API công khai."""
        local_entries = {e.id: e for e in self.list()}
        params: dict[str, Any] = {"per_page": min(max(count, 1), 24)}
        if query.strip():
            params["search"] = query.strip()

        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
                resp = await client.get(GREENSCREEN_API, params=params)
                if resp.status_code != 200:
                    logger.warning("greenscreenmemes.com trả về mã lỗi: %d", resp.status_code)
                    return list(local_entries.values())

                posts = resp.json()
                if not isinstance(posts, list):
                    return list(local_entries.values())

                async def fetch_item_details(p: dict) -> MemeEntry | None:
                    post_id = str(p.get("id", ""))
                    if post_id in local_entries:
                        return local_entries[post_id]

                    raw_title = p.get("title", {}).get("rendered", "")
                    clean_title = html.unescape(raw_title).replace("Meme Green Screen", "").strip()
                    clean_title = unicodedata.normalize("NFC", clean_title)

                    page_link = p.get("link", "")
                    video_url = ""
                    poster_url = ""

                    if page_link:
                        try:
                            page_resp = await client.get(page_link)
                            if page_resp.status_code == 200:
                                v_m = re.search(r'<video[^>]+src="([^"]+\.mp4)"', page_resp.text)
                                p_m = re.search(r'<video[^>]+poster="([^"]+)"', page_resp.text)
                                if v_m:
                                    video_url = v_m.group(1)
                                if p_m:
                                    poster_url = p_m.group(1)
                        except Exception:
                            pass

                    if not video_url:
                        return None

                    return MemeEntry(
                        id=post_id,
                        title=clean_title or post_id,
                        file="",
                        video_url=video_url,
                        poster_url=poster_url,
                        duration=0.0,
                        downloaded=False,
                    )

                tasks = [fetch_item_details(p) for p in posts]
                results = await asyncio.gather(*tasks)
                return [r for r in results if r is not None]

        except Exception as exc:
            logger.warning("Không thể kết nối đến greenscreenmemes.com: %s", exc)
            # Rơi về danh sách cục bộ nếu mất mạng
            if query.strip():
                q_lower = query.strip().lower()
                return [e for e in local_entries.values() if q_lower in e.title.lower()]
            return list(local_entries.values())

    def download(self, meme_id: str, video_url: str, title: str, poster_url: str = "") -> MemeEntry:
        """Tải file video meme MP4 về lưu trong library/memes/ và cập nhật index.json."""
        if not video_url.startswith(("http://", "https://")):
            raise BadRequest("URL video meme không hợp lệ")

        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", meme_id) or "meme"
        filename = f"{safe_id}.mp4"
        target_path = self.root / filename

        # Nếu đã tải sẵn thì trả về luôn
        if target_path.is_file():
            entries = self._read_index()
            for e in entries:
                if e.id == meme_id:
                    e.downloaded = True
                    return e

        # Tải video
        try:
            with httpx.Client(timeout=30.0, headers=HEADERS, follow_redirects=True) as client:
                resp = client.get(video_url)
                if resp.status_code != 200:
                    raise Unprocessable(
                        f"Không thể tải video từ {video_url} (HTTP {resp.status_code})"
                    )
                target_path.write_bytes(resp.content)
        except httpx.RequestError as exc:
            raise Unprocessable(f"Lỗi kết nối khi tải meme: {exc}") from exc

        # Đo thông số bằng ffprobe
        width, height, duration = 1080, 1920, 3.0
        try:
            info = probe(target_path)
            duration = float(info.get("format", {}).get("duration", 3.0))
            vs = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
            if vs:
                width = int(vs.get("width", 1080))
                height = int(vs.get("height", 1920))
        except (FFmpegError, ValueError, KeyError):
            pass

        entry = MemeEntry(
            id=meme_id,
            title=unicodedata.normalize("NFC", title.strip()),
            file=filename,
            video_url=video_url,
            poster_url=poster_url,
            duration=round(duration, 2),
            width=width,
            height=height,
            downloaded=True,
        )

        entries = [e for e in self._read_index() if e.id != meme_id]
        entries.append(entry)
        self._save_index(entries)
        return entry

    def delete(self, meme_id: str) -> None:
        """Xoá một meme khỏi thư viện cục bộ."""
        entries = self._read_index()
        kept = []
        for e in entries:
            if e.id == meme_id:
                file_path = self.root / e.file
                file_path.unlink(missing_ok=True)
            else:
                kept.append(e)
        self._save_index(kept)
