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
            fps=30,
            aspect="16:9",
            brand_dir=brand,
            library_dir=lib,
            chunks_dir=chunks,
        )
        fc_169 = cmds[-1][cmds[-1].index("-filter_complex") + 1]
        assert "#B22228" in fc_169
        assert "xfade=transition=fade:duration=0.5" in fc_169


def test_natural_speech_pauses_and_locked_karaoke(tmp_path: Path) -> None:
    import wave

    import numpy as np
    import pytest

    from hbt.stickv.audio import (
        align_beat_karaoke,
        compute_pause_after,
        split_beat_sentences,
    )

    assert split_beat_sentences("Câu một. Câu hai?") == ["Câu một.", "Câu hai?"]
    assert compute_pause_after("Kết thúc câu.") == pytest.approx(0.14)
    assert compute_pause_after("Ngắt giữa câu,") == pytest.approx(0.14)

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

    beats = [
        StickvBeat(id="b1", narration="Câu một. Câu hai?"),
        StickvBeat(id="b2", narration="Ý tiếp theo,"),
    ]
    audio_dir = tmp_path / "audio"
    out_beats = synth_stickv_beats_audio(
        beats,
        audio_dir,
        voice_provider=_FakeVoiceProvider(),
        voice_id="Thanh Bình",
        pause_scale=1.0,
    )

    # b1: 0.06 lead + 0.80 s1 + 0.16 gap + 0.80 s2 + 0.14 pause_after = 1.96s
    assert beats[0].duration_sec == pytest.approx(1.96, abs=0.05)
    assert out_beats[0][1] == pytest.approx(1.96, abs=0.05)
    # b2: 0.06 lead + 0.80 s1 + 0.14 pause_after = 1.00s (clamped >= 1.2s)
    assert beats[1].duration_sec >= 1.15

    b1_wav = audio_dir / "b1.wav"
    env = extract_wav_rms_envelope(b1_wav, fps=20, duration_sec=beats[0].duration_sec)
    # 0.10s cuối nằm trong 0.14s trailing pause -> im lặng
    assert max(env[-2:]) == 0.0

    timings = align_beat_karaoke(
        "Câu một. Câu hai?",
        b1_wav,
        beats[0].duration_sec,
        lead_in_s=0.06,
        pause_after_s=0.14,
    )
    assert len(timings) == 4
    assert timings[0][1] >= 0.04
    assert timings[-1][2] <= beats[0].duration_sec - 0.14 + 0.02

    # Kiểm tra spoken_segments sidecar + khóa Karaoke qua khoảng nghỉ
    from hbt.stickv.audio import load_beat_spoken_segments
    from hbt.stickv.backdrops import BackdropRenderer
    from hbt.stickv.stage import draw_karaoke_strip

    segs = load_beat_spoken_segments(b1_wav)
    assert len(segs) == 2
    assert segs[0][2] == "Câu một."
    assert segs[1][2] == "Câu hai?"
    # Khoảng giữa câu 1 và câu 2 có gap ~0.16s (nhịp kể liên tục)
    assert segs[1][0] - segs[0][1] == pytest.approx(0.16, abs=0.03)

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
    assert lay_focus.char_scale == pytest.approx(0.82)

    lay_close = compute_layered_camera_layout(
        "closeup_react",
        aspect="9:16",
        w=1080,
        h=1920,
        t_sec=0.35,
        prev_stage_state=BeatStageState(x=500.0, y=1200.0, board_alpha=1.0),
    )
    assert lay_close.board_alpha == pytest.approx(0.0, abs=0.01)
    assert lay_close.char_scale == pytest.approx(1.22)

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
