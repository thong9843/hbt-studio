"""Tests cho chế độ Dán kịch bản trực tiếp (Bypass LLM) và lưu trữ job.json."""

from pathlib import Path

from hbt.chatting.sources import parse_direct_script
from hbt.chatting.stickers import count_stickers_per_tag, pick_sticker
from hbt.chatting.store import load_job, save_job


def test_parse_direct_script_two_characters():
    text = """
    Minh: Ê nay rảnh không đi cafe?
    Linh: Tầm mấy giờ thế? (cười)
    Minh: 8h tối nha [sticker: ok]
    Linh: Ok bạn ơi!
    """
    res = parse_direct_script(text)
    assert res["title"] != ""
    assert len(res["characters"]) == 2

    # Người đầu tiên phải bên phải ('me')
    c_me = res["characters"][0]
    assert c_me["id"] == "me"
    assert c_me["name"] == "Minh"
    assert c_me["side"] == "right"

    # Người thứ hai phải bên trái
    c_linh = res["characters"][1]
    assert c_linh["name"] == "Linh"
    assert c_linh["side"] == "left"

    assert len(res["messages"]) == 4
    # Kiểm tra sticker bóc tách
    assert res["messages"][1]["sticker"] == "cuoi"
    assert res["messages"][2]["sticker"] == "ok"


def test_save_and_load_job(tmp_path: Path):
    workspace = tmp_path
    slug = "test-job-slug"

    assert load_job(workspace, slug) is None

    job_data = {
        "slug": slug,
        "status": "running",
        "phase": "fetch",
        "percent": 15,
        "text": "Đang lấy bài...",
    }
    save_job(workspace, slug, job_data)

    loaded = load_job(workspace, slug)
    assert loaded is not None
    assert loaded["status"] == "running"
    assert loaded["percent"] == 15
    assert loaded["phase"] == "fetch"


def test_pick_meme_from_library(tmp_path: Path):
    # Tạo cấu trúc library/memes giả lập
    library = tmp_path / "library"
    memes = library / "memes"
    memes.mkdir(parents=True)
    idx = {"soc": ["shocked_cat.mp4"], "cuoi": ["laugh_cat.mp4"]}
    (memes / "index.json").write_text(__import__("json").dumps(idx), encoding="utf-8")
    (memes / "shocked_cat.mp4").write_bytes(b"fake video")

    counts = count_stickers_per_tag(library)
    assert counts["soc"] == 1
    assert counts["cuoi"] == 1

    picked = pick_sticker(library, "soc", seed=0)
    assert picked is not None
    assert picked.name == "shocked_cat.mp4"


def test_parse_direct_script_scene_transition_and_meme_tag():
    text = """
    Minh: Ê nay rảnh không đi cafe?
    Linh: [meme: soc] Gì bất ngờ vậy!
    (5 phút sau tại nhà vệ sinh)
    Minh: Tới chưa bạn ê?
    Linh: Haha đang kẹt xe nè
    """
    res = parse_direct_script(text)
    assert len(res["messages"]) == 5
    # Tin 2: [meme: soc] -> sticker="soc"
    assert res["messages"][1]["sticker"] == "soc"
    # Tin 3: Chuyển cảnh ngoặc đơn
    assert res["messages"][2]["text"] == "(5 phút sau tại nhà vệ sinh)"
    assert res["messages"][2]["sticker"] is None
    # Tin 5: Từ khóa "haha" tự động nhận diện sticker="cuoi"
    assert res["messages"][4]["sticker"] == "cuoi"


def test_chatdoc_unlimited_stickers():
    from hbt.chatting.models import Character, ChatDoc, Message

    chars = [
        Character(id="me", name="Nam", side="right"),
        Character(id="c1", name="Hoa", side="left"),
    ]
    # Tạo 10 tin nhắn và cả 10 tin đều có sticker hợp lệ (không bị giới hạn 1/3 tin)
    msgs = [
        Message(from_="me" if i % 2 == 0 else "c1", text=f"Tin nhắn số {i}", sticker="soc")
        for i in range(10)
    ]
    doc = ChatDoc(
        hbt_chat=1,
        title="Đoạn chat thử nghiệm nhiều sticker",
        characters=chars,
        messages=msgs,
    )
    assert len(doc.messages) == 10
    assert sum(1 for m in doc.messages if m.sticker is not None) == 10


