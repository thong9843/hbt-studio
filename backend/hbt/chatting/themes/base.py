"""Định nghĩa cấu trúc Theme cho Chatting theo §7."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ChatTheme:
    name: str
    frame_width: int = 936
    frame_max_height: int = 1280
    top_y: int = 160
    corner_radius: int = 40
    bg_color: str = "#FFFFFF"

    # Header 120 px
    header_height: int = 120
    header_bg: str = "#FFFFFF"
    header_title_color: str = "#111111"
    header_status_color: str = "#6E6A72"
    header_status_text: str = "Đang hoạt động"
    status_dot_color: str | None = "#22A55B"
    header_avatar_size: int = 72

    # Bubble phải (me)
    bubble_right_bg: str = "#0084FF"
    bubble_right_text_color: str = "#FFFFFF"
    bubble_right_radius: int = 36

    # Bubble trái
    bubble_left_bg: str = "#F0F0F0"
    bubble_left_text_color: str = "#111111"
    bubble_left_radius: int = 36
    bubble_left_avatar_size: int = 48

    # Chữ
    font_size: int = 40
    line_spacing: int = 52
    bubble_max_width: int = 640

    # Đang nhập
    typing_dot_color: str = "#8E8E93"

    # Đã xem
    seen_style: Literal["mini_avatar", "text"] = "mini_avatar"
    seen_text: str = "Đã xem"
    seen_mini_avatar_size: int = 28
