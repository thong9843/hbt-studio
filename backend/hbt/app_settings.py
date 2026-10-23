"""Cài đặt chung của app (màn Cài đặt, IMPLEMENT.md mục 10.2): lưu ở `workspace/settings/app.json`.

- `default_fps`, `theme` được dùng khi tạo project mới.
- `whisper_model`, `whisper_timeout_seconds` được lưu từ M3 và áp dụng khi Whisper vào (M4).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from hbt.config import DEFAULT_FPS
from hbt.models import HEX_COLOR

FpsChoice = Literal[30, 50, 60]
WhisperModelChoice = Literal["auto", "small", "medium", "large-v3"]


class ThemeDefaults(BaseModel):
    primary: str = "#146268"
    accent: str = "#DE5C48"

    @field_validator("primary", "accent")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not HEX_COLOR.match(v):
            raise ValueError(f"Màu phải dạng #RRGGBB, nhận {v!r}")
        return v


class AppSettings(BaseModel):
    default_fps: FpsChoice = DEFAULT_FPS
    theme: ThemeDefaults = Field(default_factory=ThemeDefaults)
    whisper_model: WhisperModelChoice = "auto"
    whisper_timeout_seconds: int = Field(default=900, ge=30, le=7200)


class AppSettingsStore:
    def __init__(self, workspace_dir: Path, env_default_fps: int = DEFAULT_FPS):
        self.path = Path(workspace_dir) / "settings" / "app.json"
        self.env_default_fps = env_default_fps

    def load(self) -> AppSettings:
        """Giá trị đã lưu; chưa có file thì lấy mặc định (fps theo `.env`)."""
        base = {"default_fps": self.env_default_fps}
        if self.path.is_file():
            try:
                base.update(json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass  # file hỏng: dùng mặc định thay vì làm sập app
        return AppSettings.model_validate(base)

    def save(self, settings: AppSettings) -> AppSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        text = json.dumps(settings.model_dump(), ensure_ascii=False, indent=2)
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return settings
