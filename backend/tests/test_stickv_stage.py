"""Kiểm thử sân khấu Pillow, bảng minh họa, audio anchoring & dọn dẹp chunk render StickV."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from hbt.stickv.audio import (
    compute_word_timings,
    extract_wav_rms_envelope,
    mix_stickv_audio,
    synth_stickv_beats_audio,
)
from hbt.stickv.models import StickvBeat, StickvProject
from hbt.stickv.render import render_stickv
from hbt.stickv.stage import render_animated_beat_frame, render_beat_layers


def test_render_beat_layers_all_board_types_and_aspects(tmp_path: Path) -> None:
    lib = tmp_path / "library"
    assets = tmp_path / "assets"
    out = tmp_path / "out"

    beats = [
        StickvBeat(
            id="b1",
            narration="Danh sách",
            pose="explain",
            board_type="bullets",
            board_title="3 Lý do",
            board_data={"items": ["Nhanh", "Nhẹ", "Rõ"]},
        ),
        StickvBeat(
            id="b2",
            narration="Con số",
            pose="shock",
            facing="left",
            board_type="big_number",
            board_title="Tăng trưởng",
            board_data={"value": "85%", "label": "Người xem giữ chân"},
        ),
        StickvBeat(
            id="b3",
            narration="So sánh",
            pose="think",
            board_type="comparison",
            board_title="Trước và Sau",
            board_data={
                "left_title": "Cũ",
                "left_items": ["Chậm"],
                "right_title": "Mới",
                "right_items": ["Mượt"],
            },
        ),
        StickvBeat(
            id="b4",
            narration="Quy trình",
            pose="happy",
            board_type="flow_steps",
            board_title="3 Bước",
            board_data={"steps": ["Ý tưởng", "Giọng đọc", "Xuất bản"]},
        ),
    ]

    for aspect, expected_size in (("9:16", (1080, 1920)), ("16:9", (1920, 1080))):
        for theme in ("cream", "dark"):
            bg_p, char_p = render_beat_layers(
                beats[0],
                aspect=aspect,
                theme=theme,
                out_dir=out / f"{aspect.replace(':', 'x')}_{theme}",
                library_dir=lib,
                assets_dir=assets,
            )
            assert bg_p.is_file()
            assert char_p is not None and char_p.is_file()
            with Image.open(bg_p) as im:
                assert im.size == expected_size

    for b in beats[1:]:
        bg_p, _ = render_beat_layers(
            b, aspect="16:9", theme="cream", out_dir=out, library_dir=lib, assets_dir=assets
        )
        assert bg_p.is_file()


def test_synth_and_render_cleans_up_chunks_dir(tmp_path: Path) -> None:
    pdir = tmp_path / "proj"
    lib = tmp_path / "library"
    assets = tmp_path / "assets"
    brand = tmp_path / "brand"
    brand.mkdir(parents=True, exist_ok=True)

    proj = StickvProject(
        slug="test-stickv",
        title="Test StickV",
        beats=[
            StickvBeat(id="b001", narration="Một câu ngắn.", pose="explain", sfx_tag="none"),
            StickvBeat(id="b002", narration="Câu thứ hai.", pose="happy", sfx_tag="none"),
        ],
    )

    def fake_ffmpeg(cmd: list[str], *args, **kwargs):
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"fake-media-bytes")

    def fake_stream_chunk(*, out_mp4: Path, global_frame_offset: int, acc_audio_t: float, **kwargs):
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(b"fake-media-bytes")
        return global_frame_offset + 60, acc_audio_t + 2.4, None

    with (
        patch("hbt.stickv.audio.run_ffmpeg", side_effect=fake_ffmpeg),
        patch("hbt.stickv.render.run_ffmpeg", side_effect=fake_ffmpeg),
        patch("hbt.stickv.render._stream_chunk_frames_to_ffmpeg", side_effect=fake_stream_chunk),
        patch("hbt.stickv.render.measure_audio_duration", return_value=3.2),
    ):
        res = render_stickv(
            proj,
            pdir,
            library_dir=lib,
            assets_dir=assets,
            brand_dir=brand,
            preview=True,
        )

    assert Path(res["file_path"]).is_file()
    assert not (pdir / "build" / "chunks").exists()
    assert proj.beats[0].duration_sec >= 1.2

    # Kiểm tra synth_stickv_beats_audio & mix_stickv_audio độc lập
    wavs = synth_stickv_beats_audio(
        proj.beats, pdir / "a2", voice_provider=None, voice_id="vienneu_default"
    )
    assert len(wavs) == 2
    with patch("hbt.stickv.audio.run_ffmpeg", side_effect=fake_ffmpeg):
        mixed = mix_stickv_audio(
            beats=proj.beats,
            beat_wavs=wavs,
            topic="science",
            library_dir=lib,
            assets_dir=assets,
            out_wav=pdir / "mixed.wav",
        )
    assert mixed.is_file()


def test_lipsync_karaoke_and_vieneu_status_check(tmp_path: Path) -> None:
    timings = compute_word_timings("Xin chào các bạn", 2.0)
    assert len(timings) == 4
    assert timings[0][0] == "Xin"

    bg = Image.new("RGB", (1080, 1920), (250, 247, 240))
    ch = Image.new("RGBA", (300, 400), (0, 0, 0, 0))
    beat = StickvBeat(id="b1", narration="Xin chào các bạn", pose="explain")
    frame = render_animated_beat_frame(
        bg_img=bg,
        char_img=ch,
        beat=beat,
        aspect="9:16",
        t_sec=0.5,
        mouth_open=0.8,
        word_timings=timings,
    )
    assert frame.size == (1080, 1920)
    frame.close()
    bg.close()
    ch.close()

    env = extract_wav_rms_envelope(tmp_path / "missing.wav", 24, 1.0)
    assert len(env) == 24

    broken_provider = SimpleNamespace(status=lambda: SimpleNamespace(ok=False, note="Thiếu model"))
    with pytest.raises(RuntimeError, match="Thiếu model"):
        synth_stickv_beats_audio(
            [beat], tmp_path / "aud", voice_provider=broken_provider, voice_id="Thanh Bình"
        )

    # Kiểm tra fallback khi voice_id cũ không nằm trong provider.list_voices()
    captured_voices: list[str] = []

    def fake_synth_many(items):
        for it in items:
            captured_voices.append(it.voice_id)
            it.out.parent.mkdir(parents=True, exist_ok=True)
            it.out.write_bytes(b"RIFF" + b"\x00" * 100)

    ok_provider = SimpleNamespace(
        status=lambda: SimpleNamespace(ok=True, note=""),
        list_voices=lambda: [
            SimpleNamespace(id="Adam bựa"),
            SimpleNamespace(id="Thanh Bình"),
        ],
        synthesize_many=fake_synth_many,
    )
    synth_stickv_beats_audio(
        [beat],
        tmp_path / "aud_ok",
        voice_provider=ok_provider,
        voice_id="Bình (nam miền Bắc)",
    )
    assert captured_voices == ["Thanh Bình"]

    # Kiểm tra resolve_pose_png ưu tiên ảnh người dùng upload (assets/stickman) thay vì mặc định
    from hbt.stickv.stage import resolve_pose_png

    user_shock = tmp_path / "assets" / "stickman" / "shock.png"
    user_shock.parent.mkdir(parents=True, exist_ok=True)
    user_shock.write_bytes(b"custom-shock")
    assert resolve_pose_png("shock", tmp_path / "library", tmp_path / "assets") == user_shock

    # Kiểm tra nhận diện file có tiền tố {pose}. hoặc {pose}_ (Google Flow)
    flow_happy = tmp_path / "assets" / "stickman" / "happy.png_Same_stickman_mascot_abc.png"
    flow_happy.write_bytes(b"flow-happy")
    assert resolve_pose_png("happy", tmp_path / "library", tmp_path / "assets") == flow_happy

    # Kiểm tra render_single_beat_clip khớp thời lượng Video Pose (lặp/cắt theo giọng đọc)
    from hbt.stickv.render import _render_single_beat_clip

    vp_file = tmp_path / "assets" / "stickman" / "flow_wave.mp4"
    vp_file.write_bytes(b"mp4")
    vp_beat = StickvBeat(
        id="b_vp", narration="Xin chào", clip_path="flow_wave.mp4", duration_sec=6.0
    )
    cmds: list[list[str]] = []

    def cap_ffmpeg(cmd: list[str], *a, **kw):
        cmds.append(cmd)
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"out")

    with (
        patch("hbt.stickv.render.run_ffmpeg", side_effect=cap_ffmpeg),
        patch("hbt.stickv.render.measure_audio_duration", return_value=3.0),
    ):
        _render_single_beat_clip(
            beat=vp_beat,
            wav_path=tmp_path / "w.wav",
            bg_png=tmp_path / "b.png",
            char_png=None,
            out_mp4=tmp_path / "out_short.mp4",
            w=1080,
            h=1920,
            fps=24,
            aspect="9:16",
            project_dir=tmp_path,
            library_dir=tmp_path / "library",
            assets_dir=tmp_path / "assets",
        )
    assert "-stream_loop" in cmds[-1]
    assert "6.000" in cmds[-1]

    with (
        patch("hbt.stickv.render.run_ffmpeg", side_effect=cap_ffmpeg),
        patch("hbt.stickv.render.measure_audio_duration", return_value=10.0),
    ):
        _render_single_beat_clip(
            beat=vp_beat,
            wav_path=tmp_path / "w.wav",
            bg_png=tmp_path / "b.png",
            char_png=None,
            out_mp4=tmp_path / "out_long.mp4",
            w=1080,
            h=1920,
            fps=24,
            aspect="9:16",
            project_dir=tmp_path,
            library_dir=tmp_path / "library",
            assets_dir=tmp_path / "assets",
        )
    assert "-stream_loop" not in cmds[-1]
    assert "6.000" in cmds[-1]


def test_append_outro_both_aspects_and_dynamic_pose_discovery(tmp_path: Path) -> None:
    from hbt.stickv.render import _append_outro
    from hbt.stickv.stage import list_available_poses

    # 1. Quét động pose mới (confused, facepalm...)
    user_dir = tmp_path / "assets" / "stickman"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "confused.png").write_bytes(b"png")
    (user_dir / "facepalm.png_Same_stickman_mascot_123.png").write_bytes(b"png")
    poses = list_available_poses(tmp_path / "library", tmp_path / "assets")
    assert "confused" in poses
    assert "facepalm" in poses

    # 2. Ghép outro 9:16 và 16:9
    brand = tmp_path / "brand"
    (brand / "outro").mkdir(parents=True, exist_ok=True)
    (brand / "outro" / "outro_4s_50fps.mp4").write_bytes(b"outro")
    lib = tmp_path / "library"
    (lib / "outro").mkdir(parents=True, exist_ok=True)
    (lib / "outro" / "voice.wav").write_bytes(b"wav")
    chunks = tmp_path / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    main_mp4 = chunks / "body.mp4"
    main_mp4.write_bytes(b"body")
    main_wav = chunks / "mixed.wav"
    main_wav.write_bytes(b"wav")

    cmds: list[list[str]] = []

    def fake_ff(cmd: list[str], *a, **kw):
        cmds.append(cmd)
        Path(cmd[-1]).write_bytes(b"final")

    with (
        patch("hbt.stickv.render.build_outro_audio"),
        patch("hbt.stickv.render.measure_audio_duration", return_value=10.0),
        patch("hbt.stickv.render.run_ffmpeg", side_effect=fake_ff),
    ):
        _append_outro(
            main_mp4=main_mp4,
            main_wav=main_wav,
            out_mp4=tmp_path / "out_916.mp4",
            w=1080,
            h=1920,
            fps=30,
            aspect="9:16",
            brand_dir=brand,
            library_dir=lib,
            chunks_dir=chunks,
        )
        fc_916 = cmds[-1][cmds[-1].index("-filter_complex") + 1]
        assert "xfade=transition=fade:duration=0.5" in fc_916
        assert "acrossfade=d=0.5" in fc_916

        _append_outro(
            main_mp4=main_mp4,
            main_wav=main_wav,
            out_mp4=tmp_path / "out_169.mp4",
            w=1920,
            h=1080,
            fps=60,
            aspect="16:9",
            brand_dir=brand,
            library_dir=lib,
            chunks_dir=chunks,
        )
        fc_169 = cmds[-1][cmds[-1].index("-filter_complex") + 1]
        assert "#B22228" in fc_169
        assert "xfade=transition=fade:duration=0.5" in fc_169
        assert ",fps=60[vout]" in fc_169

        (brand / "outro" / "outro_4s_60fps.mp4").write_bytes(b"outro60")
        _append_outro(
            main_mp4=main_mp4,
            main_wav=main_wav,
            out_mp4=tmp_path / "out_916_60.mp4",
            w=1080,
            h=1920,
            fps=60,
            aspect="9:16",
            brand_dir=brand,
            library_dir=lib,
            chunks_dir=chunks,
        )
        assert any("outro_4s_60fps.mp4" in arg for arg in cmds[-1])
        fc_60 = cmds[-1][cmds[-1].index("-filter_complex") + 1]
        assert ",fps=60[vout]" in fc_60


def test_natural_speech_pauses_and_locked_karaoke(tmp_path: Path) -> None:
    import wave

    import numpy as np
    import pytest

    from hbt.stickv.audio import (
        GLOBAL_LEAD_SILENCE_S,
        PAUSE_END_SENTENCE_S,
        PAUSE_MID_CLAUSE_S,
        SENTENCE_GAP_S,
        align_beat_karaoke,
        compute_pause_after,
        split_beat_sentences,
    )

    # Câu vụn < 5 từ được gộp để giữ ngữ điệu tự nhiên; câu >= 5 từ tách nhịp rõ ràng
    assert split_beat_sentences("Câu một. Câu hai?") == ["Câu một. Câu hai?"]
    assert split_beat_sentences(
        "Ánh sáng truyền đi rất nhanh trong chân không. Bạn có nhận ra điều kỳ diệu này không?"
    ) == [
        "Ánh sáng truyền đi rất nhanh trong chân không.",
        "Bạn có nhận ra điều kỳ diệu này không?",
    ]
    assert compute_pause_after("Kết thúc câu.") == pytest.approx(PAUSE_END_SENTENCE_S)
    assert compute_pause_after("Ngắt giữa câu,") == pytest.approx(PAUSE_MID_CLAUSE_S)

    def _write_tone_wav(out_path: Path, dur_s: float = 0.80, sr: int = 24000) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        n = int(dur_s * sr)
        t = np.arange(n, dtype=np.float32) / sr
        samples = (np.sin(2.0 * np.pi * 440.0 * t) * 12000.0).astype(np.int16)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(samples.tobytes())

    class _FakeVoiceProvider:
        def status(self) -> SimpleNamespace:
            return SimpleNamespace(ok=True, note="")

        def list_voices(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="Thanh Bình")]

        def synthesize_many(self, items) -> None:
            for it in items:
                _write_tone_wav(it.out, dur_s=0.80)

    s1 = "Ánh sáng truyền đi rất nhanh trong chân không."
    s2 = "Bạn có nhận ra điều kỳ diệu này không?"
    beats = [
        StickvBeat(id="b1", narration=f"{s1} {s2}"),
        StickvBeat(id="b2", narration="Ý tiếp theo mang góc nhìn mới,"),
    ]
    audio_dir = tmp_path / "audio"
    out_beats = synth_stickv_beats_audio(
        beats,
        audio_dir,
        voice_provider=_FakeVoiceProvider(),
        voice_id="Thanh Bình",
        pause_scale=1.0,
    )

    # b1: 0.18 global_lead + (0.80+0.11 clean s1) + 0.20 gap + (0.80+0.11 clean s2) + 0.24 tail
    assert beats[0].duration_sec == pytest.approx(2.44, abs=0.06)
    assert out_beats[0][1] == pytest.approx(2.44, abs=0.06)
    assert beats[1].duration_sec >= 1.2

    b1_wav = audio_dir / "b1.wav"
    env = extract_wav_rms_envelope(b1_wav, fps=20, duration_sec=beats[0].duration_sec)
    # 0.15s cuối nằm trong 0.24s trailing pause -> im lặng
    assert max(env[-3:]) == 0.0

    timings = align_beat_karaoke(
        f"{s1} {s2}",
        b1_wav,
        beats[0].duration_sec,
        lead_in_s=GLOBAL_LEAD_SILENCE_S,
        pause_after_s=PAUSE_END_SENTENCE_S,
    )
    assert len(timings) == len(f"{s1} {s2}".split())
    assert timings[0][1] >= GLOBAL_LEAD_SILENCE_S - 0.01
    assert timings[-1][2] <= beats[0].duration_sec - PAUSE_END_SENTENCE_S + 0.02

    # Kiểm tra spoken_segments sidecar + khóa Karaoke qua khoảng nghỉ
    from hbt.stickv.audio import load_beat_spoken_segments
    from hbt.stickv.backdrops import BackdropRenderer
    from hbt.stickv.stage import draw_karaoke_strip

    segs = load_beat_spoken_segments(b1_wav)
    assert len(segs) == 2
    assert segs[0][2] == s1
    assert segs[1][2] == s2
    # Khoảng giữa câu 1 và câu 2 có gap ~0.20s (nhịp thở chuẩn GĐ9)
    assert segs[1][0] - segs[0][1] == pytest.approx(SENTENCE_GAP_S, abs=0.03)

    # Kiểm tra domain="physics_science" sinh phông xanh kỹ thuật khác #FAF7F0
    bd_phys = BackdropRenderer("physics_science", 360, 640)
    try:
        bg_phys = bd_phys.render_frame(0.5)
        assert bg_phys.getpixel((10, 10)) != (250, 247, 240)
        bg_phys.close()
    finally:
        bd_phys.close()

    # Khoảng lặng cuối câu ẩn phụ đề; ngắt <= 0.22s giữ ổn định nền mờ; đang nói vẽ đầy đủ
    canvas_sil = Image.new("RGBA", (540, 1200), (0, 0, 0, 0))
    draw_karaoke_strip(
        canvas_sil, timings, beats[0].duration_sec - 0.04, aspect="9:16", spoken_segments=segs
    )
    assert canvas_sil.getbbox() is None
    gap_t = (segs[0][1] + segs[1][0]) / 2.0
    draw_karaoke_strip(canvas_sil, timings, gap_t, aspect="9:16", spoken_segments=segs)
    assert canvas_sil.getbbox() is not None  # Giữ ổn định nền mờ trong khoảng ngắt <= 0.22s
    draw_karaoke_strip(canvas_sil, timings, segs[0][0] + 0.1, aspect="9:16", spoken_segments=segs)
    assert canvas_sil.getbbox() is not None
    canvas_sil.close()


def test_v8_stage_100pct_coverage_3_history_cards_virtual_cam_and_16x9() -> None:
    from hbt.stickv.stage import (
        BeatStageState,
        compute_beat_character_target,
        compute_camera_state,
        infer_auto_prop_query,
    )

    assert infer_auto_prop_query("Kim tự tháp Giza năm 2560 TCN") == "pyramid"

    # 1. board_type="none" vẫn dựng Thẻ Minh Họa Tự Động (nửa trên không bao giờ trống trơn)
    bg_916 = Image.new("RGB", (540, 960), (229, 207, 168))
    char_916 = Image.new("RGBA", (140, 280), (11, 14, 20, 255))
    try:
        b_none = StickvBeat(
            id="b_auto",
            chapter=2,
            narration="Kim tự tháp Giza xây năm 2560 TCN.",
            board_type="none",
        )
        out_none = render_animated_beat_frame(
            bg_img=bg_916,
            char_img=char_916,
            beat=b_none,
            aspect="9:16",
            t_sec=0.5,
            mouth_open=0.4,
            word_timings=[],
            draw_board=True,
            domain="history_geo",
            duration_sec=2.0,
        )
        # Vùng thẻ nửa trên khác màu nền phẳng nhờ thẻ minh họa tự động
        crop_top = out_none.crop((80, 120, 460, 420))
        assert crop_top.getcolors(maxcolors=2048) is None or len(crop_top.getcolors(2048) or []) > 5
        crop_top.close()
        out_none.close()

        # 2. 3 mẫu thẻ lịch sử & cross-fade khi trùng board_title
        prev_st = BeatStageState(x=200.0, y=520.0, last_board_title="Ai Cập Cổ Đại")
        for bt, bdata in (
            (
                "timeline_era",
                {"events": [{"year": "2560 TCN", "title": "Xây Kim Tự Tháp"}]},
            ),
            (
                "location_map",
                {"location": "Cao nguyên Giza", "coordinates": "29.9792° N, 31.1342° E"},
            ),
            (
                "myth_vs_fact",
                {"myth": "Nô lệ xây dựng", "fact": "Thợ lành nghề được trả lương"},
            ),
        ):
            b_hist = StickvBeat(
                id=f"b_{bt}",
                narration="Khám phá sự thật",
                board_type=bt,  # type: ignore[arg-type]
                board_title="Ai Cập Cổ Đại",
                board_data=bdata,
                camera_shot="focus_board",
            )
            f_h = render_animated_beat_frame(
                bg_img=bg_916,
                char_img=char_916,
                beat=b_hist,
                aspect="9:16",
                t_sec=0.20,
                mouth_open=0.2,
                word_timings=[],
                draw_board=True,
                prev_stage_state=prev_st,
                show_chapter_banner=True,
            )
            assert f_h.size == (540, 960)
            f_h.close()
    finally:
        bg_916.close()
        char_916.close()

    # 3. Nội suy 3 camera_shot mượt 0.55s & layout 16:9 Stickman đứng bên trái
    z0, _, _ = compute_camera_state(
        "closeup_react",
        aspect="16:9",
        t_sec=0.0,
        prev_stage_state=BeatStageState(x=0.0, y=0.0, camera_zoom=1.0),
    )
    z_mid, _, _ = compute_camera_state(
        "closeup_react",
        aspect="16:9",
        t_sec=0.275,
        prev_stage_state=BeatStageState(x=0.0, y=0.0, camera_zoom=1.0),
    )
    z1, px1, _ = compute_camera_state(
        "closeup_react",
        aspect="16:9",
        t_sec=0.55,
        prev_stage_state=BeatStageState(x=0.0, y=0.0, camera_zoom=1.0),
    )
    assert z0 == pytest.approx(1.0)
    assert 1.05 < z_mid < 1.18
    assert z1 == pytest.approx(1.22)
    assert px1 < 0.30

    tx_169, _, _ = compute_beat_character_target(
        1920, 1080, 300, 690, interaction="none", aspect="16:9"
    )
    assert tx_169 < 420.0  # Stickman đứng bên trái màn hình 16:9


def test_v9_layered_camera_clamping_2tier_board_and_recap_card() -> None:
    from hbt.stickv.stage import (
        BeatStageState,
        compute_layered_camera_layout,
    )

    # 1. Kiểm tra kẹp biên tách lớp trên 1080x1920
    lay_focus = compute_layered_camera_layout(
        "focus_board", aspect="9:16", w=1080, h=1920, t_sec=0.6
    )
    assert lay_focus.board_scale == pytest.approx(1.07)
    assert lay_focus.clamp_bounds is not None
    assert lay_focus.clamp_bounds[1] >= 115
    assert lay_focus.clamp_bounds[3] <= 865
    assert lay_focus.char_scale == pytest.approx(0.92)

    lay_close_fade = compute_layered_camera_layout(
        "closeup_react",
        aspect="9:16",
        w=1080,
        h=1920,
        t_sec=0.35,
        prev_stage_state=BeatStageState(x=500.0, y=1200.0, board_alpha=1.0),
    )
    assert lay_close_fade.board_alpha == pytest.approx(0.0, abs=0.01)

    lay_close_done = compute_layered_camera_layout(
        "closeup_react",
        aspect="9:16",
        w=1080,
        h=1920,
        t_sec=0.72,
        prev_stage_state=BeatStageState(x=500.0, y=1200.0, board_alpha=1.0),
    )
    assert lay_close_done.board_alpha == pytest.approx(0.0, abs=0.01)
    assert lay_close_done.char_scale == pytest.approx(1.06)

    # 2. Kiểm tra focus_board không đẩy chữ lên sát mép y < 110 và closeup_react ẩn bảng lớn
    bg = Image.new("RGB", (540, 960), (250, 247, 240))
    char = Image.new("RGBA", (140, 280), (11, 14, 20, 255))
    try:
        b_recap = StickvBeat(
            id="b_recap",
            chapter=3,
            chapter_title="Tổng kết",
            narration="Hãy bình luận bên dưới!",
            pose="wave_hello",
            emotion="happy",
            camera_shot="focus_board",
            board_type="recap_card",
            board_title="TÓM TẮT **3 Ý CỐT LÕI**",
            board_data={
                "items": [
                    "**Amygdala** phản ứng 12ms",
                    "**Thói quen** cần 21 ngày",
                    "**Ngủ đủ 8h** tăng trí nhớ",
                ],
                "takeaway": "Hiểu cơ chế để làm chủ hành vi",
            },
        )
        f_focus = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=b_recap,
            aspect="9:16",
            t_sec=0.6,
            mouth_open=0.3,
            word_timings=[("Hãy", 0.0, 0.4), ("bình", 0.4, 0.8)],
            draw_board=True,
        )
        # Vùng mép trên y < 55 vẫn giữ nguyên màu nền (không cắt bảng)
        assert f_focus.getpixel((270, 30)) == (250, 247, 240)
        f_focus.close()

        b_close = b_recap.model_copy(update={"camera_shot": "closeup_react"})
        f_close = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=b_close,
            aspect="9:16",
            t_sec=0.4,
            mouth_open=0.3,
            word_timings=[],
            draw_board=True,
            prev_stage_state=BeatStageState(x=200.0, y=500.0, board_alpha=1.0),
        )
        # Vùng giữa bảng cũ y = 260 ở closeup_react trở về màu nền vì bảng lớn đã ẩn mượt
        assert f_close.getpixel((270, 260)) == (250, 247, 240)
        f_close.close()
    finally:
        bg.close()
        char.close()


def test_mp4_compat_flags_and_legacy_shake_motion_normalized() -> None:
    from hbt.stickv.llm import VALID_MOTIONS, sanitize_beats
    from hbt.stickv.render import STICKV_MP4_COMPAT_FLAGS

    flags_str = " ".join(STICKV_MP4_COMPAT_FLAGS)
    assert "-pix_fmt yuv420p" in flags_str
    assert "-profile:v high" in flags_str
    assert "-movflags +faststart" in flags_str
    assert "-ar 48000" in flags_str

    assert "shake" not in VALID_MOTIONS
    legacy = StickvBeat(id="b_old", narration="Kiểm tra", motion="shake")
    assert legacy.motion == "float"

    sanitized = sanitize_beats([{"narration": "Một câu", "motion": "shake"}])
    assert sanitized[0].motion == "float"


def test_phase9_zero_raw_markdown_across_all_board_templates_and_shots() -> None:
    """Mọi mẫu bảng StickV & 6 góc máy Cinema Core tuyệt đối không in ký tự `**` thô."""
    from PIL import ImageDraw

    from hbt.cinema.schema import BeatSpec, BoardSpec
    from hbt.cinema.shots import bake_static_shot_layer, compute_shot_layout
    from hbt.stickv.stage import (
        _draw_smart_board_content,
        parse_rich_spans,
        resolve_stage_palette,
    )

    # Kiểm thử trực tiếp parse_rich_spans cả trường hợp thiếu dấu đóng **
    spans = parse_rich_spans("1. **Vi chấn thương** sợi cơ và **mảnh cắt dở")
    assert all("**" not in seg for seg, _ in spans)
    assert any(seg == "Vi chấn thương" and hl for seg, hl in spans)

    drawn_texts: list[str] = []
    orig_text = ImageDraw.ImageDraw.text

    def spy_text(self, xy, text, *args, **kwargs):
        drawn_texts.append(str(text))
        return orig_text(self, xy, text, *args, **kwargs)

    board_cases: list[tuple[str, dict]] = [
        (
            "bullets",
            {
                "items": ["**Vi chấn thương** tạo tín hiệu tái tạo sợi cơ"],
                "takeaway": "**Ngủ đủ** mới tăng cơ",
            },
        ),
        (
            "flow_steps",
            {
                "steps": [
                    "**Bước 1:** Vi chấn thương cơ học",
                    "**Bước 2:** Tổng hợp protein khi ngủ",
                ]
            },
        ),
        (
            "comparison",
            {
                "left_title": "**Cách cũ**",
                "left_items": ["**Ép đau** không nghỉ"],
                "right_title": "**Khoa học**",
                "right_items": ["**Tải tăng tiến** + ngủ sâu"],
            },
        ),
        (
            "myth_vs_fact",
            {
                "myth": "**Đau mới hiệu quả:** Ngộ nhận phổ biến khiến người tập dễ chấn thương",
                "fact": "**Áp lực cơ học:** Mới là tín hiệu kích thích tổng hợp sợi cơ bền vững",
            },
        ),
        (
            "big_number",
            {
                "value": "**48h**",
                "label": "Chu kỳ **phục hồi** sợi cơ",
                "sub": "**Tổng hợp** protein tối ưu",
            },
        ),
        ("counter_grow", {"target": "**72**", "unit": "**giờ**", "label": "Ngưỡng **tái tạo** mô"}),
        (
            "bar_compare",
            {
                "values": [
                    {"label": "**Ngủ 8h**", "value": 95},
                    {"label": "**Ngủ 5h**", "value": 45},
                ]
            },
        ),
        (
            "timeline_era",
            {"events": [{"year": "**2560 TCN**", "title": "**Xây dựng** Kim Tự Tháp Giza"}]},
        ),
        ("location_map", {"location": "**Cao nguyên Giza**", "coordinates": "**29.97° N**"}),
        ("quote", {"quote": "Cơ bắp chỉ **lớn lên** trong giấc ngủ sâu."}),
        (
            "recap_card",
            {"items": ["**Ý 1:** Cơ chế gốc", "**Ý 2:** Ngủ đủ 8h", "**Ý 3:** Dinh dưỡng"]},
        ),
        ("none", {"items": ["**Auto Card** xử lý markdown sạch"]}),
    ]

    pal = resolve_stage_palette("physics_science", "dark")
    with patch.object(ImageDraw.ImageDraw, "text", spy_text):
        for bt, bdata in board_cases:
            canvas = Image.new("RGBA", (1080, 1920), pal["bg"])
            try:
                beat = StickvBeat(
                    id=f"b_{bt}",
                    narration="Cơ chế **vi chấn thương** và phục hồi.",
                    board_type=bt,  # type: ignore[arg-type]
                    board_title="**Tiêu đề** bảng kiểm định",
                    takeaway="Ghi nhớ **nguyên lý** cốt lõi",
                    board_data=bdata,
                )
                _draw_smart_board_content(canvas, beat, (56, 125, 1024, 830), pal)
            finally:
                canvas.close()

        for shot_t in (
            "desk_wide",
            "card_hero",
            "split_compare",
            "data_spotlight",
            "puppet_closeup",
            "recap_grid",
        ):
            bs = BeatSpec(
                id=f"c_{shot_t}",
                narration="Kiểm thử Cinema Core.",
                shot_type=shot_t,  # type: ignore[arg-type]
                board=BoardSpec(
                    board_type="myth_vs_fact" if shot_t == "split_compare" else "bullets",
                    title="**Tiêu đề** Tactile Desk",
                    bullets=["**Điểm 1:** Không lộ dấu sao", "**Điểm 2:** Đậm rõ từ khóa"],
                    takeaway="**Chốt lại** không lộ sao",
                ),
            )
            lay = compute_shot_layout(shot_t, "9:16", beat=bs, width=540, height=960)  # type: ignore[arg-type]
            baked = bake_static_shot_layer(bs, lay, width=540, height=960)
            baked.close()

    assert len(drawn_texts) > 30
    leaked = [t for t in drawn_texts if "**" in t]
    assert leaked == [], f"Phát hiện ký tự '**' thô bị vẽ ra màn hình: {leaked}"


def test_phase9_karaoke_highlight_box_clearance_and_closeup_quote_banner() -> None:
    """Hộp highlight Karaoke cách từ kế cận >= 10px (không dính chữ) & closeup có Quote."""
    from hbt.stickv.stage import compute_karaoke_word_boxes, draw_karaoke_strip

    words = ["Khoa", "học", "lại", "chứng", "minh"]
    for aspect, frame_w in (("9:16", 1080), ("16:9", 1920)):
        for active_idx in range(len(words)):
            _font, _strip, items = compute_karaoke_word_boxes(
                words,
                active_idx,
                frame_w=frame_w,
                base_y=900,
                aspect=aspect,  # type: ignore[arg-type]
            )
            hl_box = items[active_idx]["highlight_box"]
            assert hl_box is not None
            # Kiểm tra khoảng hở tối thiểu >= 10px với từ bên trái và bên phải
            if active_idx > 0:
                left_box = items[active_idx - 1]["text_box"]
                assert hl_box[0] - left_box[2] >= 10, f"Dính từ trái ở idx={active_idx}"
            if active_idx + 1 < len(items):
                right_box = items[active_idx + 1]["text_box"]
                assert right_box[0] - hl_box[2] >= 10, f"Dính từ phải ở idx={active_idx}"

    # Vẽ thực tế draw_karaoke_strip lên RGBA 1080x1920 không lỗi
    canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    try:
        timings = [(w, i * 0.3, (i + 1) * 0.3) for i, w in enumerate(words)]
        draw_karaoke_strip(canvas, timings, 0.45, aspect="9:16")
        assert canvas.getbbox() is not None
    finally:
        canvas.close()

    # Kiểm tra closeup_react hiển thị dải Quote/Keyword ở vùng trên (không để trống hoác)
    bg = Image.new("RGB", (1080, 1920), (20, 26, 38))
    char = Image.new("RGBA", (280, 560), (255, 255, 255, 255))
    try:
        b_close = StickvBeat(
            id="b_quote",
            chapter=1,
            chapter_title="Sự thật bất ngờ",
            narration="Cơ bắp chỉ to lên khi bạn ngủ đủ giấc mỗi đêm.",
            camera_shot="closeup_react",
            board_type="bullets",
            board_title="**Ngủ sâu** xây cơ bắp",
            takeaway="Giấc ngủ sâu mới tạo mô cơ",
        )
        out_f = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=b_close,
            aspect="9:16",
            t_sec=0.5,
            mouth_open=0.3,
            word_timings=[],
            draw_board=True,
            domain="physics_science",
            theme="dark",
        )
        # Vùng banner Quote y=180..360 trên 1080x1920 phải có nhiều màu (không trống nền phẳng)
        quote_crop = out_f.crop((100, 180, 980, 360))
        colors = quote_crop.getcolors(maxcolors=2048)
        assert colors is None or len(colors) > 8
        quote_crop.close()
        out_f.close()
    finally:
        bg.close()
        char.close()


def test_pinned_photo_polaroid_board_on_dynamic_backdrop() -> None:
    """Thẻ Polaroid `pinned_photo` có viền trắng #FFFFFF, ghim đỏ #D9232E, không phủ kín nền."""
    import numpy as np

    bg_color = (22, 34, 54)
    bg = Image.new("RGB", (1080, 1920), bg_color)
    char = Image.new("RGBA", (240, 480), (11, 14, 20, 255))
    photo = Image.new("RGBA", (600, 400), (70, 130, 180, 255))
    try:
        beat = StickvBeat(
            id="b_polaroid",
            narration="Tượng đá Moai cổ đại trên đảo Phục Sinh.",
            board_type="pinned_photo",
            board_title="Tượng đá Moai cổ đại",
            board_data={"caption": "Tượng đá Moai cổ đại", "pin_style": "pin"},
        )
        frame = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=beat,
            aspect="9:16",
            t_sec=0.50,
            mouth_open=0.3,
            word_timings=[],
            prop_img=photo,
            draw_board=True,
            domain="physics_science",
            duration_sec=2.5,
        )
        arr = np.array(frame)
        # 1. Không phủ kín nền: góc trên trái & mép trên vẫn giữ đúng màu nền động
        assert frame.getpixel((20, 20)) == bg_color
        assert frame.getpixel((1060, 20)) == bg_color
        # 2. Vùng bảng chứa khung ảnh lớn Visual-First (màu ảnh xanh dương) + dải tiêu đề sáng
        top_zone = arr[100:860, 50:1030]
        photo_blue_mask = (
            (top_zone[:, :, 0] < 95) & (top_zone[:, :, 1] > 100) & (top_zone[:, :, 2] > 150)
        )
        white_card_mask = (
            (top_zone[:, :, 0] > 235) & (top_zone[:, :, 1] > 235) & (top_zone[:, :, 2] > 235)
        )
        assert int(photo_blue_mask.sum()) > 50000
        assert int(white_card_mask.sum()) > 5000
        frame.close()

        # 3. Kiểu băng dính (pin_style='tape') + pha vào mượt 0.35s không lỗi
        beat_tape = beat.model_copy(
            update={"board_data": {"caption": "Băng dính mờ", "pin_style": "tape"}}
        )
        f_enter = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=beat_tape,
            aspect="9:16",
            t_sec=0.12,
            mouth_open=0.2,
            word_timings=[],
            prop_img=photo,
            draw_board=True,
            duration_sec=2.5,
        )
        assert f_enter.size == (1080, 1920)
        f_enter.close()
    finally:
        bg.close()
        char.close()
        photo.close()


