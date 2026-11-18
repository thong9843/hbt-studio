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

    def fake_stream(*, out_mp4: Path, **kwargs):
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(b"fake-media-bytes")
        return out_mp4

    with (
        patch("hbt.stickv.audio.run_ffmpeg", side_effect=fake_ffmpeg),
        patch("hbt.stickv.render.run_ffmpeg", side_effect=fake_ffmpeg),
        patch("hbt.stickv.render._stream_beat_frames_to_ffmpeg", side_effect=fake_stream),
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
    assert compute_pause_after("Kết thúc câu.") == pytest.approx(0.45)
    assert compute_pause_after("Ngắt giữa câu,") == pytest.approx(0.25)

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

    # b1: 0.10 lead + 0.80 s1 + 0.30 gap + 0.80 s2 + 0.45 pause_after = 2.45s
    assert beats[0].duration_sec == pytest.approx(2.45, abs=0.05)
    assert out_beats[0][1] == pytest.approx(2.45, abs=0.05)
    # b2: 0.10 lead + 0.80 s1 + 0.25 pause_after = 1.15s (clamped >= 1.2s)
    assert beats[1].duration_sec >= 1.15

    b1_wav = audio_dir / "b1.wav"
    env = extract_wav_rms_envelope(b1_wav, fps=20, duration_sec=beats[0].duration_sec)
    # Last 0.40s (8 frames at 20fps) are inside the 0.45s trailing pause -> silent
    assert max(env[-8:]) == 0.0

    timings = align_beat_karaoke(
        "Câu một. Câu hai?",
        b1_wav,
        beats[0].duration_sec,
        lead_in_s=0.10,
        pause_after_s=0.45,
    )
    assert len(timings) == 4
    assert timings[0][1] >= 0.08
    assert timings[-1][2] <= beats[0].duration_sec - 0.45 + 0.02

    # Kiểm tra spoken_segments sidecar + khóa Karaoke không lấn sang khoảng lặng
    from hbt.stickv.audio import load_beat_spoken_segments
    from hbt.stickv.backdrops import BackdropRenderer
    from hbt.stickv.stage import draw_karaoke_strip

    segs = load_beat_spoken_segments(b1_wav)
    assert len(segs) == 2
    assert segs[0][2] == "Câu một."
    assert segs[1][2] == "Câu hai?"
    # Khoảng giữa câu 1 và câu 2 có gap 0.30s
    assert segs[1][0] - segs[0][1] >= 0.25

    # Kiểm tra domain="physics_science" sinh phông xanh kỹ thuật khác #FAF7F0
    bd_phys = BackdropRenderer("physics_science", 360, 640)
    try:
        bg_phys = bd_phys.render_frame(0.5)
        assert bg_phys.getpixel((10, 10)) != (250, 247, 240)
        bg_phys.close()
    finally:
        bd_phys.close()

    # Kiểm tra draw_karaoke_strip ẩn trong khoảng lặng & chỉ hiện trong spoken_segments
    canvas_sil = Image.new("RGBA", (540, 1200), (0, 0, 0, 0))
    gap_t = (segs[0][1] + segs[1][0]) / 2.0
    draw_karaoke_strip(canvas_sil, timings, gap_t, aspect="9:16", spoken_segments=segs)
    assert canvas_sil.getbbox() is None  # Khoảng lặng giữa 2 câu không vẽ phụ đề
    draw_karaoke_strip(canvas_sil, timings, segs[0][0] + 0.1, aspect="9:16", spoken_segments=segs)
    assert canvas_sil.getbbox() is not None  # Đang nói câu 1 có vẽ phụ đề
    canvas_sil.close()
