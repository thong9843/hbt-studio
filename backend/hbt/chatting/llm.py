"""Giao tiếp với Ollama local (POST /api/chat) theo §1, §5.

- keep_alive: 0 (giải phóng RAM ngay)
- format: JSON schema
- Đo timings (llm_s, llm_tokens, llm_retry)
- CHATTING_FAKE_LLM=1 cho e2e/test
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from hbt.chatting.prompt import SYSTEM_PROMPT, build_user_prompt

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = "qwen2.5:3b-instruct"

CHAT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "side": {"type": "string", "enum": ["left", "right"]},
                },
                "required": ["id", "name", "side"],
            },
        },
        "messages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "string"},
                    "text": {"type": "string"},
                    "sticker": {"type": ["string", "null"]},
                },
                "required": ["from", "text", "sticker"],
            },
        },
    },
    "required": ["title", "characters", "messages"],
}

MOCK_CHAT_RESPONSE = {
    "title": "Bất ngờ nửa đêm",
    "characters": [
        {"id": "me", "name": "Tôi", "side": "right"},
        {"id": "a", "name": "Nam", "side": "left"},
    ],
    "messages": [
        {"from": "a", "text": "Còn thức không ông ơi?", "sticker": None},
        {"from": "me", "text": "Sao thế, có chuyện gì à?", "sticker": None},
        {"from": "a", "text": "Vừa thấy ví ông để quên ở quán!", "sticker": "soc"},
        {"from": "me", "text": "Ủa thật hả trời ơi?", "sticker": None},
        {"from": "a", "text": "Thật mà, nhân viên đang giữ này.", "sticker": None},
        {"from": "me", "text": "May quá, cảm ơn ông nhiều nha!", "sticker": "cuoi"},
        {"from": "a", "text": "Mai nhớ bao trà sữa là được haha.", "sticker": None},
        {"from": "me", "text": "Ok chốt luôn bạn ơi!", "sticker": "ok"},
    ],
}


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str | None = None,
        timeout: float = 600.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model or os.environ.get("CHATTING_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    def check_status(self) -> dict[str, Any]:
        """Kiểm tra Ollama có đang chạy và model đã tải chưa (không lỗi 500 nếu Ollama tắt)."""
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    return {
                        "ollama_running": False,
                        "model_available": False,
                        "model_name": self.model,
                    }
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Kiểm tra model có trong danh sách (khớp tên chính xác hoặc tiền tố)
                is_available = any(
                    m == self.model
                    or m.startswith(f"{self.model}:")
                    or self.model.startswith(f"{m}:")
                    for m in models
                )
                return {
                    "ollama_running": True,
                    "model_available": is_available,
                    "model_name": self.model,
                    "available_models": models,
                }
        except Exception:
            return {"ollama_running": False, "model_available": False, "model_name": self.model}

    def generate_chat(
        self,
        title: str,
        body: str,
        comments: list[str] | None = None,
        platform: str = "messenger",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Sinh đoạn chat từ nội dung đầu vào.
        Trả về: (chat_data, timings_dict)
        """
        # Nếu đang ở chế độ fake LLM (test / e2e)
        if os.environ.get("CHATTING_FAKE_LLM") == "1":
            mock = json.loads(json.dumps(MOCK_CHAT_RESPONSE))
            mock["title"] = title or mock["title"]
            timings = {
                "fetch_s": 0.0,
                "llm_s": 0.05,
                "llm_tokens": 120,
                "llm_retry": 0,
                "model": "fake-llm",
            }
            return mock, timings

        user_content = build_user_prompt(title, body, comments, platform)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        t0 = time.perf_counter()
        retries = 0
        total_eval_tokens = 0

        while retries <= 1:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": CHAT_JSON_SCHEMA,
                "keep_alive": 0,  # BẮT BUỘC để giải phóng RAM ngay
                "options": {
                    "temperature": 0.8,
                    "num_ctx": 8192,
                },
            }

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{self.base_url}/api/chat", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                raise RuntimeError(f"Lỗi kết nối Ollama: {e}") from e

            eval_count = data.get("eval_count", 0)
            total_eval_tokens += eval_count
            raw_msg = data.get("message", {}).get("content", "").strip()

            try:
                parsed = json.loads(raw_msg)
                # Kiểm tra sơ bộ các trường bắt buộc
                if (
                    isinstance(parsed, dict)
                    and "title" in parsed
                    and isinstance(parsed.get("characters"), list)
                    and isinstance(parsed.get("messages"), list)
                ):
                    elapsed_s = round(time.perf_counter() - t0, 3)
                    timings = {
                        "llm_s": elapsed_s,
                        "llm_tokens": total_eval_tokens,
                        "llm_retry": retries,
                        "model": self.model,
                    }
                    return parsed, timings
                else:
                    raise ValueError("JSON thiếu các trường bắt buộc title, characters, messages")
            except Exception as err:
                retries += 1
                if retries > 1:
                    raise RuntimeError(
                        f"Ollama trả về JSON không hợp lệ sau 1 lần thử lại: {err}\n"
                        f"Nội dung: {raw_msg}"
                    ) from err
                # Thử lại: gửi lỗi lại cho LLM
                messages.append({"role": "assistant", "content": raw_msg})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"JSON của bạn bị lỗi cấu trúc: {err}. "
                            "Hãy sửa lại và chỉ trả về đúng JSON theo schema."
                        ),
                    }
                )

        raise RuntimeError("Không thể tạo kịch bản từ Ollama")
