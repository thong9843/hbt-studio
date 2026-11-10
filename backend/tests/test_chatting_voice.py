"""Kiểm thử tách sạch lời thoại cho TTS trong Chatting (§9, CH5)."""

from hbt.chatting.voice import clean_spoken_text


def test_clean_spoken_text_timestamps():
    # Mốc giờ định dạng hh:mm
    assert clean_spoken_text("20:15 Alo bạn có nhà không?") == "Alo bạn có nhà không?"
    assert clean_spoken_text("Hôm qua lúc 10:30 PM mình thấy bạn") == "Hôm qua lúc mình thấy bạn"
    assert clean_spoken_text("20h15 tối nay đi ăn nhé") == "tối nay đi ăn nhé"
    assert clean_spoken_text("9 giờ 30 phút có mặt nha") == "có mặt nha"


def test_clean_spoken_text_seen_and_status():
    # Trạng thái đã xem, đã gửi
    assert clean_spoken_text("Alo 20:18 đã xem") == "Alo"
    assert clean_spoken_text("Oke bạn đã gửi") == "Oke bạn"
    assert clean_spoken_text("seen") == ""


def test_clean_spoken_text_sticker_and_meta():
    # Mô tả sticker trong ngoặc
    assert clean_spoken_text("Haha vui quá (cười)") == "Haha vui quá"
    assert clean_spoken_text("[sticker: soc] Thật không thể tin được!") == "Thật không thể tin được!"
    assert clean_spoken_text("[ảnh]") == ""
    assert clean_spoken_text("(khóc) buồn ghê") == "buồn ghê"


def test_clean_spoken_text_pure_time_or_meta_becomes_empty():
    assert clean_spoken_text("20:15") == ""
    assert clean_spoken_text("20:15 - đã xem") == ""
    assert clean_spoken_text("[sticker: haha]") == ""
    assert clean_spoken_text("   ---   ") == ""
