"""Sinh kịch bản StickV (Gemini API nén token, Import JSON Web Gemini 0 token & Tách lời thoại)."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from hbt.shared.llm import GEMINI_MODEL, generate_structured_json
from hbt.stickv.backdrops import normalize_domain
from hbt.stickv.models import StickvAspect, StickvBeat
from hbt.stickv.poses_init import DEFAULT_POSES

POSES_V8: tuple[str, ...] = (
    "point_up",
    "think_chin",
    "arms_crossed",
    "hands_on_hips",
    "shrug_ask",
    "present_board",
    "emphatic_chop",
    "shock_hands_up",
    "lean_secret",
    "count_points",
    "walk_explore",
    "idle_breathe",
)
VALID_MOTIONS = {"bounce", "slide_left", "slide_right", "float", "static"}
VALID_CAMERA_SHOTS = {"wide_stage", "focus_board", "closeup_react"}
VALID_BOARD_TYPES = {
    "none",
    "bullets",
    "big_number",
    "comparison",
    "flow_steps",
    "card",
    "list",
    "quote",
    "bar_compare",
    "counter_grow",
    "timeline_era",
    "location_map",
    "myth_vs_fact",
}
VALID_INTERACTIONS = {"none", "hold_prop", "point_chart", "versus_split"}
VALID_SFX = {"none", "whoosh", "pop", "vine_boom", "ding"}


def _build_system_prompt(available_poses: list[str] | None = None) -> str:
    extra = [p for p in (available_poses or []) if p not in POSES_V8]
    pose_str = "|".join([*POSES_V8, *extra[:20]])
    return (
        "Biên kịch video Người que (Stickman 2D/2.5D) kênh Hay Biết Tuốt. "
        "Cấu trúc 5 chặng: 1.Hook nghịch lý -> 2.Phá vỡ lầm tưởng -> 3.Hé lộ sự thật -> "
        "4.Bài học cốt lõi -> 5.Câu hỏi & CTA. Trả về JSON thuần, không markdown.\n"
        "Mỗi beat chỉ dài 1-2 câu ngắn (12-22 từ), dùng dấu chấm/phẩy rõ ràng "
        "để tạo nhịp ngắt tự nhiên cho VieNeu-TTS, không viết câu ghép dài.\n"
        "LUẬT ĐA DẠNG: Không dùng cùng 1 pose cho 2 beat đứng liền kề.\n"
        "Phân loại domain phù hợp: "
        "paper_classic|physics_science|history_geo|psychology_story|cosmos_mystery.\n"
        "music_mood: curious_science|history_epic|funny_quirky|mysterious_tense|calm_lofi.\n"
        f"pose (ưu tiên 12 hành động 2-đoạn khuỷu tay): {pose_str}. "
        "anim_oneshot: null|shock_jump|idea_bulb|point_board|facepalm|nod_agree|celebrate. "
        "anim_loop: talk_explain|talk_excited|think_loop|idle_breathe|walk_loop. "
        "interaction: none|hold_prop|point_chart|versus_split "
        "(nếu hold_prop thêm prop_query 1-2 từ tiếng Anh). "
        "camera_shot: wide_stage|focus_board|closeup_react. "
        "motion: bounce|slide_left|slide_right|float|static. "
        "sfx_tag: none|whoosh|pop|vine_boom|ding. "
        "board_type: bullets|big_number|comparison|flow_steps|"
        "bar_compare|counter_grow|timeline_era|location_map|myth_vs_fact|card|quote|list|none.\n"
        "board_data: bullets={items:[...],takeaway}, "
        "big_number={value,label,sub,takeaway}, "
        "bar_compare={values:[{label,value}],takeaway}, counter_grow={target,unit,label}, "
        "timeline_era={events:[{year,title}],takeaway}, "
        "location_map={location,coordinates,takeaway}, "
        "myth_vs_fact={myth,fact,takeaway}, "
        "comparison={left_title,left_items,right_title,right_items,takeaway}, "
        "flow_steps={steps:[...],takeaway}."
    )


def _target_beat_count(target_minutes: float) -> int:
    m = max(0.5, float(target_minutes))
    if m <= 1.2:
        return 10
    if m <= 3.5:
        return 24
    if m <= 5.5:
        return 40
    if m <= 8.5:
        return 60
    return max(70, min(85, round(m * 7.8)))


def build_director_prompt(
    *,
    idea: str = "<CHỦ ĐỀ VIDEO>",
    topic: str = "science",
    aspect: StickvAspect = "9:16",
    target_minutes: float = 1.0,
    available_poses: list[str] | None = None,
) -> str:
    """Tạo Prompt Đạo diễn chuẩn 5 chặng để người dùng copy sang Web Gemini Pro (0 Token API)."""
    beat_count = _target_beat_count(target_minutes)
    sys_p = _build_system_prompt(available_poses)
    return (
        f"{sys_p}\n\n"
        f"Chủ đề: {idea}\n"
        f"Nhóm: {topic} | Khung: {aspect} | Số beat: {beat_count}\n"
        'Schema JSON:\n{"title":"Tiêu đề","domain":"physics_science",'
        '"music_mood":"curious_science",'
        '"beats":[{"narration":"1-2 câu tiếng Việt","pose":"point_up","camera_shot":"wide_stage",'
        '"anim_oneshot":"idea_bulb","anim_loop":"talk_explain","interaction":"hold_prop",'
        '"prop_query":"brain","facing":"right","motion":"bounce","sfx_tag":"whoosh",'
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
    if board_type in (
        "bar_compare",
        "counter_grow",
        "card",
        "quote",
        "list",
        "timeline_era",
        "location_map",
        "myth_vs_fact",
    ):
        return dict(raw)
    return {}


def enforce_pose_diversity(beats: list[StickvBeat]) -> list[StickvBeat]:
    """Đảm bảo không bao giờ có 2 beat đứng liền kề lặp lại cùng một `pose`."""
    if len(beats) <= 1:
        return beats
    from hbt.stickv.puppet import normalize_stickv_pose

    out: list[StickvBeat] = [beats[0]]
    cycle_idx = 0
    for b in beats[1:]:
        prev_norm = normalize_stickv_pose(out[-1].pose)
        cur_norm = normalize_stickv_pose(b.pose)
        if cur_norm == prev_norm:
            cand = POSES_V8[cycle_idx % len(POSES_V8)]
            cycle_idx += 1
            if cand == prev_norm:
                cand = POSES_V8[cycle_idx % len(POSES_V8)]
                cycle_idx += 1
            b = b.model_copy(update={"pose": cand})
        out.append(b)
    return out


def sanitize_beats(
    raw_beats: Any,
    *,
    chapter: int = 1,
    chapter_title: str = "",
    start_idx: int = 1,
    allowed_poses: set[str] | None = None,
) -> list[StickvBeat]:
    """Chuẩn hóa danh sách beat từ Gemini JSON thành StickvBeat hợp lệ."""
    if not isinstance(raw_beats, list):
        return []
    valid_poses = (allowed_poses or set(DEFAULT_POSES)) | set(POSES_V8)
    out: list[StickvBeat] = []
    for item in raw_beats:
        if not isinstance(item, dict):
            continue
        narration = str(item.get("narration") or item.get("text") or "").strip()
        if not narration:
            continue
        pose = str(item.get("pose") or "explain").strip().lower()
        if pose not in valid_poses:
            pose = "explain"
        motion = str(item.get("motion") or "bounce").strip().lower()
        if motion == "shake":
            motion = "float"
        elif motion not in VALID_MOTIONS:
            motion = "bounce"
        sfx = str(item.get("sfx_tag") or item.get("sfx") or "whoosh").strip().lower()
        if sfx not in VALID_SFX:
            sfx = "whoosh"
        btype = str(item.get("board_type") or item.get("visual_type") or "bullets").strip().lower()
        if btype not in VALID_BOARD_TYPES:
            btype = "bullets"
        interaction = str(item.get("interaction") or "none").strip().lower()
        if interaction not in VALID_INTERACTIONS:
            interaction = "none"
        camera_shot = str(item.get("camera_shot") or "wide_stage").strip().lower()
        if camera_shot not in VALID_CAMERA_SHOTS:
            camera_shot = "wide_stage"
        anim_oneshot = str(item.get("anim_oneshot") or "").strip() or None
        anim_loop = str(item.get("anim_loop") or "talk_explain").strip() or "talk_explain"
        prop_query = str(item.get("prop_query") or "").strip()[:80] or None
        raw_vdata = item.get("visual_data")
        vdata = dict(raw_vdata) if isinstance(raw_vdata, dict) else {}
        raw_items = item.get("board_items")
        bitems = (
            [str(x).strip()[:90] for x in raw_items if str(x).strip()][:5]
            if isinstance(raw_items, list)
            else []
        )
        facing = "left" if str(item.get("facing") or "right").strip().lower() == "left" else "right"
        idx = start_idx + len(out)
        c_title = str(item.get("chapter_title") or (chapter_title if len(out) == 0 else "")).strip()
        out.append(
            StickvBeat(
                id=f"b{idx:03d}",
                chapter=chapter,
                chapter_title=c_title[:120],
                narration=narration[:750],
                pose=pose,
                anim_oneshot=anim_oneshot,
                anim_loop=anim_loop,
                interaction=interaction,  # type: ignore[arg-type]
                camera_shot=camera_shot,  # type: ignore[arg-type]
                prop_query=prop_query,
                facing=facing,
                motion=motion,  # type: ignore[arg-type]
                sfx_tag=sfx,  # type: ignore[arg-type]
                board_type=btype,  # type: ignore[arg-type]
                board_title=str(item.get("board_title") or "").strip()[:80],
                board_items=bitems,
                board_data=_sanitize_board_data(btype, item.get("board_data")),
                visual_data=vdata,
            )
        )
    return out


def parse_stickv_json_payload(
    raw_text: str, *, allowed_poses: set[str] | None = None
) -> tuple[str, list[StickvBeat]]:
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
        beats = sanitize_beats(parsed, allowed_poses=allowed_poses)
    elif isinstance(parsed, dict):
        title = str(parsed.get("title") or "Kịch bản StickV (JSON)").strip()[:160]
        beats = sanitize_beats(parsed.get("beats"), allowed_poses=allowed_poses)
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
            pose, motion, sfx = "angry", "bounce", "vine_boom"
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
    available_poses: list[str] | None = None,
) -> tuple[str, list[StickvBeat], dict[str, Any]]:
    """Sinh kịch bản StickV; tự chia lô theo chương nếu target_minutes > 2.5 phút."""
    chosen_model = (model or "").strip() or GEMINI_MODEL
    clean_idea = (idea or "").strip()
    if not clean_idea:
        raise ValueError("Vui lòng nhập ý tưởng hoặc chủ đề video")

    sys_prompt = _build_system_prompt(available_poses)
    allowed_set = set(available_poses) if available_poses else None

    if target_minutes <= 2.5:
        beat_count = _target_beat_count(target_minutes)
        user_prompt = (
            f"Chủ đề: {clean_idea} | Nhóm: {topic} | Khung: {aspect} | {beat_count} beat.\n"
            'JSON: {"title":"...","domain":"history_geo","music_mood":"history_epic",'
            '"beats":[{"narration":"...","pose":"point_up","camera_shot":"wide_stage",'
            '"facing":"right","motion":"bounce","sfx_tag":"whoosh","board_type":"bullets",'
            '"board_title":"...","board_data":{"items":["..."],"takeaway":"..."}}]}'
        )
        parsed, timings = generate_structured_json(
            sys_prompt, user_prompt, model=chosen_model, timeout=60.0
        )
        title = str(parsed.get("title") or clean_idea[:80]).strip()
        beats = enforce_pose_diversity(
            sanitize_beats(parsed.get("beats"), chapter=1, start_idx=1, allowed_poses=allowed_set)
        )
        return (
            title,
            beats,
            {
                "chapters": 1,
                "chapter_list": [],
                "domain": normalize_domain(parsed.get("domain")),
                "music_mood": str(parsed.get("music_mood") or "curious_science").strip(),
                **timings,
            },
        )

    num_chapters = max(4, min(8, round(target_minutes * 0.8)))
    beats_per_ch = max(7, min(12, math.ceil(_target_beat_count(target_minutes) / num_chapters)))
    outline_prompt = (
        f"Video khám phá {target_minutes:.0f}p ({aspect}, {topic}): {clean_idea}. "
        f"Lập dàn ý {num_chapters} chương hấp dẫn.\n"
        'JSON: {"title":"...","domain":"history_geo","music_mood":"history_epic",'
        '"chapters":[{"chapter":1,"heading":"...","summary":"..."}]}'
    )
    outline, t0 = generate_structured_json(
        sys_prompt, outline_prompt, model=chosen_model, timeout=60.0
    )
    title = str(outline.get("title") or clean_idea[:80]).strip()
    raw_chapters = outline.get("chapters") or []
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raw_chapters = [
            {"chapter": i + 1, "heading": f"Phần {i + 1}", "summary": clean_idea}
            for i in range(num_chapters)
        ]

    all_beats: list[StickvBeat] = []
    chapter_list: list[dict[str, Any]] = []
    total_llm_s = float(t0.get("llm_s") or 0.0)
    for ch_idx, ch in enumerate(raw_chapters[:num_chapters], start=1):
        heading = str((ch or {}).get("heading") or f"Chương {ch_idx}")
        summary = str((ch or {}).get("summary") or clean_idea)
        chapter_list.append({"chapter": ch_idx, "heading": heading, "summary": summary})
        ch_prompt = (
            f"Video: {title} | Chương {ch_idx}/{len(raw_chapters[:num_chapters])}: "
            f"{heading} ({summary}). Viết {beats_per_ch} beat chi tiết, chuyển góc máy linh hoạt.\n"
            'JSON: {"beats":[{"narration":"...","pose":"point_up","camera_shot":"focus_board",'
            '"facing":"right","motion":"bounce","sfx_tag":"whoosh","board_type":"bullets",'
            '"board_title":"...","board_data":{}}]}'
        )
        ch_parsed, ch_t = generate_structured_json(
            sys_prompt, ch_prompt, model=chosen_model, timeout=60.0
        )
        total_llm_s += float(ch_t.get("llm_s") or 0.0)
        ch_beats = sanitize_beats(
            ch_parsed.get("beats"),
            chapter=ch_idx,
            chapter_title=heading,
            start_idx=len(all_beats) + 1,
            allowed_poses=allowed_set,
        )
        all_beats.extend(ch_beats)

    all_beats = enforce_pose_diversity(all_beats)
    return (
        title,
        all_beats,
        {
            "chapters": len(raw_chapters[:num_chapters]),
            "chapter_list": chapter_list,
            "domain": normalize_domain(outline.get("domain")),
            "music_mood": str(outline.get("music_mood") or "curious_science").strip(),
            "llm_s": round(total_llm_s, 3),
            "model": chosen_model,
        },
    )
