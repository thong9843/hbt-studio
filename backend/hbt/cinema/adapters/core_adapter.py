"""Bộ chuyển đổi `HbtCoreScript` (10–12 cảnh) -> `TimelineSpec IR v1` không chạm `pipeline/`."""

from __future__ import annotations

import re

from hbt.cinema.director_ai import assign_editorial_shots
from hbt.cinema.preflight import PreflightQualityGate
from hbt.cinema.schema import (
    AspectRatio,
    AudioPlan,
    BeatSpec,
    BoardSpec,
    CinemaTheme,
    PuppetSpec,
    ShotType,
    TimelineSpec,
)
from hbt.core.models import HbtCoreScript, infer_music_topic

_TOPIC_TO_DOMAIN: dict[str, str] = {
    "history": "history_geo",
    "science": "physics_science",
    "mystery": "cosmos_mystery",
    "fun": "psychology_story",
}

_STICKER_TO_EMOTION: dict[str, str] = {
    "shock": "shock",
    "warning": "serious",
    "question": "curious",
    "think": "curious",
    "laugh": "happy",
    "check": "confident",
}

_STICKER_TO_POSE: dict[str, str] = {
    "shock": "shock_hands_up",
    "warning": "arms_crossed",
    "question": "shrug_ask",
    "think": "think_chin",
    "laugh": "wave_hello",
    "check": "hands_on_hips",
}


def _slugify(raw: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", (raw or "hbt-core").lower()).strip("-")
    return clean[:64] or "hbt-core"


def _distill_core_bullets(text: str, headline: str) -> list[str]:
    nums = re.findall(r"\d[\d.,]*\s*(?:%|ms|năm|km|triệu|tỷ|lần)?", text or "", re.I)
    out: list[str] = []
    if nums:
        out.append(f"Mốc số liệu: **{nums[0].strip()}**")
    if headline:
        out.append(f"Trọng tâm: **{headline[:46]}**")
    if not out:
        out.append("Phân tích **nguyên lý nền tảng**")
    return out[:3]


def core_script_to_timeline(
    script: HbtCoreScript,
    *,
    slug: str | None = None,
    aspect: AspectRatio = "9:16",
    fps: int = 30,
    voice_id: str = "Thanh Bình",
    theme: CinemaTheme = "cream",
    run_director: bool = True,
    run_preflight: bool = True,
) -> TimelineSpec:
    """Biên dịch kịch bản `HbtCoreScript` sang `TimelineSpec v1` mà không sửa `pipeline/`."""
    music_topic = infer_music_topic(script.topic, script.title)
    domain = _TOPIC_TO_DOMAIN.get(music_topic, "paper_classic")
    beats: list[BeatSpec] = []

    for idx, seg in enumerate(script.segments):
        dur = float(seg.duration or 0.0)
        if dur <= 0.0:
            words = len((seg.text or "").split())
            dur = round(max(2.2, min(12.0, words * 0.36)), 2)

        sticker = (seg.sticker or "question").strip().lower()
        pose = _STICKER_TO_POSE.get(sticker, "present_board")
        emotion = _STICKER_TO_EMOTION.get(sticker, "auto")
        headline = (seg.title or seg.card_text or f"Phân đoạn {seg.order}").strip()
        bullets = _distill_core_bullets(seg.text, headline)

        shot: ShotType = "card_hero" if idx % 2 == 0 else "desk_wide"
        if seg.punch or sticker == "shock":
            shot = "puppet_closeup"

        beats.append(
            BeatSpec(
                id=f"seg{seg.order:03d}",
                chapter=1 if idx < max(1, len(script.segments) // 2) else 2,
                chapter_title=script.title[:60],
                narration=seg.text,
                duration_sec=dur,
                shot_type=shot,
                transition_in="whip_pan"
                if seg.punch
                else ("editorial_cut" if idx == 0 else "paper_slide"),
                board=BoardSpec(
                    board_type="bullets",
                    title=headline[:120],
                    bullets=bullets,
                    takeaway=headline[:140],
                ),
                puppet=PuppetSpec(
                    enabled=True,
                    pose=pose,
                    emotion=emotion,
                ),
                media_path=str(seg.image or ""),
                image_prompt=str(seg.image_prompt or ""),
                sfx_tag=str(seg.sfx or "whoosh"),
                punch=bool(seg.punch),
            )
        )

    spec = TimelineSpec(
        slug=slug or _slugify(script.title),
        title=script.title or "HBT Core Cinema",
        source_engine="core",
        topic=music_topic,
        domain=domain,
        theme=theme,
        aspect=aspect,
        fps=max(15, min(60, int(fps))),
        audio=AudioPlan(voice_id=voice_id or "Thanh Bình", music_mood=music_topic),
        beats=beats,
    )
    if run_director:
        spec = assign_editorial_shots(spec)
    if run_preflight:
        spec = PreflightQualityGate().validate_and_reflow(spec, auto_fix=True).repaired_spec
    return spec
