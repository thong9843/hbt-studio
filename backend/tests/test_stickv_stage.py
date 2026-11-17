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
            [beat], tmp_path / "aud", voice_provider=broken_provider, voice_id="vienneu_default"
        )
