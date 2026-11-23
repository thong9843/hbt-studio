"""Giao tiếp với Gemini API (Structured Outputs) cho phân hệ Chatting.

- Dùng chung gemini_client & GEMINI_API_KEY với HBT Core qua hbt.shared.llm
- Đo timings (llm_s, llm_tokens, llm_retry, model)
- CHATTING_FAKE_LLM=1 cho e2e/test
"""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

DEFAULT_MODEL = GEMINI_MODEL
CHATTING_MAX_OUTPUT_TOKENS = 8192

_WRAPPER_KEYS = (
    "data",
    "chat",
    "script",
    "result",
    "conversation",
    "dialogue",
    "response",
    "output",
)

# Schema chuẩn Gemini REST `responseSchema` (không dùng anyOf/oneOf/additionalProperties/type mảng)
CHAT_JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "music_mood": {
            "type": "STRING",
            "nullable": True,
            "enum": ["vui_nhon", "kich_tinh", "bi_an", "thu_gian", "hanh_dong"],
        },
        "characters": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "name": {"type": "STRING"},
                    "side": {"type": "STRING", "enum": ["left", "right"]},
                },
                "required": ["id", "name", "side"],
            },
        },
        "messages": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "from": {"type": "STRING"},
                    "text": {"type": "STRING"},
                    "beat_role": {
                        "type": "STRING",
                        "nullable": True,
                        "enum": ["setup", "build", "twist", "punchline", "reaction"],
                    },
                    "intensity": {"type": "INTEGER"},
                    "meme_query": {"type": "STRING", "nullable": True},
                    "sfx_query": {"type": "STRING", "nullable": True},
                    "sticker": {"type": "STRING", "nullable": True},
                },
                "required": ["from", "text"],
            },
        },
    },
    "required": ["title", "characters", "messages"],
}

