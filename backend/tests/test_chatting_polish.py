"""Tests cho đợt CH-Polish: Xoay vòng Meme không lặp, Playlist BGM acrossfade và 60fps Easing."""

from __future__ import annotations

import json
import wave
from pathlib import Path

from hbt.chatting.audio import build_bgm_playlist, render_bgm_playlist_wav
from hbt.chatting.draw import ChatFrameRenderer
from hbt.chatting.models import Character, Message
from hbt.chatting.render import cubic_ease_out, spring_scale_curve
from hbt.chatting.stickers import find_meme_by_emojis, pick_sticker
from hbt.chatting.themes import get_theme
from hbt.pipeline.ffutil import media_duration


def _make_wav(path: Path, dur_s: float, rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(dur_s * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x10\x00" * frames)


def test_meme_rotation_no_repeat_until_exhausted(tmp_path: Path):
    library = tmp_path / "library"
    memes = library / "memes"
    memes.mkdir(parents=True)

    meta = {
        "memes": [
            {"file": "gian_1.mp4", "tags": ["gian"], "emojis": ["🤬"]},
            {"file": "gian_2.mp4", "tags": ["gian"], "emojis": ["🤬"]},
            {"file": "gian_3.mp4", "tags": ["gian"], "emojis": ["🤬"]},
            {"file": "soc_1.mp4", "tags": ["soc"], "emojis": ["👁️👄👁️"]},
        ]
    }
    (memes / "index.json").write_text(json.dumps(meta), encoding="utf-8")
    for item in meta["memes"]:
        (memes / item["file"]).write_bytes(b"video")

    used_memes: set[str] = set()
    first_round = [pick_sticker(library, "gian", used_memes=used_memes) for _ in range(3)]
    first_names = [p.name for p in first_round if p is not None]

    # Cả 3 lượt chọn đầu phải trả về 3 clip khác nhau hoàn toàn
    assert len(set(first_names)) == 3
    assert {"gian_1.mp4", "gian_2.mp4", "gian_3.mp4"} == set(first_names)

    # Chọn thêm clip thuộc tag khác ("soc") không bị ảnh hưởng
    soc_pick = find_meme_by_emojis(library, "Trời ơi 👁️👄👁️", used_memes=used_memes)
    assert soc_pick is not None
    assert soc_pick.name == "soc_1.mp4"

    # Lượt thứ 4 cho "gian" khi đã hết kho -> tự động reset nhóm tag "gian" để xoay vòng mới
    fourth_pick = pick_sticker(library, "gian", used_memes=used_memes)
    assert fourth_pick is not None
    assert fourth_pick.name in {"gian_1.mp4", "gian_2.mp4", "gian_3.mp4"}
    # Tag "soc" vẫn được nhớ trong used_memes
    assert "soc_1.mp4" in used_memes


def test_bgm_playlist_acrossfade_covers_long_duration(tmp_path: Path):
    library = tmp_path / "library"
    music_dir = library / "music"
    music_dir.mkdir(parents=True)

    # Tạo 3 track ngắn 6.0s mỗi track -> cần nối >= 2 track để phủ 10.0s video
    _make_wav(music_dir / "track_a.wav", 6.0)
    _make_wav(music_dir / "track_b.wav", 6.0)
    _make_wav(music_dir / "track_c.wav", 6.0)

    playlist = build_bgm_playlist(library, "track_a", total_duration=10.0, crossfade_s=1.5)
    assert len(playlist) >= 2
    assert playlist[0][0].name == "track_a.wav"
    assert playlist[1][0].name != "track_a.wav"

    out_wav = tmp_path / "bgm_out.wav"
    render_bgm_playlist_wav(playlist, total_duration=10.0, out_wav=out_wav, crossfade_s=1.5)
    assert out_wav.is_file()
    dur = media_duration(out_wav)
    assert dur is not None and 9.7 <= dur <= 10.2


def test_60fps_spring_and_cubic_ease_out_and_float_scroll():
    # 1. Spring curve 18 sub-frames: 0.80 -> 0.92 -> 1.03 -> 0.99 -> 1.0
    curve = spring_scale_curve(18)
    assert len(curve) == 18
    assert curve[0] == 0.80
    assert max(curve) >= 1.029
    assert curve[-1] == 1.0

    # 2. Cubic Ease-Out: 1 - (1 - t)^3
    assert cubic_ease_out(0.0) == 0.0
    assert cubic_ease_out(0.5) == 0.875
    assert cubic_ease_out(1.0) == 1.0

    # 3. Draw nhận toạ độ cuộn float và làm tròn bước vẽ cuối cùng
    chars = [
        Character(id="me", name="Nam", side="right"),
        Character(id="c1", name="Khánh", side="left"),
    ]
    msgs = [Message(from_="me" if i % 2 == 0 else "c1", text=f"Tin nhắn {i}") for i in range(10)]
    renderer = ChatFrameRenderer(get_theme("messenger"), chars)
    img = renderer.render_chat_view(msgs, scroll_offset_override=45.67)
    assert img.size == (1080, 1920)
    img.close()

