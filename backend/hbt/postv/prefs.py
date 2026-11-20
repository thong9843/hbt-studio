"""Cài đặt ghi nhớ của PostV: `workspace/settings/postv.json`."""

from __future__ import annotations

import json
from pathlib import Path

from hbt.storage import _write_json_atomic


class PostvPrefs:
    def __init__(self, workspace_dir: Path):
        self.path = Path(workspace_dir) / "settings" / "postv.json"

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def voice_id(self) -> str | None:
        data = self._read()
        vid = data.get("voice_id")
        if not vid and isinstance(data.get("voice"), dict):
            vid = data["voice"].get("id")
        return vid if isinstance(vid, str) and vid.strip() else None

    def set_voice_id(self, voice_id: str | None) -> None:
        data = self._read()
        clean = voice_id.strip() if voice_id else None
        data["voice_id"] = clean or ""
        data["voice"] = {"id": clean} if clean else {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self.path, data)