def test_stickv_boards_autofit_long_vietnamese_no_overflow() -> None:
    """Chữ tiếng Việt dài trong bullets, myth_vs_fact, pinned_photo, big_number không vượt biên."""
    import numpy as np

    from hbt.stickv.stage import _draw_smart_board_content, resolve_stage_palette

    pal = resolve_stage_palette("paper_classic", "cream")
    box = (80, 140, 1000, 820)
    long_vi = (
        "Nghiên cứu thần kinh học hiện đại chứng minh não bộ tiêu thụ lượng đường glucose và oxy "
        "vượt trội ngay cả khi ngủ sâu REM để củng cố trí nhớ dài hạn và tái tạo khớp thần kinh."
    )
    cases = [
        StickvBeat(
            id="b_bul",
            narration=long_vi,
            board_type="bullets",
            board_title=(
                "**Tiêu đề siêu dài tiếng Việt có đầy đủ dấu mũ nặng huyền sắc hỏi ngã** "
                "kiểm tra tự co chữ"
            ),
            board_data={"items": [long_vi, long_vi, long_vi]},
            takeaway="Ghi nhớ câu chốt rất dài có dấu tiếng Việt không bao giờ tràn viền phải",
        ),
        StickvBeat(
            id="b_mvf",
            narration=long_vi,
            board_type="myth_vs_fact",
            board_title="Giải mã lầm tưởng khoa học cổ điển",
            board_data={
                "myth_title": "Quan niệm cũ",
                "myth": long_vi,
                "fact_title": "Bằng chứng",
                "fact": long_vi,
            },
        ),
        StickvBeat(
            id="b_pin",
            narration=long_vi,
            board_type="pinned_photo",
            board_title="Ảnh tư liệu lịch sử cổ đại với chú thích dài nhiều dấu tiếng Việt",
            board_data={"caption": "Tượng đài kiến trúc cổ đại khổng lồ giữa sa mạc Sahara"},
        ),
        StickvBeat(
            id="b_big",
            narration=long_vi,
            board_type="big_number",
            board_data={"value": "1.250.000.000 tỷ đồng", "label": long_vi, "sub": long_vi},
        ),
        StickvBeat(
            id="b_tl",
            narration=long_vi,
            board_type="timeline_era",
            board_data={"events": [f"Năm {2000 + i} TCN: {long_vi}" for i in range(4)]},
        ),
    ]
    for beat in cases:
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        try:
            x0, y0, x1, y1 = _draw_smart_board_content(canvas, beat, box, pal, progress=1.0)
            arr = np.array(canvas)
            # Cho phép sai số bóng đổ nhẹ quanh shell (+14px) và xoay Polaroid trong khung box
            pad = 16
            top_out = arr[: max(0, y0 - pad), :, 3]
            bot_out = arr[min(canvas.height, y1 + pad) :, :, 3]
            left_out = arr[:, : max(0, x0 - pad), 3]
            right_out = arr[:, min(canvas.width, x1 + pad) :, 3]
            assert int(top_out.max()) == 0, f"Tràn mép trên với {beat.board_type}"
            assert int(bot_out.max()) == 0, f"Tràn mép dưới với {beat.board_type}"
            assert int(left_out.max()) == 0, f"Tràn mép trái với {beat.board_type}"
            assert int(right_out.max()) == 0, f"Tràn mép phải với {beat.board_type}"
        finally:
            canvas.close()


