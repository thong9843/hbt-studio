"""Mô hình dữ liệu Chatting (chat.json, Pydantic 2) theo đặc tả §3."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VALID_STICKER_TAGS = {
    "soc",
    "cuoi",
    "khoc",
    "gian",
    "ngai",
    "yeu",
    "nghi",
    "can",
    "bat_luc",
    "ok",
}


class Character(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    side: Literal["left", "right"]
    voice: str = "nam_1"
    avatar: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from", min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=120)
    sticker: str | None = None

    @field_validator("sticker")
    @classmethod
    def validate_sticker(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STICKER_TAGS:
            accepted = ", ".join(sorted(VALID_STICKER_TAGS))
            raise ValueError(f"Tag sticker không hợp lệ: '{v}'. Chỉ chấp nhận: {accepted}")
        return v


class SourceInfo(BaseModel):
    kind: str = "pasted"  # "reddit", "threads", "pasted"
    url: str | None = None


class BackgroundInfo(BaseModel):
    name: str = "parkour_01"
    seed: int = 7


class ChatDoc(BaseModel):
    hbt_chat: Literal[1] = 1
    title: str = Field(min_length=1, max_length=200)
    platform: Literal["messenger", "zalo"] = "messenger"
    source: SourceInfo = Field(default_factory=SourceInfo)
    background: BackgroundInfo = Field(default_factory=BackgroundInfo)
    music: str | None = "chill_02"
    characters: list[Character]
    messages: list[Message]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rules(self) -> ChatDoc:
        # 1. characters: 2-4
        if not (2 <= len(self.characters) <= 4):
            raise ValueError(f"Số lượng nhân vật phải từ 2 đến 4, nhận {len(self.characters)}")

        # Kiểm tra đúng 1 nhân vật side right
        rights = [c for c in self.characters if c.side == "right"]
        if len(rights) != 1:
            raise ValueError(f"Phải có đúng 1 nhân vật bên phải (side: right), nhận {len(rights)}")

        # Kiểm tra trùng id
        char_ids = {c.id for c in self.characters}
        if len(char_ids) != len(self.characters):
            raise ValueError("ID nhân vật không được trùng nhau")

        # 2. messages: 8-30 tin
        if not (8 <= len(self.messages) <= 30):
            raise ValueError(f"Số lượng tin nhắn phải từ 8 đến 30, nhận {len(self.messages)}")

        # 3. Tổng ký tự <= 900
        total_chars = sum(len(m.text) for m in self.messages)
        if total_chars > 900:
            raise ValueError(f"Tổng số ký tự tin nhắn tối đa 900, hiện tại là {total_chars}")

        # 4. Người gửi phải tồn tại trong characters
        for i, m in enumerate(self.messages):
            if m.from_ not in char_ids:
                raise ValueError(
                    f"Tin nhắn thứ {i + 1} có người gửi '{m.from_}' "
                    "không tồn tại trong danh sách nhân vật"
                )

        # 5. Tần suất sticker <= 1 sticker / 3 tin
        sticker_count = sum(1 for m in self.messages if m.sticker is not None)
        max_allowed_stickers = math.ceil(len(self.messages) / 3)
        if sticker_count > max_allowed_stickers:
            raise ValueError(
                f"Quá nhiều sticker ({sticker_count} sticker cho {len(self.messages)} tin). "
                f"Tối đa cho phép: {max_allowed_stickers} (tối đa 1 sticker mỗi 3 tin)"
            )

        return self
