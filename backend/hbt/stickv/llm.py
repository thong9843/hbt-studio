"""Sinh kịch bản StickV (Gemini API nén token, Import JSON Web Gemini 0 token & Tách lời thoại)."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from hbt.shared.llm import GEMINI_MODEL, generate_structured_json
from hbt.stickv.models import StickvAspect, StickvBeat
from hbt.stickv.poses_init import DEFAULT_POSES

VALID_MOTIONS = {"bounce", "slide_left", "slide_right", "shake", "float", "static"}
VALID_BOARD_TYPES = {"none", "bullets", "big_number", "comparison", "flow_steps"}
VALID_SFX = {"none", "whoosh", "pop", "vine_boom", "ding"}

# System prompt nén gọn (~40% ít token hơn) theo cấu trúc giữ chân 5 chặng
_SYSTEM_PROMPT = (
    "Biên kịch video Người que (Stickman 2D/2.5D) kênh Hay Biết Tuốt. "
    "Cấu trúc 5 chặng: 1.Hook nghịch lý -> 2.Phá vỡ lầm tưởng -> 3.Hé lộ sự thật -> "
    "4.Bài học cốt lõi -> 5.Câu hỏi & CTA. Trả về JSON thuần, không markdown.\n"
    "pose: explain|think|shock|happy|run|rich|sad|angry. "
    "motion: bounce|slide_left|slide_right|shake|float|static. "
    "sfx_tag: none|whoosh|pop|vine_boom|ding. "
    "board_type: bullets|big_number|comparison|flow_steps|none.\n"
    "board_data: bullets={items:[...],takeaway}, big_number={value,label,sub,takeaway}, "
    "comparison={left_title,left_items,right_title,right_items,takeaway}, "
    "flow_steps={steps:[...],takeaway}."
)


def build_director_prompt(
    *,
    idea: str = "<CHỦ ĐỀ VIDEO>",
    topic: str = "science",
    aspect: StickvAspect = "9:16",
    target_minutes: float = 1.0,
) -> str:
    """Tạo Prompt Đạo diễn chuẩn 5 chặng để người dùng copy sang Web Gemini Pro (0 Token API)."""
    beat_count = max(6, min(14, round(target_minutes * 7)))
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Chủ đề: {idea}\n"
        f"Nhóm: {topic} | Khung: {aspect} | Số beat: {beat_count}\n"
        'Schema JSON:\n{"title":"Tiêu đề","beats":[{"narration":"1-2 câu tiếng Việt",'
        '"pose":"explain","facing":"right","motion":"bounce","sfx_tag":"whoosh",'
        '"board_type":"bullets","board_title":"Tiêu đề bảng",'
        '"board_data":{"items":["Ý 1","Ý 2"],"takeaway":"Chốt lại ngắn"}}]}'
    )


def _sanitize_board_data(board_type: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    takeaway = str(raw.get("takeaway") or "").strip()[:90]
    if board_type == "bullets":
        items = [str(x).strip()[:90] for x in (raw.get("items") or []) if str(x).strip()][:5]
        res: dict[str, Any] = {"items": items or ["Điểm chính cần nhớ"]}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "big_number":
        res = {
            "value": str(raw.get("value") or "100%").strip()[:24],
            "label": str(raw.get("label") or "").strip()[:60],
            "sub": str(raw.get("sub") or "").strip()[:90],
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "comparison":
        res = {
            "left_title": str(raw.get("left_title") or "Trước").strip()[:32],
            "left_items": [
                str(x).strip()[:70] for x in (raw.get("left_items") or []) if str(x).strip()
            ][:4],
            "right_title": str(raw.get("right_title") or "Sau").strip()[:32],
            "right_items": [
                str(x).strip()[:70] for x in (raw.get("right_items") or []) if str(x).strip()
            ][:4],
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "flow_steps":
        steps = [str(x).strip()[:50] for x in (raw.get("steps") or []) if str(x).strip()][:4]
        res = {"steps": steps or ["Bước 1", "Bước 2"]}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    return {}


def sanitize_beats(raw_beats: Any, *, chapter: int = 1, start_idx: int = 1) -> list[StickvBeat]:
    """Chuẩn hóa danh sách beat từ Gemini JSON thành StickvBeat hợp lệ."""
    if not isinstance(raw_beats, list):
        return []
    out: list[StickvBeat] = []
    for item in raw_beats:
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration") or "").strip()
        if not narration:
            continue
        pose = str(item.get("pose") or "explain").strip().lower()
        if pose not in DEFAULT_POSES:
            pose = "explain"
        motion = str(item.get("motion") or "bounce").strip().lower()
        if motion not in VALID_MOTIONS:
            motion = "bounce"
        sfx = str(item.get("sfx_tag") or "whoosh").strip().lower()
        if sfx not in VALID_SFX:
            sfx = "whoosh"
        btype = str(item.get("board_type") or "bullets").strip().lower()
        if btype not in VALID_BOARD_TYPES:
            btype = "bullets"
        facing = "left" if str(item.get("facing") or "right").strip().lower() == "left" else "right"
        idx = start_idx + len(out)
        out.append(
            StickvBeat(
                id=f"b{idx:03d}",
                chapter=chapter,
                narration=narration[:750],
                pose=pose,
                facing=facing,
                motion=motion,  # type: ignore[arg-type]
                sfx_tag=sfx,  # type: ignore[arg-type]
                board_type=btype,  # type: ignore[arg-type]
                board_title=str(item.get("board_title") or "").strip()[:80],
                board_data=_sanitize_board_data(btype, item.get("board_data")),
            )
        )
    return out


def parse_stickv_json_payload(raw_text: str) -> tuple[str, list[StickvBeat]]:
    """Phân tích JSON dán từ Web Gemini Pro (0 Token API)."""
    clean = (raw_text or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean).strip()
    if not clean:
        raise ValueError("Vui lòng dán nội dung JSON kịch bản")
    parsed = json.loads(clean)
    if isinstance(parsed, list):
        title = "Kịch bản StickV (JSON)"
        beats = sanitize_beats(parsed)
    elif isinstance(parsed, dict):
        title = str(parsed.get("title") or "Kịch bản StickV (JSON)").strip()[:160]
        beats = sanitize_beats(parsed.get("beats"))
    else:
        raise ValueError("JSON phải là object {title, beats} hoặc mảng beats")
    if not beats:
        raise ValueError("Không tìm thấy beat hợp lệ trong JSON")
    return title, beats


def split_raw_narration_to_beats(raw_text: str, *, title: str = "") -> tuple[str, list[StickvBeat]]:
    """Tách văn bản lời thoại có sẵn thành từng beat StickV (Không cần AI)."""
    clean = (raw_text or "").strip()
    if not clean:
        raise ValueError("Vui lòng nhập hoặc dán lời thoại")

    chunks: list[str] = []
    for para in clean.splitlines():
        para = para.strip()
        if not para:
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", para) if s.strip()]
        buf = ""
        for s in sentences:
            if buf and len(buf) + len(s) > 170:
                chunks.append(buf)
                buf = s
            else:
                buf = f"{buf} {s}".strip() if buf else s
        if buf:
            chunks.append(buf)

    if not chunks:
        raise ValueError("Không tách được câu thoại nào hợp lệ")

    beats: list[StickvBeat] = []
    total = len(chunks)
    for idx, line in enumerate(chunks, start=1):
        low = line.lower()
        num_match = re.search(r"\b(\d+(?:[.,]\d+)?%|\d+\s*(?:triệu|tỷ|nghìn|năm|ngày|lần))\b", low)
        if idx == 1:
            pose, motion, sfx = "shock", "slide_left", "vine_boom"
        elif idx == total:
            pose, motion, sfx = "happy", "bounce", "ding"
        elif any(k in low for k in ("tại sao", "vì sao", "liệu", "?")):
            pose, motion, sfx = "think", "float", "pop"
        elif any(k in low for k in ("tiền", "giàu", "lương", "lãi")):
            pose, motion, sfx = "rich", "bounce", "ding"
        elif any(k in low for k in ("sai lầm", "mất", "nguy hiểm", "tức", "cảnh báo")):
            pose, motion, sfx = "angry", "shake", "vine_boom"
        else:
            pose, motion, sfx = "explain", "bounce", "whoosh"

        if num_match:
            btype = "big_number"
            bdata: dict[str, Any] = {
                "value": num_match.group(1).upper(),
                "label": line[:60],
                "takeaway": "Con số đáng chú ý",
            }
        else:
            btype = "bullets"
            bdata = {"items": [line[:88]]}

        beats.append(
            StickvBeat(
                id=f"b{idx:03d}",
                chapter=1 + (idx - 1) // 8,
                narration=line[:750],
                pose=pose,
                facing="right" if idx % 2 == 1 else "left",
                motion=motion,  # type: ignore[arg-type]
                sfx_tag=sfx,  # type: ignore[arg-type]
                board_type=btype,  # type: ignore[arg-type]
                board_title=f"Điểm #{idx}",
                board_data=bdata,
            )
        )

    final_title = (title or chunks[0][:60]).strip() or "Kịch bản StickV"
    return final_title, beats


def generate_stickv_script(
    *,
    idea: str,
    topic: str = "science",
    aspect: StickvAspect = "9:16",
    target_minutes: float = 1.0,
    model: str | None = None,
) -> tuple[str, list[StickvBeat], dict[str, Any]]:
    """Sinh kịch bản StickV; tự chia lô theo chương nếu target_minutes > 2.5 phút."""
    chosen_model = (model or "").strip() or GEMINI_MODEL
    clean_idea = (idea or "").strip()
    if not clean_idea:
        raise ValueError("Vui lòng nhập ý tưởng hoặc chủ đề video")

    if target_minutes <= 2.5:
        beat_count = max(5, min(14, round(target_minutes * 7)))
        user_prompt = (
            f"Chủ đề: {clean_idea} | Nhóm: {topic} | Khung: {aspect} | {beat_count} beat.\n"
            'JSON: {"title":"...","beats":[{"narration":"...","pose":"explain","facing":"right",'
            '"motion":"bounce","sfx_tag":"whoosh","board_type":"bullets","board_title":"...",'
            '"board_data":{"items":["..."],"takeaway":"..."}}]}'
        )
        parsed, timings = generate_structured_json(
            _SYSTEM_PROMPT, user_prompt, model=chosen_model, timeout=60.0
        )
        title = str(parsed.get("title") or clean_idea[:80]).strip()
        beats = sanitize_beats(parsed.get("beats"), chapter=1, start_idx=1)
        return title, beats, {"chapters": 1, **timings}

    num_chapters = max(2, min(6, math.ceil(target_minutes / 2.5)))
    outline_prompt = (
        f"Video {target_minutes:.0f}p ({aspect}, {topic}): {clean_idea}. "
        f"Lập dàn ý {num_chapters} chương theo cấu trúc 5 chặng.\n"
        'JSON: {"title":"...","chapters":[{"chapter":1,"heading":"...","summary":"..."}]}'
    )
    outline, t0 = generate_structured_json(
        _SYSTEM_PROMPT, outline_prompt, model=chosen_model, timeout=60.0
    )
    title = str(outline.get("title") or clean_idea[:80]).strip()
    raw_chapters = outline.get("chapters") or []
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raw_chapters = [
            {"chapter": i + 1, "heading": f"Phần {i + 1}", "summary": clean_idea}
            for i in range(num_chapters)
        ]

    all_beats: list[StickvBeat] = []
    total_llm_s = float(t0.get("llm_s") or 0.0)
    for ch_idx, ch in enumerate(raw_chapters[:num_chapters], start=1):
        heading = str((ch or {}).get("heading") or f"Chương {ch_idx}")
        summary = str((ch or {}).get("summary") or clean_idea)
        ch_prompt = (
            f"Video: {title} | Chương {ch_idx}/{num_chapters}: {heading} ({summary}). "
            "Viết 7-9 beat.\n"
            'JSON: {"beats":[{"narration":"...","pose":"explain","facing":"right",'
            '"motion":"bounce","sfx_tag":"whoosh","board_type":"bullets",'
            '"board_title":"...","board_data":{}}]}'
        )
        ch_parsed, ch_t = generate_structured_json(
            _SYSTEM_PROMPT, ch_prompt, model=chosen_model, timeout=60.0
        )
        total_llm_s += float(ch_t.get("llm_s") or 0.0)
        ch_beats = sanitize_beats(
            ch_parsed.get("beats"), chapter=ch_idx, start_idx=len(all_beats) + 1
        )
        all_beats.extend(ch_beats)

    return (
        title,
        all_beats,
        {
            "chapters": len(raw_chapters[:num_chapters]),
            "llm_s": round(total_llm_s, 3),
            "model": chosen_model,
        },
    )