def test_stickv_karaoke_sync_trims_silence_to_active_speech(tmp_path: Path) -> None:
    """align_beat_karaoke bám sát tiếng nói thật, không trải từ lên đoạn im lặng đầu/cuối."""
    import wave

    import numpy as np

    from hbt.stickv.audio import align_beat_karaoke

    wav_p = tmp_path / "sync_test.wav"
    sr = 16000
    # 0.30s im lặng -> 0.80s sóng sin giọng nói -> 0.40s im lặng (tổng 1.50s)
    sil_head = np.zeros(int(sr * 0.30), dtype=np.int16)
    t_sp = np.linspace(0.0, 0.80, int(sr * 0.80), endpoint=False)
    speech = (np.sin(2 * np.pi * 240 * t_sp) * 18000).astype(np.int16)
    sil_tail = np.zeros(int(sr * 0.40), dtype=np.int16)
    with wave.open(str(wav_p), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.concatenate([sil_head, speech, sil_tail]).tobytes())

    timings = align_beat_karaoke(
        "Xin chào các bạn học sinh",
        wav_p,
        total_dur=1.50,
        spoken_segments=[(0.10, 1.35, "Xin chào các bạn học sinh")],
    )
    assert len(timings) == 6
    assert timings[0][1] >= 0.28  # Không bắt đầu trong đoạn im lặng 0.00..0.30s
    assert timings[-1][2] <= 1.15  # Không kéo dài sang đoạn im lặng 1.10..1.50s


