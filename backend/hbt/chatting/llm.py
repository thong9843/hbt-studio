"""Giao tiếp với Ollama local (POST /api/chat) theo §1, §5.

- keep_alive: 0 (giải phóng RAM ngay)
- format: JSON schema
- Đo timings (llm_s, llm_tokens, llm_retry)
- CHATTING_FAKE_LLM=1 cho e2e/test
"""

from __future__ import annotations

import json
import math
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


def sanitize_chat_raw(parsed: dict[str, Any]) -> dict[str, Any]:
    """Làm sạch và chuẩn hoá dữ liệu từ LLM để luôn thoả mãn mô hình ChatDoc:
    - Tiêu đề: cắt ngắn tối đa 200 ký tự.
    - Nhân vật: 2-4 nhân vật, đúng 1 nhân vật bên phải (side: right).
    - Tin nhắn: 8-30 tin, mỗi tin tối đa 120 ký tự, tổng ký tự tối đa 900.
    - Cắt tin để tổng <= 900 ký tự (ưu tiên giữ tin đầu + 2 tin cuối).
    - Lọc sticker: tần suất tối đa 1 sticker mỗi 3 tin (cách nhau ít nhất 2 tin).
    - Cảnh báo: trả danh sách warnings (số tin cắt, số sticker bỏ) để hiển thị trên UI.
    """
    from hbt.chatting.models import VALID_STICKER_TAGS

    data = dict(parsed)
    warnings: list[str] = []
    title = str(data.get("title") or "Đoạn chat vui").strip()[:200]
    data["title"] = title or "Đoạn chat vui"

    # 1. Nhân vật
    raw_chars = data.get("characters")
    if not isinstance(raw_chars, list) or len(raw_chars) < 2:
        chars = [
            {"id": "me", "name": "Tôi", "side": "right"},
            {"id": "a", "name": "Bạn", "side": "left"},
        ]
    else:
        chars = []
        seen_ids: set[str] = set()
        for idx, c in enumerate(raw_chars[:4]):
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
            chars.append({"id": cid, "name": name, "side": side})

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
        if len(text) > 120:
            text = text[:117] + "..."

        st = m.get("sticker")
        if st is not None:
            raw_sticker_count += 1
            st = str(st).strip()
            if st not in VALID_STICKER_TAGS:
                st = None

        clean_msgs.append(
            {
                "from": sender,
                "text": text,
                "sticker": st,
            }
        )

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
        # Nếu > 30 tin hoặc tổng ký tự > 900:
        # Cắt bớt tin từ phần giữa, ưu tiên giữ tin đầu (index 0) và 2 tin cuối (len-2, len-1)
        # Giữ tối thiểu 8 tin
        while len(clean_msgs) > 8 and (
            len(clean_msgs) > 30 or sum(len(m["text"]) for m in clean_msgs) > 900
        ):
            # Cắt 1 tin ở giữa (từ index 1 đến len(clean_msgs) - 3)
            # Chọn tin dài nhất ở phần giữa để giảm tổng ký tự nhanh nhất
            mid_indices = list(range(1, len(clean_msgs) - 2))
            if not mid_indices:
                break
            best_idx = max(mid_indices, key=lambda i: len(clean_msgs[i]["text"]))
            clean_msgs.pop(best_idx)
            cut_msgs_count += 1

        # Nếu sau khi cắt tin còn 8 tin mà tổng ký tự vẫn > 900:
        # Rút ngắn các tin ở giữa để tổng <= 900
        total_chars = sum(len(m["text"]) for m in clean_msgs)
        if total_chars > 900:
            for idx in range(1, len(clean_msgs) - 2):
                if total_chars <= 880:
                    break
                excess = total_chars - 880
                cur_len = len(clean_msgs[idx]["text"])
                cut = min(excess, max(0, cur_len - 30))
                if cut > 0:
                    clean_msgs[idx]["text"] = clean_msgs[idx]["text"][: cur_len - cut].rstrip()
                    total_chars -= cut

    # 3. Lọc sticker: tối đa 1 sticker mỗi 3 tin và cách nhau ít nhất 2 tin (khoảng cách index >= 3)
    max_stickers = math.ceil(len(clean_msgs) / 3)
    kept_stickers = 0
    last_sticker_idx = -99

    for idx, m in enumerate(clean_msgs):
        if m.get("sticker") is not None:
            if kept_stickers < max_stickers and (idx - last_sticker_idx >= 3):
                kept_stickers += 1
                last_sticker_idx = idx
            else:
                m["sticker"] = None

    dropped_stickers_count = max(0, raw_sticker_count - kept_stickers)

    # 4. Tạo cảnh báo (warnings)
    if cut_msgs_count > 0:
        warnings.append(
            f"Đã cắt bớt {cut_msgs_count} tin nhắn ở giữa (giữ tin đầu và 2 tin cuối) "
            "để kịch bản không vượt quá 900 ký tự."
        )
    if dropped_stickers_count > 0:
        warnings.append(
            f"Đã bỏ {dropped_stickers_count} sticker dư thừa "
            "để đảm bảo tối đa 1 sticker mỗi 3 tin nhắn."
        )

    data["messages"] = clean_msgs
    data["warnings"] = warnings
    return data


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
                    parsed = sanitize_chat_raw(parsed)
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
