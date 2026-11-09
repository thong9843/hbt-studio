"""Hệ thống Theme cho Chatting."""

from __future__ import annotations

from hbt.chatting.themes.base import ChatTheme
from hbt.chatting.themes.messenger import MESSENGER_THEME
from hbt.chatting.themes.zalo import ZALO_THEME

THEMES: dict[str, ChatTheme] = {
    "messenger": MESSENGER_THEME,
    "zalo": ZALO_THEME,
}


def get_theme(platform: str) -> ChatTheme:
    return THEMES.get(platform.lower(), MESSENGER_THEME)

