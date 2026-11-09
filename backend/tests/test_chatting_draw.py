"""Tests cho vẽ giao diện Pillow và timeline (CH2)."""

from pathlib import Path

from hbt.chatting.draw import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    ChatFrameRenderer,
    wrap_text,
)
from hbt.chatting.models import Character, ChatDoc, Message
from hbt.chatting.themes import get_theme
from hbt.chatting.timeline import build_timeline


def test_wrap_text():
    from hbt.chatting.draw import get_font

    font = get_font(40)
    text = "Đây là một câu văn dài nhằm kiểm tra tính năng xuống dòng tự động của bong bóng chat"
    lines = wrap_text(text, font, max_width=400)
    assert len(lines) > 1
    assert "Đây là" in lines[0]


def test_timeline_calculation():
    characters = [
        Character(id="me", name="Tôi", side="right"),
        Character(id="a", name="Linh", side="left"),
    ]
    doc = ChatDoc(
        title="Test timeline",
        characters=characters,
        messages=[
            Message(from_="a", text="Tin 1"),
            Message(from_="me", text="Tin 2"),
            Message(from_="a", text="Tin 3"),
            Message(from_="me", text="Tin 4"),
            Message(from_="a", text="Tin 5"),
            Message(from_="me", text="Tin 6"),
            Message(from_="a", text="Tin 7"),
            Message(from_="me", text="Tin 8"),
        ],
    )
    voice_durations = [(i, Path("fake.wav"), 1.5) for i in range(8)]
    timeline = build_timeline(doc, voice_durations)

    assert timeline.total_duration > 10.0
    assert len(timeline.states) > 8
    # Khung mở đầu có duration 0.4s
    assert timeline.states[0].duration == 0.4
    # Khung kết thúc giữ 1.5s
    assert timeline.states[-1].duration == 1.5


def test_render_chat_frame_dimensions():
    characters = [
        Character(id="me", name="Tôi", side="right"),
        Character(id="a", name="Linh", side="left"),
    ]
    theme = get_theme("messenger")
    renderer = ChatFrameRenderer(theme, characters)

    messages = [
        Message(from_="a", text="Chào bạn!"),
        Message(from_="me", text="Chào Linh nha, có chuyện gì thế?"),
    ]
    img = renderer.render_chat_view(visible_messages=messages, show_typing=True)

    assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    assert img.mode == "RGBA"
