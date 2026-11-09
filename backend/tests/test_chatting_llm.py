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