MOCK_CHAT_RESPONSE = {
    "title": "Bất ngờ nửa đêm",
    "music_mood": "vui_nhon",
    "characters": [
        {"id": "me", "name": "Tôi", "side": "right"},
        {"id": "a", "name": "Nam", "side": "left"},
    ],
    "messages": [
        {
            "from": "a",
            "text": "Còn thức không ông ơi?",
            "beat_role": "setup",
            "intensity": 2,
            "sticker": None,
        },
        {
            "from": "me",
            "text": "Sao thế, có chuyện gì à?",
            "beat_role": "build",
            "intensity": 2,
            "sticker": None,
        },
        {
            "from": "a",
            "text": "Vừa thấy ví ông để quên ở quán!",
            "beat_role": "twist",
            "intensity": 5,
            "meme_query": "cat shocked",
            "sfx_query": "vine boom",
            "sticker": "soc",
        },
        {
            "from": "me",
            "text": "Ủa thật hả trời ơi?",
            "beat_role": "reaction",
            "intensity": 3,
            "sticker": None,
        },
        {
            "from": "a",
            "text": "Thật mà, nhân viên đang giữ này.",
            "beat_role": "build",
            "intensity": 2,
            "sticker": None,
        },
        {
            "from": "me",
            "text": "May quá, cảm ơn ông nhiều nha!",
            "beat_role": "build",
            "intensity": 2,
            "sticker": None,
        },
        {
            "from": "a",
            "text": "Mai nhớ bao trà sữa là được haha.",
            "beat_role": "build",
            "intensity": 3,
            "sticker": None,
        },
        {
            "from": "me",
            "text": "Ok chốt luôn bạn ơi!",
            "beat_role": "punchline",
            "intensity": 4,
            "meme_query": "thumbs up happy",
            "sticker": "ok",
        },
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
            st = str(st).strip().lower()
            if st not in VALID_STICKER_TAGS:
                st = None

        raw_role = str(m.get("beat_role") or "").strip().lower()
        beat_role = (
            raw_role if raw_role in ("setup", "build", "twist", "punchline", "reaction") else None
        )
        raw_int = m.get("intensity")
        if raw_int is None:
            intensity = 4 if (st or m.get("meme_query") or m.get("sfx_query")) else 2
        else:
            try:
                intensity = max(1, min(5, int(raw_int)))
            except (TypeError, ValueError):
                intensity = 2

        meme_q = str(m.get("meme_query") or "").strip()[:80] or None
        sfx_q = str(m.get("sfx_query") or "").strip()[:60] or None

        msg_entry: dict[str, Any] = {
            "from": sender,
            "text": text,
            "sticker": st,
            "beat_role": beat_role,
            "intensity": intensity,
            "meme_query": meme_q,
            "sfx_query": sfx_q,
        }
        if m.get("meme_id"):
            msg_entry["meme_id"] = str(m["meme_id"])
        if m.get("sfx_id"):
            msg_entry["sfx_id"] = str(m["sfx_id"])
        if m.get("asset_origin") in ("local", "online_fetched"):
            msg_entry["asset_origin"] = m["asset_origin"]
        if m.get("display_text"):
            msg_entry["display_text"] = str(m["display_text"])
        if m.get("spoken_text") is not None:
            msg_entry["spoken_text"] = str(m["spoken_text"])
        if m.get("media_type") in ("none", "image", "video"):
            msg_entry["media_type"] = m["media_type"]
        if m.get("media_path"):
            msg_entry["media_path"] = str(m["media_path"])
        if m.get("media_hint"):
            msg_entry["media_hint"] = str(m["media_hint"])[:120]
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

    # 3. Siết mật độ sticker/meme & SFX bằng PacingGovernor (khóa cứng mật độ + giãn cách)
    from hbt.shared.asset_director.models import BeatCue, PacingPolicy
    from hbt.shared.asset_director.pacing import PacingGovernor

    governor = PacingGovernor(PacingPolicy.for_engine("chatting"))
    est_t = 0.4
    cues: list[BeatCue] = []
    for idx, m in enumerate(clean_msgs):
        txt = str(m.get("text") or "")
        cues.append(
            BeatCue(
                index=idx,
                text=txt,
                beat_role=m.get("beat_role") or ("setup" if idx == 0 else "reaction"),
                intensity=int(m.get("intensity", 2)),
                meme_query=m.get("meme_query"),
                sticker_tag=m.get("sticker"),
                sfx_query=m.get("sfx_query"),
                est_time_s=round(est_t, 2),
            )
        )
        est_t += max(1.3, min(5.5, len(txt) / 14.0)) + 0.85

    chosen_set = set(governor.select_visual_beats(cues))
    chosen_sfx_set = set(governor.select_sfx_beats(cues))

    dropped_stickers = 0
    for idx, m in enumerate(clean_msgs):
        had_visual = bool(m.get("sticker") or m.get("meme_query") or m.get("meme_id"))
        if had_visual and idx not in chosen_set:
            m["sticker"] = None
            m["meme_query"] = None
            m["meme_id"] = None
            m["asset_origin"] = None
            dropped_stickers += 1
        if idx not in chosen_sfx_set:
            m["sfx_query"] = None
            m["sfx_id"] = None

    # 4. Tạo cảnh báo (warnings)
    if cut_msgs_count > 0:
        warnings.append(
            f"Đã cắt bớt {cut_msgs_count} tin nhắn ở giữa (giữ tin đầu và 2 tin cuối) "
            "để kịch bản không vượt quá 5.000 ký tự."
        )
    if dropped_stickers > 0:
        warnings.append(
            f"Đã lược bỏ {dropped_stickers} sticker/meme thừa "
            f"để giữ tối đa {governor.effective_max_visual(len(clean_msgs))} điểm cao trào."
        )

    data["messages"] = clean_msgs
    data["warnings"] = warnings
    return data


def _unwrap_chat_payload(parsed: Any, fallback_title: str = "") -> dict[str, Any] | None:
    """Bóc tách & phục hồi cấu trúc JSON Chatting từ phản hồi Gemini (bọc khóa/mảng/thiếu title)."""
    cur: Any = parsed
    if isinstance(cur, list) and len(cur) == 1 and isinstance(cur[0], dict):
        cur = cur[0]
    if not isinstance(cur, dict):
        return None

    # Nếu bọc trong khóa trung gian (data/chat/script/result/conversation...) thì tự bóc ra
    if not (isinstance(cur.get("characters"), list) and isinstance(cur.get("messages"), list)):
        for key in _WRAPPER_KEYS:
            inner = cur.get(key)
            if isinstance(inner, dict) and (
                isinstance(inner.get("characters"), list) or isinstance(inner.get("messages"), list)
            ):
                cur = inner
                break

    if not isinstance(cur.get("characters"), list) or not isinstance(cur.get("messages"), list):
        return None

    out = dict(cur)
    if not str(out.get("title") or "").strip():
        out["title"] = (fallback_title or "").strip()[:200] or "Đoạn chat vui"
    return out


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
            "models": AVAILABLE_GEMINI_MODELS,
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
            response_schema=CHAT_JSON_SCHEMA,
            max_output_tokens=CHATTING_MAX_OUTPUT_TOKENS,
        )
        unwrapped = _unwrap_chat_payload(parsed, fallback_title=title)

        # Tự động retry 1 lần kèm nhắc cấu trúc JSON nếu thiếu characters/messages
        if unwrapped is None:
            raw_preview = json.dumps(parsed, ensure_ascii=False)[:300]
            keys = list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__
            logger.warning(
                "Gemini thiếu trường bắt buộc (lần 1), keys=%s, preview=%s — thử lại 1 lần",
                keys,
                raw_preview,
            )
            retry_prompt = (
                f"{user_content}\n\n"
                "LƯU Ý BẮT BUỘC: Phản hồi trước thiếu trường bắt buộc. "
                "Hãy trả về ĐÚNG 1 JSON object ở cấp gốc gồm đủ 3 khóa: "
                "`title` (chuỗi), `characters` (mảng ít nhất 2 nhân vật), "
                "`messages` (mảng ít nhất 8 tin nhắn). Không bọc trong khóa trung gian."
            )
            parsed_retry, retry_timings = generate_structured_json(
                SYSTEM_PROMPT,
                retry_prompt,
                model=self.model,
                timeout=self.timeout,
                response_schema=CHAT_JSON_SCHEMA,
                max_output_tokens=CHATTING_MAX_OUTPUT_TOKENS,
            )
            timings["llm_s"] = round(
                float(timings.get("llm_s", 0.0)) + float(retry_timings.get("llm_s", 0.0)), 3
            )
            timings["llm_tokens"] = int(timings.get("llm_tokens", 0)) + int(
                retry_timings.get("llm_tokens", 0)
            )
            timings["llm_retry"] = int(timings.get("llm_retry", 0)) + 1
            unwrapped = _unwrap_chat_payload(parsed_retry, fallback_title=title)
            if unwrapped is None:
                retry_preview = json.dumps(parsed_retry, ensure_ascii=False)[:300]
                retry_keys = (
                    list(parsed_retry.keys())
                    if isinstance(parsed_retry, dict)
                    else type(parsed_retry).__name__
                )
                logger.warning(
                    "Gemini vẫn thiếu trường bắt buộc sau retry, keys=%s, preview=%s",
                    retry_keys,
                    retry_preview,
                )
                raise RuntimeError(
                    "Gemini trả về JSON thiếu trường bắt buộc title, characters, messages"
                )

        sanitized = sanitize_chat_raw(unwrapped)
        return sanitized, timings
