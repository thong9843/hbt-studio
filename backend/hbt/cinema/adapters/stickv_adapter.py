"""Bộ chuyển đổi `StickvProject` -> `TimelineSpec IR v1` (nối puppet.py v3 18 dáng x 10 cảm xúc)."""

from __future__ import annotations

from hbt.cinema.director_ai import assign_editorial_shots
from hbt.cinema.preflight import PreflightQualityGate
from hbt.cinema.schema import (
    AudioPlan,
    BeatSpec,
    BoardSpec,
    PuppetSpec,
    ShotType,
    TimelineSpec,
)
from hbt.stickv.models import StickvProject
from hbt.stickv.puppet import normalize_stickv_pose, resolve_stickv_emotion

_CAM_TO_SHOT: dict[str, ShotType] = {
    "wide_stage": "desk_wide",
    "focus_board": "card_hero",
    "closeup_react": "puppet_closeup",
}


def stickv_to_timeline(
    project: StickvProject,
    *,
    run_director: bool = True,
    run_preflight: bool = True,
) -> TimelineSpec:
    """Biên dịch `StickvProject` sang `TimelineSpec` v1 giữ nguyên toàn bộ cấu trúc StickV v9."""
    beats: list[BeatSpec] = []
    for idx, sb in enumerate(project.beats):
        bdata = dict(sb.board_data or {})
        raw_items = sb.board_items or bdata.get("items") or []
        bullets = [str(x).strip() for x in raw_items if str(x).strip()][:4]
        takeaway = str(sb.takeaway or bdata.get("takeaway") or "").strip()[:200]
        btype = str(sb.board_type or "bullets").strip().lower()

        if btype == "recap_card":
            shot: ShotType = "recap_grid"
        elif btype in ("comparison", "myth_vs_fact"):
            shot = "split_compare"
        elif btype in ("big_number", "bar_compare", "counter_grow"):
            shot = "data_spotlight"
        else:
            shot = _CAM_TO_SHOT.get(str(sb.camera_shot or "wide_stage"), "desk_wide")

        dur = float(sb.duration_sec or 0.0)
        if dur <= 0.0:
            words = len((sb.narration or "").split())
            dur = round(max(2.2, min(12.0, words * 0.36)), 2)

        pose = normalize_stickv_pose(sb.pose)
        emotion = resolve_stickv_emotion(sb.emotion, sb.pose, sb.narration)

        beats.append(
            BeatSpec(
                id=sb.id or f"b{idx + 1:03d}",
                chapter=int(sb.chapter or 1),
                chapter_title=str(sb.chapter_title or ""),
                narration=str(sb.narration or ""),
                duration_sec=dur,
                shot_type=shot,
                transition_in="editorial_cut" if idx == 0 else "paper_slide",
                board=BoardSpec(
                    board_type=btype,
                    title=str(sb.board_title or ""),
                    bullets=bullets,
                    takeaway=takeaway,
                    data=bdata,
                ),
                puppet=PuppetSpec(
                    enabled=True,
                    pose=pose,
                    emotion=emotion,
                    facing=sb.facing,
                    interaction=sb.interaction,
                    prop_query=sb.prop_query,
                ),
                media_path=str(sb.media_path or ""),
                sfx_tag=str(sb.sfx_tag or "whoosh"),
                punch=(sb.sfx_tag == "vine_boom"),
            )
        )

    spec = TimelineSpec(
        slug=project.slug,
        title=project.title,
        source_engine="stickv",
        topic=project.topic,
        domain=project.domain,
        theme=project.theme,
        aspect=project.aspect,
        fps=project.fps,
        outro=project.outro,
        audio=AudioPlan(
            voice_id=project.voice_id or "Thanh Bình",
            music_mood=project.music_mood or "curious_science",
        ),
        beats=beats,
    )

    if run_director:
        spec = assign_editorial_shots(spec)
    if run_preflight:
        spec = PreflightQualityGate().validate_and_reflow(spec, auto_fix=True).repaired_spec
    return spec
