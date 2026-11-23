"""Tests cho GeminiChatClient và prompt (CH1)."""

import json
from unittest.mock import patch

import httpx

from hbt.chatting.llm import GeminiChatClient
from hbt.chatting.prompt import SYSTEM_PROMPT, build_user_prompt


def test_system_prompt_rules():
    assert "Bạn là biên kịch video ngắn tiếng Việt" in SYSTEM_PROMPT
    assert "me" in SYSTEM_PROMPT
    assert "gemini" in GeminiChatClient().model


def test_build_user_prompt():
    p = build_user_prompt("Tiêu đề", "Nội dung", ["Bình luận 1"], platform="zalo")
    assert "Nền tảng: zalo" in p
    assert "Tiêu đề gốc: Tiêu đề" in p
    assert "Nội dung:\nNội dung" in p
    assert "Bình luận nổi bật:\n- Bình luận 1" in p


def test_gemini_check_status_missing_key():
    with patch("hbt.chatting.llm.load_gemini_api_key", return_value=""):
        client = GeminiChatClient()
        st = client.check_status()
        assert st["gemini_configured"] is False
        assert st["model_available"] is False


def test_gemini_check_status_configured():
    with patch(
        "hbt.chatting.llm.load_gemini_api_key",
        return_value="AIzaSyTestKeyForUnitTestsOnly1234567890",
    ):
        client = GeminiChatClient(model="gemini-3.8-flash")
        st = client.check_status()
        assert st["gemini_configured"] is True
        assert st["model_available"] is True


def test_gemini_generate_chat_success():
    expected_payload = {
        "title": "Chuyện nhặt ví",
        "characters": [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Bảo", "side": "left"},
        ],
        "messages": [
            {"from": "a", "text": "Tin 1", "sticker": None},
            {"from": "me", "text": "Tin 2", "sticker": None},
        ],
    }

    mock_resp = httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(expected_payload)}]}}],
            "usageMetadata": {"candidatesTokenCount": 85},
        },
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
        ),
    )

    with (
        patch(
            "hbt.shared.llm.load_gemini_api_key",
            return_value="AIzaSyTestKeyForUnitTestsOnly1234567890",
        ),
        patch("httpx.Client.post", return_value=mock_resp),
    ):
        client = GeminiChatClient(model="gemini-3.8-flash")
        doc, timings = client.generate_chat("Tiêu đề", "Nội dung")

        assert doc["title"] == "Chuyện nhặt ví"
        assert timings["llm_tokens"] == 85
        assert timings["llm_retry"] == 0
        assert timings["model"] == "gemini-3.8-flash"


def test_fake_llm_mode(monkeypatch):
    monkeypatch.setenv("CHATTING_FAKE_LLM", "1")
    client = GeminiChatClient()
    doc, timings = client.generate_chat("Tiêu đề test", "Nội dung test")
    assert doc["title"] == "Tiêu đề test"
    assert len(doc["characters"]) == 2
    assert len(doc["messages"]) >= 8
    assert timings["model"] == "fake-llm"


def test_sanitize_chat_raw_excess_stickers():
    from hbt.chatting.llm import sanitize_chat_raw
    from hbt.chatting.models import ChatDoc

    # Giả lập LLM sinh 10 tin nhắn đều có sticker
    raw = {
        "title": "Chuyện vui",
        "characters": [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Bạn", "side": "left"},
        ],
        "messages": [
            {"from": "me" if i % 2 == 0 else "a", "text": f"Tin nhắn số {i}", "sticker": "ok"}
            for i in range(10)
        ],
    }

    clean = sanitize_chat_raw(raw)
    sticker_indices = [i for i, m in enumerate(clean["messages"]) if m["sticker"] is not None]
    # Giới hạn cứng tối đa 3 sticker/video và cách nhau ít nhất 3 tin nhắn
    assert 1 <= len(sticker_indices) <= 3
    for a, b in zip(sticker_indices, sticker_indices[1:], strict=False):
        assert b - a >= 4
    assert any("lược bỏ" in w for w in clean["warnings"])

    # Và ChatDoc validate thành công mà không bị quăng lỗi
    doc = ChatDoc.model_validate(clean)
    assert doc.title == "Chuyện vui"
    assert len(doc.messages) == 10