def test_v10_board_dict_sanitization_2line_takeaway_and_no_empty_polaroid() -> None:
    """Không lọt dict Python thô, CHỐT LẠI 2 dòng, ẩn CHƯƠNG 1 ở CTA & không vẽ Polaroid rỗng."""
    from hbt.stickv.llm import (
        _sanitize_board_data,
        format_unwrapped_text,
        parse_stickv_json_payload,
    )
    from hbt.stickv.stage import _draw_smart_board_content, resolve_stage_palette

    # 1. Giải mã sạch cả dict thật lẫn chuỗi bị str(dict) hóa
    raw_dict_str = "{'title': 'LẦM TƯỞNG CƠ BẮP', 'text': 'Cơ càng to thì chạy càng nhanh.'}"
    cleaned = format_unwrapped_text(raw_dict_str)
    assert "{" not in cleaned and "'title'" not in cleaned
    assert "LẦM TƯỞNG CƠ BẮP" in cleaned
    assert "Cơ càng to" in cleaned

    sanitized = _sanitize_board_data(
        "myth_vs_fact",
        {
            "myth": {"title": "Lầm tưởng", "text": "Chạy nhanh cần cơ bắp khổng lồ"},
            "fact": raw_dict_str,
            "takeaway": "Sức bền và tỷ lệ công suất trên trọng lượng mới là yếu tố quyết định",
        },
    )
    assert "{" not in sanitized["myth"] and "{" not in sanitized["fact"]
    assert len(sanitized["takeaway"].split()) <= 13

    # 2. Beat CTA cuối khóa wide_stage (không chuyển closeup_react làm ẩn recap_card)
    payload = (
        '{"title":"Nghịch lý cầu thủ","beats":['
        '{"narration":"Cầu thủ không cần quá đô con.","board_type":"myth_vs_fact",'
        '"board_data":{"myth":{"title":"Lầm tưởng","text":"To mới khỏe"},"fact":"Bền mới thắng"}},'
        '{"narration":"Hãy đăng ký kênh và bình luận ý kiến của bạn nhé!",'
        '"camera_shot":"closeup_react","board_type":"recap_card",'
        '"board_title":"TÓM TẮT 3 Ý CỐT LÕI"}'
        "]}"
    )
    _, parsed_beats = parse_stickv_json_payload(payload)
    assert parsed_beats[-1].board_type == "pinned_photo"
    assert parsed_beats[-1].camera_shot == "wide_stage"

    # 3. pinned_photo khi prop_img=None tự vẽ thẻ icon Visual-First gọn (0 crash, 0 text-wall)
    pal = resolve_stage_palette("paper_classic", "cream")
    canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    try:
        b_empty_photo = StickvBeat(
            id="b_photo",
            narration="Sợi cơ bền bỉ giúp vận động viên duy trì nhịp chạy suốt trận.",
            board_type="pinned_photo",
            board_title="Sợi cơ bền bỉ",
            takeaway="Cân bằng giữa sức bền hiếu khí và tốc độ bứt phá",
        )
        box = _draw_smart_board_content(
            canvas,
            b_empty_photo,
            (56, 125, 1024, 830),
            pal,
            prop_img=None,
            total_chapters=1,
        )
        assert box[2] - box[0] > 700
    finally:
        canvas.close()

    # 4. Guard cứng trong draw_karaoke_strip: từ chứa dict thô phải ném ValueError ngay
    from hbt.stickv.stage import draw_karaoke_strip

    bad_frame = Image.new("RGBA", (540, 960), (0, 0, 0, 255))
    try:
        with pytest.raises(ValueError, match="dict"):
            draw_karaoke_strip(
                bad_frame,
                [("{'disp': 'tượng', 'syl': ['tuong']}", 0.0, 0.5)],
                0.2,
                aspect="9:16",
            )
    finally:
        bad_frame.close()


