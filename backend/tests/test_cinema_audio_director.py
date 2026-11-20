"""Unit test cho AudioDirector (siết thở, J/L-cut, Silence Drop, script) & Director AI."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from hbt.cinema.audio_director import (
    build_mix_filtergraph_script,
    compute_jl_cut_schedule,
    compute_silence_drops,
    mix_cinema_audio,
    resolve_foley_sfx,
    tighten_breaths_wav,
)
from hbt.cinema.director_ai import (
    assign_editorial_shots,
    build_pass1_story_prompt,
    build_pass2_editorial_prompt,
    direct_timeline,
)
from hbt.cinema.hardware import detect_hardware, resolve_filter_complex_script_flag
from hbt.cinema.schema import AudioCue, BeatSpec, BoardSpec, TimelineSpec


def _write_speech_gap_wav(dest: Path, *, sr: int = 24000) -> Path:
    """Tạo file WAV có 2 đoạn tiếng nói xen giữa bởi khoảng lặng 600ms."""
    t1 = np.linspace(0.0, 0.3, int(sr * 0.3), endpoint=False)
    tone1 = (0.35 * np.sin(2.0 * math.pi * 240.0 * t1) * 32767.0).astype(np.int16)
    gap = np.zeros(int(sr * 0.6), dtype=np.int16)
    t2 = np.linspace(0.0, 0.3, int(sr * 0.3), endpoint=False)
    tone2 = (0.35 * np.sin(2.0 * math.pi * 300.0 * t2) * 32767.0).astype(np.int16)
    payload = np.concatenate([tone1, gap, tone2])
    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(payload.tobytes())
    return dest


def test_tighten_breaths_wav_compresses_long_silence_under_120ms(tmp_path: Path) -> None:
    in_wav = _write_speech_gap_wav(tmp_path / "speech_with_gap.wav")
    out_wav = tmp_path / "tight.wav"

    stats = tighten_breaths_wav(in_wav, out_wav, max_breath_ms=120)
    assert out_wav.is_file()
    assert stats["original_ms"] == 1200.0
    # 600ms lặng siết xuống <= 120ms -> tiết kiệm >= 460ms
    assert stats["removed_ms"] >= 460.0
    assert stats["tightened_ms"] <= 740.0


def test_jl_cut_and_silence_drop_and_filtergraph_script(tmp_path: Path) -> None:
    beats = [
        BeatSpec(id="b001", narration="Mở đầu", duration_sec=2.0, transition_in="editorial_cut"),
        BeatSpec(
            id="b002",
            narration="Điểm nhấn!",
            duration_sec=2.0,
            transition_in="whip_pan",
            punch=True,
            audio_cues=[
                AudioCue(kind="j_cut", tag="lead", offset_ms=-160),
                AudioCue(kind="silence_drop", tag="drop", duration_ms=320),
            ],
        ),
    ]
    sched = compute_jl_cut_schedule(beats, jl_cut_ms=160)
    assert sched[1]["visual_start_s"] == 2.0
    assert sched[1]["audio_start_s"] == 1.84  # J-cut sớm 160ms
    assert sched[1]["delay_ms"] == 1840

    drops = compute_silence_drops(beats, silence_drop_ms=320)
    assert drops == [(1.68, 2.0)]

    v1 = _write_speech_gap_wav(tmp_path / "v1.wav")
    sfx = resolve_foley_sfx("whoosh", tmp_path / "empty_lib", fallback_dir=tmp_path / "fb")
    assert sfx is not None and sfx.is_file()

    _, fc = build_mix_filtergraph_script(
        voice_entries=[(v1, 0)],
        foley_entries=[(sfx, 1840, -2.0)],
        bgm_wav=v1,
        total_duration_s=4.0,
        silence_drops=drops,
        target_lufs=-14.0,
    )
    assert "between(t,1.680,2.000)" in fc
    assert "adelay=1840|1840" in fc
    assert "loudnorm=I=-14.0" in fc


def test_mix_cinema_audio_runs_ffmpeg_with_script_and_ci_fallbacks(tmp_path: Path) -> None:
    v1 = _write_speech_gap_wav(tmp_path / "b001.wav")
    v2 = _write_speech_gap_wav(tmp_path / "b002.wav")
    spec = TimelineSpec(
        slug="ci-audio-mix",
        title="Audio Mix CI",
        beats=[
            BeatSpec(id="b001", narration="Đoạn 1", duration_sec=1.2, sfx_tag="whoosh"),
            BeatSpec(
                id="b002",
                narration="Đoạn 2",
                duration_sec=1.2,
                transition_in="paper_slide",
                punch=True,
                sfx_tag="vine_boom",
            ),
        ],
    )
    assert resolve_filter_complex_script_flag(help_output="-filter_complex_script <f>") == (
        "-filter_complex_script"
    )
    assert resolve_filter_complex_script_flag(help_output="-filter_complex <g>") == (
        "-/filter_complex"
    )

    hw = detect_hardware(probe_fn=lambda: (False, "cpu test"))
    out_wav = tmp_path / "mixed_cinema.wav"
    res = mix_cinema_audio(
        spec,
        {"b001": v1, "b002": v2},
        out_wav,
        library_dir=tmp_path / "empty_lib",  # Mô phỏng Ubuntu CI thiếu sạch library/
        work_dir=tmp_path / "work",
        hw=hw,
    )
    assert out_wav.is_file()
    assert Path(res["filtergraph_path"]).is_file()
    assert res["script_flag"] in ("-filter_complex_script", "-/filter_complex")
    assert res["foley_count"] >= 2
    assert res["bgm_used"] is False
    with wave.open(str(out_wav), "rb") as wf:
        assert wf.getframerate() == 48000
        assert wf.getnchannels() == 2


def test_director_ai_dual_pass_prompts_and_shot_diversity() -> None:
    p1 = build_pass1_story_prompt("Vì sao bầu trời màu xanh?", topic="science", target_minutes=1.0)
    assert "Anti-Parrot" in p1
    assert "narration" in p1

    p2 = build_pass2_editorial_prompt([{"id": "b001", "narration": "Thử"}], aspect="9:16")
    for s in (
        "desk_wide",
        "card_hero",
        "split_compare",
        "data_spotlight",
        "puppet_closeup",
        "recap_grid",
    ):
        assert s in p2

    # Gán luật biên tập trên timeline thô bị trùng góc máy
    raw = TimelineSpec(
        slug="dir-test",
        title="Đạo diễn biên tập",
        beats=[
            BeatSpec(id="b001", chapter=1, narration="Câu hỏi mở đầu?", board=BoardSpec(title="A")),
            BeatSpec(
                id="b002", chapter=1, narration="Khác biệt 75% số liệu", board=BoardSpec(title="B")
            ),
            BeatSpec(
                id="b003", chapter=2, narration="Lầm tưởng vs thực tế", board=BoardSpec(title="C")
            ),
            BeatSpec(
                id="b004", chapter=2, narration="Hãy đăng ký kênh nhé!", board=BoardSpec(title="D")
            ),
        ],
    )
    directed = assign_editorial_shots(raw)
    for prev_b, cur_b in zip(directed.beats, directed.beats[1:], strict=False):
        assert prev_b.shot_type != cur_b.shot_type
        assert prev_b.puppet.pose != cur_b.puppet.pose
    assert directed.beats[-1].shot_type == "recap_grid"
    assert directed.beats[-1].board.board_type == "recap_card"

    # direct_timeline offline chạy trọn vẹn qua Preflight
    full = direct_timeline("Bí mật giấc mơ REM", use_llm=False)
    assert full.preflight_passed is True
    assert len(full.beats) >= 4
