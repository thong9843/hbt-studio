"""Kiểm thử tách sạch lời thoại cho TTS trong Chatting (§9, CH5)."""

from hbt.chatting.voice import (
    FEMALE_VOICES,
    MALE_VOICES,
    assign_character_voices,
    clean_spoken_text,
    normalize_vietnamese_for_tts,
)


def test_clean_spoken_text_timestamps():
    # Mốc giờ UI định dạng hh:mm vẫn bị lọc sạch
    assert clean_spoken_text("20:15 Alo bạn có nhà không?") == "Alo bạn có nhà không?"
    assert clean_spoken_text("Hôm qua lúc 10:30 PM mình thấy bạn") == "Hôm qua lúc mình thấy bạn"
    # Giờ nói tự nhiên trong lời thoại ("2h sáng", "20h15", "9 giờ 30") được giữ nguyên để TTS đọc
    assert clean_spoken_text("2h sáng mà còn thức hả?") == "2h sáng mà còn thức hả?"
    assert clean_spoken_text("20h15 tối nay đi ăn nhé") == "20h15 tối nay đi ăn nhé"
    assert clean_spoken_text("9 giờ 30 phút có mặt nha") == "9 giờ 30 phút có mặt nha"


def test_normalize_vietnamese_for_tts():
    assert normalize_vietnamese_for_tts("2h sáng rồi bà ơi") == "2 giờ sáng rồi bà ơi"
    assert normalize_vietnamese_for_tts("Hẹn 20h15 nhé") == "Hẹn 20 giờ 15 nhé"
    assert normalize_vietnamese_for_tts("Chờ 15p thôi, hết 50k") == "Chờ 15 phút thôi, hết 50 nghìn"
    assert (
        normalize_vietnamese_for_tts("Rep ib fb của crush đi")
        == "rép in bốc phây búc của cờ rớt đi"
    )


def test_assign_character_voices_matches_gender():
    chars = [
        {"id": "me", "name": "Linh Drama", "side": "right"},
        {"id": "a", "name": "Trang", "side": "left", "gender": "female"},
        {"id": "b", "name": "Minh", "side": "left", "gender": "male"},
    ]
    msgs = [
        {"from": "me", "text": "Bà ơi 2h sáng rồi mà còn drama"},
        {"from": "a", "text": "Kể lẹ đi bà"},
    ]
    assigned = assign_character_voices(chars, msgs)
    assert assigned[0]["gender"] == "female"
    assert assigned[0]["voice"] in FEMALE_VOICES
    assert assigned[1]["gender"] == "female"
    assert assigned[1]["voice"] in FEMALE_VOICES
    assert assigned[0]["voice"] != assigned[1]["voice"]
    assert assigned[2]["gender"] == "male"
    assert assigned[2]["voice"] in MALE_VOICES


def test_clean_spoken_text_seen_and_status():
    # Trạng thái đã xem, đã gửi
    assert clean_spoken_text("Alo 20:18 đã xem") == "Alo"
    assert clean_spoken_text("Oke bạn đã gửi") == "Oke bạn"
    assert clean_spoken_text("seen") == ""


def test_clean_spoken_text_sticker_and_meta():
    # Mô tả sticker trong ngoặc
    assert clean_spoken_text("Haha vui quá (cười)") == "Haha vui quá"
    assert clean_spoken_text("[sticker: soc] Thật không tin được!") == "Thật không tin được!"
    assert clean_spoken_text("[ảnh]") == ""
    assert clean_spoken_text("(khóc) buồn ghê") == "buồn ghê"


def test_clean_spoken_text_pure_time_or_meta_becomes_empty():
    assert clean_spoken_text("20:15") == ""
    assert clean_spoken_text("20:15 - đã xem") == ""
    assert clean_spoken_text("[sticker: haha]") == ""
    assert clean_spoken_text("   ---   ") == ""
