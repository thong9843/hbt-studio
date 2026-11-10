"""Test dựng video Chatting preview (CH2)."""

from pathlib import Path

import pytest

from hbt.chatting.models import Character, ChatDoc, Message
from hbt.chatting.render import render_chat_video
from hbt.postv.voice import FileVoice


@pytest.mark.slow
def test_render_chat_video_preview(tmp_path):
    workspace_dir = tmp_path / "workspace"
    library_dir = Path(__file__).resolve().parents[2] / "library"
    brand_dir = Path(__file__).resolve().parents[2] / "brand"

    slug = "test-chat-render"
    doc = ChatDoc(
        title="Dựng video mẫu",
        platform="messenger",
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Linh", side="left"),
        ],
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

    voice_provider = FileVoice()
    out_video = render_chat_video(
        workspace_dir=workspace_dir,
        slug=slug,
        doc=doc,
        voice_provider=voice_provider,
        library_dir=library_dir,
        brand_dir=brand_dir,
        preview=True,
    )

    assert out_video.is_file()
    assert out_video.stat().st_size > 1000


@pytest.mark.slow
def test_render_chat_video_with_colorkey_meme(tmp_path):
    workspace_dir = tmp_path / "workspace"
    library_dir = Path(__file__).resolve().parents[2] / "library"
    brand_dir = Path(__file__).resolve().parents[2] / "brand"

    slug = "test-chat-render-meme"
    doc = ChatDoc(
        title="Dựng video kèm meme",
        platform="messenger",
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Linh", side="left"),
        ],
        messages=[
            Message(from_="a", text="Tin 1"),
            Message(from_="me", text="Tin 2"),
            Message(from_="a", text="Mày làm gì đấy 🤬🔨🔥", sticker="gian"),
            Message(from_="me", text="Tin 4"),
            Message(from_="a", text="Tin 5"),
            Message(from_="me", text="Tin 6"),
            Message(from_="a", text="Tin 7"),
            Message(from_="me", text="Tin 8"),
        ],
    )

    voice_provider = FileVoice()
    out_video = render_chat_video(
        workspace_dir=workspace_dir,
        slug=slug,
        doc=doc,
        voice_provider=voice_provider,
        library_dir=library_dir,
        brand_dir=brand_dir,
        preview=True,
    )

    assert out_video.is_file()
    assert out_video.stat().st_size > 1000
