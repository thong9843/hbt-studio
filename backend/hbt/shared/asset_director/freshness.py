"""Lớp 3A — Bộ nhớ độ mới & chống trùng lặp xuyên video (`workspace/asset_usage.json`)."""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class FreshnessMemory:
    """Theo dõi lịch sử sử dụng tài nguyên để phạt cooldown 6 video và xoay vòng kho đều."""

    def __init__(self, usage_path: Path, *, cooldown_videos: int = 6) -> None:
        self.usage_path = Path(usage_path)
        self.cooldown_videos = max(1, int(cooldown_videos))
        self._lock = threading.Lock()

    @staticmethod
    def make_key(category: str, asset_id: str) -> str:
        return f"{category.strip().lower()}:{asset_id.strip()}"

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.usage_path.is_file():
            return {"version": 1, "video_seq": 0, "assets": {}}
        try:
            data = json.loads(self.usage_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("assets"), dict):
                data.setdefault("version", 1)
                data.setdefault("video_seq", 0)
                return data
        except Exception:
            pass
        return {"version": 1, "video_seq": 0, "assets": {}}

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        self.usage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.usage_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.usage_path)

    def current_video_seq(self) -> int:
        with self._lock:
            return int(self._load_unlocked().get("video_seq", 0))

    def advance_video_seq(self) -> int:
        with self._lock:
            data = self._load_unlocked()
            seq = int(data.get("video_seq", 0)) + 1
            data["video_seq"] = seq
            self._save_unlocked(data)
            return seq

    def get_entry(self, category: str, asset_id: str) -> dict[str, Any] | None:
        key = self.make_key(category, asset_id)
        with self._lock:
            assets = self._load_unlocked().get("assets", {})
            entry = assets.get(key)
            return dict(entry) if isinstance(entry, dict) else None

    def is_in_cooldown(
        self,
        category: str,
        asset_id: str,
        *,
        video_seq: int | None = None,
    ) -> bool:
        key = self.make_key(category, asset_id)
        with self._lock:
            data = self._load_unlocked()
            entry = data.get("assets", {}).get(key)
            if not isinstance(entry, dict):
                return False
            seq = int(data.get("video_seq", 0)) if video_seq is None else int(video_seq)
            last_seq = int(entry.get("last_video_seq", -self.cooldown_videos))
            age = seq - last_seq
            return age < self.cooldown_videos

    def cooldown_penalty(
        self,
        category: str,
        asset_id: str,
        *,
        video_seq: int | None = None,
    ) -> float:
        key = self.make_key(category, asset_id)
        with self._lock:
            data = self._load_unlocked()
            entry = data.get("assets", {}).get(key)
            if not isinstance(entry, dict):
                return 0.0
            seq = int(data.get("video_seq", 0)) if video_seq is None else int(video_seq)
            last_seq = int(entry.get("last_video_seq", -self.cooldown_videos))
            age = seq - last_seq
            if age < self.cooldown_videos:
                clamped_age = max(0, age)
                return round(0.65 * (1.0 - clamped_age / float(self.cooldown_videos)), 4)
            return 0.0

    def use_decay(self, category: str, asset_id: str) -> float:
        key = self.make_key(category, asset_id)
        with self._lock:
            entry = self._load_unlocked().get("assets", {}).get(key)
            if not isinstance(entry, dict):
                return 0.0
            use_count = int(entry.get("use_count", 0))
            return round(min(0.20, max(0, use_count) * 0.03), 4)

    def total_penalty(
        self,
        category: str,
        asset_id: str,
        *,
        video_seq: int | None = None,
    ) -> float:
        return round(
            self.cooldown_penalty(category, asset_id, video_seq=video_seq)
            + self.use_decay(category, asset_id),
            4,
        )

    def record_usage(
        self,
        category: str,
        asset_id: str,
        *,
        source: str = "local",
        source_id: str = "",
        video_seq: int | None = None,
    ) -> dict[str, Any]:
        key = self.make_key(category, asset_id)
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            data = self._load_unlocked()
            seq = int(data.get("video_seq", 0)) if video_seq is None else int(video_seq)
            if seq > int(data.get("video_seq", 0)):
                data["video_seq"] = seq
            assets = data.setdefault("assets", {})
            prev = assets.get(key) if isinstance(assets.get(key), dict) else {}
            entry = {
                "category": category.strip().lower(),
                "source": source or prev.get("source") or "local",
                "source_id": source_id or prev.get("source_id") or "",
                "last_video_seq": seq,
                "last_used_at": now_iso,
                "use_count": int(prev.get("use_count", 0)) + 1,
            }
            assets[key] = entry
            self._save_unlocked(data)
            return entry
