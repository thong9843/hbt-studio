"""Thư viện Meme & Sticker phông xanh cục bộ (library/memes/) cho PostV."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import random
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
MEME_VIDEO_EXTS = frozenset({".mp4", ".mov", ".webm"})
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

FILENAME_TAG_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gian", ("angry", "gian", "mad", "rage", "trump")),
    ("cuoi", ("laugh", "cuoi", "haha", "hyena", "godzilla", "goat")),
    ("khoc", ("cry", "crying", "sad", "khoc", "ronaldo")),
    ("soc", ("shocked", "ishowspeed", "kai-cenat", "soc")),
    ("nghi", ("confused", "nick-young", "tai-lung", "nghi")),
    ("ngai", ("awkward", "side-eye", "ngai")),
    ("bat_luc", ("disappointed", "bat_luc", "fail")),
    ("yeu", ("love", "heart", "yeu")),
    ("ok", ("nice", "goat", "ok")),
)


def resolve_memes_dir(library_dir: str | Path) -> Path:
    """Trả về đường dẫn tuyệt đối thư mục meme cục bộ (`library/memes/` hoặc `library/meme/`)."""
    base = Path(library_dir).resolve()
    primary = base / "memes"
    alt = base / "meme"
    if primary.is_dir():
        has_videos = any(
            p.is_file() and p.suffix.lower() in MEME_VIDEO_EXTS for p in primary.iterdir()
        )
        if has_videos or not alt.is_dir():
            return primary
    if alt.is_dir():
        return alt
    return primary


def resolve_meme_file(library_dir: str | Path | None, meme_id: str | None) -> Path | None:
    """Tìm file video meme theo `id`, tên file, stem hoặc thư mục con trong library/memes/."""
    if not meme_id or not str(meme_id).strip() or library_dir is None:
        return None
    needle = str(meme_id).strip()
    memes_dir = resolve_memes_dir(library_dir)
    if not memes_dir.is_dir():
        return None

    direct = memes_dir / needle
    if direct.is_file():
        return direct
    for ext in MEME_VIDEO_EXTS:
        candidate = memes_dir / f"{needle}{ext}"
        if candidate.is_file():
            return candidate

    try:
        _, found = MemeLibrary(library_dir).find(needle)
        if found.is_file():
            return found
    except NotFound:
        pass

    stem_needle = Path(needle).stem
    for p in sorted(memes_dir.rglob("*"), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in MEME_VIDEO_EXTS:
            if p.name == needle or p.stem == needle or p.stem == stem_needle:
                return p
    return None


def _infer_tags_from_name(filename: str) -> list[str]:
    low = filename.lower()
    tags = [tag for tag, cues in FILENAME_TAG_CUES if any(cue in low for cue in cues)]
    return tags or ["ok"]


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
    source: str = ""  # URL gốc
    license: str = "chưa rõ"  # giấy phép
    tags: list[str] = Field(default_factory=list)
    emojis: list[str] = Field(default_factory=list)
    start_time: float = 0.0


class MemeLibrary:
    """Quản lý danh mục meme cục bộ (quét trực tiếp library/memes/ & library/meme/)."""

    def __init__(self, library_dir: str | Path) -> None:
        self.root = resolve_memes_dir(library_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_file = self.root / "index.json"
        if not self.index_file.is_file():
            self._save_index([])

    def _read_index(self) -> list[MemeEntry]:
        if not self.index_file.is_file():
            return []
        try:
            raw = json.loads(self.index_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

        items = raw.get("memes", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        entries: list[MemeEntry] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            fname = str(item.get("file") or "").strip()
            if not item.get("id") and fname:
                item = {
                    **item,
                    "id": Path(fname).stem,
                    "title": item.get("title") or Path(fname).stem.replace("-", " "),
                    "downloaded": True,
                }
            try:
                entries.append(MemeEntry.model_validate(item))
            except ValueError:
                continue
        return entries

    def _save_index(self, entries: list[MemeEntry]) -> None:
        # Ghi an toàn qua file tạm rồi replace
        payload = [e.model_dump() for e in entries]
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp = self.root / f".tmp_{os.getpid()}_{id(self)}.json"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.index_file)

    def scan_local(self) -> list[MemeEntry]:
        """Quét toàn bộ file video meme có sẵn trong library/memes/ (hoặc library/meme/)."""
        by_file: dict[str, MemeEntry] = {e.file: e for e in self._read_index() if e.file}
        entries: list[MemeEntry] = []
        if not self.root.is_dir():
            return entries

        for path in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
            if not path.is_file() or path.suffix.lower() not in MEME_VIDEO_EXTS:
                continue
            meta = by_file.get(path.name)
            if meta is not None:
                entry = meta.model_copy(
                    update={
                        "downloaded": True,
                        "tags": meta.tags or _infer_tags_from_name(path.name),
                    }
                )
            else:
                entry = MemeEntry(
                    id=path.stem,
                    title=path.stem.replace("-", " ").replace("_", " ").strip() or path.name,
                    file=path.name,
                    duration=3.5,
                    downloaded=True,
                    source="local",
                    license="local",
                    tags=_infer_tags_from_name(path.name),
                )
            entries.append(entry)
        return entries

    def list(self) -> list[MemeEntry]:
        """Danh sách toàn bộ meme cục bộ đang có trên đĩa."""
        return self.scan_local()

    def search_local(self, query: str = "", count: int = 100) -> list[MemeEntry]:
        """Tìm kiếm thuần cục bộ trong library/memes/, tuyệt đối không gọi API ngoài."""
        all_local = self.scan_local()
        q = query.strip().lower()
        if not q:
            return all_local[: max(count, 1)]
        matched = [
            e
            for e in all_local
            if q in e.title.lower() or q in e.file.lower() or any(q in t.lower() for t in e.tags)
        ]
        return matched[: max(count, 1)]

    def find(self, meme_id: str) -> tuple[MemeEntry, Path]:
        """Tìm meme theo ID, tên file hoặc stem trong kho cục bộ."""
        for e in self.scan_local():
            path = self.root / e.file
            if (e.id == meme_id or e.file == meme_id or path.stem == meme_id) and path.is_file():
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
                        source=page_link or video_url,
                        license="chưa rõ",
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

    def download(
        self,
        meme_id: str,
        video_url: str,
        title: str,
        poster_url: str = "",
        source: str = "",
        license: str = "chưa rõ",
    ) -> MemeEntry:
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
                    if source and not e.source:
                        e.source = source
                    if license and not e.license:
                        e.license = license
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
            source=source or video_url,
            license=license or "chưa rõ",
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


class RoundRobinMemePool:
    """Vòng xoay tua luân phiên (Round-Robin Shuffle) toàn bộ kho meme cục bộ không lặp lại."""

    def __init__(self, library_dir: str | Path, seed: int | None = None) -> None:
        self.lib = MemeLibrary(library_dir)
        self._rng = random.Random(seed)
        self._entries = self.lib.scan_local()
        self._deck: list[MemeEntry] = []
        self._used_names: set[str] = set()
        self._refill_deck()

    @property
    def size(self) -> int:
        return len(self._entries)

    def _refill_deck(self) -> None:
        self._deck = list(self._entries)
        self._rng.shuffle(self._deck)

    def next_meme(
        self,
        preferred_emojis_text: str = "",
        preferred_tag: str | None = None,
    ) -> Path | None:
        """Chọn 1 meme kế tiếp theo vòng xoay tua (ưu tiên khớp emoji/tag, hết kho mới lặp)."""
        if not self._entries:
            return None

        if len(self._used_names) >= len(self._entries):
            self._used_names.clear()
            self._refill_deck()

        unused = [e for e in self._entries if e.file not in self._used_names]

        # 1. Ưu tiên meme trong nhóm chưa dùng có emoji khớp trực tiếp với bình luận
        if preferred_emojis_text:
            scored = [
                (sum(preferred_emojis_text.count(em) for em in e.emojis), e)
                for e in unused
                if e.emojis
            ]
            hits = [e for score, e in scored if score > 0]
            if hits:
                chosen = self._rng.choice(hits)
                self._used_names.add(chosen.file)
                return self.lib.root / chosen.file

        # 2. Ưu tiên meme trong nhóm chưa dùng khớp tag cảm xúc
        if preferred_tag:
            tagged = [e for e in unused if preferred_tag in e.tags]
            if tagged:
                chosen = self._rng.choice(tagged)
                self._used_names.add(chosen.file)
                return self.lib.root / chosen.file

        # 3. Xoay vòng tuần tự theo deck đã trộn đều toàn bộ kho cục bộ
        while True:
            if not self._deck:
                self._refill_deck()
            cand = self._deck.pop(0)
            if cand.file not in self._used_names:
                self._used_names.add(cand.file)
                return self.lib.root / cand.file


def pick_round_robin_memes(
    library_dir: str | Path, count: int, seed: int | None = None
) -> list[Path]:
    """Lấy `count` file meme cục bộ theo vòng xoay tua luân phiên không trùng trong 1 chu kỳ."""
    pool = RoundRobinMemePool(library_dir, seed=seed)
    out: list[Path] = []
    for _ in range(max(count, 0)):
        picked = pool.next_meme()
        if picked is None:
            break
        out.append(picked)
    return out
