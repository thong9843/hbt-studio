"""Mô hình dữ liệu project (IMPLEMENT.md mục 3) — validate bằng Pydantic."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hbt.config import ALLOWED_FPS, DEFAULT_FPS

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MIN_SCENES, MAX_SCENES = 3, 12

LineSize = Literal["s", "m", "l", "xl"]
CardY = Literal["top", "upper", "middle", "lower"]


def _check_color(value: str, *, allow_names: bool) -> str:
    if HEX_COLOR.match(value) or (allow_names and value in ("ink", "primary", "accent")):
        return value
    raise ValueError(f"Màu không hợp lệ: {value!r}")


class _Model(BaseModel):
    # Bỏ qua trường lạ (ví dụ `_notes` trong project mẫu) thay vì báo lỗi.
    model_config = ConfigDict(extra="ignore")


class CardLine(_Model):
    text: str
    size: LineSize = "m"
    color: str = "ink"

    @field_validator("color")
    @classmethod
    def _color(cls, v: str) -> str:
        return _check_color(v, allow_names=True)


class Card(_Model):
    y: CardY | int = "top"
    lines: list[CardLine] = Field(default_factory=list)

    @field_validator("y")
    @classmethod
    def _y(cls, v: CardY | int) -> CardY | int:
        if isinstance(v, int) and not 0 <= v <= 1920:
            raise ValueError("card.y phải trong 0..1920")
        return v


class Label(_Model):
    text: str
    x: int
    y: int
    size: int = Field(default=80, ge=10, le=400)
    color: str = "ink"
    rot: float = 0

    @field_validator("color")
    @classmethod
    def _color(cls, v: str) -> str:
        return _check_color(v, allow_names=True)


class Scene(_Model):
    image: str
    card: Card = Field(default_factory=Card)
    labels: list[Label] = Field(default_factory=list)
    voice: str = Field(min_length=1)
    punch: bool = False
    caption_y: int | None = None

    @field_validator("voice")
    @classmethod
    def _voice(cls, v: str) -> str:
        if not v.replace("|", " ").strip():
            raise ValueError("Lời đọc của cảnh đang trống")
        return v


class Theme(_Model):
    primary: str = "#146268"
    accent: str = "#DE5C48"

    @field_validator("primary", "accent")
    @classmethod
    def _color(cls, v: str) -> str:
        return _check_color(v, allow_names=False)


class Music(_Model):
    file: str | None = None
    start: float | None = Field(default=None, ge=0)
    credit: str = ""


class Settings(_Model):
    fps: int = DEFAULT_FPS
    captions: bool = True
    aligner: Literal["auto", "whisper", "silence"] = "auto"
    sfx_on_punch: bool = True
    outro: bool = True

    @field_validator("fps")
    @classmethod
    def _fps(cls, v: int) -> int:
        if v not in ALLOWED_FPS:
            raise ValueError(f"fps phải là một trong {ALLOWED_FPS}")
        return v


class Publish(_Model):
    hook: str = ""
    hashtags: list[str] = Field(default_factory=list)


class Thumbnail(_Model):
    """Ảnh bìa (IMPLEMENT.md mục 4e) — được dựng ở M4, M1 chỉ đọc/ghi trường này."""

    scene: int = Field(default=1, ge=1)
    lines: list[str] = Field(min_length=2, max_length=3)
    series: str = ""
    accent: str = "#FFD43B"

    @field_validator("accent")
    @classmethod
    def _color(cls, v: str) -> str:
        return _check_color(v, allow_names=False)


class Project(_Model):
    version: Literal[1] = 1
    slug: str
    title: str
    series: str = ""
    theme: Theme = Field(default_factory=Theme)
    voice: str
    music: Music | None = None
    settings: Settings = Field(default_factory=Settings)
    scenes: list[Scene] = Field(min_length=MIN_SCENES, max_length=MAX_SCENES)
    publish: Publish = Field(default_factory=Publish)
    thumbnail: Thumbnail | None = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG.match(v):
            raise ValueError("slug chỉ gồm chữ thường, số và dấu gạch ngang")
        return v

    @model_validator(mode="after")
    def _thumbnail_scene(self) -> Project:
        if self.thumbnail and self.thumbnail.scene > len(self.scenes):
            raise ValueError("thumbnail.scene vượt quá số cảnh")
        return self


def load_project(project_dir: Path | str) -> Project:
    """Đọc `<project_dir>/project.json`; báo lỗi rõ khi thiếu file hoặc JSON sai."""
    path = Path(project_dir) / "project.json"
    if not path.is_file():
        raise FileNotFoundError(f"Không thấy {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} không phải JSON hợp lệ: {e}") from e
    return Project.model_validate(data)
