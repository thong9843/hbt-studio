"""Theme kiểu Messenger (§7, CH5)."""

from __future__ import annotations

from hbt.chatting.themes.base import ChatTheme

MESSENGER_THEME = ChatTheme(
    name="messenger",
    frame_width=936,
    frame_max_height=1280,
    top_y=160,
    corner_radius=40,
    bg_color="#FFFFFF",
    header_height=120,
    header_bg="#FFFFFF",
    header_title_color="#050505",
    header_status_color="#65676B",
    header_status_text="Đang hoạt động",
    status_dot_color="#31A24C",
    header_avatar_size=72,
    bubble_right_bg="#0084FF",
    bubble_right_text_color="#FFFFFF",
    bubble_right_radius=36,
    bubble_left_bg="#E4E6EB",
    bubble_left_text_color="#050505",
    bubble_left_radius=36,
    bubble_left_avatar_size=48,
    font_size=40,
    line_spacing=52,
    bubble_max_width=640,
    typing_dot_color="#8E8E93",
    seen_style="mini_avatar",
    seen_mini_avatar_size=28,
)
