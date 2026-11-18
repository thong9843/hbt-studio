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

POSES_V9: tuple[str, ...] = (
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
    "point_board_high",
    "wave_hello",
    "scratch_head",
    "facepalm_light",
    "nod_yes",
    "shake_no",
)
POSES_V8: tuple[str, ...] = POSES_V9
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
    "recap_card",
}
VALID_INTERACTIONS = {"none", "hold_prop", "point_chart", "versus_split"}
VALID_SFX = {"none", "whoosh", "pop", "vine_boom", "ding"}


def _build_system_prompt(available_poses: list[str] | None = None) -> str:
    extra = [p for p in (available_poses or []) if p not in POSES_V9]
    pose_str = "|".join([*POSES_V9, *extra[:16]])
    return (
        "Biên kịch video Người que (Stickman 2D/2.5D) kênh Hay Biết Tuốt. "
        "Cấu trúc 5 chặng: 1.Hook nghịch lý -> 2.Phá vỡ lầm tưởng -> 3.Hé lộ sự thật -> "
        "4.Bài học cốt lõi -> 5.Tóm tắt & CTA. Trả về JSON thuần, không markdown.\n"
        "Mỗi beat chỉ dài 1-2 câu ngắn (12-22 từ), dùng dấu chấm/phẩy rõ ràng "
        "để tạo nhịp ngắt tự nhiên cho VieNeu-TTS, không viết câu ghép dài.\n"
        "LUẬT CẤM CHÉP LỜI THOẠI (ANTI-PARROT): Cấm tuyệt đối chép lại nguyên văn "
        "narration lên bảng! "
        "`board_data` là Tấm Bảng Bằng Chứng & Ghi Chú Khoa Học chứa SỐ LIỆU ĐỊNH LƯỢNG THẬT, "
        "chuỗi cơ chế (Nguyên nhân -> Cơ chế -> Hệ quả), so sánh (Lầm tưởng vs Sự thật), "
        "hoặc thuật ngữ + giải thích + `takeaway`. Cấm cụm sáo rỗng như "
        "'100% Mức độ cảnh báo', 'Thông tin quan trọng', 'Lưu ý đặc biệt'. "
        "Dùng `**từ khóa**` trong `items` để tô sáng từ khóa chính.\n"
        "THẺ CUỐI VIDEO (CTA): 1-2 beat cuối (bình luận / đăng ký kênh) BẮT BUỘC đặt "
        "`board_type='recap_card'`, `board_title='TÓM TẮT 3 Ý CỐT LÕI'`, `items` đúc kết 3 ý "
        "giá trị nhất từ cả video (tuyệt đối không ghi câu kêu gọi đăng ký kênh lên bảng).\n"
        "LUẬT ĐA DẠNG: Không dùng cùng 1 `pose` hoặc 1 `emotion` cho 2 beat đứng liền kề.\n"
        "domain: paper_classic|physics_science|history_geo|psychology_story|cosmos_mystery.\n"
        "music_mood: curious_science|history_epic|funny_quirky|mysterious_tense|calm_lofi.\n"
        f"pose (18 hành động 2-đoạn): {pose_str}.\n"
        "emotion (10 biểu cảm): neutral|confident|curious|idea|shock|skeptical|"
        "serious|sad|happy|excited.\n"
        "anim_oneshot: null|shock_jump|idea_bulb|point_board|facepalm|nod_agree|celebrate. "
        "anim_loop: talk_explain|talk_excited|think_loop|idle_breathe|walk_loop. "
        "interaction: none|hold_prop|point_chart|versus_split "
        "(nếu hold_prop hoặc bullets thêm prop_query 1-2 từ tiếng Anh). "
        "camera_shot: wide_stage|focus_board|closeup_react. "
        "motion: bounce|slide_left|slide_right|float|static. "
        "sfx_tag: none|whoosh|pop|vine_boom|ding. "
        "board_type: bullets|big_number|comparison|flow_steps|bar_compare|counter_grow|"
        "timeline_era|location_map|myth_vs_fact|recap_card|card|quote|list|none.\n"
        "board_data: bullets/recap_card={items:['...**từ khóa**...'],takeaway:'...'}, "
        "big_number={value,label,sub,takeaway}, bar_compare={values:[{label,value}],takeaway}, "
        "counter_grow={target,unit,label}, timeline_era={events:[{year,title}],takeaway}, "
        "location_map={location,coordinates,takeaway}, myth_vs_fact={myth,fact,takeaway}, "
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
        '"beats":[{"narration":"1-2 câu tiếng Việt","pose":"point_up","emotion":"curious",'
        '"camera_shot":"wide_stage","anim_oneshot":"idea_bulb","anim_loop":"talk_explain",'
        '"interaction":"hold_prop","prop_query":"brain","facing":"right","motion":"bounce",'
        '"sfx_tag":"whoosh","board_type":"bullets","board_title":"Số liệu / Cơ chế",'
        '"board_data":{"items":["**Cơ chế** ngắn gọn (<11 từ)","Số liệu thật cụ thể"],'
        '"takeaway":"Chốt lại giá trị ngắn"}}]}'
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
    if board_type == "recap_card":
        raw_items = raw.get("items") or raw.get("bullets") or []
        items = [str(x).strip()[:90] for x in raw_items if str(x).strip()][:3]
        res = {"items": items or ["Ghi nhớ cơ chế cốt lõi"]}
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


_CLICHE_PATTERNS = (
    "100% mức độ cảnh báo",
    "mức độ cảnh báo",
    "thông tin quan trọng",
    "lưu ý đặc biệt",
    "điểm chính cần nhớ",
    "mở đầu video",
    "hãy tìm hiểu",
)
_CTA_KEYWORDS = (
    "đăng ký",
    "subscribe",
    "bình luận",
    "comment",
    "theo dõi",
    "chia sẻ",
    "bấm like",
    "nhấn chuông",
    "ý kiến của bạn",
)


def _word_overlap_ratio(a: str, b: str) -> float:
    wa = {w for w in re.findall(r"[^\W_]+", (a or "").lower()) if len(w) >= 2}
    wb = {w for w in re.findall(r"[^\W_]+", (b or "").lower()) if len(w) >= 2}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def _condense_to_keyword_bullets(narration: str, takeaway: str) -> list[str]:
    clean = (narration or "").strip()
    num_hits = re.findall(r"\d[\d.,]*\s*(?:%|ms|giây|phút|năm|tcn|triệu|tỷ|lần|km|°)?", clean, re.I)
    clauses = [c.strip() for c in re.split(r"[.;:!?…]", clean) if len(c.strip().split()) >= 2]
    out: list[str] = []
    if num_hits and clauses:
        hl = num_hits[0].strip()
        short_c = " ".join(clauses[0].split()[:8])
        if hl and hl in short_c:
            short_c = short_c.replace(hl, f"**{hl}**", 1)
        out.append(short_c)
    else:
        for cl in clauses[:2]:
            words = cl.split()
            if len(words) >= 3:
                out.append(f"**{words[0]} {words[1]}** {' '.join(words[2:8])}".strip())
    if takeaway:
        out.append(f"Cốt lõi: **{takeaway[:45]}**")
    return out[:3] or ["Phân tích cơ chế thực tế"]


def _enforce_meaningful_boards(beats: list[StickvBeat]) -> list[StickvBeat]:
    """Hậu kiểm bảng tri thức: chống lặp sáo rỗng/chép lời thoại & ép CTA cuối thành recap_card."""
    if not beats:
        return beats

    out: list[StickvBeat] = []
    collected_insights: list[str] = []
    n_total = len(beats)

    for idx, beat in enumerate(beats):
        bdata = dict(beat.board_data or {})
        items = [
            str(x).strip() for x in (bdata.get("items") or beat.board_items or []) if str(x).strip()
        ]
        takeaway = str(beat.takeaway or bdata.get("takeaway") or "").strip()
        btitle = (beat.board_title or "").strip()
        btype = beat.board_type

        # 1. Loại bỏ cụm sáo rỗng vô nghĩa
        items = [it for it in items if not any(cl in it.lower() for cl in _CLICHE_PATTERNS)]
        if any(cl in btitle.lower() for cl in _CLICHE_PATTERNS):
            btitle = ""

        # 2. Phát hiện CTA ở 1-2 beat cuối -> chuyển bắt buộc sang recap_card 3 ý cốt lõi
        is_tail = idx >= max(0, n_total - 2)
        low_nar = (beat.narration or "").lower()
        is_cta = is_tail and any(kw in low_nar for kw in _CTA_KEYWORDS)
        if is_cta:
            recap_pts = list(dict.fromkeys(collected_insights))[-3:]
            if len(recap_pts) < 3:
                for prev_b in beats[:idx]:
                    pt = str(prev_b.board_title or "").strip()
                    if (
                        pt
                        and pt not in recap_pts
                        and not any(k in pt.lower() for k in _CTA_KEYWORDS)
                    ):
                        recap_pts.append(f"**{pt}**")
                    if len(recap_pts) >= 3:
                        break
            recap_pts = (
                recap_pts
                or ["Hiểu rõ **nguyên lý gốc**", "Nhận diện **lầm tưởng**", "Áp dụng **thực tế**"]
            )[:3]
            bdata["items"] = recap_pts
            if not takeaway:
                takeaway = "Lưu lại để áp dụng ngay hôm nay"
            bdata["takeaway"] = takeaway
            out.append(
                beat.model_copy(
                    update={
                        "board_type": "recap_card",
                        "board_title": "TÓM TẮT 3 Ý CỐT LÕI",
                        "board_items": recap_pts,
                        "takeaway": takeaway,
                        "board_data": bdata,
                    }
                )
            )
            continue

        # 3. Anti-Parrot Rule: bảng dạng chữ trùng >70% từ với lời thoại -> rút gọn từ khóa/cơ chế
        if btype in ("bullets", "list", "card") and items:
            joined = f"{btitle} {' '.join(items)}".strip()
            if _word_overlap_ratio(beat.narration, joined) > 0.70:
                items = _condense_to_keyword_bullets(beat.narration, takeaway)
                bdata["items"] = items

        if btype in ("bullets", "list", "card") and not items:
            items = _condense_to_keyword_bullets(beat.narration, takeaway)
            bdata["items"] = items

        # Thu thập ý giá trị để nạp cho recap_card cuối video
        if takeaway and not any(k in takeaway.lower() for k in _CTA_KEYWORDS):
            collected_insights.append(takeaway[:72])
        elif items and not any(k in items[0].lower() for k in _CTA_KEYWORDS):
            collected_insights.append(items[0][:72])

        if takeaway:
            bdata["takeaway"] = takeaway
        out.append(
            beat.model_copy(
                update={
                    "board_title": btitle[:120],
                    "board_items": items if items else list(beat.board_items),
                    "takeaway": takeaway[:160],
                    "board_data": bdata,
                }
            )
        )

    return out


def enforce_pose_diversity(beats: list[StickvBeat]) -> list[StickvBeat]:
    """Đảm bảo không có 2 beat đứng liền kề lặp lại cùng một `pose` hoặc `emotion`."""
    if len(beats) <= 1:
        return beats
    from hbt.stickv.puppet import VALID_EMOTIONS, normalize_stickv_pose, resolve_stickv_emotion

    out: list[StickvBeat] = [beats[0]]
    p_cycle = 0
    e_cycle = 0
    for b in beats[1:]:
        prev_pose = normalize_stickv_pose(out[-1].pose)
        cur_pose = normalize_stickv_pose(b.pose)
        updates: dict[str, Any] = {}
        if cur_pose == prev_pose:
            cand = POSES_V9[p_cycle % len(POSES_V9)]
            p_cycle += 1
            if cand == prev_pose:
                cand = POSES_V9[p_cycle % len(POSES_V9)]
                p_cycle += 1
            updates["pose"] = cand

        prev_emo = resolve_stickv_emotion(out[-1].emotion, out[-1].pose, out[-1].narration)
        cur_emo = resolve_stickv_emotion(b.emotion, updates.get("pose", b.pose), b.narration)
        if cur_emo == prev_emo:
            cand_emo = VALID_EMOTIONS[e_cycle % len(VALID_EMOTIONS)]
            e_cycle += 1
            if cand_emo == prev_emo:
                cand_emo = VALID_EMOTIONS[e_cycle % len(VALID_EMOTIONS)]
                e_cycle += 1
            updates["emotion"] = cand_emo

        if updates:
            b = b.model_copy(update=updates)
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
    valid_poses = (allowed_poses or set(DEFAULT_POSES)) | set(POSES_V9)
    from hbt.stickv.puppet import VALID_EMOTIONS

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
        raw_emo = str(item.get("emotion") or "auto").strip().lower()
        emotion = raw_emo if (raw_emo == "auto" or raw_emo in VALID_EMOTIONS) else "auto"
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

        raw_bdata = (
            dict(item.get("board_data") or {}) if isinstance(item.get("board_data"), dict) else {}
        )
        if isinstance(item.get("bullets"), list) and "items" not in raw_bdata:
            raw_bdata["items"] = item.get("bullets")
        takeaway = str(item.get("takeaway") or raw_bdata.get("takeaway") or "").strip()[:160]
        if takeaway and "takeaway" not in raw_bdata:
            raw_bdata["takeaway"] = takeaway

        raw_items = item.get("board_items") or item.get("bullets")
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
                emotion=emotion,  # type: ignore[arg-type]
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
                takeaway=takeaway,
                board_data=_sanitize_board_data(btype, raw_bdata),
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
    beats = enforce_pose_diversity(_enforce_meaningful_boards(beats))
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
            _enforce_meaningful_boards(
                sanitize_beats(
                    parsed.get("beats"), chapter=1, start_idx=1, allowed_poses=allowed_set
                )
            )
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

    all_beats = enforce_pose_diversity(_enforce_meaningful_boards(all_beats))
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
