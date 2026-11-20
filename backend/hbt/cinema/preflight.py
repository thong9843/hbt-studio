"""Cổng kiểm định tiền kỳ (PreflightQualityGate): AABB Auto-Reflow, Anti-Parrot & Pacing."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from hbt.cinema.schema import AspectRatio, BBox, BeatSpec, ShotType, TimelineSpec

ANTI_PARROT_THRESHOLD = 0.55

SAFE_ZONES: dict[AspectRatio, dict[str, BBox]] = {
    "9:16": {
        "stage": BBox(x=48, y=115, w=984, h=1585),  # y in [115, 1700]
        "karaoke": BBox(x=64, y=890, w=952, h=140),
        "board_max": BBox(x=48, y=115, w=984, h=745),
        "puppet_zone": BBox(x=140, y=1055, w=800, h=640),
    },
    "16:9": {
        "stage": BBox(x=56, y=72, w=1808, h=938),  # y in [72, 1010]
        "karaoke": BBox(x=160, y=905, w=1600, h=96),
        "board_max": BBox(x=640, y=72, w=1224, h=810),
        "puppet_zone": BBox(x=56, y=140, w=570, h=745),
    },
}

_CTA_KEYWORDS: tuple[str, ...] = (
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

_SHOT_CYCLE: tuple[ShotType, ...] = (
    "desk_wide",
    "card_hero",
    "data_spotlight",
    "puppet_closeup",
    "split_compare",
)

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


class PreflightIssue(BaseModel):
    """Một lỗi hoặc cảnh báo phát hiện tại cổng kiểm định hình học & nội dung."""

    beat_id: str | None = None
    beat_index: int | None = None
    code: str
    severity: Literal["error", "warn"] = "error"
    message: str
    auto_fixed: bool = False


class PreflightReport(BaseModel):
    """Báo cáo đầy đủ sau kiểm định & Auto-Reflow."""

    ok: bool
    errors: list[PreflightIssue] = Field(default_factory=list)
    warnings: list[PreflightIssue] = Field(default_factory=list)
    fixed_count: int = 0
    repaired_spec: TimelineSpec
    stats: dict[str, Any] = Field(default_factory=dict)


def default_boxes_for_shot(
    shot_type: ShotType,
    aspect: AspectRatio,
) -> tuple[BBox, BBox, BBox]:
    """Trả về bộ khung `(board_bbox, puppet_bbox, karaoke_bbox)` chuẩn an toàn không đè nhau."""
    if aspect == "9:16":
        if shot_type == "puppet_closeup":
            board = BBox(x=200, y=122, w=680, h=76)
            karaoke = BBox(x=64, y=820, w=952, h=140)
            puppet = BBox(x=190, y=990, w=700, h=700)
            return board, puppet, karaoke
        if shot_type == "card_hero":
            board = BBox(x=48, y=120, w=984, h=730)
            karaoke = BBox(x=64, y=888, w=952, h=140)
            puppet = BBox(x=140, y=1065, w=540, h=625)
            return board, puppet, karaoke
        if shot_type == "split_compare":
            board = BBox(x=52, y=128, w=976, h=710)
            karaoke = BBox(x=64, y=890, w=952, h=140)
            puppet = BBox(x=240, y=1060, w=600, h=630)
            return board, puppet, karaoke
        if shot_type == "data_spotlight":
            board = BBox(x=52, y=124, w=976, h=720)
            karaoke = BBox(x=64, y=890, w=952, h=140)
            puppet = BBox(x=230, y=1060, w=600, h=630)
            return board, puppet, karaoke
        if shot_type == "recap_grid":
            board = BBox(x=52, y=120, w=976, h=734)
            karaoke = BBox(x=64, y=890, w=952, h=140)
            puppet = BBox(x=240, y=1060, w=580, h=625)
            return board, puppet, karaoke
        # desk_wide mặc định
        board = BBox(x=56, y=130, w=968, h=704)
        karaoke = BBox(x=64, y=890, w=952, h=140)
        puppet = BBox(x=240, y=1060, w=600, h=630)
        return board, puppet, karaoke

    # 16:9 (1920x1080)
    if shot_type == "puppet_closeup":
        board = BBox(x=1040, y=110, w=800, h=680)
        karaoke = BBox(x=160, y=905, w=1600, h=96)
        puppet = BBox(x=120, y=150, w=720, h=730)
        return board, puppet, karaoke
    if shot_type == "card_hero":
        board = BBox(x=640, y=84, w=1208, h=792)
        karaoke = BBox(x=160, y=905, w=1600, h=96)
        puppet = BBox(x=80, y=220, w=510, h=660)
        return board, puppet, karaoke
    board = BBox(x=680, y=96, w=1160, h=770)
    karaoke = BBox(x=160, y=905, w=1600, h=96)
    puppet = BBox(x=90, y=200, w=530, h=680)
    return board, puppet, karaoke


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2}


def word_overlap_ratio(narration: str, board_text: str) -> float:
    """Tính tỷ lệ trùng lặp từ vựng giữa lời thoại và chữ trên bảng (0.0 .. 1.0)."""
    wa = _tokens(narration)
    wb = _tokens(board_text)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def _board_joined_text(beat: BeatSpec) -> str:
    parts = [beat.board.title, *beat.board.bullets]
    return " ".join(p.strip() for p in parts if p and p.strip())


def _is_cta_narration(text: str) -> bool:
    low = (text or "").lower()
    return any(kw in low for kw in _CTA_KEYWORDS)


def _rewrite_anti_parrot_board(beat: BeatSpec) -> tuple[str, list[str], str]:
    """Chuyển bảng chép lời thoại thành thẻ phân tích cô đọng, đảm bảo overlap <= 0.55."""
    nar = (beat.narration or "").strip()
    nums = re.findall(
        r"\d[\d.,]*\s*(?:%|ms|giây|phút|năm|tcn|triệu|tỷ|nghìn|lần|km|°)?",
        nar,
        re.I,
    )
    takeaway = (beat.board.takeaway or "").strip()

    new_title = "DỮ KIỆN PHÂN TÍCH"
    for cand_t in ("DỮ KIỆN PHÂN TÍCH", "TỔNG HỢP KHOA HỌC", "BẢN ĐỒ Ý CHÍNH", "HỒ SƠ PHÂN TÍCH"):
        if word_overlap_ratio(nar, cand_t) <= ANTI_PARROT_THRESHOLD:
            new_title = cand_t
            break

    raw_bullets: list[str] = []
    if nums:
        metric = nums[0].strip()
        raw_bullets.append(f"Thông số đo: **{metric}** (mốc kiểm chứng thực tế)")
    else:
        raw_bullets.append("Bản chất cơ chế: **Nguyên nhân dẫn tới hệ quả**")

    if takeaway and word_overlap_ratio(nar, takeaway) <= ANTI_PARROT_THRESHOLD:
        raw_bullets.append(f"Kết luận cốt lõi: **{takeaway[:48]}**")
    else:
        raw_bullets.append("Điểm phân biệt: **Góc nhìn thực nghiệm khách quan**")
    raw_bullets.append("Ứng dụng nhanh: **Ghi nhớ theo mô hình chuẩn**")

    bullets = [b for b in raw_bullets if word_overlap_ratio(nar, b) <= ANTI_PARROT_THRESHOLD]
    safe_fallbacks = (
        "Trục số liệu: **Định lượng kiểm chứng khách quan**",
        "Chuỗi tác động: **Cơ chế nền tảng xuyên suốt**",
        "Ghi chú chuyên môn: **Thực tế đối chiếu chuẩn xác**",
    )
    for fb in safe_fallbacks:
        if len(bullets) >= 3:
            break
        if word_overlap_ratio(nar, fb) <= ANTI_PARROT_THRESHOLD and fb not in bullets:
            bullets.append(fb)

    if word_overlap_ratio(nar, f"{new_title} {' '.join(bullets)}") > ANTI_PARROT_THRESHOLD:
        new_title = "BẢN ĐỒ Ý CHÍNH"
        bullets = [
            "Mốc #1: **Nguyên nhân gốc rễ**",
            "Mốc #2: **Hệ quả trực tiếp**",
            "Mốc #3: **Áp dụng thực tiễn**",
        ]
    new_takeaway = takeaway or "Tập trung cơ chế cốt lõi thay vì học thuộc"
    return new_title, bullets[:3], new_takeaway[:160]


def _pick_diverse_shot(
    beat: BeatSpec,
    prev_shot: ShotType | None,
    next_shot: ShotType | None,
) -> ShotType:
    preferred: list[ShotType] = []
    btype = beat.board.board_type
    if btype == "recap_card":
        preferred.append("recap_grid")
    elif btype in ("comparison", "myth_vs_fact"):
        preferred.append("split_compare")
    elif btype in ("big_number", "bar_compare", "counter_grow"):
        preferred.append("data_spotlight")
    for cand in _SHOT_CYCLE:
        if cand not in preferred:
            preferred.append(cand)

    for cand in preferred:
        if cand != prev_shot and cand != next_shot:
            return cand
    for cand in preferred:
        if cand != prev_shot:
            return cand
    return "card_hero" if prev_shot != "card_hero" else "desk_wide"


def _inspect_timeline(spec: TimelineSpec) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    safe = SAFE_ZONES[spec.aspect]["stage"]
    n_beats = len(spec.beats)

    for idx, beat in enumerate(spec.beats):
        default_board, default_puppet, default_karaoke = default_boxes_for_shot(
            beat.shot_type, spec.aspect
        )
        b_box = beat.board.bbox or default_board
        p_box = beat.puppet.bbox or default_puppet
        k_box = beat.karaoke_bbox or default_karaoke

        # 1. Kiểm tra tọa độ âm (y < 0 hoặc x < 0)
        for label, box in (("Bảng", b_box), ("Nhân vật", p_box), ("Karaoke", k_box)):
            if label == "Nhân vật" and not beat.puppet.enabled:
                continue
            if box.y < 0 or box.x < 0:
                issues.append(
                    PreflightIssue(
                        beat_id=beat.id,
                        beat_index=idx,
                        code="NEGATIVE_COORD",
                        severity="error",
                        message=f"{label} bị đẩy ra tọa độ âm (x={box.x:.0f}, y={box.y:.0f})",
                    )
                )

        # 2. Kiểm tra tràn Safe-Zone
        for label, box in (("Bảng", b_box), ("Nhân vật", p_box), ("Karaoke", k_box)):
            if label == "Nhân vật" and not beat.puppet.enabled:
                continue
            if box.x < safe.x or box.y < safe.y or box.x2 > safe.x2 or box.y2 > safe.y2:
                issues.append(
                    PreflightIssue(
                        beat_id=beat.id,
                        beat_index=idx,
                        code="SAFE_ZONE_VIOLATION",
                        severity="error",
                        message=(
                            f"{label} vượt vùng an toàn "
                            f"[{safe.x:.0f}..{safe.x2:.0f}, {safe.y:.0f}..{safe.y2:.0f}]"
                        ),
                    )
                )

        # 3. Kiểm tra va chạm với dải Karaoke
        if beat.board.board_type != "none" and b_box.intersects(k_box, margin=4.0):
            issues.append(
                PreflightIssue(
                    beat_id=beat.id,
                    beat_index=idx,
                    code="KARAOKE_COLLISION",
                    severity="error",
                    message="Bảng tri thức đè lên vùng phụ đề Karaoke",
                )
            )
        if beat.puppet.enabled and p_box.intersects(k_box, margin=4.0):
            issues.append(
                PreflightIssue(
                    beat_id=beat.id,
                    beat_index=idx,
                    code="PUPPET_KARAOKE_COLLISION",
                    severity="error",
                    message="Nhân vật đè lên vùng phụ đề Karaoke",
                )
            )

        # 4. Kiểm tra Bảng đè Nhân vật
        if (
            beat.puppet.enabled
            and beat.board.board_type != "none"
            and b_box.intersects(p_box, margin=4.0)
        ):
            issues.append(
                PreflightIssue(
                    beat_id=beat.id,
                    beat_index=idx,
                    code="BOARD_PUPPET_COLLISION",
                    severity="error",
                    message="Bảng tri thức đè lên nhân vật Stickman",
                )
            )

        # 5. Kiểm tra Anti-Parrot (>55% trùng từ trên tiêu đề, từng mục hoặc toàn bảng)
        if beat.board.board_type not in ("none", "recap_card", "big_number", "counter_grow"):
            joined = _board_joined_text(beat)
            title_hit = bool(beat.board.title) and (
                word_overlap_ratio(beat.narration, beat.board.title) > ANTI_PARROT_THRESHOLD
            )
            bullet_hit = any(
                word_overlap_ratio(beat.narration, bl) > ANTI_PARROT_THRESHOLD
                for bl in beat.board.bullets
                if bl and bl.strip()
            )
            if (
                title_hit
                or bullet_hit
                or (joined and word_overlap_ratio(beat.narration, joined) > ANTI_PARROT_THRESHOLD)
            ):
                issues.append(
                    PreflightIssue(
                        beat_id=beat.id,
                        beat_index=idx,
                        code="ANTI_PARROT",
                        severity="error",
                        message="Nội dung bảng trùng lời thoại >55% (vi phạm luật Anti-Parrot)",
                    )
                )

        # 6. Kiểm tra beat CTA cuối phải chuyển sang recap_card
        is_tail = idx >= max(0, n_beats - 2)
        if is_tail and _is_cta_narration(beat.narration) and beat.board.board_type != "recap_card":
            issues.append(
                PreflightIssue(
                    beat_id=beat.id,
                    beat_index=idx,
                    code="CTA_RECAP_REQUIRED",
                    severity="error",
                    message="Beat CTA cuối video phải dùng bảng recap_card tổng hợp 3 ý cốt lõi",
                )
            )

        # 7. Kiểm tra lặp 2 shot_type liên tiếp
        if idx > 0 and spec.beats[idx - 1].shot_type == beat.shot_type:
            issues.append(
                PreflightIssue(
                    beat_id=beat.id,
                    beat_index=idx,
                    code="REPEATED_SHOT_TYPE",
                    severity="error",
                    message=f"Lặp 2 góc máy '{beat.shot_type}' liên tiếp",
                )
            )

    return issues


class PreflightQualityGate:
    """Cổng kiểm định + Auto-Reflow chặn 100% lỗi bố cục và nội dung trước khi render."""

    def validate_and_reflow(
        self,
        spec: TimelineSpec,
        *,
        auto_fix: bool = True,
    ) -> PreflightReport:
        initial_issues = _inspect_timeline(spec)
        if not auto_fix:
            errs = [i for i in initial_issues if i.severity == "error"]
            warns = [i for i in initial_issues if i.severity == "warn"]
            out_spec = spec.model_copy(update={"preflight_passed": len(errs) == 0})
            return PreflightReport(
                ok=len(errs) == 0,
                errors=errs,
                warnings=warns,
                fixed_count=0,
                repaired_spec=out_spec,
                stats={
                    "initial_errors": len(errs),
                    "remaining_errors": len(errs),
                    "bbox_reflows": 0,
                    "anti_parrot_rewrites": 0,
                    "pacing_diversifications": 0,
                    "recap_conversions": 0,
                },
            )

        repaired_beats: list[BeatSpec] = []
        collected_insights: list[str] = []
        n_beats = len(spec.beats)
        bbox_reflows = 0
        anti_parrot_rewrites = 0
        pacing_diversifications = 0
        recap_conversions = 0

        for idx, beat in enumerate(spec.beats):
            cur = beat.model_copy(deep=True)
            prev_shot = repaired_beats[-1].shot_type if repaired_beats else None
            next_shot = spec.beats[idx + 1].shot_type if idx + 1 < n_beats else None

            # A. Chuyển beat CTA cuối sang recap_card + shot recap_grid
            is_tail = idx >= max(0, n_beats - 2)
            if (
                is_tail
                and _is_cta_narration(cur.narration)
                and cur.board.board_type != "recap_card"
            ):
                recap_pts = list(dict.fromkeys(collected_insights))[-3:]
                if len(recap_pts) < 3:
                    for pb in spec.beats[:idx]:
                        t = (pb.board.title or "").strip()
                        if t and not _is_cta_narration(t) and t not in recap_pts:
                            recap_pts.append(f"**{t[:42]}**")
                        if len(recap_pts) >= 3:
                            break
                recap_pts = (
                    recap_pts
                    or [
                        "Nắm vững **nguyên lý gốc**",
                        "Nhận diện **lầm tưởng**",
                        "Áp dụng **thực tiễn**",
                    ]
                )[:3]
                cur.board = cur.board.model_copy(
                    update={
                        "board_type": "recap_card",
                        "title": "TÓM TẮT 3 Ý CỐT LÕI",
                        "bullets": recap_pts,
                        "takeaway": cur.board.takeaway or "Lưu lại để áp dụng ngay",
                    }
                )
                cur.shot_type = "recap_grid"
                recap_conversions += 1

            # B. Phá lặp 2 shot_type liên tiếp
            if prev_shot is not None and cur.shot_type == prev_shot:
                cur.shot_type = _pick_diverse_shot(cur, prev_shot, next_shot)
                pacing_diversifications += 1

            # C. Anti-Parrot >55% (kiểm cả tiêu đề, từng ý và tổng bảng)
            if cur.board.board_type not in ("none", "recap_card", "big_number", "counter_grow"):
                joined = _board_joined_text(cur)
                title_hit = bool(cur.board.title) and (
                    word_overlap_ratio(cur.narration, cur.board.title) > ANTI_PARROT_THRESHOLD
                )
                bullet_hit = any(
                    word_overlap_ratio(cur.narration, bl) > ANTI_PARROT_THRESHOLD
                    for bl in cur.board.bullets
                    if bl and bl.strip()
                )
                if (
                    title_hit
                    or bullet_hit
                    or (
                        joined and word_overlap_ratio(cur.narration, joined) > ANTI_PARROT_THRESHOLD
                    )
                ):
                    nt, nb, nk = _rewrite_anti_parrot_board(cur)
                    cur.board = cur.board.model_copy(
                        update={"title": nt, "bullets": nb, "takeaway": nk}
                    )
                    anti_parrot_rewrites += 1

            # Thu thập điểm chốt cho recap cuối
            if cur.board.takeaway and not _is_cta_narration(cur.board.takeaway):
                collected_insights.append(cur.board.takeaway[:64])
            elif cur.board.bullets and not _is_cta_narration(cur.board.bullets[0]):
                collected_insights.append(cur.board.bullets[0][:64])

            # D. Auto-Reflow hình học AABB
            def_board, def_puppet, def_karaoke = default_boxes_for_shot(cur.shot_type, spec.aspect)
            safe = SAFE_ZONES[spec.aspect]["stage"]
            b_box = cur.board.bbox or def_board
            p_box = cur.puppet.bbox or def_puppet
            k_box = cur.karaoke_bbox or def_karaoke

            bad_geom = (
                b_box.y < 0
                or b_box.x < safe.x
                or b_box.y < safe.y
                or b_box.x2 > safe.x2
                or b_box.y2 > safe.y2
                or k_box.y < 0
                or k_box.x < safe.x
                or k_box.y < safe.y
                or k_box.x2 > safe.x2
                or k_box.y2 > safe.y2
                or (
                    cur.puppet.enabled
                    and (
                        p_box.y < 0
                        or p_box.x < safe.x
                        or p_box.y < safe.y
                        or p_box.x2 > safe.x2
                        or p_box.y2 > safe.y2
                    )
                )
                or (cur.board.board_type != "none" and b_box.intersects(k_box, margin=4.0))
                or (cur.puppet.enabled and p_box.intersects(k_box, margin=4.0))
                or (
                    cur.puppet.enabled
                    and cur.board.board_type != "none"
                    and b_box.intersects(p_box, margin=4.0)
                )
            )

            if bad_geom or cur.board.bbox is None or cur.karaoke_bbox is None:
                if bad_geom:
                    bbox_reflows += 1
                b_box, p_box, k_box = def_board, def_puppet, def_karaoke
                cur.board = cur.board.model_copy(update={"bbox": b_box})
                cur.puppet = cur.puppet.model_copy(update={"bbox": p_box})
                cur.karaoke_bbox = k_box

            repaired_beats.append(cur)

        # Hợp nhất 2 beat cuối nếu cùng là recap_card -> duy nhất 1 nội dung tóm tắt nhất quán
        if (
            len(repaired_beats) >= 2
            and repaired_beats[-2].board.board_type == "recap_card"
            and repaired_beats[-1].board.board_type == "recap_card"
        ):
            src_board = repaired_beats[-2].board
            repaired_beats[-1] = repaired_beats[-1].model_copy(
                update={
                    "board": repaired_beats[-1].board.model_copy(
                        update={
                            "title": src_board.title or "TÓM TẮT 3 Ý CỐT LÕI",
                            "bullets": list(src_board.bullets),
                            "takeaway": src_board.takeaway,
                        }
                    )
                }
            )

        repaired_spec = spec.model_copy(update={"beats": repaired_beats})
        remaining = _inspect_timeline(repaired_spec)
        rem_errs = [i for i in remaining if i.severity == "error"]
        rem_warns = [i for i in remaining if i.severity == "warn"]
        repaired_spec = repaired_spec.model_copy(update={"preflight_passed": len(rem_errs) == 0})

        fixed_issues = [i.model_copy(update={"auto_fixed": True}) for i in initial_issues]
        return PreflightReport(
            ok=len(rem_errs) == 0,
            errors=rem_errs,
            warnings=rem_warns,
            fixed_count=len([i for i in fixed_issues if i.severity == "error"]) - len(rem_errs),
            repaired_spec=repaired_spec,
            stats={
                "initial_errors": len([i for i in initial_issues if i.severity == "error"]),
                "remaining_errors": len(rem_errs),
                "bbox_reflows": bbox_reflows,
                "anti_parrot_rewrites": anti_parrot_rewrites,
                "pacing_diversifications": pacing_diversifications,
                "recap_conversions": recap_conversions,
                "fixed_issues": [i.model_dump(mode="json") for i in fixed_issues],
            },
        )
