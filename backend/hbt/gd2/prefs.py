"""Lựa chọn nhớ của GĐ2 (IMPLEMENT-GD2 mục 7): `workspace/settings/gd2.json`.

Hiện chỉ có giọng HBT đã chọn lần trước: `{"voice": {"id": "…"}}`. Không có khoá API."""

from __future__ import annotations

import json
from pathlib import Path

from hbt.storage import _write_json_atomic


class Gd2Prefs:
    def __init__(self, workspace_dir: Path):
        self.path = Path(workspace_dir) / "settings" / "gd2.json"

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def voice_id(self) -> str | None:
        voice = self._read().get("voice")
        vid = voice.get("id") if isinstance(voice, dict) else None
        return vid if isinstance(vid, str) and vid.strip() else None

    def set_voice_id(self, voice_id: str | None) -> None:
        data = self._read()
        data["voice"] = {"id": voice_id} if voice_id else {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self.path, data)
