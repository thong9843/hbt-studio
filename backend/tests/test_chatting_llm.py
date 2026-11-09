"""Tests cho OllamaClient và prompt (CH1)."""

import json
from unittest.mock import patch

import httpx

from hbt.chatting.llm import OllamaClient
from hbt.chatting.prompt import SYSTEM_PROMPT, build_user_prompt


def test_system_prompt_rules():
    assert "Bạn là biên kịch video ngắn tiếng Việt" in SYSTEM_PROMPT
    assert "me" in SYSTEM_PROMPT
    assert "qwen2.5:3b-instruct" in OllamaClient().model or "qwen" in OllamaClient().model


def test_build_user_prompt():
    p = build_user_prompt("Tiêu đề", "Nội dung", ["Bình luận 1"], platform="zalo")
    assert "Nền tảng: zalo" in p
    assert "Tiêu đề gốc: Tiêu đề" in p
    assert "Nội dung:\nNội dung" in p
    assert "Bình luận nổi bật:\n- Bình luận 1" in p


def test_ollama_check_status_offline():
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Offline")):
        client = OllamaClient()
        st = client.check_status()
        assert st["ollama_running"] is False
        assert st["model_available"] is False


def test_ollama_check_status_online_with_model():
    mock_resp = httpx.Response(
        200,
        json={"models": [{"name": "qwen2.5:3b-instruct:latest"}, {"name": "llama3:latest"}]},
        request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"),
    )
    with patch("httpx.Client.get", return_value=mock_resp):
        client = OllamaClient(model="qwen2.5:3b-instruct")
        st = client.check_status()
        assert st["ollama_running"] is True
        assert st["model_available"] is True


def test_ollama_generate_chat_success():
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
            "message": {"content": json.dumps(expected_payload)},
            "eval_count": 85,
        },
        request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat"),
    )

    captured_req = {}

    def mock_post(*args, **kwargs):
        captured_req["json"] = kwargs.get("json")
        return mock_resp

    with patch("httpx.Client.post", side_effect=mock_post):
        client = OllamaClient(model="qwen2.5:3b-instruct")
        doc, timings = client.generate_chat("Tiêu đề", "Nội dung")

        assert doc["title"] == "Chuyện nhặt ví"
        assert timings["llm_tokens"] == 85
        assert timings["llm_retry"] == 0

        # Kiểm tra lời gọi gửi keep_alive: 0
        assert captured_req["json"].get("keep_alive") == 0


def test_fake_llm_mode(monkeypatch):
    monkeypatch.setenv("CHATTING_FAKE_LLM", "1")
    client = OllamaClient()
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
    stickers = [m["sticker"] for m in clean["messages"] if m["sticker"] is not None]
    # Tối đa ceil(10/3) = 4 sticker
    assert len(stickers) <= 4

    # Kiểm tra cảnh báo bỏ sticker dư
    assert any("sticker dư" in w for w in clean["warnings"])

    # Và ChatDoc validate thành công mà không bị quăng lỗi
    doc = ChatDoc.model_validate(clean)
    assert doc.title == "Chuyện vui"
    assert len(doc.messages) == 10
    assert len(doc.warnings) > 0


def test_sanitize_chat_raw_cut_messages_keeps_first_and_last_two():
    from hbt.chatting.llm import sanitize_chat_raw
    from hbt.chatting.models import ChatDoc

    # 35 tin nhắn, tổng ký tự > 1500
    msgs = [{"from": "me", "text": "Tin đầu tiên số 0", "sticker": None}]
    for i in range(1, 33):
        msgs.append({"from": "a" if i % 2 == 1 else "me", "text": f"Tin nhắn giữa số {i} " * 5})
    msgs.append({"from": "a", "text": "Tin áp chót số 33", "sticker": None})
    msgs.append({"from": "me", "text": "Tin kết thúc số 34", "sticker": None})

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

    # Đảm bảo tổng tin 8-30 và tổng ký tự <= 900
    assert 8 <= len(doc.messages) <= 30
    assert sum(len(m.text) for m in doc.messages) <= 900

    # Ưu tiên giữ tin đầu và 2 tin cuối
    assert doc.messages[0].text == "Tin đầu tiên số 0"
    assert doc.messages[-2].text == "Tin áp chót số 33"
    assert doc.messages[-1].text == "Tin kết thúc số 34"

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
    assert 8 <= len(doc.messages) <= 30
    assert sum(1 for c in doc.characters if c.side == "right") == 1
    char_ids = {c.id for c in doc.characters}
    for m in doc.messages:
        assert m.from_ in char_ids
        if m.sticker:
            assert m.sticker in {"ok", "tym", "haha", "wow", "sad", "angry"}
