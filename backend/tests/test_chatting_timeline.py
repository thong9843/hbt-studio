"""Tests cho timeline Chatting: thời lượng meme động/tĩnh và phân giải memes + stickers + sfx."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hbt.chatting.models import Character, ChatDoc, Message
from hbt.chatting.stickers import (
    load_sticker_or_meme_image,
    resolve_meme_or_sticker_path,
    resolve_sfx_path,
)
from hbt.chatting.timeline import build_timeline, compute_meme_duration


def test_compute_meme_duration_clamps_video_and_static_by_intensity(tmp_path: Path) -> None:
    vid = tmp_path / "clip.mp4"
    vid.write_bytes(b"fake")
    with patch("hbt.pipeline.ffutil.media_duration", return_value=7.5):
        assert compute_meme_duration(vid) == 3.8
    with patch("hbt.pipeline.ffutil.media_duration", return_value=0.5):
        assert compute_meme_duration(vid) == 1.2
    with patch("hbt.pipeline.ffutil.media_duration", return_value=2.6):
        assert compute_meme_duration(vid) == 2.6

    img_file = tmp_path / "sticker.webp"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(img_file, format="WEBP")
    assert compute_meme_duration(img_file, intensity=4) == 1.1
    assert compute_meme_duration(img_file, intensity=5) == 1.5
    assert 0.9 <= compute_meme_duration(img_file, intensity=3) <= 1.6


def test_resolve_meme_sticker_webp_and_sfx_paths(tmp_path: Path) -> None:
    lib = tmp_path / "library"
    (lib / "stickers").mkdir(parents=True)
    (lib / "memes").mkdir(parents=True)
    (lib / "sfx").mkdir(parents=True)

    webp_path = lib / "stickers" / "giphy-shock1.webp"
    Image.new("RGBA", (48, 48), (10, 200, 100, 255)).save(webp_path, format="WEBP")
    (lib / "stickers" / "index.json").write_text(
        json.dumps([{"id": "giphy-shock1", "file": "giphy-shock1.webp", "tag": "soc"}]),
        encoding="utf-8",
    )

    mp4_path = lib / "memes" / "boom.mp4"
    mp4_path.write_bytes(b"mp4")
    (lib / "memes" / "index.json").write_text(
        json.dumps([{"id": "boom-meme", "file": "boom.mp4", "tags": ["bat_ngo"]}]),
        encoding="utf-8",
    )

    sfx_path = lib / "sfx" / "tuna-bonk.mp3"
    sfx_path.write_bytes(b"mp3")
    (lib / "sfx" / "index.json").write_text(
        json.dumps([{"id": "tuna-bonk", "file": "tuna-bonk.mp3", "tags": ["bonk"]}]),
        encoding="utf-8",
    )

    assert resolve_meme_or_sticker_path(lib, "giphy-shock1") == webp_path
    assert resolve_meme_or_sticker_path(lib, "boom-meme") == mp4_path
    assert resolve_sfx_path(lib, "tuna-bonk") == sfx_path

    # Nạp sticker Giphy .webp bằng Pillow sạch sẽ
    loaded = load_sticker_or_meme_image(webp_path)
    assert loaded is not None
    assert loaded.size == (48, 48)
    loaded.close()

    # build_timeline ưu tiên msg.meme_id từ library/stickers/
    doc = ChatDoc(
        title="Test webp timeline",
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Nam", side="left"),
        ],
        messages=[
            Message(from_="a", text=f"Tin {i}", meme_id="giphy-shock1" if i == 4 else None, intensity=5 if i == 4 else 2)
            for i in range(8)
        ],
    )
    voices = [(i, Path("none.wav"), 1.0) for i in range(8)]
    tl = build_timeline(doc, voices, library_dir=lib)
    cutins = [s for s in tl.states if s.is_meme_cutin]
    assert len(cutins) == 1
    assert cutins[0].duration == 1.5
