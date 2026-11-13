"""Giao tiếp với Gemini API (Structured Outputs) cho phân hệ Chatting.

- Dùng chung gemini_client & GEMINI_API_KEY với HBT Core qua hbt.shared.llm
- Đo timings (llm_s, llm_tokens, llm_retry, model)
- CHATTING_FAKE_LLM=1 cho e2e/test
"""

from __future__ import annotations

import json
import os
from typing import Any

from hbt.chatting.prompt import SYSTEM_PROMPT, build_user_prompt
from hbt.shared.llm import (
    AVAILABLE_GEMINI_MODELS,
    GEMINI_MODEL,
    generate_structured_json,
    is_valid_gemini_api_key,
    load_gemini_api_key,
    normalize_model_name,
)

DEFAULT_MODEL = GEMINI_MODEL

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


def sanitize_chat_raw(parsed: dict[str, Any]) -> dict[str, Any]:
    """Làm sạch và chuẩn hoá dữ liệu từ LLM để luôn thoả mãn mô hình ChatDoc:
    - Tiêu đề: cắt ngắn tối đa 200 ký tự.
    - Nhân vật: 2-10 nhân vật (hỗ trợ group chat), đúng 1 nhân vật bên phải (side: right).
    - Tin nhắn: 8-80 tin, mỗi tin tối đa 300 ký tự, tổng ký tự tối đa 5000.
    - Cắt tin để tổng <= 5000 ký tự (ưu tiên giữ tin đầu + 2 tin cuối).
    - Cảnh báo: trả danh sách warnings để hiển thị trên UI.
    """
    from hbt.chatting.models import VALID_STICKER_TAGS

    data = dict(parsed)
    warnings: list[str] = []
    title = str(data.get("title") or "Đoạn chat vui").strip()[:200]
    data["title"] = title or "Đoạn chat vui"

    # 1. Nhân vật (tối đa 10 nhân vật cho Group Chat)
    raw_chars = data.get("characters")
    if not isinstance(raw_chars, list) or len(raw_chars) < 2:
        chars = [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Bạn", "side": "left"},
        ]
    else:
        chars = []
        seen_ids: set[str] = set()
        for idx, c in enumerate(raw_chars[:10]):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("id") or f"user_{idx}").strip()[:32]
            if cid in seen_ids or not cid:
                cid = f"char_{idx}"
            seen_ids.add(cid)
            name = str(c.get("name") or f"Người {idx + 1}").strip()[:64]
            side = c.get("side")
            if side not in ("left", "right"):
                side = "left"
            char_entry: dict[str, Any] = {"id": cid, "name": name, "side": side}
            if c.get("voice"):
                char_entry["voice"] = str(c["voice"])
            chars.append(char_entry)

        if len(chars) < 2:
            chars.append({"id": "other", "name": "Bạn", "side": "left"})

        # Đảm bảo đúng 1 nhân vật side right
        rights = [c for c in chars if c["side"] == "right"]
        if not rights:
            chars[0]["side"] = "right"
        elif len(rights) > 1:
            for c in rights[1:]:
                c["side"] = "left"

    data["characters"] = chars
    valid_cids = {c["id"] for c in chars}
    default_right = next((c["id"] for c in chars if c["side"] == "right"), chars[0]["id"])
    default_left = next((c["id"] for c in chars if c["side"] == "left"), chars[1]["id"])

    # 2. Tin nhắn
    raw_msgs = data.get("messages")
    if not isinstance(raw_msgs, list):
        raw_msgs = []

    clean_msgs: list[dict[str, Any]] = []
    raw_sticker_count = 0

    for idx, m in enumerate(raw_msgs):
        if not isinstance(m, dict):
            continue
        sender = str(m.get("from") or "").strip()
        if sender not in valid_cids:
            sender = default_right if idx % 2 == 0 else default_left

        text = str(m.get("text") or "").strip()
        if not text:
            text = "..."
        if len(text) > 300:
            text = text[:297] + "..."

        st = m.get("sticker")
        if st is not None:
            raw_sticker_count += 1
            st = str(st).strip()
            if st not in VALID_STICKER_TAGS:
                st = None

        msg_entry: dict[str, Any] = {
            "from": sender,
            "text": text,
            "sticker": st,
        }
        if m.get("display_text"):
            msg_entry["display_text"] = str(m["display_text"])
        if m.get("spoken_text") is not None:
            msg_entry["spoken_text"] = str(m["spoken_text"])
        clean_msgs.append(msg_entry)

    cut_msgs_count = 0

    # Nếu ít hơn 8 tin -> bổ sung thêm cho đủ 8
    if len(clean_msgs) < 8:
        while len(clean_msgs) < 8:
            idx = len(clean_msgs)
            sender = default_right if idx % 2 == 0 else default_left
            clean_msgs.append(
                {
                    "from": sender,
                    "text": "Haha thật luôn đấy!" if idx % 2 == 0 else "Ủa sao hay vậy?",
                    "sticker": None,
                }
            )
    else:
        # Nếu > 80 tin hoặc tổng ký tự > 5000:
        # Cắt bớt tin từ phần giữa, ưu tiên giữ tin đầu (index 0) và 2 tin cuối (len-2, len-1)
        # Giữ tối thiểu 8 tin
        while len(clean_msgs) > 8 and (
            len(clean_msgs) > 80 or sum(len(m["text"]) for m in clean_msgs) > 5000
        ):
            mid_indices = list(range(1, len(clean_msgs) - 2))
            if not mid_indices:
                break
            best_idx = max(mid_indices, key=lambda i: len(clean_msgs[i]["text"]))
            clean_msgs.pop(best_idx)
            cut_msgs_count += 1

        # Nếu sau khi cắt tin còn 8 tin mà tổng ký tự vẫn > 5000:
        # Rút ngắn các tin ở giữa để tổng <= 5000
        total_chars = sum(len(m["text"]) for m in clean_msgs)
        if total_chars > 5000:
            for idx in range(1, len(clean_msgs) - 2):
                if total_chars <= 4950:
                    break
                excess = total_chars - 4950
                cur_len = len(clean_msgs[idx]["text"])
                cut = min(excess, max(0, cur_len - 30))
                if cut > 0:
                    clean_msgs[idx]["text"] = clean_msgs[idx]["text"][: cur_len - cut].rstrip()
                    total_chars -= cut

    # 3. Giữ nguyên mọi sticker/meme hợp lệ của kịch bản (không giới hạn cứng)
    for m in clean_msgs:
        if m.get("sticker") is not None:
            st = str(m.get("sticker")).strip().lower()
            m["sticker"] = st if st in VALID_STICKER_TAGS else None

    # 4. Tạo cảnh báo (warnings)
    if cut_msgs_count > 0:
        warnings.append(
            f"Đã cắt bớt {cut_msgs_count} tin nhắn ở giữa (giữ tin đầu và 2 tin cuối) "
            "để kịch bản không vượt quá 5.000 ký tự."
        )

    data["messages"] = clean_msgs
    data["warnings"] = warnings
    return data


