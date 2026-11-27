"""Kiểm thử State-Chained Beat Cache & Per-Beat TTS WAV Cache (P3b)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from hbt.shared.audio_utils import write_fallback_speech_wav_atomic
from hbt.shared.pipeline.watermark import WatermarkSettings
from hbt.stickv.audio import synth_stickv_beats_audio
from hbt.stickv.beat_cache import (
    StickvBeatCache,
    compute_beat_cache_key,
    deserialize_stage_state,
    serialize_stage_state,
)
from hbt.stickv.models import StickvBeat
from hbt.stickv.puppet import PuppetPoseState
from hbt.stickv.stage import BeatStageState


def test_stage_state_roundtrip_preserves_all_6_spring_velocities() -> None:
    ps = PuppetPoseState(
        head_angle=3.25,
        head_dx=-1.5,
        arm_l_angle=12.0,
        elbow_l_angle=-18.0,
        arm_r_angle=9.5,
        elbow_r_angle=-22.0,
        torso_angle=1.75,
        torso_dx=4.2,
        torso_dy=-2.1,
        torso_scale_y=1.03,
        lw_x=-0.18,
        lw_y=-0.34,
        rw_x=0.22,
        rw_y=-0.41,
        lw_vx=0.8125,
        lw_vy=-0.4375,
        rw_vx=-0.25,
        rw_vy=0.625,
        head_vel=-2.125,
        torso_vel=1.375,
    )
    st = BeatStageState(
        x=180.5,
        y=512.25,
        scale=0.92,
        pose_state=ps,
        camera_zoom=1.08,
        camera_pan_x=0.45,
        camera_pan_y=0.52,
        board_alpha=0.88,
        camera_shot="focus_board",
        last_board_title="Tháp nghiêng Pisa",
        last_board_type="pinned_photo",
        last_chapter=2,
    )
    raw = serialize_stage_state(st)
    restored = deserialize_stage_state(raw)
    assert restored == st


def test_beat_cache_hit_chain_invalidation_and_env_bypass(tmp_path: Path) -> None:
    cache = StickvBeatCache(tmp_path / "beat_cache", max_mb=50.0)
    b1 = StickvBeat(id="b001", narration="Beat đầu tiên.", pose="explain", sfx_tag="none")
    b2 = StickvBeat(id="b002", narration="Beat thứ hai.", pose="happy", sfx_tag="none")
    wm = WatermarkSettings(enabled=False)

    st1 = BeatStageState(
        x=100.0,
        y=500.0,
        scale=1.0,
        pose_state=PuppetPoseState(lw_vx=0.42, head_vel=-0.75),
        camera_shot="wide_stage",
    )
    board1 = Image.new("RGBA", (64, 64), (255, 0, 0, 180))
    src_mp4 = tmp_path / "src.mp4"
    src_mp4.write_bytes(b"\x00" * 512)

    key1 = compute_beat_cache_key(
        beat=b1,
        aspect="9:16",
        w=1080,
        h=1920,
        fps=60,
        domain="paper_classic",
        theme="cream",
        animation_mode="auto",
        pause_scale=1.0,
        primary_entity_en="",
        total_chapters=1,
        has_next_diff_title=True,
        show_chapter_banner=False,
        watermark=wm,
        n_frames_beat=180,
        eff_dur_b=3.0,
        speech_start=0.1,
        speech_end=2.7,
        word_timings=[("Beat", 0.1, 0.5)],
        spoken_segs=[(0.1, 2.7, "Beat đầu tiên.")],
        wav_sha256="abc123",
        global_frame_offset=0,
        prev_stage_state=None,
        prev_board_img=None,
    )
    cache.store(key1, src_mp4, st1, board1)

    hit1 = cache.lookup(key1)
    assert hit1 is not None
    mp4_hit, st_hit, board_hit = hit1
    assert mp4_hit.is_file()
    assert st_hit == st1
    assert board_hit is not None and board_hit.size == (64, 64)
    board1.close()
    board_hit.close()

    # Sửa beat 1 -> st1_mod khác -> beat 2 chained từ st1_mod phải miss, beat 1 vẫn hit khi quay lại
    st1_mod = BeatStageState(
        x=100.0,
        y=500.0,
        scale=1.0,
        pose_state=PuppetPoseState(lw_vx=0.99, head_vel=-0.75),
        camera_shot="wide_stage",
    )
    key2_a = compute_beat_cache_key(
        beat=b2,
        aspect="9:16",
        w=1080,
        h=1920,
        fps=60,
        domain="paper_classic",
        theme="cream",
        animation_mode="auto",
        pause_scale=1.0,
        primary_entity_en="",
        total_chapters=1,
        has_next_diff_title=True,
        show_chapter_banner=False,
        watermark=wm,
        n_frames_beat=180,
        eff_dur_b=3.0,
        speech_start=0.1,
        speech_end=2.7,
        word_timings=[],
        spoken_segs=[],
        wav_sha256="def456",
        global_frame_offset=180,
        prev_stage_state=st1,
        prev_board_img=None,
    )
    key2_b = compute_beat_cache_key(
        beat=b2,
        aspect="9:16",
        w=1080,
        h=1920,
        fps=60,
        domain="paper_classic",
        theme="cream",
        animation_mode="auto",
        pause_scale=1.0,
        primary_entity_en="",
        total_chapters=1,
        has_next_diff_title=True,
        show_chapter_banner=False,
        watermark=wm,
        n_frames_beat=180,
        eff_dur_b=3.0,
        speech_start=0.1,
        speech_end=2.7,
        word_timings=[],
        spoken_segs=[],
        wav_sha256="def456",
        global_frame_offset=180,
        prev_stage_state=st1_mod,
        prev_board_img=None,
    )
    assert key2_a != key2_b

    # Kiểm tra STICKV_DISABLE_BEAT_CACHE=1 tắt cache hoàn toàn
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("STICKV_DISABLE_BEAT_CACHE", "1")
        assert cache.enabled is False
        assert cache.lookup(key1) is None
    assert os.environ.get("STICKV_DISABLE_BEAT_CACHE") != "1"


def test_per_beat_tts_wav_cache_reuses_unchanged_beats(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    synth_calls: list[str] = []

    class _FakeVoiceProvider:
        def status(self):
            return type("S", (), {"ok": True, "note": ""})()

        def list_voices(self):
            return [type("V", (), {"id": "v1"})()]

        def synthesize_many(self, items):
            for it in items:
                synth_calls.append(it.text)
                write_fallback_speech_wav_atomic(it.out, it.text, audible=True)

    vp = _FakeVoiceProvider()
    beats = [
        StickvBeat(id="b001", narration="Câu một giữ nguyên.", pose="explain", sfx_tag="none"),
        StickvBeat(id="b002", narration="Câu hai ban đầu.", pose="happy", sfx_tag="none"),
    ]
    with patch("hbt.stickv.audio.measure_audio_duration", return_value=1.8):
        synth_stickv_beats_audio(beats, audio_dir, voice_provider=vp, voice_id="v1")
        assert len(synth_calls) == 2
        assert (audio_dir / "b001.tts.sha256").is_file()
        assert (audio_dir / "b002.tts.sha256").is_file()

        synth_calls.clear()
        # Chỉ sửa b002 -> chỉ b002 phải synth lại, b001 dùng lại WAV cache
        beats[1] = StickvBeat(
            id="b002", narration="Câu hai đã sửa nội dung.", pose="happy", sfx_tag="none"
        )
        synth_stickv_beats_audio(beats, audio_dir, voice_provider=vp, voice_id="v1")
        assert synth_calls == ["Câu hai đã sửa nội dung."]
