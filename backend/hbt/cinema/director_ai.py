"""Editorial Director AI: Dual-Pass Prompt & Rule-based Shot/Transition/AudioCue Assigner."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from hbt.cinema.preflight import PreflightQualityGate, _is_cta_narration
from hbt.cinema.schema import (
    AspectRatio,
    AudioCue,
    AudioPlan,
    BeatSpec,
    BoardSpec,
    CinemaTheme,
    PuppetSpec,
    ShotType,
    TimelineSpec,
    TransitionType,
)
from hbt.shared.llm import GeminiClientError, generate_structured_json

_DIVERSITY_ORDER: tuple[ShotType, ...] = (
    "desk_wide",
    "card_hero",
    "data_spotlight",
    "split_compare",
    "puppet_closeup",
)

_EMOTION_ORDER: tuple[str, ...] = (
    "confident",
    "curious",
    "idea",
    "serious",
    "skeptical",
    "excited",
    "happy",
)

_POSE_ORDER: tuple[str, ...] = (
    "present_board",
    "point_board_high",
    "think_chin",
    "emphatic_chop",
    "hands_on_hips",
    "shrug_ask",
    "count_points",
    "wave_hello",
)


def build_pass1_story_prompt(
    idea: str,
    *,
    topic: str = "science",
    target_minutes: float = 1.0,
) -> str:
    """Pass 1: Sinh xương sống kể chuyện tự nhiên & dữ kiện kiểm chứng (chưa gán góc máy)."""
    beat_count = max(4, min(28, int(round(max(0.4, float(target_minutes)) * 7))))
    return (
        "Bạn là Biên kịch Đạo diễn cấp cao của kênh 'Hay Biết Tuốt' (HBT Studio).\n"
        f"Ý tưởng: {idea}\nChủ đề: {topic}\nSố beat mục tiêu: {beat_count}\n\n"
        "NHIỆM VỤ PASS 1 (NỘI DUNG & KHOA HỌC):\n"
        "1. Chia kịch bản thành các beat ngắn 4–8 giây, mở đầu 3 giây đầu phải có hook gây tò mò.\n"
        "2. Mỗi beat bắt buộc có 2 lớp thông tin ĐỘC LẬP:\n"
        "   - `narration`: Lời thoại kể chuyện tự nhiên cho VieNeu-TTS.\n"
        "   - `facts`: 2–3 gạch đầu dòng chứa SỐ LIỆU / CƠ CHẾ / SO SÁNH BỔ SUNG + `takeaway`.\n"
        "3. NGHIÊM CẤM Anti-Parrot: Không chép lại y nguyên lời thoại lên `facts`.\n"
        "4. Beat CTA cuối cùng KHÔNG ghi chữ 'Đăng ký kênh' lên bảng mà tóm tắt 3 ý cốt lõi.\n\n"
        'Trả về JSON: {"title": "...", "beats": [{"id": "b001", "chapter": 1, '
        '"chapter_title": "...", "narration": "...", "board_title": "...", '
        '"facts": ["..."], "takeaway": "...", "punch": false}]}.'
    )


def build_pass2_editorial_prompt(
    story_beats: Sequence[dict[str, Any]],
    *,
    aspect: AspectRatio = "9:16",
    domain: str = "paper_classic",
) -> str:
    """Pass 2: Phân bổ 6 ngữ pháp góc máy HBT Tactile Desk, chuyển cảnh & diễn hoạt Puppet."""
    beats_json = json.dumps(list(story_beats), ensure_ascii=False)
    return (
        "Bạn là Đạo diễn Hình ảnh & Âm thanh (Editorial Director) của HBT Studio.\n"
        f"Khung hình: {aspect} | Bối cảnh: {domain}\n\n"
        "6 NGỮ PHÁP KHUNG HÌNH HBT TACTILE DESK:\n"
        "- `desk_wide`: Toàn cảnh bàn làm việc + thẻ bên cạnh.\n"
        "- `card_hero`: Thẻ tri thức nổi bật trung tâm (hỗ trợ từ khóa `**...**`).\n"
        "- `split_compare`: Đối chiếu 2 cột Lầm tưởng vs Sự thật.\n"
        "- `data_spotlight`: Phóng to số liệu định lượng nổi bật.\n"
        "- `puppet_closeup`: Cận biểu cảm MC + thu bảng thành nhãn chủ đề gọn.\n"
        "- `recap_grid`: Thẻ tổng kết 3 điểm cốt lõi ở cuối video.\n\n"
        "LUẬT CỨNG:\n"
        "1. Cấm 2 beat liền kề trùng `shot_type` hoặc trùng `pose`/`emotion`.\n"
        "2. Dùng `whip_pan` khi đổi chương hoặc có `punch=true`; "
        "dùng `paper_slide` cho chuỗi bước.\n"
        '3. Beat CTA cuối đặt `shot_type="recap_grid"` và `board_type="recap_card"`.\n\n'
        f"Đầu vào Pass 1:\n{beats_json}\n"
        'Trả về JSON: {"beats": [{"id": "b001", "shot_type": "...", "transition_in": "...", '
        '"board_type": "...", "pose": "...", "emotion": "...", "sfx_tag": "..."}]}.'
    )


def _infer_semantic_shot(beat: BeatSpec, idx: int, total: int) -> ShotType:
    btype = (beat.board.board_type or "").lower()
    nar = (beat.narration or "").lower()
    if btype == "recap_card" or (idx >= max(0, total - 1) and _is_cta_narration(nar)):
        return "recap_grid"
    if btype in ("comparison", "myth_vs_fact") or any(
        k in nar for k in ("lầm tưởng", "trái ngược", "so sánh", "khác biệt")
    ):
        return "split_compare"
    if btype in ("big_number", "bar_compare", "counter_grow") or re.search(
        r"\d[\d.,]*\s*(?:%|ms|km|lần|triệu|tỷ|năm)", nar, re.I
    ):
        return "data_spotlight"
    if beat.punch or any(k in nar for k in ("bất ngờ", "sốc", "tuy nhiên", "thật ra", "?")):
        return "puppet_closeup"
    if len(beat.board.bullets) >= 2:
        return "card_hero"
    return "desk_wide"


def assign_editorial_shots(spec: TimelineSpec) -> TimelineSpec:
    """Đạo diễn biên tập dựa trên luật: gán góc máy đa dạng, transition & audio cues chuẩn."""
    if not spec.beats:
        return spec

    assigned: list[BeatSpec] = []
    n_total = len(spec.beats)
    prev_shot: ShotType | None = None
    prev_pose: str | None = None
    prev_emo: str | None = None
    cycle_idx = 0

    for idx, beat in enumerate(spec.beats):
        cur = beat.model_copy(deep=True)
        cand_shot = _infer_semantic_shot(cur, idx, n_total)
        if prev_shot is not None and cand_shot == prev_shot:
            for step in range(len(_DIVERSITY_ORDER)):
                alt = _DIVERSITY_ORDER[(cycle_idx + step) % len(_DIVERSITY_ORDER)]
                if alt != prev_shot:
                    cand_shot = alt
                    cycle_idx += step + 1
                    break

        cur.shot_type = cand_shot
        prev_shot = cand_shot

        # Gán loại bảng tương thích với góc máy
        if cand_shot == "recap_grid":
            cur.board = cur.board.model_copy(update={"board_type": "recap_card"})
        elif cand_shot == "split_compare" and cur.board.board_type in ("bullets", "card"):
            cur.board = cur.board.model_copy(update={"board_type": "myth_vs_fact"})
        elif cand_shot == "data_spotlight" and cur.board.board_type in ("bullets", "card"):
            cur.board = cur.board.model_copy(update={"board_type": "big_number"})

        # Chống trùng dáng & biểu cảm liên tiếp
        pose = cur.puppet.pose or "present_board"
        if prev_pose is not None and pose == prev_pose:
            pose = _POSE_ORDER[(idx + 1) % len(_POSE_ORDER)]
            if pose == prev_pose:
                pose = _POSE_ORDER[(idx + 2) % len(_POSE_ORDER)]
        prev_pose = pose

        emo = cur.puppet.emotion or "auto"
        if emo == "auto" or (prev_emo is not None and emo == prev_emo):
            emo = _EMOTION_ORDER[idx % len(_EMOTION_ORDER)]
            if emo == prev_emo:
                emo = _EMOTION_ORDER[(idx + 1) % len(_EMOTION_ORDER)]
        prev_emo = emo
        cur.puppet = cur.puppet.model_copy(update={"pose": pose, "emotion": emo})

        # Chọn transition theo ngữ nghĩa biên tập
        chapter_changed = idx > 0 and cur.chapter != spec.beats[idx - 1].chapter
        if idx == 0:
            trans: TransitionType = "editorial_cut"
        elif cur.punch or chapter_changed:
            trans = "whip_pan"
        elif cand_shot in ("card_hero", "split_compare", "data_spotlight"):
            trans = "paper_slide"
        else:
            trans = "editorial_cut"
        cur.transition_in = trans

        # Audio cues (Silence Drop 320ms, J-cut 160ms, Foley)
        cues = list(cur.audio_cues)
        existing_kinds = {c.kind for c in cues}
        if cur.punch and "silence_drop" not in existing_kinds:
            cues.append(
                AudioCue(
                    kind="silence_drop",
                    tag="drop",
                    duration_ms=spec.audio.silence_drop_ms,
                )
            )
        if chapter_changed and "j_cut" not in existing_kinds:
            cues.append(AudioCue(kind="j_cut", tag="lead", offset_ms=-spec.audio.jl_cut_ms))
        if "foley" not in existing_kinds:
            foley_tag = (
                "paper_slide"
                if trans == "paper_slide"
                else ("whoosh" if trans == "whip_pan" else cur.sfx_tag or "pop")
            )
            cues.append(AudioCue(kind="foley", tag=foley_tag, gain_db=-2.0))
        cur.audio_cues = cues

        assigned.append(cur)

    return spec.model_copy(update={"beats": assigned})


def _offline_story_beats(idea: str, *, topic: str, target_minutes: float) -> list[BeatSpec]:
    clean_idea = (idea or "Khám phá khoa học").strip()
    n_beats = max(4, min(8, int(round(max(0.5, float(target_minutes)) * 5))))
    templates = [
        (
            f"Bạn có biết một sự thật bất ngờ về {clean_idea} mà ít ai để ý không?",
            "Điểm khởi đầu",
            [
                "**Góc nhìn mới** vượt khỏi trực giác thông thường",
                "Dữ liệu mở đầu **khác biệt 3 lần**",
            ],
            "Không phải điều hiển nhiên nào cũng đúng",
            "bullets",
            True,
        ),
        (
            "Nhiều người tin theo lầm tưởng cũ, nhưng bằng chứng thực nghiệm lại chỉ ngược lại.",
            "Đối chiếu 2 góc nhìn",
            ["Tin theo cảm tính truyền miệng", "Kiểm chứng bằng **đo lường thực tế**"],
            "Kiểm chứng luôn thắng cảm tính",
            "myth_vs_fact",
            False,
        ),
        (
            "Các số liệu đo đạc ghi nhận mức chênh lệch tới 85% so với giả thuyết ban đầu.",
            "Con số biết nói",
            ["Chênh lệch thực nghiệm đạt **85%**", "Chu kỳ lặp ổn định **120ms**"],
            "85% khác biệt đến từ cơ chế nền",
            "big_number",
            True,
        ),
        (
            "Nếu hiểu đúng cơ chế này, bạn sẽ lý giải được hàng loạt hiện tượng trong đời sống.",
            "Cơ chế vận hành",
            ["Bước 1: **Kích hoạt** tín hiệu gốc", "Bước 2: **Khuếch đại** hiệu ứng dây chuyền"],
            "Hiểu bản chất giúp dự đoán chính xác",
            "bullets",
            False,
        ),
    ]
    out: list[BeatSpec] = []
    for i in range(max(3, n_beats - 1)):
        tpl = templates[i % len(templates)]
        out.append(
            BeatSpec(
                id=f"b{i + 1:03d}",
                chapter=1 if i < 2 else 2,
                chapter_title=f"Phần {1 if i < 2 else 2}: {topic.title()}",
                narration=tpl[0],
                duration_sec=3.5,
                board=BoardSpec(
                    board_type=tpl[4],
                    title=tpl[1],
                    bullets=list(tpl[2]),
                    takeaway=tpl[3],
                ),
                puppet=PuppetSpec(enabled=True, pose=_POSE_ORDER[i % len(_POSE_ORDER)]),
                punch=tpl[5],
            )
        )
    out.append(
        BeatSpec(
            id=f"b{len(out) + 1:03d}",
            chapter=2,
            chapter_title="Tổng kết",
            narration=(
                "Bạn nghĩ sao về điều này? Hãy bình luận và đăng ký kênh để khám phá tiếp nhé!"
            ),
            duration_sec=3.5,
            board=BoardSpec(
                board_type="recap_card",
                title="TÓM TẮT 3 Ý CỐT LÕI",
                bullets=[
                    "Góc nhìn **kiểm chứng**",
                    "Chênh lệch **85%** thực nghiệm",
                    "Hiểu **cơ chế nền tảng**",
                ],
                takeaway="Lưu lại để áp dụng ngay",
            ),
            puppet=PuppetSpec(enabled=True, pose="wave_hello", emotion="happy"),
        )
    )
    return out


def direct_timeline(
    idea: str,
    *,
    topic: str = "science",
    domain: str = "paper_classic",
    aspect: AspectRatio = "9:16",
    theme: CinemaTheme = "cream",
    fps: int = 30,
    target_minutes: float = 1.0,
    model: str | None = None,
    use_llm: bool = False,
) -> TimelineSpec:
    """Biên tập 1 TimelineSpec hoàn chỉnh (Dual-Pass LLM nếu bật, fallback offline an toàn 100%)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (idea or "cinema").lower()).strip("-")[:48] or "cinema-clip"
    title = (idea or "Video HBT Cinema").strip()[:120]
    beats: list[BeatSpec] | None = None

    if use_llm:
        try:
            p1 = build_pass1_story_prompt(idea, topic=topic, target_minutes=target_minutes)
            story_json, _ = generate_structured_json(
                "Bạn là biên kịch HBT Studio.", p1, model=model, temperature=0.7
            )
            raw_beats = story_json.get("beats") or []
            if isinstance(raw_beats, list) and raw_beats:
                title = str(story_json.get("title") or title)[:120]
                p2 = build_pass2_editorial_prompt(raw_beats, aspect=aspect, domain=domain)
                ed_json, _ = generate_structured_json(
                    "Bạn là đạo diễn hình ảnh HBT Studio.", p2, model=model, temperature=0.4
                )
                ed_map = {
                    str(item.get("id") or ""): item
                    for item in (ed_json.get("beats") or [])
                    if isinstance(item, dict)
                }
                compiled: list[BeatSpec] = []
                for idx, sb in enumerate(raw_beats):
                    if not isinstance(sb, dict):
                        continue
                    bid = str(sb.get("id") or f"b{idx + 1:03d}")
                    eb = ed_map.get(bid, {})
                    compiled.append(
                        BeatSpec(
                            id=bid,
                            chapter=max(1, int(sb.get("chapter") or 1)),
                            chapter_title=str(sb.get("chapter_title") or ""),
                            narration=str(sb.get("narration") or ""),
                            duration_sec=4.0,
                            shot_type=eb.get("shot_type", "desk_wide"),
                            transition_in=eb.get("transition_in", "editorial_cut"),
                            board=BoardSpec(
                                board_type=str(eb.get("board_type") or "bullets"),
                                title=str(sb.get("board_title") or ""),
                                bullets=[str(x) for x in (sb.get("facts") or [])][:3],
                                takeaway=str(sb.get("takeaway") or ""),
                            ),
                            puppet=PuppetSpec(
                                enabled=True,
                                pose=str(eb.get("pose") or "present_board"),
                                emotion=str(eb.get("emotion") or "auto"),
                            ),
                            sfx_tag=str(eb.get("sfx_tag") or "whoosh"),
                            punch=bool(sb.get("punch", False)),
                        )
                    )
                if compiled:
                    beats = compiled
        except (GeminiClientError, Exception):
            beats = None

    if not beats:
        beats = _offline_story_beats(idea, topic=topic, target_minutes=target_minutes)

    raw_spec = TimelineSpec(
        slug=slug,
        title=title,
        source_engine="cinema",
        topic=topic,
        domain=domain,
        theme=theme,
        aspect=aspect,
        fps=fps,
        audio=AudioPlan(),
        beats=beats,
    )
    directed = assign_editorial_shots(raw_spec)
    report = PreflightQualityGate().validate_and_reflow(directed, auto_fix=True)
    return report.repaired_spec