class GeminiChatClient:
    """Client sinh kịch bản Chatting bằng Gemini API dùng chung cấu hình HBT Core."""

    def __init__(
        self,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        raw_model = model or os.environ.get("CHATTING_MODEL") or DEFAULT_MODEL
        if not str(raw_model).strip().lower().startswith("gemini-"):
            raw_model = DEFAULT_MODEL
        self.model = normalize_model_name(raw_model)
        self.timeout = timeout

    def check_status(self) -> dict[str, Any]:
        """Kiểm tra GEMINI_API_KEY dùng chung với HBT Core (không lỗi 500)."""
        api_key = load_gemini_api_key()
        has_key = is_valid_gemini_api_key(api_key)
        return {
            "gemini_configured": has_key,
            "model_available": has_key,
            "model_name": self.model,
            "available_models": [m["id"] for m in AVAILABLE_GEMINI_MODELS],
        }

    def generate_chat(
        self,
        title: str,
        body: str,
        comments: list[str] | None = None,
        platform: str = "messenger",
        target_duration_s: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Sinh đoạn chat từ nội dung đầu vào qua Gemini API.
        Trả về: (chat_data, timings_dict)
        """
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

        user_content = build_user_prompt(
            title, body, comments, platform, target_duration_s=target_duration_s
        )
        parsed, timings = generate_structured_json(
            SYSTEM_PROMPT,
            user_content,
            model=self.model,
            timeout=self.timeout,
        )
        if (
            not isinstance(parsed, dict)
            or "title" not in parsed
            or not isinstance(parsed.get("characters"), list)
            or not isinstance(parsed.get("messages"), list)
        ):
            raise RuntimeError(
                "Gemini trả về JSON thiếu trường bắt buộc title, characters, messages"
            )

        sanitized = sanitize_chat_raw(parsed)
        return sanitized, timings
