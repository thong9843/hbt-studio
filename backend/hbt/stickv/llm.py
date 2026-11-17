"""Sinh kịch bản StickV theo từng beat bằng Gemini (hỗ trợ chia lô cho video dài 5-15 phút)."""

from __future__ import annotations

import math
from typing import Any

from hbt.shared.llm import GEMINI_MODEL, generate_structured_json
from hbt.stickv.models import StickvAspect, StickvBeat
from hbt.stickv.poses_init import DEFAULT_POSES

VALID_MOTIONS = {"bounce", "slide_left", "slide_right", "shake", "float", "static"}
VALID_BOARD_TYPES = {"none", "bullets", "big_number", "comparison", "flow_steps"}
VALID_SFX = {"none", "whoosh", "pop", "vine_boom", "ding"}

_SYSTEM_PROMPT = """Bạn là biên kịch video giải thích kiến thức phong cách Người que (Stickman 2D/2.5D) cho kênh Hay Biết Tuốt.
Nhiệm vụ: chia nội dung thành các beat ngắn (mỗi beat 1-2 câu tiếng Việt tự nhiên, dễ đọc thành tiếng).
Trả về đúng JSON object theo schema yêu cầu, KHÔNG thêm markdown hay giải thích ngoài JSON.

Quy tắc:
- pose chỉ chọn trong: explain, think, shock, happy, run, rich, sad, angry.
- motion chỉ chọn trong: bounce, slide_left, slide_right, shake, float, static.
- sfx_tag chỉ chọn trong: none, whoosh, pop, vine_boom, ding.
- board_type chỉ chọn trong: none, bullets, big_number, comparison, flow_steps.
- Cấu trúc board_data tương ứng:
  * bullets: {"items": ["ý 1 ngắn", "ý 2 ngắn", "ý 3 ngắn"]}
  * big_number: {"value": "85%", "label": "tiêu đề ngắn", "sub": "giải thích 1 dòng"}
  * comparison: {"left_title": "Cách cũ", "left_items": ["..."], "right_title": "Cách mới", "right_items": ["..."]}
  * flow_steps: {"steps": ["Bước 1", "Bước 2", "Bước 3"]}
  * none: {}"""


def _sanitize_board_data(board_type: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    if board_type == "bullets":
        items = [str(x).strip()[:90] for x in (raw.get("items") or []) if str(x).strip()][:5]
        return {"items": items or ["Điểm chính cần nhớ"]}
    if board_type == "big_number":
        return {
            "value": str(raw.get("value") or "100%").strip()[:24],
            "label": str(raw.get("label") or "").strip()[:60],
            "sub": str(raw.get("sub") or "").strip()[:90],
        }
    if board_type == "comparison":
        return {
            "left_title": str(raw.get("left_title") or "Trước").strip()[:32],
            "left_items": [str(x).strip()[:70] for x in (raw.get("left_items") or []) if str(x).strip()][:4],
            "right_title": str(raw.get("right_title") or "Sau").strip()[:32],
            "right_items": [str(x).strip()[:70] for x in (raw.get("right_items") or []) if str(x).strip()][:4],
        }
    if board_type == "flow_steps":
        steps = [str(x).strip()[:50] for x in (raw.get("steps") or []) if str(x).strip()][:4]
        return {"steps": steps or ["Bước 1", "Bước 2"]}
    return {}


def sanitize_beats(raw_beats: Any, *, chapter: int = 1, start_idx: int = 1) -> list[StickvBeat]:
    """Chuẩn hóa danh sách beat từ Gemini JSON thành StickvBeat hợp lệ."""
    if not isinstance(raw_beats, list):
        return []
    out: list[StickvBeat] = []
    for offset, item in enumerate(raw_beats):
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
            f"Chủ đề: {clean_idea}\n"
            f"Nhóm nội dung: {topic} | Khung hình: {aspect}\n"
            f"Hãy viết kịch bản gồm {beat_count} beat.\n"
            'Schema JSON: {"title": "Tiêu đề hấp dẫn", "beats": [{"narration": "...", "pose": "explain", '
            '"facing": "right", "motion": "bounce", "sfx_tag": "whoosh", "board_type": "bullets", '
            '"board_title": "...", "board_data": {"items": ["..."]}}]}'
        )
        parsed, timings = generate_structured_json(
            _SYSTEM_PROMPT, user_prompt, model=chosen_model, timeout=60.0
        )
        title = str(parsed.get("title") or clean_idea[:80]).strip()
        beats = sanitize_beats(parsed.get("beats"), chapter=1, start_idx=1)
        return title, beats, {"chapters": 1, **timings}

    # Longform 5-15 phút: chia thành các chương 2-3 phút để tránh quá tải token & RAM
    num_chapters = max(2, min(6, math.ceil(target_minutes / 2.5)))
    outline_prompt = (
        f"Chủ đề video dài ({target_minutes:.0f} phút, {aspect}, nhóm {topic}): {clean_idea}\n"
        f"Hãy lập dàn ý gồm đúng {num_chapters} chương mạch lạc.\n"
        'Schema JSON: {"title": "Tiêu đề video", "chapters": [{"chapter": 1, "heading": "...", "summary": "..."}]}'
    )
    outline, t0 = generate_structured_json(
        _SYSTEM_PROMPT, outline_prompt, model=chosen_model, timeout=60.0
    )
    title = str(outline.get("title") or clean_idea[:80]).strip()
    raw_chapters = outline.get("chapters") or []
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raw_chapters = [{"chapter": i + 1, "heading": f"Phần {i + 1}", "summary": clean_idea} for i in range(num_chapters)]

    all_beats: list[StickvBeat] = []
    total_llm_s = float(t0.get("llm_s") or 0.0)
    for ch_idx, ch in enumerate(raw_chapters[:num_chapters], start=1):
        heading = str((ch or {}).get("heading") or f"Chương {ch_idx}")
        summary = str((ch or {}).get("summary") or clean_idea)
        ch_prompt = (
            f"Video: {title}\n"
            f"Chương {ch_idx}/{num_chapters}: {heading}\n"
            f"Tóm tắt chương: {summary}\n"
            "Hãy viết 7-9 beat cho riêng chương này.\n"
            'Schema JSON: {"beats": [{"narration": "...", "pose": "explain", "facing": "right", '
            '"motion": "bounce", "sfx_tag": "whoosh", "board_type": "bullets", "board_title": "...", "board_data": {}}]}'
        )
        ch_parsed, ch_t = generate_structured_json(
            _SYSTEM_PROMPT, ch_prompt, model=chosen_model, timeout=60.0
        )
        total_llm_s += float(ch_t.get("llm_s") or 0.0)
        ch_beats = sanitize_beats(
            ch_parsed.get("beats"), chapter=ch_idx, start_idx=len(all_beats) + 1
        )
        all_beats.extend(ch_beats)

    return title, all_beats, {"chapters": len(raw_chapters[:num_chapters]), "llm_s": round(total_llm_s, 3), "model": chosen_model}
