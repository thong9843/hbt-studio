"""Theme kiểu Zalo (§7)."""

from __future__ import annotations

from hbt.chatting.themes.base import ChatTheme

ZALO_THEME = ChatTheme(
    name="zalo",
    frame_width=936,
    frame_max_height=1280,
    top_y=160,
    corner_radius=40,
    bg_color="#E2E9F1",
    header_height=120,
    header_bg="#0068FF",
    header_title_color="#FFFFFF",
    header_status_color="#D9EAFF",
    header_status_text="Vừa truy cập",
    status_dot_color=None,
    header_avatar_size=72,
    bubble_right_bg="#D9EAFF",
    bubble_right_text_color="#111111",
    bubble_right_radius=24,
    bubble_left_bg="#FFFFFF",
    bubble_left_text_color="#111111",
    bubble_left_radius=24,
    bubble_left_avatar_size=48,
    font_size=40,
    line_spacing=52,
    bubble_max_width=640,
    typing_dot_color="#0068FF",
    seen_style="text",
    seen_text="Đã xem",
)

