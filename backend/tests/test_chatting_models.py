"""Tests cho ChatDoc và Pydantic schema validation (CH1)."""

import pytest
from pydantic import ValidationError

from hbt.chatting.models import Character, ChatDoc, Message


def make_valid_messages(count: int = 8, with_stickers: int = 1) -> list[Message]:
    msgs = []
    for i in range(count):
        sender = "me" if i % 2 == 0 else "a"
        sticker = "soc" if i < with_stickers else None
        msgs.append(Message(from_=sender, text=f"Tin nhắn thứ {i + 1}", sticker=sticker))
    return msgs


def test_valid_chat_doc():
    doc = ChatDoc(
        hbt_chat=1,
        title="Đoạn chat thử nghiệm",
        platform="messenger",
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Linh", side="left"),
        ],
        messages=make_valid_messages(8, with_stickers=2),
    )
    assert doc.title == "Đoạn chat thử nghiệm"
    assert len(doc.characters) == 2
    assert len(doc.messages) == 8


def test_invalid_characters_count():
    # Chỉ 1 nhân vật -> lỗi
    with pytest.raises(ValidationError, match="Số lượng nhân vật phải từ 2 đến 10"):
        ChatDoc(
            title="Lỗi",
            characters=[Character(id="me", name="Tôi", side="right")],
            messages=make_valid_messages(8),
        )

    # 11 nhân vật -> lỗi (> 10)
    with pytest.raises(ValidationError, match="Số lượng nhân vật phải từ 2 đến 10"):
        ChatDoc(
            title="Lỗi",
            characters=[Character(id="me", name="Tôi", side="right")]
            + [Character(id=f"c{i}", name=f"P{i}", side="left") for i in range(10)],
            messages=make_valid_messages(8),
        )

    # 4-5 nhân vật (Group Chat) -> hợp lệ
    doc_group = ChatDoc(
        title="Nhóm lớp",
        characters=[
            Character(id="me", name="Nam", side="right"),
            Character(id="a", name="Khánh", side="left"),
            Character(id="b", name="Thầy Chủ Nhiệm", side="left"),
            Character(id="c", name="Mẹ của Nam", side="left"),
        ],
        messages=make_valid_messages(8),
    )
    assert len(doc_group.characters) == 4


def test_must_have_exactly_one_right_character():
    # 0 nhân vật right -> lỗi
    with pytest.raises(ValidationError, match="Phải có đúng 1 nhân vật bên phải"):
        ChatDoc(
            title="Lỗi",
            characters=[
                Character(id="a", name="A", side="left"),
                Character(id="b", name="B", side="left"),
            ],
            messages=make_valid_messages(8),
        )

    # 2 nhân vật right -> lỗi
    with pytest.raises(ValidationError, match="Phải có đúng 1 nhân vật bên phải"):
        ChatDoc(
            title="Lỗi",
            characters=[
                Character(id="me", name="Tôi", side="right"),
                Character(id="me2", name="Tôi 2", side="right"),
            ],
            messages=make_valid_messages(8),
        )


def test_duplicate_character_ids():
    with pytest.raises(ValidationError, match="ID nhân vật không được trùng nhau"):
        ChatDoc(
            title="Lỗi",
            characters=[
                Character(id="a", name="Tôi", side="right"),
                Character(id="a", name="Linh", side="left"),
            ],
            messages=make_valid_messages(8),
        )


def test_invalid_messages_count():
    # 7 tin nhắn (< 8) -> lỗi
    with pytest.raises(ValidationError, match="Số lượng tin nhắn phải từ 8 đến 80"):
        ChatDoc(
            title="Lỗi",
            characters=[
                Character(id="me", name="Tôi", side="right"),
                Character(id="a", name="Linh", side="left"),
            ],
            messages=make_valid_messages(7),
        )


def test_max_total_chars():
    # 50 tin nhắn dài (~4500 ký tự) -> hợp lệ dưới 5000
    doc_long = ChatDoc(
        title="Hội thoại dài",
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Linh", side="left"),
        ],
        messages=[
            Message(from_="me" if i % 2 == 0 else "a", text="A" * 90) for i in range(50)
        ],  # 50 * 90 = 4500 <= 5000
    )
    assert len(doc_long.messages) == 50

    # Tin nhắn dài vượt quá 5000 ký tự -> lỗi
    msgs = [
        Message(from_="me" if i % 2 == 0 else "a", text="A" * 260) for i in range(20)
    ]  # 20 * 260 = 5200 > 5000
    with pytest.raises(ValidationError, match="Tổng số ký tự tin nhắn tối đa 5000"):
        ChatDoc(
            title="Lỗi",
            characters=[
                Character(id="me", name="Tôi", side="right"),
                Character(id="a", name="Linh", side="left"),
            ],
            messages=msgs,
        )


def test_invalid_message_sender():
    msgs = make_valid_messages(8)
    msgs[2] = Message(from_="unknown_user", text="Alo")
    with pytest.raises(ValidationError, match="không tồn tại trong danh sách nhân vật"):
        ChatDoc(
            title="Lỗi",
            characters=[
                Character(id="me", name="Tôi", side="right"),
                Character(id="a", name="Linh", side="left"),
            ],
            messages=msgs,
        )


def test_invalid_sticker_tag():
    with pytest.raises(ValidationError, match="Tag sticker không hợp lệ"):
        Message(from_="me", text="Chào", sticker="tag_la_lung")


def test_multiple_stickers_allowed():
    # 8 tin nhắn mà 4 sticker -> được phép linh hoạt theo kịch bản (không giới hạn cứng)
    doc = ChatDoc(
        title="Nhiều sticker",
        characters=[
            Character(id="me", name="Tôi", side="right"),
            Character(id="a", name="Linh", side="left"),
        ],
        messages=make_valid_messages(8, with_stickers=4),
    )
    assert sum(1 for m in doc.messages if m.sticker is not None) == 4