def test_sanitize_chat_raw_cut_messages_keeps_first_and_last_two():
    from hbt.chatting.llm import sanitize_chat_raw
    from hbt.chatting.models import ChatDoc

    # 85 tin nhắn, tổng ký tự > 6000
    msgs = [{"from": "me", "text": "Tin đầu tiên số 0", "sticker": None}]
    for i in range(1, 83):
        msgs.append({"from": "a" if i % 2 == 1 else "me", "text": f"Tin nhắn giữa số {i} " * 4})
    msgs.append({"from": "a", "text": "Tin áp chót số 83", "sticker": None})
    msgs.append({"from": "me", "text": "Tin kết thúc số 84", "sticker": None})

    raw = {
        "title": "Hội thoại dài",
        "characters": [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Bạn", "side": "left"},
        ],
        "messages": msgs,
    }

    clean = sanitize_chat_raw(raw)
    doc = ChatDoc.model_validate(clean)

    # Đảm bảo tổng tin 8-80 và tổng ký tự <= 5000
    assert 8 <= len(doc.messages) <= 80
    assert sum(len(m.text) for m in doc.messages) <= 5000

    # Ưu tiên giữ tin đầu và 2 tin cuối
    assert doc.messages[0].text == "Tin đầu tiên số 0"
    assert doc.messages[-2].text == "Tin áp chót số 83"
    assert doc.messages[-1].text == "Tin kết thúc số 84"

    # Có cảnh báo cắt tin
    assert any("cắt bớt" in w for w in doc.warnings)


def test_sanitize_chat_raw_edge_cases():
    from hbt.chatting.llm import sanitize_chat_raw
    from hbt.chatting.models import ChatDoc

    # Giả lập LLM sinh thiếu tin (< 8 tin), không có nhân vật right, sender lạ, sticker bậy
    raw = {
        "title": "Chuyện ngắn",
        "characters": [
            {"id": "c1", "name": "A", "side": "left"},
            {"id": "c2", "name": "B", "side": "left"},
        ],
        "messages": [
            {"from": "unknown_char", "text": "Tin 1", "sticker": "invalid_sticker_tag"},
            {"from": "c2", "text": "Tin 2", "sticker": "ok"},
            {"from": "c1", "text": "Tin 3", "sticker": "tym"},
        ],
    }

    clean = sanitize_chat_raw(raw)
    doc = ChatDoc.model_validate(clean)
    assert 8 <= len(doc.messages) <= 80
    assert sum(1 for c in doc.characters if c.side == "right") == 1
    char_ids = {c.id for c in doc.characters}
    for m in doc.messages:
        assert m.from_ in char_ids
        if m.sticker:
            assert m.sticker in {"ok", "tym", "haha", "wow", "sad", "angry"}


def test_direct_script_keyword_spam_stripped_by_pacing_governor():
    from hbt.chatting.llm import sanitize_chat_raw
    from hbt.chatting.sources import parse_direct_script

    lines = [
        "Minh: Chào bạn haha",
        "Linh: Ok bạn ơi",
        "Minh: Hôm nay chán quá",
        "Linh: Thật hả trời ơi",
        "Minh: Vừa trúng số 10 tỷ [meme: soc]",
        "Linh: Haha đùa à",
        "Minh: Ok thật luôn",
        "Linh: Chán chả buồn nói",
        "Minh: Đi ăn mừng thôi [sticker: cuoi]",
        "Linh: Ok chốt luôn",
    ]
    parsed = parse_direct_script("\n".join(lines))
    clean = sanitize_chat_raw(parsed)
    kept = [i for i, m in enumerate(clean["messages"]) if m.get("sticker")]
    # Chỉ giữ tối đa 1-2 điểm cao trào tường minh (cách nhau >= 4 tin), loại sạch câu từ khóa yếu
    assert 1 <= len(kept) <= 2
    assert 4 in kept
    for a, b in zip(kept, kept[1:], strict=False):
        assert b - a >= 4


