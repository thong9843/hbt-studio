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
        "board_data: pinned_photo={caption:'3-6 từ tiếng Việt',pin_style:'pin'|'tape'}, "
        "bullets/recap_card={items:['...**từ khóa**...'],takeaway:'...'}, "
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
        items = [str(x).strip()[:130] for x in (raw.get("items") or []) if str(x).strip()][:5]
        res: dict[str, Any] = {"items": items or ["Điểm chính cần nhớ"]}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "big_number":
        res = {
            "value": str(raw.get("value") or "100%").strip()[:24],
            "label": str(raw.get("label") or "").strip()[:80],
            "sub": str(raw.get("sub") or "").strip()[:120],
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "comparison":
        res = {
            "left_title": str(raw.get("left_title") or "Trước").strip()[:40],
            "left_items": [
                str(x).strip()[:120] for x in (raw.get("left_items") or []) if str(x).strip()
            ][:4],
            "right_title": str(raw.get("right_title") or "Sau").strip()[:40],
            "right_items": [
                str(x).strip()[:120] for x in (raw.get("right_items") or []) if str(x).strip()
            ][:4],
        }
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "flow_steps":
        steps = [str(x).strip()[:120] for x in (raw.get("steps") or []) if str(x).strip()][:4]
        res = {"steps": steps or ["Bước 1", "Bước 2"]}
        if takeaway:
            res["takeaway"] = takeaway
        return res
    if board_type == "recap_card":
        raw_items = raw.get("items") or raw.get("bullets") or []
        items = [str(x).strip()[:120] for x in raw_items if str(x).strip()][:3]
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
        "pinned_photo",
    ):
        return dict(raw)
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


def _word_overlap_ratio(a: str, b: str) -> float:
    wa = {w for w in re.findall(r"[^\W_]+", (a or "").lower()) if len(w) >= 2}
    wb = {w for w in re.findall(r"[^\W_]+", (b or "").lower()) if len(w) >= 2}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def _rewrite_non_parrot_title(narration: str) -> str:
    has_num = bool(re.search(r"\d", narration or ""))
    candidates = (
        ("DỮ KIỆN ĐỊNH LƯỢNG", "PHÂN TÍCH CƠ CHẾ", "BẢN ĐỒ Ý CHÍNH", "GÓC NHÌN THỰC NGHIỆM")
        if has_num
        else ("PHÂN TÍCH CƠ CHẾ", "BẢN ĐỒ Ý CHÍNH", "GÓC NHÌN THỰC NGHIỆM", "TỔNG HỢP KHOA HỌC")
    )
    for cand in candidates:
        if _word_overlap_ratio(narration, cand) <= ANTI_PARROT_THRESHOLD:
            return cand
    return "HỒ SƠ PHÂN TÍCH"


def _condense_to_keyword_bullets(narration: str, takeaway: str) -> list[str]:
    """Rút gọn bảng Anti-Parrot thành 3 ý cấu trúc `**Thuật ngữ:** cơ chế` (overlap <= 0.55)."""
    clean = (narration or "").strip()
    num_hits = re.findall(
        r"\d[\d.,]*\s*(?:%|ms|giây|phút|năm|tcn|triệu|tỷ|nghìn|lần|km|°)?",
        clean,
        re.I,
    )
    out: list[str] = []
    if num_hits:
        hl = num_hits[0].strip()
        cand1 = f"**Mốc {hl}:** Thông số kiểm chứng phản ánh cơ chế gốc."
        if _word_overlap_ratio(clean, cand1) <= ANTI_PARROT_THRESHOLD:
            out.append(cand1)
    if not out:
        cand1 = "**Cơ chế gốc:** Phản ứng vận hành theo quy luật tự nhiên."
        if _word_overlap_ratio(clean, cand1) <= ANTI_PARROT_THRESHOLD:
            out.append(cand1)
        else:
            out.append("**Quy luật gốc:** Chuỗi nhân quả kiểm chứng thực nghiệm.")

    tk_clean = (takeaway or "").strip().replace("**", "")
    if tk_clean and _word_overlap_ratio(clean, tk_clean) <= ANTI_PARROT_THRESHOLD:
        out.append(f"**Điểm chốt:** {tk_clean[:54]}")
    else:
        cand2 = "**Hệ quả trực tiếp:** Quyết định tốc độ thích nghi và phục hồi dài hạn."
        if _word_overlap_ratio(clean, cand2) <= ANTI_PARROT_THRESHOLD:
            out.append(cand2)
        else:
            out.append("**Tác động chính:** Biến đổi cấu trúc bền vững qua từng chu kỳ.")

    cand3 = "**Ứng dụng thực tiễn:** Đối chiếu dữ kiện đo lường thay vì đoán cảm tính."
    if _word_overlap_ratio(clean, cand3) <= ANTI_PARROT_THRESHOLD:
        out.append(cand3)
    else:
        out.append("**Ghi nhớ nhanh:** Nắm trục nguyên lý cốt lõi để áp dụng chuẩn.")

    # Bảo đảm độ dài gọn gàng & tỷ lệ trùng từ từng mục và tổng thể <= ANTI_PARROT_THRESHOLD
    safe_out: list[str] = []
    for item in out[:3]:
        if _word_overlap_ratio(clean, item) <= ANTI_PARROT_THRESHOLD:
            safe_out.append(item)
    if len(safe_out) < 3:
        fallbacks = (
            "**Trục định lượng:** Bằng chứng đo lường khách quan.",
            "**Chuỗi cơ chế:** Nguyên nhân trực tiếp dẫn tới hệ quả.",
            "**Áp dụng chuẩn:** Tối ưu hành động dựa trên thực nghiệm.",
        )
        for fb in fallbacks:
            if len(safe_out) >= 3:
                break
            if fb not in safe_out:
                safe_out.append(fb)
    return safe_out[:3]


