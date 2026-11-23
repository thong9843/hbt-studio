"""Kiểm thử Smart Asset Director: PacingGovernor & FreshnessMemory."""

from __future__ import annotations

from pathlib import Path

from hbt.shared.asset_director import (
    BeatCue,
    FreshnessMemory,
    PacingGovernor,
    PacingPolicy,
)


def test_pacing_governor_strips_15_msg_spam_and_keeps_climax() -> None:
    """15 tin nhắn bị LLM nhồi meme cả 15 -> siết còn <= 2 tin, cách >= 4 tin, bỏ setup đầu."""
    cues = [
        BeatCue(
            index=i,
            text=f"Tin nhắn {i}",
            beat_role="setup" if i == 0 else ("punchline" if i in (6, 13) else "build"),
            intensity=5 if i in (6, 13) else 4,
            meme_query=f"reaction {i}",
            est_time_s=i * 3.0,
        )
        for i in range(15)
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    kept = gov.select_visual_beats(cues)

    # floor(15 * 0.18) = 2
    assert 1 <= len(kept) <= 2
    assert 0 not in kept
    assert 6 in kept and 13 in kept
    for a, b in zip(kept, kept[1:], strict=False):
        assert b - a >= 4
        assert cues[b].est_time_s - cues[a].est_time_s >= 8.0


def test_pacing_governor_enforces_time_gap_and_no_consecutive() -> None:
    """Dù intensity=5 liên tiếp, không bao giờ chọn 2 tin sát nhau hoặc cách < 8.0s."""
    cues = [
        BeatCue(
            index=i,
            beat_role="punchline" if i > 0 else "setup",
            intensity=5,
            meme_query="cat shocked",
            est_time_s=i * 1.5,  # 15 tin * 1.5s = 22.5s
        )
        for i in range(18)
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    kept = gov.select_visual_beats(cues)

    assert 1 <= len(kept) <= 3
    assert 0 not in kept
    for a, b in zip(kept, kept[1:], strict=False):
        assert b - a >= 4
        assert cues[b].est_time_s - cues[a].est_time_s >= 8.0


def test_pacing_governor_fallback_to_single_intensity_3_punchline() -> None:
    """Khi không có tin nào intensity >= 4, hạ 1 bậc giữ đúng 1 punchline/twist intensity == 3."""
    cues = [
        BeatCue(index=0, beat_role="setup", intensity=3, meme_query="hi", est_time_s=0.0),
        BeatCue(index=3, beat_role="build", intensity=3, meme_query="ok", est_time_s=9.0),
        BeatCue(index=8, beat_role="twist", intensity=3, meme_query="side eye", est_time_s=24.0),
        BeatCue(index=11, beat_role="punchline", intensity=3, meme_query="facepalm", est_time_s=33.0),
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    assert gov.select_visual_beats(cues) == [11]


def test_pacing_governor_sfx_and_duration_clamps() -> None:
    cues = [
        BeatCue(index=i, beat_role="twist" if i > 0 else "setup", intensity=4, sfx_query="vine boom", est_time_s=i * 2.5)
        for i in range(12)
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    sfx_kept = gov.select_sfx_beats(cues)
    assert 1 <= len(sfx_kept) <= 4
    assert 0 not in sfx_kept
    for a, b in zip(sfx_kept, sfx_kept[1:], strict=False):
        assert cues[b].est_time_s - cues[a].est_time_s >= 6.5

    assert gov.clamp_video_meme_duration(0.4) == 1.2
    assert gov.clamp_video_meme_duration(9.5) == 3.8
    assert gov.clamp_video_meme_duration(2.4) == 2.4
    assert gov.static_sticker_duration(4) == 1.1
    assert gov.static_sticker_duration(5) == 1.5


def test_freshness_memory_cooldown_and_recovery(tmp_path: Path) -> None:
    """Tài nguyên dùng ở video N bị phạt trong 6 video tiếp theo và hồi về 0 từ video N+6."""
    mem = FreshnessMemory(tmp_path / "asset_usage.json", cooldown_videos=6)
    seq_n = mem.advance_video_seq()  # seq = 1
    assert seq_n == 1
    mem.record_usage("memes", "shocked-cat", source="giphy", source_id="g1", video_seq=seq_n)

    # Ngay ở video N (age=0): penalty = 0.65
    assert mem.is_in_cooldown("memes", "shocked-cat", video_seq=seq_n) is True
    assert mem.cooldown_penalty("memes", "shocked-cat", video_seq=seq_n) == 0.65
    assert mem.use_decay("memes", "shocked-cat") == 0.03

    # Video N+3 (age=3): penalty giảm một nửa
    p_mid = mem.cooldown_penalty("memes", "shocked-cat", video_seq=seq_n + 3)
    assert 0.30 < p_mid < 0.35

    # Video N+5 (age=5): vẫn trong cooldown
    assert mem.is_in_cooldown("memes", "shocked-cat", video_seq=seq_n + 5) is True

    # Video N+6 (age=6): hết cooldown, penalty == 0.0
    assert mem.is_in_cooldown("memes", "shocked-cat", video_seq=seq_n + 6) is False
    assert mem.cooldown_penalty("memes", "shocked-cat", video_seq=seq_n + 6) == 0.0
