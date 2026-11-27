"""Bộ đệm FontCache & LayerCache RGBA dùng chung cho tất cả động cơ."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageFont

DEFAULT_CPU_CACHE_MB = 256


class FontCache:
    """Cache `ImageFont` theo `(path, size)` để không mở lại file TTF từ đĩa."""

    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max(4, int(max_entries))
        self._fonts: OrderedDict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = (
            OrderedDict()
        )
        self.hits = 0
        self.misses = 0

    def get_font(
        self,
        path: Path | str | None,
        size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        key_path = str(Path(path).resolve()) if path is not None else "__default__"
        clamped_size = max(10, int(size))
        key = (key_path, clamped_size)

        if key in self._fonts:
            self.hits += 1
            self._fonts.move_to_end(key)
            return self._fonts[key]

        self.misses += 1
        loaded: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        if path is not None:
            p = Path(path)
            if p.is_file():
                try:
                    loaded = ImageFont.truetype(str(p), size=clamped_size)
                except Exception:
                    loaded = None
        if loaded is None:
            loaded = ImageFont.load_default()

        self._fonts[key] = loaded
        while len(self._fonts) > self.max_entries:
            self._fonts.popitem(last=False)
        return loaded

    def clear(self) -> None:
        self._fonts.clear()

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._fonts),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }


_GLOBAL_FONT_CACHE = FontCache(max_entries=128)


def load_cached_font(
    path: Path | str | None, size: int
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Nạp font có cache LRU toàn cục theo `(path, size)`."""
    return _GLOBAL_FONT_CACHE.get_font(path, size)


def estimate_image_bytes(img: Image.Image) -> int:
    """Ước lượng dung lượng RAM (bytes) của ảnh Pillow khi giải nén trong bộ nhớ."""
    channels = max(1, len(img.getbands()))
    return max(1, int(img.width) * int(img.height) * channels)


def _safe_close(img: Image.Image) -> None:
    try:
        img.close()
    except Exception:
        pass


class LayerCache:
    """LRU cache cho lớp nền/bảng RGBA đã pre-bake, ép trần RAM cứng và gọi `.close()` khi evict."""

    def __init__(
        self,
        *,
        max_mb: float = DEFAULT_CPU_CACHE_MB,
        max_bytes: int | None = None,
    ) -> None:
        cap = (
            int(max_bytes) if max_bytes is not None else int(max(1.0, float(max_mb)) * 1024 * 1024)
        )
        self.max_bytes = max(1024, cap)
        self._entries: OrderedDict[str, tuple[Image.Image, int]] = OrderedDict()
        self.current_bytes = 0
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0

    def get(self, key: str) -> Image.Image | None:
        item = self._entries.get(key)
        if item is None:
            self.misses += 1
            return None
        self.hits += 1
        self._entries.move_to_end(key)
        return item[0]

    def put(self, key: str, img: Image.Image) -> bool:
        """Lưu ảnh vào cache; nếu vượt trần `max_bytes` thì evict + `.close()` ảnh cũ."""
        size = estimate_image_bytes(img)
        if key in self._entries:
            old_img, old_size = self._entries.pop(key)
            self.current_bytes -= old_size
            if old_img is not img:
                _safe_close(old_img)

        if size > self.max_bytes:
            self.clear()
            return False

        while self._entries and (self.current_bytes + size > self.max_bytes):
            _, (evicted_img, evicted_size) = self._entries.popitem(last=False)
            self.current_bytes -= evicted_size
            self.evictions += 1
            _safe_close(evicted_img)

        self._entries[key] = (img, size)
        self.current_bytes += size
        return True

    def get_or_bake(self, key: str, factory: Callable[[], Image.Image]) -> Image.Image:
        """Lấy từ cache hoặc gọi `factory()` đúng 1 lần rồi lưu lại."""
        cached = self.get(key)
        if cached is not None:
            return cached
        img = factory()
        self.put(key, img)
        return img

    def clear(self) -> None:
        while self._entries:
            _, (img, _) = self._entries.popitem(last=False)
            _safe_close(img)
        self.current_bytes = 0

    def close(self) -> None:
        self.clear()

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._entries),
            "current_bytes": self.current_bytes,
            "max_bytes": self.max_bytes,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate": self.hit_rate,
        }