def test_chatdoc_backward_compatible_with_legacy_chat_json():
    from hbt.chatting.models import ChatDoc

    legacy = {
        "hbt_chat": 1,
        "title": "Chat cũ",
        "platform": "messenger",
        "characters": [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Bạn", "side": "left"},
        ],
        "messages": [{"from": "me" if i % 2 == 0 else "a", "text": f"Câu {i}"} for i in range(8)],
    }
    doc = ChatDoc.model_validate(legacy)
    assert doc.auto_fetch_online is True
    assert doc.messages[0].intensity == 2
    assert doc.messages[0].meme_query is None
    assert doc.messages[0].sfx_id is None


def test_chat_json_schema_is_valid_gemini_response_schema():
    from hbt.chatting.llm import CHAT_JSON_SCHEMA

    assert CHAT_JSON_SCHEMA["type"] == "OBJECT"
    assert CHAT_JSON_SCHEMA["required"] == ["title", "characters", "messages"]

    forbidden_keys = {"anyOf", "oneOf", "additionalProperties"}

    def _walk(node):
        if isinstance(node, dict):
            assert not (forbidden_keys & set(node.keys()))
            if "type" in node:
                assert isinstance(node["type"], str)
                assert node["type"] in {"OBJECT", "ARRAY", "STRING", "INTEGER", "NUMBER", "BOOLEAN"}
            if "enum" in node:
                assert all(v is not None for v in node["enum"])
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for el in node:
                _walk(el)

    _walk(CHAT_JSON_SCHEMA)


def test_unwrap_chat_payload_handles_wrapped_dict_list_and_missing_title():
    from hbt.chatting.llm import _unwrap_chat_payload

    core = {
        "characters": [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Nam", "side": "left"},
        ],
        "messages": [{"from": "a", "text": "Alo"}],
    }
    # Bọc trong {"chat": {...}} và thiếu title -> tự bóc + tự suy title
    u1 = _unwrap_chat_payload({"chat": core}, fallback_title="Chủ đề gốc")
    assert u1 is not None
    assert u1["title"] == "Chủ đề gốc"
    assert len(u1["messages"]) == 1

    # Bọc trong mảng 1 phần tử [{...}]
    u2 = _unwrap_chat_payload([{**core, "title": "Tiêu đề có sẵn"}], fallback_title="X")
    assert u2 is not None
    assert u2["title"] == "Tiêu đề có sẵn"


def test_gemini_generate_chat_retries_once_when_missing_messages():
    bad_payload = {"title": "Chỉ có tiêu đề"}
    good_payload = {
        "chat": {
            "characters": [
                {"id": "me", "name": "Tôi", "side": "right"},
                {"id": "a", "name": "Linh", "side": "left"},
            ],
            "messages": [{"from": "a", "text": f"Tin {i}"} for i in range(8)],
        }
    }

    req = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent",
    )
    resp_bad = httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": json.dumps(bad_payload)}]}}]},
        request=req,
    )
    resp_good = httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": json.dumps(good_payload)}]}}]},
        request=req,
    )

    with (
        patch(
            "hbt.shared.llm.load_gemini_api_key",
            return_value="AIzaSyTestKeyForUnitTestsOnly1234567890",
        ),
        patch("httpx.Client.post", side_effect=[resp_bad, resp_good]) as mock_post,
    ):
        client = GeminiChatClient()
        doc, timings = client.generate_chat("Chủ đề dự phòng", "Nội dung")
        assert mock_post.call_count == 2
        assert timings["llm_retry"] >= 1
        assert doc["title"] == "Chủ đề dự phòng"
        assert len(doc["messages"]) == 8