def test_timeline_meme_cutin_pause_and_scene_transition():
    from hbt.chatting.models import Character, ChatDoc, Message
    from hbt.chatting.timeline import build_timeline

    chars = [
        Character(id="me", name="Nam", side="right"),
        Character(id="c1", name="Hoa", side="left"),
    ]
    msgs = [
        Message(from_="c1", text="Chào bạn", sticker="soc"),
        Message(from_="c1", text="(10 phút sau tại quán cafe)"),
        Message(from_="me", text="Mình tới rồi nè"),
        Message(from_="c1", text="Đợi xíu nha"),
        Message(from_="me", text="Oke bạn"),
        Message(from_="c1", text="Mình đang gửi xe"),
        Message(from_="me", text="Tầng 2 nha"),
        Message(from_="c1", text="Ok thấy rồi"),
    ]
    doc = ChatDoc(
        hbt_chat=1,
        title="Test timeline",
        characters=chars,
        messages=msgs,
    )
    # Giả lập wav_dur = 1.0s cho mỗi tin
    voice_durations = [(i, Path("fake.wav"), 1.0) for i in range(len(msgs))]
    timeline = build_timeline(doc, voice_durations)

    # Tìm state meme cut-in (duration 3.5s)
    cutin_states = [s for s in timeline.states if s.is_meme_cutin]
    assert len(cutin_states) == 1
    assert cutin_states[0].duration == 3.5
    assert cutin_states[0].active_sticker == "soc"

    # Tìm state chuyển cảnh (duration 1.2s - 1.5s, show_typing=False)
    transition_states = [
        s for s in timeline.states if 1.2 <= s.duration <= 1.5 and s.visible_count == 2
    ]
    assert len(transition_states) == 1
    assert transition_states[0].show_typing is False


def test_emoji_rendering_and_segmentation():
    from hbt.chatting.draw import (
        get_emoji_font,
        get_font,
        measure_line_width,
        segment_text_and_emojis,
        wrap_text,
    )

    text = "Mày nói cái gì đấy 🤬🔨🔥 chạy nè 🏃‍♂️💨! 👁️👄👁️"
    segs = segment_text_and_emojis(text)
    # Phải bóc tách được các emoji
    emojis_found = [s for s, is_em in segs if is_em]
    assert len(emojis_found) >= 4

    font_text = get_font(30)
    font_emoji = get_emoji_font(30)
    w = measure_line_width(text, font_text, font_emoji)
    assert w > 100

    lines = wrap_text(text, font_text, 250, font_emoji)
    assert len(lines) >= 2


def test_message_display_and_spoken_text_separation():
    from hbt.chatting.models import Message
    from hbt.chatting.voice import clean_spoken_text

    raw = "Mày nói cái gì đấy 🤬🔨🔥 (cười lớn) 20:15"
    msg = Message(from_="me", text=raw)
    assert msg.display_text == raw
    assert msg.spoken_text == "Mày nói cái gì đấy"

    # Chỉ emoji -> spoken_text rỗng
    assert clean_spoken_text("🤣🤣🤣") == ""
    # Chuyển cảnh -> spoken_text rỗng
    assert clean_spoken_text("(5 phút sau tại nhà vệ sinh)") == ""


def test_meme_metadata_and_climax_highlight(tmp_path: Path):
    from hbt.chatting.stickers import (
        find_meme_by_emojis,
        get_meme_metadata,
        load_memes_metadata,
    )

    library = tmp_path / "library"
    memes_dir = library / "memes"
    memes_dir.mkdir(parents=True)

    data = {
        "memes": [
            {
                "file": "Angry-cat.mp4",
                "tags": ["gian"],
                "emojis": ["🤬", "🔨", "🔥"],
                "start_time": 0.5,
                "duration": 3.5,
            },
            {
                "file": "Shocked-cat.mp4",
                "tags": ["soc"],
                "emojis": ["👁️👄👁️"],
                "start_time": 1.0,
                "duration": 3.0,
            },
        ]
    }
    import json

    (memes_dir / "index.json").write_text(json.dumps(data), encoding="utf-8")
    (memes_dir / "Angry-cat.mp4").write_bytes(b"fake video")
    (memes_dir / "Shocked-cat.mp4").write_bytes(b"fake video")

    meta_list = load_memes_metadata(library)
    assert len(meta_list) == 2

    meta = get_meme_metadata(library, "Angry-cat.mp4")
    assert meta["start_time"] == 0.5
    assert meta["duration"] == 3.5

    # Ánh xạ tự động emoji cuối câu
    matched = find_meme_by_emojis(library, "Mày nói gì đấy 🤬🔨🔥")
    assert matched is not None
    assert matched.name == "Angry-cat.mp4"

    matched_soc = find_meme_by_emojis(library, "Ủa gì dạ 👁️👄👁️")
    assert matched_soc is not None
    assert matched_soc.name == "Shocked-cat.mp4"


def test_safe_fallback_missing_meme(tmp_path: Path):
    from hbt.chatting.models import Character, ChatDoc, Message
    from hbt.chatting.timeline import build_timeline

    chars = [
        Character(id="me", name="Nam", side="right"),
        Character(id="c1", name="Hoa", side="left"),
    ]
    msgs = [
        Message(from_="c1", text=f"Tin số {i}", sticker="soc" if i == 0 else None) for i in range(8)
    ]
    doc = ChatDoc(
        hbt_chat=1,
        title="Test fallback",
        characters=chars,
        messages=msgs,
    )
    voice_durations = [(i, Path("fake.wav"), 1.0) for i in range(8)]

    # Thư viện rỗng (không có file meme)
    empty_lib = tmp_path / "empty_lib"
    empty_lib.mkdir(parents=True)

    timeline = build_timeline(doc, voice_durations, library_dir=empty_lib)
    # Không tạo state cut-in nếu thiếu file meme
    cutin_states = [s for s in timeline.states if s.is_meme_cutin]
    assert len(cutin_states) == 0
