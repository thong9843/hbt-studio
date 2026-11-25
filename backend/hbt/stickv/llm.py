"""Sinh kịch bản StickV (Gemini API nén token, Import JSON Web Gemini 0 token & Tách lời thoại)."""

from __future__ import annotations

import ast
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
    "guide_sweep_board",
    "guide_two_sides",
    "guide_step_count",
    "guide_zoom_focus",
    "welcome_open",
    "lean_curious",
)
POSES_V8: tuple[str, ...] = POSES_V9
VALID_MOTIONS = {"bounce", "slide_left", "slide_right", "float", "static"}
VALID_CAMERA_SHOTS = {"wide_stage", "focus_board", "closeup_react"}
VALID_FACE_MOODS = {"explaining", "curious", "excited", "skeptical", "shocked", "warm_cta"}
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
    "pinned_photo",
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
        "LUẬT CẤM CHÉP LỜI THOẠI (ANTI-PARROT <= 55%): Cấm tuyệt đối chép lại nguyên văn "
        "narration lên `board_title` hay `items` (trùng từ <= 55%)! "
        "`board_data` là Tấm Bảng Bằng Chứng & Ghi Chú Khoa Học giàu thông tin:\n"
        "- `myth_vs_fact` / `comparison`: mỗi ô (LẦM TƯỞNG / SỰ THẬT) BẮT BUỘC có Tiêu đề ngắn "
        "(4-7 từ) + 1 câu giải thích cơ chế/số liệu cụ thể (10-18 từ), không viết 3 chữ cụt lủn.\n"
        "- `bullets` / `flow_steps`: đủ 3 ý (8-15 từ/ý) dạng `**Thuật ngữ/Con số:** cơ chế "
        "hoặc tác động cụ thể`, kèm `takeaway` ở đáy thẻ.\n"
        "- `takeaway` (CHỐT LẠI): BẮT BUỘC ngắn gọn tối đa 10-13 từ để đọc lướt trong 1 giây, "
        "không bao giờ viết dài lê thê.\n"
        "- CÂN BẰNG & RẢI ĐỀU ẢNH MINH HỌA (50%-60% BEAT, KHÔNG TRỐNG NỬA SAU): Với kịch bản "
        ">=7 beat, BẮT BUỘC có ít nhất 3-4 beat `board_type='pinned_photo'` rải đều đủ 3 chặng: "
        "Đầu (beat 1-3), Giữa (beat 4-6) và Gần cuối (60%-85% trước `recap_card`), xen kẽ với "
        "bảng phân tích (`myth_vs_fact`, `comparison`, `big_number`, `flow_steps`, `recap_card`). "
        "Trả về `primary_entity_en` (thực thể trung tâm của video nếu là 1 chủ thể duy nhất, "
        "vd 'Leaning Tower of Pisa'). Trên MỌI beat `pinned_photo`, BẮT BUỘC ghi `beat_entity_en` "
        "(tên địa danh/sự vật/hiện tượng thật CỤ THỂ của RIÊNG beat đó bằng tiếng Anh, vd "
        "'Bermuda Triangle', 'Racetrack Playa', 'Richat Structure Sahara') và `prop_query` neo "
        "thực thể đó + bối cảnh (vd 'Racetrack Playa sailing stones'), CẤM ghép cụm chung chung "
        "như 'Mysterious Places' hay từ dễ lạc đề ('old building', 'ruler', 'blueprint'); kèm "
        "`image_prompt` 1 câu tiếng Anh mô tả tranh 2D minh họa nếu cần fallback AI.\n"
        "- Cấm cụm sáo rỗng: '100% Mức độ cảnh báo', 'Thông tin quan trọng', 'Lưu ý đặc biệt'.\n"
        "THẺ TÓM TẮT CUỐI VIDEO (DUY NHẤT 1 RECAP): Nếu 2 beat cuối là tổng kết + CTA "
        "(bình luận / đăng ký kênh), BẮT BUỘC giữ CHUNG DUY NHẤT 1 `recap_card` giống hệt nhau "
        "(`board_title='TÓM TẮT 3 Ý CỐT LÕI'`, đúng 3 ý đúc kết giá trị nhất, không đổi bảng "
        "tóm tắt thứ hai và không ghi câu đăng ký kênh lên bảng).\n"
        "LUẬT ĐA DẠNG: Không dùng cùng 1 `pose` hoặc 1 `emotion` cho 2 beat đứng liền kề.\n"
        "domain: paper_classic|physics_science|history_geo|psychology_story|cosmos_mystery.\n"
        "music_mood: curious_science|history_epic|funny_quirky|mysterious_tense|calm_lofi.\n"
        f"pose (cử chỉ hướng dẫn 2-đoạn, không lặp liền kề): {pose_str}.\n"
        "emotion (10 biểu cảm): neutral|confident|curious|idea|shock|skeptical|"
        "serious|sad|happy|excited.\n"
        "face_mood (6 sắc thái khuôn mặt): explaining|curious|excited|skeptical|shocked|warm_cta.\n"
        "anim_oneshot: null|shock_jump|idea_bulb|point_board|facepalm|nod_agree|celebrate. "
        "anim_loop: talk_explain|talk_excited|think_loop|idle_breathe|walk_loop. "
        "interaction: none|hold_prop|point_chart|versus_split "
        "(nếu hold_prop, bullets hoặc pinned_photo thêm prop_query 2-4 từ tiếng Anh). "
        "camera_shot: wide_stage|focus_board|closeup_react. "
        "motion: bounce|slide_left|slide_right|float|static. "
        "sfx_tag: none|whoosh|pop|vine_boom|ding. "
        "board_type: pinned_photo|bullets|big_number|comparison|flow_steps|bar_compare|"
        "counter_grow|timeline_era|location_map|myth_vs_fact|recap_card|card|quote|list|none.\n"
        "SCHEMA `board_data` KHỚP 100% RENDERER (MỌI BEAT TỪ ĐẦU ĐẾN CUỐI PHẢI ĐỦ DỮ LIỆU THẬT, "
        "CẤM BỎ TRỐNG `board_data` Ở NỬA SAU, CẤM DÙNG '100%' NẾU CHỦ ĐỀ KHÔNG NÓI 100%):\n"
        '- `pinned_photo`: {"caption":"Tên địa điểm/sự vật cụ thể (3-7 từ tiếng Việt)",'
        '"pin_style":"pin"|"tape"}\n'
        '- `bullets`: {"items":["**Từ khóa 1:** dữ kiện thật","**Từ khóa 2:** dữ kiện thật",'
        '"**Từ khóa 3:** dữ kiện thật"],"takeaway":"Chốt ý ngắn <=12 từ"}\n'
        '- `flow_steps`: {"steps":["**Bước 1:** diễn biến thật","**Bước 2:** cơ chế thật",'
        '"**Bước 3:** kết quả thật"],"takeaway":"..."}\n'
        '- `myth_vs_fact`: {"myth":"**Lầm tưởng cụ thể:** giải thích ngắn",'
        '"fact":"**Sự thật kiểm chứng:** số liệu/cơ chế cụ thể","takeaway":"..."}\n'
        '- `comparison`: {"left_title":"Tên bên A","left_items":["Đặc điểm A1","Đặc điểm A2"],'
        '"right_title":"Tên bên B","right_items":["Đặc điểm B1","Đặc điểm B2"],'
        '"takeaway":"..."}\n'
        '- `big_number`: {"value":"500.000 km²","label":"Diện tích vùng biển",'
        '"sub":"Số liệu đo thực tế gắn chủ đề","takeaway":"..."}\n'
        '- `recap_card`: {"items":["**Ý 1:** rút từ video","**Ý 2:** rút từ video",'
        '"**Ý 3:** rút từ video"],"takeaway":"Tóm ý chính video <=12 từ"}\n'
        '- `bar_compare`: {"values":[{"label":"...","value":10}],"takeaway":"..."}, '
        '`counter_grow`: {"target":1173,"unit":"năm","label":"..."}, '
        '`timeline_era`: {"events":[{"year":"1173","title":"..."}],"takeaway":"..."}, '
        '`location_map`: {"location":"...","coordinates":"...","takeaway":"..."}'
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
        'Schema JSON:\n{"title":"Tiêu đề","primary_entity_en":"Leaning Tower of Pisa",'
        '"domain":"physics_science","music_mood":"curious_science",'
        '"beats":[{"narration":"1-2 câu tiếng Việt","pose":"point_up","emotion":"curious",'
        '"camera_shot":"wide_stage","anim_oneshot":"idea_bulb","anim_loop":"talk_explain",'
        '"interaction":"hold_prop","prop_query":"brain","facing":"right","motion":"bounce",'
        '"sfx_tag":"whoosh","board_type":"bullets","board_title":"Số liệu / Cơ chế",'
        '"board_data":{"items":["**Cơ chế** ngắn gọn (<11 từ)","Số liệu thật cụ thể"],'
        '"takeaway":"Chốt lại giá trị ngắn"}}]}'
    )