def test_stage_board_schemas_no_empty_comparison_or_fake_100_percent() -> None:
    """stage.py đọc đủ alias schema và tự fallback sạch khi comparison trống hoặc big_number ảo."""
    from hbt.stickv.stage import _draw_smart_board_content, resolve_stage_palette

    pal = resolve_stage_palette("history_geo", "cream")
    box = (56, 125, 1024, 830)
    sample_photo = Image.new("RGBA", (400, 300), (60, 120, 180, 255))
    beats_to_render = [
        StickvBeat(
            id="b_cmp_alias",
            narration="So sánh ngày và đêm ở Thung lũng Chết.",
            board_type="comparison",
            board_title="Ngày và Đêm",
            board_data={
                "left_title": "Ban đêm",
                "left": "Nhiệt độ xuống dưới 0°C tạo lớp băng mỏng",
                "right_title": "Ban ngày",
                "right": "Gió thổi đẩy tảng đá nặng 300 kg trượt dài",
            },
        ),
        StickvBeat(
            id="b_cmp_empty",
            narration="Hồ Natron có tính kiềm cực cao làm vôi hóa xác chim.",
            board_type="comparison",
            board_title="Hồ Natron Tanzania",
            board_data={"left_title": "Trước", "right_title": "Sau"},
        ),
        StickvBeat(
            id="b_bn_real",
            narration="Tảng đá nặng tới 300 kg vẫn tự di chuyển trên cát.",
            board_type="big_number",
            board_title="Khối lượng đá biết đi",
            board_data={"number": "300", "unit": "kg", "label": "Trọng lượng tảng đá trượt"},
        ),
        StickvBeat(
            id="b_bn_fake",
            narration="Vùng biển này nổi tiếng với nhiều truyền thuyết bí ẩn.",
            board_type="big_number",
            board_title="Tam giác Bermuda",
            board_data={"value": "100%", "label": "Truyền thuyết hàng hải"},
        ),
        StickvBeat(
            id="b_recap",
            narration="Tóm tắt 3 địa điểm kỳ lạ nhất hành tinh.",
            board_type="recap_card",
            board_title="TÓM TẮT 3 Ý CỐT LÕI",
            board_data={
                "items": [
                    "**Tam giác Bermuda:** Vùng biển 500.000 km² giàu dòng hải lưu mạnh.",
                    "**Đá biết đi California:** Lớp băng mỏng và gió nhẹ đẩy tảng đá 300 kg.",
                    "**Hồ Natron Tanzania:** Độ pH 10,5 bảo quản xác động vật như tượng đá.",
                ],
                "takeaway": "Mọi bí ẩn địa lý đều có cơ chế tự nhiên lý giải",
            },
        ),
        StickvBeat(
            id="b_photo",
            narration="Đá biết đi tại Thung lũng Chết, California.",
            board_type="pinned_photo",
            board_title="Đá biết đi — Thung lũng Chết",
            board_data={"caption": "PHÂN TÍCH CƠ CHẾ", "pin_style": "tape"},
        ),
    ]
    try:
        for b in beats_to_render:
            canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            try:
                rect = _draw_smart_board_content(
                    canvas,
                    b,
                    box,
                    pal,
                    progress=1.0,
                    prop_img=sample_photo if b.board_type == "pinned_photo" else None,
                )
                assert rect[2] > rect[0] and rect[3] > rect[1]
                assert canvas.getbbox() is not None
            finally:
                canvas.close()
    finally:
        sample_photo.close()