def _enrich_myth_vs_fact(
    bdata: dict[str, Any],
    narration: str,
    takeaway: str,
) -> dict[str, Any]:
    """Đảm bảo thẻ `myth_vs_fact` có tiêu đề ngắn + giải thích cơ chế cụ thể (không cụt 3 chữ)."""
    updated = dict(bdata)
    myth = str(updated.get("myth") or updated.get("left") or "").strip()
    fact = str(updated.get("fact") or updated.get("right") or "").strip()

    myth_plain = myth.replace("**", "").strip(" .,:;")
    if not myth_plain:
        myth = "**Ngộ nhận phổ biến:** Nhiều người đánh giá hiệu quả chỉ qua cảm giác tức thời."
    elif len(myth_plain.split()) < 7:
        myth = (
            f"**{myth_plain}:** Quan niệm truyền miệng thiếu căn cứ đo lường, "
            "dễ dẫn tới cách làm phản tác dụng."
        )
    elif _word_overlap_ratio(narration, myth) > ANTI_PARROT_THRESHOLD:
        head = " ".join(myth_plain.split()[:5])
        myth = f"**Ngộ nhận '{head}':** Cách nhìn cảm tính không phản ánh đúng bản chất cơ chế."

    fact_plain = fact.replace("**", "").strip(" .,:;")
    tk_plain = (takeaway or "").replace("**", "").strip(" .,:;")
    if not fact_plain:
        detail = (
            tk_plain
            if (tk_plain and len(tk_plain.split()) >= 5)
            else "Quá trình thích nghi chỉ hiệu quả khi đủ cơ chế nền tảng và chu kỳ phục hồi."
        )
        fact = f"**Bản chất khoa học:** {detail}"
    elif len(fact_plain.split()) < 7:
        extra = (
            tk_plain
            if (tk_plain and _word_overlap_ratio(narration, tk_plain) <= ANTI_PARROT_THRESHOLD)
            else "Cơ chế thực tế vận hành nhờ kích thích đúng ngưỡng kết hợp tái tạo bền vững."
        )
        fact = f"**{fact_plain}:** {extra}"
    elif _word_overlap_ratio(narration, fact) > ANTI_PARROT_THRESHOLD:
        detail = (
            tk_plain
            if (tk_plain and _word_overlap_ratio(narration, tk_plain) <= ANTI_PARROT_THRESHOLD)
            else "Bằng chứng thực nghiệm chỉ ra hệ quả đến từ chuỗi phản ứng sinh học chuẩn xác."
        )
        fact = f"**Cơ chế kiểm chứng:** {detail}"

    updated["myth"] = myth[:175]
    updated["fact"] = fact[:175]
    return updated


def _is_tail_recap_or_cta(beat: StickvBeat) -> bool:
    low_nar = (beat.narration or "").lower()
    low_title = (beat.board_title or "").lower()
    if beat.board_type == "recap_card":
        return True
    if any(kw in low_nar for kw in _CTA_KEYWORDS):
        return True
    return any(kw in low_nar or kw in low_title for kw in _SUMMARY_KEYWORDS)


