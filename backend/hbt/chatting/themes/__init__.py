"""Hệ thống Theme cho Chatting (chuẩn iOS Messenger & Instagram DM)."""

from __future__ import annotations

from hbt.chatting.themes.base import ChatTheme
from hbt.chatting.themes.instagram import INSTAGRAM_THEME
from hbt.chatting.themes.messenger import MESSENGER_THEME

THEMES: dict[str, ChatTheme] = {
    "messenger": MESSENGER_THEME,
    "instagram": INSTAGRAM_THEME,
    # Tương thích ngược dữ liệu cũ 'zalo' -> tự ánh xạ sang Messenger iOS
    "zalo": MESSENGER_THEME,
}


def get_theme(platform: str) -> ChatTheme:
    return THEMES.get(platform.lower(), MESSENGER_THEME)