def test_visual_first_title_unified_uppercase() -> None:
    """Packet A3: 100% tiêu đề Visual-First đồng bộ UPPERCASE 3-6 từ, không cắt dấu '...'."""
    from hbt.stickv.stage import _pick_visual_first_title

    samples = [
        StickvBeat(
            id="b1",
            narration="Kỹ sư phát hiện nền đất bị lún.",
            board_type="pinned_photo",
            board_title="Phát hiện lún móng",
        ),
        StickvBeat(
            id="b2",
            narration="Tháp nghiêng Pisa nổi tiếng toàn cầu.",
            board_type="pinned_photo",
            board_title="KIỆT TÁC KIẾN TRÚC",
        ),
        StickvBeat(
            id="b3",
            narration="Mực nước ngầm khiến nền đất sét mềm nghiêng về phía nam.",
            board_type="pinned_photo",
            board_title="",
        ),
    ]
    for b in samples:
        out = _pick_visual_first_title(b)
        assert out == out.upper(), out
        assert "..." not in out
        assert 3 <= len(out.split()) <= 6, out


def test_resolve_beat_visual_image_dedupes_adjacent_beats(tmp_path: Path, monkeypatch) -> None:
    """Packet A3: 2 beat liền kề không trả cùng 1 file ảnh khi có phương án thay thế."""
    from hbt.stickv import render as sr

    proj_dir = tmp_path / "workspace" / "stickv" / "demo"
    lib_dir = tmp_path / "library"
    proj_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)

    img_a = lib_dir / "ref_a.jpg"
    img_b = lib_dir / "ref_b.jpg"
    Image.new("RGB", (64, 64), (210, 40, 40)).save(img_a, format="JPEG")
    Image.new("RGB", (64, 64), (40, 120, 210)).save(img_b, format="JPEG")

    def _fake_resolve(query: str, *args, **kwargs):
        if "detail closeup" in query or "panorama" in query or "alternate" in query:
            return img_b, "cloudflare_flux"
        return img_a, "wikimedia"

    monkeypatch.setattr(sr, "resolve_reference_image", _fake_resolve)

    b009 = StickvBeat(
        id="b009",
        narration="Toàn cảnh quảng trường tháp nghiêng.",
        board_type="pinned_photo",
        board_title="TOÀN CẢNH QUẢNG TRƯỜNG",
        prop_query="Leaning Tower of Pisa aerial",
    )
    b010 = StickvBeat(
        id="b010",
        narration="Chi tiết phần đỉnh tháp.",
        board_type="pinned_photo",
        board_title="TÓM TẮT 3 Ý CỐT LÕI",
        prop_query="Leaning Tower of Pisa aerial",
    )
    m1: dict[str, str] = {}
    m2: dict[str, str] = {}
    im1, _ = sr._resolve_beat_visual_image(
        b009,
        project_dir=proj_dir,
        library_dir=lib_dir,
        accent=(220, 38, 38, 255),
        out_meta=m1,
    )
    im2, src2 = sr._resolve_beat_visual_image(
        b010,
        project_dir=proj_dir,
        library_dir=lib_dir,
        accent=(220, 38, 38, 255),
        prev_image_path=m1["path"],
        out_meta=m2,
    )
    if im1 is not None:
        im1.close()
    if im2 is not None:
        im2.close()

    assert m1["path"] == str(img_a)
    assert m2["path"] == str(img_b)
    assert m1["path"] != m2["path"]
    assert src2 == "cloudflare_flux"