def _enforce_meaningful_boards(beats: list[StickvBeat]) -> list[StickvBeat]:
    """Hậu kiểm bảng tri thức GĐ9: Anti-Parrot <= 55%, bảng đủ mật độ & duy nhất 1 recap_card."""
    if not beats:
        return beats

    out: list[StickvBeat] = []
    collected_insights: list[str] = []
    n_total = len(beats)
    tail_start = max(0, n_total - 2)
    tail_recap_indices = {
        idx for idx in range(tail_start, n_total) if _is_tail_recap_or_cta(beats[idx])
    }
    canonical_recap: tuple[list[str], str] | None = None

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

        # 2. Vùng tổng kết / CTA ở 1-2 beat cuối -> dùng CHUNG DUY NHẤT 1 recap_card nhất quán
        if idx in tail_recap_indices:
            if canonical_recap is None:
                seed_pts = [
                    it
                    for it in items
                    if beat.board_type == "recap_card"
                    and not any(k in it.lower() for k in _CTA_KEYWORDS)
                ]
                recap_pts = list(dict.fromkeys([*seed_pts, *collected_insights]))[-3:]
                if len(recap_pts) < 3:
                    for prev_b in out:
                        pt = str(prev_b.board_title or "").strip().replace("**", "")
                        if (
                            pt
                            and pt not in recap_pts
                            and not any(k in pt.lower() for k in _CTA_KEYWORDS)
                            and not any(cl in pt.lower() for cl in _CLICHE_PATTERNS)
                        ):
                            recap_pts.append(f"**{pt}:** Điểm mấu chốt cần ghi nhớ xuyên suốt.")
                        if len(recap_pts) >= 3:
                            break
                defaults = [
                    "**Nguyên lý gốc:** Hiểu đúng cơ chế vận hành thay vì cảm tính.",
                    "**Phá bỏ ngộ nhận:** Đối chiếu bằng dữ kiện khoa học kiểm chứng.",
                    "**Ứng dụng thực tiễn:** Áp dụng đều đặn để tạo kết quả bền vững.",
                ]
                for d_pt in defaults:
                    if len(recap_pts) >= 3:
                        break
                    recap_pts.append(d_pt)
                recap_pts = recap_pts[:3]
                recap_tk = (
                    takeaway
                    if (takeaway and not any(k in takeaway.lower() for k in _CTA_KEYWORDS))
                    else "Lưu lại 3 nguyên tắc cốt lõi để áp dụng ngay hôm nay"
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
                    }
                )
            )
            continue

        # 3. Kiểm tra Anti-Parrot (<= 55%) trên `board_title`
        if btitle and _word_overlap_ratio(beat.narration, btitle) > ANTI_PARROT_THRESHOLD:
            btitle = _rewrite_non_parrot_title(beat.narration)

        # 4. Nâng mật độ & Anti-Parrot theo từng loại bảng
        if btype == "myth_vs_fact":
            bdata = _enrich_myth_vs_fact(bdata, beat.narration, takeaway)
        elif btype == "flow_steps":
            steps = [
                str(s).strip()
                for s in (bdata.get("steps") or items or [])
                if str(s).strip() and not any(cl in str(s).lower() for cl in _CLICHE_PATTERNS)
            ]
            too_similar = not steps or any(
                _word_overlap_ratio(beat.narration, st) > ANTI_PARROT_THRESHOLD for st in steps
            )
            if too_similar or len(steps) < 3:
                steps = _condense_to_keyword_bullets(beat.narration, takeaway)
            bdata["steps"] = steps[:3]
        elif btype in ("bullets", "list", "card"):
            joined = f"{btitle} {' '.join(items)}".strip()
            item_parrots = any(
                _word_overlap_ratio(beat.narration, it) > ANTI_PARROT_THRESHOLD for it in items
            )
            if (
                not items
                or item_parrots
                or _word_overlap_ratio(beat.narration, joined) > ANTI_PARROT_THRESHOLD
            ):
                items = _condense_to_keyword_bullets(beat.narration, takeaway)
                bdata["items"] = items
            else:
                bdata["items"] = items

        # Thu thập ý giá trị để nạp cho recap_card cuối video
        if takeaway and not any(k in takeaway.lower() for k in _CTA_KEYWORDS):
            collected_insights.append(takeaway[:84])
        elif btype == "myth_vs_fact" and bdata.get("fact"):
            collected_insights.append(str(bdata["fact"])[:84])
        elif items and not any(k in items[0].lower() for k in _CTA_KEYWORDS):
            collected_insights.append(items[0][:84])

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
                face_mood=face_mood,  # type: ignore[arg-type]
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
