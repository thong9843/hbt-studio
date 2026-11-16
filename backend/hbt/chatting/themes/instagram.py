"""Theme kiểu Instagram Direct iOS."""

from __future__ import annotations

from hbt.chatting.themes.base import ChatTheme

INSTAGRAM_THEME = ChatTheme(
    name="instagram",
    frame_width=936,
    frame_max_height=1280,
    top_y=160,
    corner_radius=36,
    bg_color="#FFFFFF",
    header_height=120,
    header_bg="#FFFFFF",
    header_title_color="#0F172A",
    header_status_color="#737373",
    header_status_text="Đang hoạt động",
    status_dot_color=None,
    header_avatar_size=72,
    bubble_right_bg="#833AB4",
    bubble_right_text_color="#FFFFFF",
    bubble_right_radius=34,
    bubble_left_bg="#EFEFEF",
    bubble_left_text_color="#000000",
    bubble_left_radius=34,
    bubble_left_avatar_size=48,
    font_size=40,
    line_spacing=52,
    bubble_max_width=640,
    typing_dot_color="#8E8E93",
    seen_style="text",
    seen_mini_avatar_size=28,
)