def test_p11_locked_16_10_frame_zero_dest_y_jump_and_separated_title_fade() -> None:
    """INV-12: Khung ảnh 16:10 cố định cho ảnh dọc/ngang, 0px nhảy dest_y, tách 2 pha tiêu đề."""
    from unittest.mock import patch

    from PIL import ImageDraw

    from hbt.stickv.stage import (
        BeatStageState,
        _composite_transitioned_board,
        _compute_visual_first_rects,
        _draw_visual_first_board,
        close_stage_cache,
        compute_layered_camera_layout,
        resolve_stage_palette,
    )

    pal = resolve_stage_palette("paper_classic", "cream")
    box = (56, 125, 1024, 830)
    rects = _compute_visual_first_rects(box)
    ix0, iy0, ix1, iy1 = rects["inner"]
    assert abs((ix1 - ix0) / max(1, iy1 - iy0) - 1.6) < 0.02

    # 1. Ảnh dọc (trên xanh lá, dưới xanh dương) & ngang cùng khung 16:10, smart-crop phần trên
    portrait = Image.new("RGBA", (600, 1200), (20, 40, 220, 255))
    portrait.paste(Image.new("RGBA", (600, 500), (30, 180, 60, 255)), (0, 0))
    landscape = Image.new("RGBA", (1200, 600), (210, 60, 40, 255))
    c_p = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    c_l = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    try:
        b1 = StickvBeat(
            id="b_p",
            narration="Bản đồ khu vực sa mạc trống.",
            board_type="pinned_photo",
            board_title="Bản đồ sa mạc trống",
        )
        r_p = _draw_visual_first_board(c_p, b1, box, pal, photo_img=portrait)
        r_l = _draw_visual_first_board(c_l, b1, box, pal, photo_img=landscape)
        assert r_p == r_l == rects["outer"]
        # Smart-crop (0.5, 0.28): phần trên bên trong khung 16:10 giữ màu xanh lá từ đỉnh ảnh
        top_px = c_p.getpixel(((ix0 + ix1) // 2, iy0 + 25))
        assert top_px[1] > 140 and top_px[2] < 100
    finally:
        portrait.close()
        landscape.close()
        c_p.close()
        c_l.close()

    # 2. anchor_top_center liên tục khi chuyển wide_stage <-> focus_board
    st_wide = BeatStageState(x=540.0, y=1200.0, camera_shot="wide_stage")
    lay_start = compute_layered_camera_layout(
        "focus_board", aspect="9:16", w=1080, h=1920, t_sec=0.0, prev_stage_state=st_wide
    )
    lay_end = compute_layered_camera_layout(
        "focus_board", aspect="9:16", w=1080, h=1920, t_sec=0.70, prev_stage_state=st_wide
    )
    assert lay_start.anchor_top_center is not None and lay_end.anchor_top_center is not None
    assert lay_start.anchor_top_center[1] == pytest.approx(115.0)
    assert lay_end.anchor_top_center[1] == pytest.approx(118.0)

    # 3. Tách 2 pha tiêu đề (0% overlap) & 0px nhảy dest_y qua các mốc thời gian
    prev_board = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    photo_a = Image.new("RGBA", (800, 500), (200, 80, 60, 255))
    photo_b = Image.new("RGBA", (500, 900), (50, 150, 210, 255))
    beat_a = StickvBeat(
        id="ba",
        narration="Tiêu đề cũ đầu tiên.",
        board_type="pinned_photo",
        board_title="Tiêu đề cũ một",
    )
    beat_b = StickvBeat(
        id="bb",
        narration="Tiêu đề mới thứ hai.",
        board_type="pinned_photo",
        board_title="Tiêu đề mới hai",
    )
    prev_st = BeatStageState(
        x=540.0,
        y=1200.0,
        camera_shot="wide_stage",
        last_board_title="Tiêu đề cũ một",
        last_board_type="pinned_photo",
        last_visual_title="TIÊU ĐỀ CŨ MỘT",
    )
    cache: dict = {}
    try:
        _composite_transitioned_board(
            prev_board,
            beat_a,
            box,
            pal,
            t_sec=1.0,
            duration_sec=3.0,
            progress=1.0,
            prop_img=photo_a,
            clamp_bounds=(20, 115, 1060, 865),
            anchor_top_center=(540.0, 115.0),
        )
        seen_at_t: dict[float, list[str]] = {}
        y_tops: list[int] = []
        orig_text = ImageDraw.ImageDraw.text
        for t_check in (0.03, 0.13, 0.20, 0.30, 0.50):
            drawn: list[str] = []

            def spy(self, xy, text, *args, _d=drawn, **kwargs):
                _d.append(str(text))
                return orig_text(self, xy, text, *args, **kwargs)

            fr = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            try:
                with patch.object(ImageDraw.ImageDraw, "text", spy):
                    _composite_transitioned_board(
                        fr,
                        beat_b,
                        box,
                        pal,
                        t_sec=t_check,
                        duration_sec=3.0,
                        progress=min(1.0, t_check / 2.0),
                        prop_img=photo_b,
                        prev_stage_state=prev_st,
                        clamp_bounds=(20, 115, 1060, 865),
                        anchor_top_center=(540.0, 115.0),
                        prev_board_img=prev_board,
                        board_cache=cache,
                    )
                seen_at_t[t_check] = drawn
                bbox = fr.getbbox()
                assert bbox is not None
                y_tops.append(bbox[1])
            finally:
                fr.close()

        assert any("TIÊU ĐỀ CŨ MỘT" in t for t in seen_at_t[0.03])
        assert not any("TIÊU ĐỀ MỚI HAI" in t for t in seen_at_t[0.03])
        assert seen_at_t[0.13] == []
        for tm in (0.20, 0.30):
            assert any("TIÊU ĐỀ MỚI HAI" in t for t in seen_at_t[tm])
            assert not any("TIÊU ĐỀ CŨ MỘT" in t for t in seen_at_t[tm])
        assert len(set(y_tops)) == 1, f"dest_y jumped across transition: {y_tops}"
    finally:
        close_stage_cache(cache)
        prev_board.close()
        photo_a.close()
        photo_b.close()


def test_p12_resolve_beat_visual_image_routes_editorial_and_no_pisa_hardcode(
    tmp_path: Path, monkeypatch
) -> None:
    """INV-13: _resolve_beat_visual_image truyền visual_mode và không còn hardcode Pisa."""
    from hbt.stickv import render as sr

    render_src = Path(sr.__file__).read_text(encoding="utf-8")
    assert "bell tower monument exterior" not in render_src

    proj_dir = tmp_path / "workspace" / "stickv" / "demo"
    lib_dir = tmp_path / "library"
    proj_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)

    img_flux = lib_dir / "flux_out.jpg"
    Image.new("RGB", (64, 64), (40, 140, 210)).save(img_flux, format="JPEG")
    seen_calls: list[dict] = []

    def _fake_resolve(query: str, *args, **kwargs):
        seen_calls.append({"query": query, **kwargs})
        return img_flux, "cloudflare_flux"

    monkeypatch.setattr(sr, "resolve_reference_image", _fake_resolve)

    beat_cta = StickvBeat(
        id="b010",
        narration="Hãy để lại bình luận phía dưới video nhé.",
        pose="welcome_open",
        board_type="pinned_photo",
        board_title="Chia sẻ ý kiến ngay",
        beat_entity_en="Audience engagement",
        prop_query="Audience engagement speech bubble",
    )
    meta: dict[str, str] = {}
    log_rows: list[dict] = []
    im, src = sr._resolve_beat_visual_image(
        beat_cta,
        project_dir=proj_dir,
        library_dir=lib_dir,
        accent=(220, 38, 38, 255),
        ai_photo_budget=[10],
        visual_sources_log=log_rows,
        out_meta=meta,
    )
    if im is not None:
        im.close()
    assert src == "cloudflare_flux"
    assert seen_calls[0]["visual_mode"] == "editorial_illustration"
    assert log_rows[0]["visual_mode"] == "editorial_illustration"