def unwrap_board_text(value: Any) -> tuple[str, str]:
    """Tách sạch `(title, body)` từ dict hoặc chuỗi bị `str(dict)` hóa; cấm lọt `{`/`'title':`."""
    if value is None:
        return "", ""
    obj: Any = value
    if isinstance(obj, str):
        s = obj.strip()
        is_dict_str = s.startswith("{") and any(
            k in s for k in ("'title'", '"title"', "'text'", '"text"')
        )
        if is_dict_str:
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(s)
                    if isinstance(parsed, dict):
                        obj = parsed
                        break
                except Exception:
                    continue
        if isinstance(obj, str):
            return "", obj.strip()
    if isinstance(obj, dict):
        title = str(obj.get("title") or obj.get("heading") or obj.get("label") or "").strip()
        body = str(
            obj.get("text")
            or obj.get("body")
            or obj.get("desc")
            or obj.get("description")
            or obj.get("content")
            or obj.get("value")
            or ""
        ).strip()
        if not title and not body:
            parts = [str(v).strip() for v in obj.values() if str(v).strip()]
            return "", " — ".join(parts[:2])
        return title, body
    return "", str(obj).strip()


def format_unwrapped_text(value: Any) -> str:
    """Chuyển giá trị bảng (dict/str) thành 1 chuỗi sạch giàu định dạng `**Tiêu đề:** nội dung`."""
    title, body = unwrap_board_text(value)
    if title and body:
        t_clean = title.replace("**", "").rstrip(": ")
        return f"**{t_clean}:** {body}"
    return (title or body).strip()


def _trim_at_word_boundary(text: str, max_chars: int) -> str:
    """Cắt chuỗi gọn tại ranh giới từ (tuyệt đối không cắt cụt giữa từ như '...và c')."""
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) <= max_chars:
        return clean
    cut = clean[:max_chars].rsplit(" ", 1)[0].rstrip(",;:-–— ")
    return cut if cut else clean[:max_chars].rstrip(",;:-–— ")


def _trim_takeaway_words(text: str, max_words: int = 13) -> str:
    clean = format_unwrapped_text(text).replace("**", "").strip()
    words = clean.split()
    if len(words) <= max_words:
        return clean
    return " ".join(words[:max_words]).rstrip(",;:-–— ")


