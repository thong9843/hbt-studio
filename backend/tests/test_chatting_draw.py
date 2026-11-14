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


def test_typing_bubble_pulse():
    characters = [Character(id="a", name="Linh", side="left")]
    theme = get_theme("messenger")
    renderer = ChatFrameRenderer(theme, characters)

    b0 = renderer.draw_typing_bubble(pulse_step=0)
    b6 = renderer.draw_typing_bubble(pulse_step=6)
    assert b0.size == (128, 64)
    assert b6.size == (128, 64)
    # Hai frame pulse_step khác nhau phải có pixel khác nhau do sóng sin di chuyển
    assert b0.tobytes() != b6.tobytes()


def test_grouped_bubbles_and_content_height():
    characters = [
        Character(id="me", name="Tôi", side="right"),
        Character(id="a", name="Linh", side="left"),
    ]
    theme = get_theme("messenger")
    renderer = ChatFrameRenderer(theme, characters)

    # 3 tin nhắn liên tiếp cùng người gửi
    messages = [
        Message(from_="a", text="Tin 1 của Linh"),
        Message(from_="a", text="Tin 2 của Linh tiếp theo"),
        Message(from_="a", text="Tin 3 của Linh kết thúc nhóm"),
        Message(from_="me", text="Tin phản hồi của tôi"),
    ]

    h_empty = renderer.get_content_height([])
    h_msgs = renderer.get_content_height(messages)
    assert h_msgs > h_empty

    h_typing = renderer.get_content_height(messages, show_typing=True)
    assert h_typing > h_msgs

    # Render với scroll offset và scale
    img = renderer.render_chat_view(
        visible_messages=messages,
        show_typing=True,
        scale_last_msg=0.85,
        scroll_offset_override=50,
    )
    assert img.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    img.close()


def test_draw_message_with_image_and_video_media(tmp_path):
    from PIL import Image

    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True)
    img_path = media_dir / "photo.png"
    # Tạo ảnh ngang 1200x600 -> phải thu về rộng tối đa 560px, cao 280px (tỉ lệ 2:1)
    Image.new("RGB", (1200, 600), (220, 40, 80)).save(img_path)

    vid_path = media_dir / "clip.mp4"
    vid_path.write_bytes(b"dummy-mp4")

    chars = [
        Character(id="me", name="Nam", side="right"),
        Character(id="other", name="Lan", side="left"),
    ]
    renderer = ChatFrameRenderer(get_theme("messenger"), chars, project_dir=tmp_path)

    msg_img = Message(
        from_="other",
        text="Xem ảnh này đi",
        media_type="image",
        media_path="media/photo.png",
    )
    msg_vid = Message(
        from_="me",
        text="Còn đây là clip",
        media_type="video",
        media_path="media/clip.mp4",
    )

    img_size = renderer.resolve_message_media_size(msg_img)
    assert img_size == (560, 280)

    bw_img, bh_img, _ = renderer.measure_message(msg_img)
    assert bw_img >= 560 + 32
    assert bh_img > 280

    rects = renderer.compute_video_media_rects([msg_img, msg_vid], scroll_offset=0.0)
    assert len(rects) == 1
    m_idx, m_p, cx, cy, mw, mh = rects[0]
    assert m_idx == 1
    assert m_p == vid_path
    assert mw <= 560 and mh > 0 and cx >= 0 and cy >= 0

    frame = renderer.render_chat_view([msg_img, msg_vid])
    assert frame.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    frame.close()