def _normalize_side_items(raw_val: Any) -> list[str]:
    if isinstance(raw_val, list):
        return [
            _trim_at_word_boundary(format_unwrapped_text(x), 130)
            for x in raw_val
            if format_unwrapped_text(x)
        ][:4]
    txt = format_unwrapped_text(raw_val)
    return [_trim_at_word_boundary(txt, 130)] if txt else []


def _sanitize_board_data(board_type: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    takeaway = _trim_takeaway_words(raw.get("takeaway") or "", max_words=13)
    if board_type in ("bullets", "list", "card"):
        items = [
            _trim_at_word_boundary(format_unwrapped_text(x), 140)
            for x in (raw.get("items") or [])
            if format_unwrapped_text(x)
        ][:5]
        res: dict[str, Any] = {"items": items}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "big_number":
        raw_val = raw.get("value")
        if raw_val is None or str(raw_val).strip() == "":
            raw_val = raw.get("number")
        val_txt = format_unwrapped_text(raw_val or "").replace("**", "").strip()
        unit_txt = format_unwrapped_text(raw.get("unit") or "").replace("**", "").strip()
        if val_txt and unit_txt and unit_txt.lower() not in val_txt.lower():
            val_txt = f"{val_txt} {unit_txt}".strip()
        res = {
            "value": _trim_at_word_boundary(val_txt, 28),
            "label": _trim_at_word_boundary(format_unwrapped_text(raw.get("label") or ""), 90),
            "sub": _trim_at_word_boundary(
                format_unwrapped_text(raw.get("sub") or raw.get("detail") or ""), 120
            ),
        }
        if unit_txt:
            res["unit"] = _trim_at_word_boundary(unit_txt, 24)
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "comparison":
        lt_clean = _trim_at_word_boundary(
            format_unwrapped_text(raw.get("left_title") or "").replace("**", ""), 40
        )
        rt_clean = _trim_at_word_boundary(
            format_unwrapped_text(raw.get("right_title") or "").replace("**", ""), 40
        )
        left_items = _normalize_side_items(raw.get("left_items") or raw.get("left"))
        right_items = _normalize_side_items(raw.get("right_items") or raw.get("right"))
        res = {
            "left_title": lt_clean,
            "left_items": left_items,
            "right_title": rt_clean,
            "right_items": right_items,
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "flow_steps":
        steps = [
            _trim_at_word_boundary(format_unwrapped_text(x), 130)
            for x in (raw.get("steps") or raw.get("items") or [])
            if format_unwrapped_text(x)
        ][:4]
        res = {"steps": steps}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "recap_card":
        raw_items = raw.get("items") or raw.get("bullets") or []
        items = [
            _trim_at_word_boundary(format_unwrapped_text(x), 120)
            for x in raw_items
            if format_unwrapped_text(x)
        ][:3]
        res = {"items": items}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "myth_vs_fact":
        myth_t, myth_b = unwrap_board_text(raw.get("myth") or raw.get("left") or "")
        fact_t, fact_b = unwrap_board_text(raw.get("fact") or raw.get("right") or "")
        res = {
            "myth": f"**{myth_t}:** {myth_b}" if (myth_t and myth_b) else (myth_t or myth_b),
            "fact": f"**{fact_t}:** {fact_b}" if (fact_t and fact_b) else (fact_t or fact_b),
        }
        if raw.get("myth_title"):
            res["myth_title"] = _trim_at_word_boundary(
                format_unwrapped_text(raw.get("myth_title")).replace("**", ""), 60
            )
        if raw.get("fact_title"):
            res["fact_title"] = _trim_at_word_boundary(
                format_unwrapped_text(raw.get("fact_title")).replace("**", ""), 60
            )
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "timeline_era":
        clean_events: list[dict[str, str]] = []
        for idx, ev in enumerate((raw.get("events") or raw.get("items") or [])[:4]):
            if isinstance(ev, dict):
                raw_yr = ev.get("year") or ev.get("era") or f"Mốc {idx + 1}"
                yr = format_unwrapped_text(raw_yr).replace("**", "")
                raw_tt = ev.get("title") or ev.get("label") or ev.get("text") or ""
                tt = format_unwrapped_text(raw_tt)
                clean_events.append(
                    {
                        "year": _trim_at_word_boundary(yr, 30),
                        "title": _trim_at_word_boundary(tt, 120),
                    }
                )
            else:
                ev_t = _trim_at_word_boundary(format_unwrapped_text(ev), 120)
                clean_events.append({"year": f"Mốc {idx + 1}", "title": ev_t})
        res = {"events": clean_events}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "quote":
        res = {
            "quote": _trim_at_word_boundary(
                format_unwrapped_text(raw.get("quote") or raw.get("text") or ""), 180
            )
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "pinned_photo":
        pin_raw = str(raw.get("pin_style") or "").strip().lower()
        res = {
            "caption": _trim_at_word_boundary(
                format_unwrapped_text(raw.get("caption") or "").replace("**", ""), 80
            ),
            "pin_style": "tape" if pin_raw == "tape" else "pin",
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type in ("bar_compare", "counter_grow", "location_map"):
        out_d = dict(raw)
        if takeaway:
            out_d["takeaway"] = takeaway
        return out_d
    return {}


ANTI_PARROT_THRESHOLD = 0.55

_CLICHE_PATTERNS = (
    "100% mức độ cảnh báo",
    "mức độ cảnh báo",
    "thông tin quan trọng",
    "lưu ý đặc biệt",
    "điểm chính cần nhớ",
    "mở đầu video",
    "hãy tìm hiểu",
    "phân tích cơ chế",
    "hồ sơ phân tích",
    "bản đồ ý chính",
    "góc nhìn thực nghiệm",
    "dữ kiện định lượng",
    "ngộ nhận phổ biến",
    "chu kỳ phục hồi",
    "quy luật tự nhiên",
    "phản ứng sinh học chuẩn xác",
    "lưu lại 3 nguyên tắc cốt lõi để áp dụng ngay hôm nay",
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
_SUMMARY_KEYWORDS = (
    "tóm lại",
    "tổng kết",
    "3 ý",
    "ba ý",
    "đúc kết",
    "chốt lại",
    "nhớ kỹ",
)
_GENERIC_BOARD_TITLES = frozenset(
    {
        "phân tích cơ chế",
        "dữ kiện định lượng",
        "bản đồ ý chính",
        "góc nhìn thực nghiệm",
        "hồ sơ phân tích",
        "tổng hợp khoa học",
        "thông tin quan trọng",
        "ảnh tư liệu minh họa",
    }
)


def _word_overlap_ratio(a: str, b: str) -> float:
    wa = {w for w in re.findall(r"[^\W_]+", (a or "").lower()) if len(w) >= 2}
    wb = {w for w in re.findall(r"[^\W_]+", (b or "").lower()) if len(w) >= 2}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def _extract_subject_phrase(text: str, max_words: int = 5) -> str:
    """Trích cụm danh từ/tên riêng/số liệu trực tiếp từ lời thoại (không bịa chữ mẫu)."""
    clean = re.sub(r"\s+", " ", (text or "").replace("**", "").strip(" .,:;!?…\"'“”"))
    if not clean:
        return ""
    # Ưu tiên cụm viết hoa (tên địa danh / thực thể riêng) trong câu
    proper = re.findall(
        r"\b[A-ZÀ-Ỹ][a-zà-ỹA-ZÀ-Ỹ0-9\-]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹA-ZÀ-Ỹ0-9\-]+){1,4}\b",
        clean,
    )
    if proper:
        return " ".join(proper[0].split()[:max_words])
    clauses = [c.strip() for c in re.split(r"[.;:!?…,—–]", clean) if len(c.strip().split()) >= 2]
    chosen = clauses[0] if clauses else clean
    return " ".join(chosen.split()[:max_words]).rstrip(",;:-–— ")


def _extract_topic_points_from_beat(
    narration: str,
    board_title: str = "",
    takeaway: str = "",
) -> list[str]:
    """Trích rút các ý chính trực tiếp từ chính lời thoại & takeaway của beat (0% văn mẫu)."""
    points: list[str] = []
    seen_low: set[str] = set()

    def _add(raw_pt: str) -> None:
        pt = _trim_at_word_boundary(raw_pt.strip(" .,:;!?…"), 110)
        low = pt.lower().replace("**", "")
        if len(low.split()) < 3 or low in seen_low:
            return
        if any(cl in low for cl in _CLICHE_PATTERNS):
            return
        seen_low.add(low)
        points.append(pt)

    tk = (takeaway or "").replace("**", "").strip()
    if tk:
        _add(f"**Điểm chốt:** {tk}")

    clauses = [
        c.strip()
        for c in re.split(r"[.;:!?…—–]+", (narration or "").strip())
        if len(c.strip().split()) >= 3
    ]
    if len(clauses) == 1 and "," in clauses[0]:
        sub = [s.strip() for s in clauses[0].split(",") if len(s.strip().split()) >= 3]
        if len(sub) >= 2:
            clauses = sub

    for cl in clauses[:3]:
        words = cl.split()
        if len(words) >= 6:
            head = " ".join(words[:3]).rstrip(",;:- ")
            body = " ".join(words[3:])
            _add(f"**{head}:** {body}")
        else:
            _add(cl)

    if not points and board_title:
        _add(board_title)
    return points[:3]


def _has_real_quantitative_value(val: str, narration: str) -> bool:
    """Kiểm tra `big_number`/`counter_grow` có con số thật gắn với chủ đề (cấm '100%' mặc định)."""
    clean = (val or "").replace("**", "").strip()
    if not clean or not re.search(r"\d", clean):
        return False
    if (
        clean == "100%"
        and "100%" not in (narration or "")
        and "100 phần trăm" not in (narration or "").lower()
    ):
        return False
    return True


def _is_tail_recap_or_cta(beat: StickvBeat) -> bool:
    low_nar = (beat.narration or "").lower()
    low_title = (beat.board_title or "").lower()
    if beat.board_type == "recap_card":
        return True
    if any(kw in low_nar for kw in _CTA_KEYWORDS):
        return True
    return any(kw in low_nar or kw in low_title for kw in _SUMMARY_KEYWORDS)


def _enforce_meaningful_boards(beats: list[StickvBeat]) -> list[StickvBeat]:
    """Hậu kiểm bảng tri thức (0% văn mẫu cứng, 0% khung trống, 0% '100%' ảo, 1 recap_card thật)."""
    if not beats:
        return beats

    out: list[StickvBeat] = []
    collected_insights: list[str] = []
    seen_bullet_sigs: set[tuple[str, ...]] = set()
    n_total = len(beats)
    tail_start = max(0, n_total - 2)
    tail_recap_indices = {
        idx for idx in range(tail_start, n_total) if _is_tail_recap_or_cta(beats[idx])
    }
    canonical_recap: tuple[list[str], str] | None = None

    for idx, beat in enumerate(beats):
        bdata = dict(beat.board_data or {})
        items = [
            _trim_at_word_boundary(str(x).strip(), 130)
            for x in (bdata.get("items") or beat.board_items or [])
            if str(x).strip()
        ]
        takeaway = _trim_takeaway_words(
            str(beat.takeaway or bdata.get("takeaway") or "").strip(), max_words=13
        )
        if any(cl in takeaway.lower() for cl in _CLICHE_PATTERNS):
            takeaway = ""
        btitle = (beat.board_title or "").strip()
        btype = beat.board_type

        # 1. Loại bỏ cụm sáo rỗng / văn mẫu cũ
        items = [it for it in items if not any(cl in it.lower() for cl in _CLICHE_PATTERNS)]
        if btitle.lower() in _GENERIC_BOARD_TITLES or any(
            cl in btitle.lower() for cl in _CLICHE_PATTERNS
        ):
            btitle = ""

        # 2. Vùng tổng kết / CTA ở 1-2 beat cuối -> CHUNG DUY NHẤT 1 recap_card từ nội dung thật
        if idx in tail_recap_indices:
            if canonical_recap is None:
                seed_pts = [
                    _trim_at_word_boundary(it, 110)
                    for it in items
                    if beat.board_type == "recap_card"
                    and not any(k in it.lower() for k in _CTA_KEYWORDS)
                    and not any(cl in it.lower() for cl in _CLICHE_PATTERNS)
                ]
                recap_pts = list(dict.fromkeys([*seed_pts, *collected_insights]))[:3]
                if len(recap_pts) < 3:
                    for prev_b in out:
                        if _is_tail_recap_or_cta(prev_b):
                            continue
                        pt_title = str(prev_b.board_title or "").strip().replace("**", "")
                        cand = ""
                        if prev_b.takeaway and not any(
                            k in prev_b.takeaway.lower() for k in _CTA_KEYWORDS
                        ):
                            cand = (
                                f"**{pt_title}:** {prev_b.takeaway}"
                                if pt_title and pt_title.lower() not in prev_b.takeaway.lower()
                                else prev_b.takeaway
                            )
                        elif prev_b.narration:
                            cand = _extract_subject_phrase(prev_b.narration, max_words=11)
                        cand = _trim_at_word_boundary(cand, 110)
                        if (
                            cand
                            and cand not in recap_pts
                            and not any(k in cand.lower() for k in _CTA_KEYWORDS)
                            and not any(cl in cand.lower() for cl in _CLICHE_PATTERNS)
                        ):
                            recap_pts.append(cand)
                        if len(recap_pts) >= 3:
                            break
                recap_pts = recap_pts[:3]
                recap_tk = (
                    takeaway
                    if (takeaway and not any(k in takeaway.lower() for k in _CTA_KEYWORDS))
                    else (
                        _trim_takeaway_words(recap_pts[0], max_words=12)
                        if recap_pts
                        else _trim_takeaway_words(beat.narration, max_words=12)
                    )
                )
                canonical_recap = (recap_pts, recap_tk)

            recap_pts, recap_tk = canonical_recap
            recap_data = {**bdata, "items": list(recap_pts), "takeaway": recap_tk}
            out.append(
                beat.model_copy(
                    update={
                        "board_type": "recap_card",
                        "board_title": "TÓM TẮT 3 Ý CỐT LÕI",
                        "board_items": list(recap_pts),
                        "takeaway": recap_tk,
                        "board_data": recap_data,
                        "camera_shot": "wide_stage",
                    }
                )
            )
            continue

        # 3. Kiểm tra `pinned_photo`: đảm bảo caption là tên địa điểm/sự vật cụ thể
        if btype == "pinned_photo":
            raw_cap = format_unwrapped_text(bdata.get("caption") or "").replace("**", "").strip()
            if (
                not raw_cap
                or raw_cap.lower() in _GENERIC_BOARD_TITLES
                or any(cl in raw_cap.lower() for cl in _CLICHE_PATTERNS)
            ):
                raw_cap = (
                    btitle
                    if (btitle and btitle.lower() not in _GENERIC_BOARD_TITLES)
                    else _extract_subject_phrase(beat.narration, max_words=6)
                )
            bdata["caption"] = _trim_at_word_boundary(raw_cap, 64)
            if not btitle:
                btitle = bdata["caption"]

        # 4. Chặn `big_number`/`counter_grow` thiếu số liệu thật -> chuyển sang `bullets`
        if btype == "big_number":
            val_s = str(bdata.get("value") or bdata.get("number") or "").strip()
            if not _has_real_quantitative_value(val_s, beat.narration):
                btype = "bullets"
                lbl = format_unwrapped_text(bdata.get("label") or "").strip()
                sub = format_unwrapped_text(bdata.get("sub") or bdata.get("detail") or "").strip()
                derived = [
                    x
                    for x in (lbl, sub)
                    if x and not any(cl in x.lower() for cl in _CLICHE_PATTERNS)
                ]
                items = derived or _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
                bdata = {"items": items}
        elif btype == "counter_grow":
            tgt = bdata.get("target", bdata.get("value"))
            if tgt is None or not _has_real_quantitative_value(str(tgt), beat.narration):
                btype = "bullets"
                items = _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
                bdata = {"items": items}

        # 5. Chặn `comparison` trống cả 2 cột -> fallback sạch sang `bullets` của chính beat
        if btype == "comparison":
            l_items = _normalize_side_items(bdata.get("left_items") or bdata.get("left"))
            r_items = _normalize_side_items(bdata.get("right_items") or bdata.get("right"))
            if not l_items and not r_items:
                btype = "bullets"
                items = _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
                bdata = {"items": items}
            else:
                bdata["left_items"] = l_items
                bdata["right_items"] = r_items

        # 6. Chống lặp/rỗng cho `myth_vs_fact`, `flow_steps`, `bullets` (100% bám dữ liệu beat)
        if btype == "myth_vs_fact":
            m_txt = format_unwrapped_text(bdata.get("myth") or bdata.get("left") or "").strip()
            f_txt = format_unwrapped_text(bdata.get("fact") or bdata.get("right") or "").strip()
            if any(cl in m_txt.lower() for cl in _CLICHE_PATTERNS):
                m_txt = ""
            if any(cl in f_txt.lower() for cl in _CLICHE_PATTERNS):
                f_txt = ""
            if not m_txt and not f_txt:
                btype = "bullets"
                items = _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
                bdata = {"items": items}
            else:
                if not f_txt:
                    f_txt = takeaway or _trim_at_word_boundary(beat.narration, 140)
                if not m_txt:
                    m_txt = _extract_subject_phrase(beat.narration, max_words=8)
                bdata["myth"] = _trim_at_word_boundary(m_txt, 170)
                bdata["fact"] = _trim_at_word_boundary(f_txt, 170)
        elif btype == "flow_steps":
            steps = [
                _trim_at_word_boundary(str(s).strip(), 130)
                for s in (bdata.get("steps") or items or [])
                if str(s).strip() and not any(cl in str(s).lower() for cl in _CLICHE_PATTERNS)
            ]
            if not steps:
                steps = _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
            bdata["steps"] = steps[:4]
        elif btype in ("bullets", "list", "card"):
            if not items:
                items = _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
            # Chống lặp y nguyên cùng 1 bộ bullet ở 2 beat khác nhau
            sig = tuple(it.lower() for it in items)
            if sig in seen_bullet_sigs:
                alt = _extract_topic_points_from_beat(beat.narration, btitle, takeaway)
                if alt:
                    items = alt
                    sig = tuple(it.lower() for it in items)
            if sig:
                seen_bullet_sigs.add(sig)
            bdata["items"] = items[:3]

        # Thu thập ý giá trị thật để nạp cho `recap_card` cuối video (cắt đúng ranh giới từ)
        if takeaway and not any(k in takeaway.lower() for k in _CTA_KEYWORDS):
            collected_insights.append(_trim_at_word_boundary(takeaway, 100))
        elif btype == "myth_vs_fact" and bdata.get("fact"):
            collected_insights.append(_trim_at_word_boundary(str(bdata["fact"]), 100))
        elif btype == "flow_steps" and bdata.get("steps"):
            collected_insights.append(_trim_at_word_boundary(str(bdata["steps"][0]), 100))
        elif btype == "big_number" and bdata.get("value"):
            bn_lbl = str(bdata.get("label") or btitle or "").strip()
            collected_insights.append(
                _trim_at_word_boundary(f"**{bdata['value']}:** {bn_lbl}".strip(": "), 100)
            )
        elif items and not any(k in items[0].lower() for k in _CTA_KEYWORDS):
            collected_insights.append(_trim_at_word_boundary(items[0], 100))

        if takeaway:
            bdata["takeaway"] = takeaway
        else:
            bdata.pop("takeaway", None)

        out.append(
            beat.model_copy(
                update={
                    "board_type": btype,
                    "board_title": _trim_at_word_boundary(btitle, 100),
                    "board_items": items if items else list(beat.board_items),
                    "takeaway": _trim_at_word_boundary(takeaway, 140),
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


_ENTITY_STOPWORDS = frozenset(
    {"the", "a", "an", "of", "in", "on", "at", "for", "with", "and", "to", "by", "from"}
)
_GENERIC_BAD_QUERY_TOKENS = frozenset(
    {
        "old",
        "building",
        "measurement",
        "scale",
        "ancient",
        "history",
        "soft",
        "ground",
        "ruler",
        "blueprint",
        "floorplan",
        "coin",
        "medal",
        "stamp",
        "shutter",
        "warehouse",
        "diagram",
        "chart",
        "icon",
        "logo",
    }
)


def _core_en_tokens(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
        if len(w) >= 2 and w not in _ENTITY_STOPWORDS
    ]


_GENERIC_UMBRELLA_ENTITIES = frozenset(
    {
        "mysterious places",
        "strange places",
        "weird places",
        "unknown places",
        "places on earth",
        "world mysteries",
        "unexplained mysteries",
        "natural wonders",
        "science facts",
        "historical facts",
        "weird facts",
        "earth mysteries",
        "top places",
    }
)
_GENERIC_BEAT_CONTEXT_WORDS = frozenset(
    {
        "construction",
        "site",
        "foundation",
        "clay",
        "soil",
        "ground",
        "building",
        "tower",
        "wall",
        "scaffolding",
        "cables",
        "shield",
        "sword",
        "medieval",
        "modern",
        "architect",
        "worker",
        "map",
        "ocean",
        "mystery",
    }
)


def _is_generic_umbrella_entity(entity: str) -> bool:
    norm = re.sub(r"\s+", " ", (entity or "").strip().lower())
    if not norm:
        return True
    if norm in _GENERIC_UMBRELLA_ENTITIES:
        return True
    toks = _core_en_tokens(norm)
    return len(toks) <= 2 and any(
        w in toks for w in ("places", "mysteries", "facts", "wonders", "things", "secrets")
    )


def _ensure_balanced_pinned_photos(
    beats: list[StickvBeat], primary_entity_en: str = ""
) -> list[StickvBeat]:
    """Với kịch bản >=7 beat, đảm bảo có ảnh `pinned_photo` ở cả nửa sau (60%-85%, trước recap)."""
    n = len(beats)
    if n < 7:
        return beats

    out = list(beats)
    late_start = max(3, int(round(n * 0.58)))
    late_end = min(n - 1, max(late_start, int(round(n * 0.86))))
    late_indices = [i for i in range(late_start, late_end + 1) if not _is_tail_recap_or_cta(out[i])]
    if not late_indices:
        return out

    has_late_photo = any(out[i].board_type == "pinned_photo" for i in late_indices)
    if not has_late_photo:
        # Ưu tiên chuyển 1 beat bullets/none/card ở vùng 60%-85% thành pinned_photo
        pick = next(
            (i for i in late_indices if out[i].board_type in ("bullets", "none", "card", "list")),
            late_indices[0],
        )
        b = out[pick]
        cap = (
            b.board_title
            if (b.board_title and b.board_title.lower() not in _GENERIC_BOARD_TITLES)
            else _extract_subject_phrase(b.narration, max_words=6)
        )
        ent = (b.beat_entity_en or "").strip()
        if not ent and primary_entity_en and not _is_generic_umbrella_entity(primary_entity_en):
            ent = primary_entity_en.strip()
        pq = (
            (b.prop_query or "").strip() or ent or _extract_subject_phrase(b.narration, max_words=4)
        )
        new_bdata = {
            "caption": _trim_at_word_boundary(cap or "Hình ảnh minh họa", 64),
            "pin_style": "tape",
        }
        out[pick] = b.model_copy(
            update={
                "board_type": "pinned_photo",
                "beat_entity_en": ent[:100],
                "prop_query": pq[:80] if pq else None,
                "board_data": new_bdata,
            }
        )
    return out


def anchor_beat_image_queries(
    beats: list[StickvBeat], primary_entity_en: str = ""
) -> list[StickvBeat]:
    """Neo thực thể theo từng beat (`beat_entity_en` ưu tiên trước `primary_entity_en`)."""
    proj_entity = re.sub(r"\s+", " ", (primary_entity_en or "").strip())[:60]
    proj_is_umbrella = _is_generic_umbrella_entity(proj_entity)
    if not beats:
        return beats

    out: list[StickvBeat] = []
    for beat in beats:
        if beat.board_type != "pinned_photo":
            out.append(beat)
            continue

        raw_q = re.sub(r"\s+", " ", (beat.prop_query or "").strip())
        beat_ent = re.sub(r"\s+", " ", (beat.beat_entity_en or "").strip())[:80]
        if _is_generic_umbrella_entity(beat_ent):
            beat_ent = ""

        q_tokens = _core_en_tokens(raw_q)
        # Kiểm tra prop_query đã mang thực thể riêng (vd Racetrack Playa) hay đang chung chung
        specific_q_tokens = [
            t
            for t in q_tokens
            if t not in _GENERIC_BAD_QUERY_TOKENS and t not in _GENERIC_BEAT_CONTEXT_WORDS
        ]
        if beat_ent:
            eff_entity = beat_ent
        elif proj_entity and not proj_is_umbrella:
            # Video 1 chủ thể (vd Pisa): nếu beat query chỉ là ngữ cảnh chung -> neo proj_entity
            proj_toks = _core_en_tokens(proj_entity)
            has_proj = all(tok in q_tokens for tok in proj_toks)
            if has_proj or len(specific_q_tokens) < 2:
                eff_entity = proj_entity
            else:
                eff_entity = " ".join(
                    w
                    for w in raw_q.split()
                    if re.sub(r"[^a-zA-Z0-9]", "", w).lower() not in _GENERIC_BAD_QUERY_TOKENS
                )[:60].strip()
        else:
            # Video đa địa điểm (primary_entity_en chung như "Mysterious Places"): KHÔNG ghép đè
            eff_entity = " ".join(
                w
                for w in raw_q.split()
                if re.sub(r"[^a-zA-Z0-9]", "", w).lower() not in _GENERIC_BAD_QUERY_TOKENS
            )[:60].strip()

        entity_tokens = _core_en_tokens(eff_entity)
        if not entity_tokens:
            out.append(beat)
            continue

        has_entity_in_q = all(tok in q_tokens for tok in entity_tokens)
        if has_entity_in_q:
            clean_words = [
                w
                for w in raw_q.split()
                if re.sub(r"[^a-zA-Z0-9]", "", w).lower() not in _GENERIC_BAD_QUERY_TOKENS
                or re.sub(r"[^a-zA-Z0-9]", "", w).lower() in entity_tokens
            ]
            new_q = " ".join(clean_words).strip() or eff_entity
        else:
            extra_words: list[str] = []
            seen_low = set(entity_tokens)
            for w in raw_q.split():
                wl = re.sub(r"[^a-zA-Z0-9]", "", w).lower()
                if not wl or wl in seen_low or wl in _ENTITY_STOPWORDS:
                    continue
                if wl in _GENERIC_BAD_QUERY_TOKENS:
                    continue
                extra_words.append(w)
                seen_low.add(wl)
                if len(extra_words) >= 3:
                    break
            new_q = f"{eff_entity} {' '.join(extra_words)}".strip() if extra_words else eff_entity

        new_q = new_q[:80].strip()

        raw_prompt = re.sub(r"\s+", " ", (beat.image_prompt or "").strip())
        p_tokens = _core_en_tokens(raw_prompt)
        if not raw_prompt:
            ctx = (beat.board_data or {}).get("caption") or beat.board_title or new_q
            new_prompt = f"2D editorial illustration of {eff_entity}, scene context: {ctx}"[:320]
        elif not all(tok in p_tokens for tok in entity_tokens):
            new_prompt = f"{eff_entity} — {raw_prompt}"[:320]
        else:
            new_prompt = raw_prompt[:320]

        updates: dict[str, Any] = {}
        if new_q != (beat.prop_query or ""):
            updates["prop_query"] = new_q
        if new_prompt != (beat.image_prompt or ""):
            updates["image_prompt"] = new_prompt
        if eff_entity != (beat.beat_entity_en or ""):
            updates["beat_entity_en"] = eff_entity[:100]
        if updates:
            beat = beat.model_copy(update=updates)
        out.append(beat)
    return out


def sanitize_beats(
    raw_beats: Any,
    *,
    chapter: int = 1,
    chapter_title: str = "",
    start_idx: int = 1,
    allowed_poses: set[str] | None = None,
    primary_entity_en: str = "",
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
        raw_mood = str(item.get("face_mood") or "").strip().lower()
        face_mood = raw_mood if raw_mood in VALID_FACE_MOODS else None
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
        raw_pq = item.get("prop_query") or item.get("image_query") or ""
        prop_query = str(raw_pq).strip()[:80] or None
        beat_entity_en = str(item.get("beat_entity_en") or "").strip()[:100]
        raw_ip = item.get("image_prompt") or item.get("illustration_prompt_en") or ""
        image_prompt = str(raw_ip).strip()[:320] or None
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
                face_mood=face_mood,  # type: ignore[arg-type]
                anim_oneshot=anim_oneshot,
                anim_loop=anim_loop,
                interaction=interaction,  # type: ignore[arg-type]
                camera_shot=camera_shot,  # type: ignore[arg-type]
                prop_query=prop_query,
                beat_entity_en=beat_entity_en,
                image_prompt=image_prompt,
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
    return anchor_beat_image_queries(out, primary_entity_en=primary_entity_en)


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
    primary_entity_en = ""
    if isinstance(parsed, list):
        title = "Kịch bản StickV (JSON)"
        beats = sanitize_beats(parsed, allowed_poses=allowed_poses)
    elif isinstance(parsed, dict):
        title = str(parsed.get("title") or "Kịch bản StickV (JSON)").strip()[:160]
        primary_entity_en = str(parsed.get("primary_entity_en") or "").strip()[:60]
        beats = sanitize_beats(
            parsed.get("beats"),
            allowed_poses=allowed_poses,
            primary_entity_en=primary_entity_en,
        )
    else:
        raise ValueError("JSON phải là object {title, beats} hoặc mảng beats")
    if not beats:
        raise ValueError("Không tìm thấy beat hợp lệ trong JSON")
    beats = enforce_pose_diversity(_enforce_meaningful_boards(beats))
    beats = _ensure_balanced_pinned_photos(beats, primary_entity_en=primary_entity_en)
    beats = anchor_beat_image_queries(beats, primary_entity_en=primary_entity_en)
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
            'JSON: {"title":"...","primary_entity_en":"English primary entity",'
            '"domain":"history_geo","music_mood":"history_epic",'
            '"beats":[{"narration":"...","pose":"point_up","camera_shot":"wide_stage",'
            '"facing":"right","motion":"bounce","sfx_tag":"whoosh","board_type":"bullets",'
            '"board_title":"...","board_data":{"items":["..."],"takeaway":"..."}}]}'
        )
        parsed, timings = generate_structured_json(
            sys_prompt, user_prompt, model=chosen_model, timeout=60.0
        )
        title = str(parsed.get("title") or clean_idea[:80]).strip()
        primary_entity_en = str(parsed.get("primary_entity_en") or "").strip()[:60]
        beats = enforce_pose_diversity(
            _enforce_meaningful_boards(
                sanitize_beats(
                    parsed.get("beats"),
                    chapter=1,
                    start_idx=1,
                    allowed_poses=allowed_set,
                    primary_entity_en=primary_entity_en,
                )
            )
        )
        beats = _ensure_balanced_pinned_photos(beats, primary_entity_en=primary_entity_en)
        beats = anchor_beat_image_queries(beats, primary_entity_en=primary_entity_en)
        return (
            title,
            beats,
            {
                "chapters": 1,
                "chapter_list": [],
                "primary_entity_en": primary_entity_en,
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
        'JSON: {"title":"...","primary_entity_en":"English primary entity",'
        '"domain":"history_geo","music_mood":"history_epic",'
        '"chapters":[{"chapter":1,"heading":"...","summary":"..."}]}'
    )
    outline, t0 = generate_structured_json(
        sys_prompt, outline_prompt, model=chosen_model, timeout=60.0
    )
    title = str(outline.get("title") or clean_idea[:80]).strip()
    primary_entity_en = str(outline.get("primary_entity_en") or "").strip()[:60]
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
        entity_hint = f" | Thực thể chính: {primary_entity_en}" if primary_entity_en else ""
        ch_prompt = (
            f"Video: {title}{entity_hint} | Chương {ch_idx}/{len(raw_chapters[:num_chapters])}: "
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
            primary_entity_en=primary_entity_en,
        )
        all_beats.extend(ch_beats)

    all_beats = enforce_pose_diversity(_enforce_meaningful_boards(all_beats))
    all_beats = _ensure_balanced_pinned_photos(all_beats, primary_entity_en=primary_entity_en)
    all_beats = anchor_beat_image_queries(all_beats, primary_entity_en=primary_entity_en)
    return (
        title,
        all_beats,
        {
            "chapters": len(raw_chapters[:num_chapters]),
            "chapter_list": chapter_list,
            "primary_entity_en": primary_entity_en,
            "domain": normalize_domain(outline.get("domain")),
            "music_mood": str(outline.get("music_mood") or "curious_science").strip(),
            "llm_s": round(total_llm_s, 3),
            "model": chosen_model,
        },
    )
