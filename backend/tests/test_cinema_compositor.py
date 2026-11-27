"""Unit test cho Motion, 6 HBT Tactile Desk Shots, Transitions & Dirty-Rect Compositor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import ImageFont

from hbt.cinema.cache import BEAT_AUDIO_CHANNELS, BEAT_AUDIO_RATE, BEAT_PIX_FMT
from hbt.cinema.compositor import DirtyRectCompositor
from hbt.cinema.hardware import detect_hardware
from hbt.cinema.layer_cache import LayerCache
from hbt.cinema.motion import (
    Keyframe,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    evaluate_track,
    spring,
)
from hbt.cinema.preflight import SAFE_ZONES
from hbt.cinema.schema import SHOT_TYPES, AspectRatio, BeatSpec, BoardSpec, PuppetSpec, TimelineSpec
from hbt.cinema.shots import bake_static_shot_layer, compute_shot_layout
from hbt.pipeline.ffutil import probe


def test_motion_curves_and_keyframe_track() -> None:
    assert ease_out_cubic(0.0) == 0.0
    assert ease_out_cubic(1.0) == 1.0
    assert ease_in_out_cubic(0.5) == pytest.approx(0.5, abs=1e-4)
    assert ease_out_back(0.6) > 1.0  # Có overshoot nhẹ tự nhiên
    assert ease_out_back(1.0) == pytest.approx(1.0, abs=1e-4)
    assert spring(0.0) == 0.0
    assert spring(1.0) == pytest.approx(1.0, abs=1e-4)

    track = [
        Keyframe(t=0.0, value=10.0, easing="linear"),
        Keyframe(t=1.0, value=110.0, easing="ease_out_cubic"),
    ]
    assert evaluate_track(track, -0.5) == 10.0
    assert evaluate_track(track, 1.5) == 110.0
    assert evaluate_track(track, 0.5) > 60.0  # ease_out_cubic tăng nhanh nửa đầu


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
def test_all_six_tactile_desk_shots_stay_safe_and_disjoint(aspect: AspectRatio) -> None:
    safe = SAFE_ZONES[aspect]["stage"]
    for shot in SHOT_TYPES:
        layout = compute_shot_layout(shot, aspect)
        assert layout.board_box.y >= 0
        assert layout.puppet_box.y >= 0
        assert layout.karaoke_box.y >= 0
        assert layout.board_box.x >= safe.x and layout.board_box.x2 <= safe.x2
        assert layout.board_box.y >= safe.y and layout.board_box.y2 <= safe.y2
        assert not layout.board_box.intersects(layout.karaoke_box)
        assert not layout.puppet_box.intersects(layout.karaoke_box)
        assert not layout.board_box.intersects(layout.puppet_box)

        beat = BeatSpec(
            id=f"b_{shot}",
            narration="Kiểm thử 6 góc máy độc bản HBT Tactile Desk.",
            shot_type=shot,
            board=BoardSpec(
                title=f"Góc {shot}",
                bullets=["Ý **#1** nổi bật", "Ý **#2** đối chiếu", "Ý **#3** kết luận"],
                takeaway="Chốt kiến thức rõ ràng",
            ),
        )
        tw = 360 if aspect == "9:16" else 640
        th = 640 if aspect == "9:16" else 360
        scaled_layout = compute_shot_layout(shot, aspect, width=tw, height=th)
        baked = bake_static_shot_layer(
            beat,
            scaled_layout,
            width=tw,
            height=th,
        )
        try:
            assert baked.mode == "RGBA"
        finally:
            baked.close()


def test_compositor_zero_truetype_in_frame_loop_and_high_layer_cache_hit_rate(
    tmp_path: Path,
) -> None:
    hw = detect_hardware(probe_fn=lambda: (False, "cpu test"))
    comp = DirtyRectCompositor(hw=hw, layer_cache=LayerCache(max_mb=64))
    beat = BeatSpec(
        id="b001",
        narration="Ánh sáng Mặt Trời truyền tới Trái Đất mất tám phút.",
        duration_sec=0.8,
        shot_type="desk_wide",
        board=BoardSpec(
            title="Tốc độ ánh sáng",
            bullets=["Vận tốc **300.000 km/s**", "Khoảng cách **150 triệu km**"],
            takeaway="Ánh sáng mất 8 phút tới Trái Đất",
        ),
        puppet=PuppetSpec(enabled=True, pose="present_board"),
    )
    spec = TimelineSpec(slug="spy-test", title="Spy Font", aspect="9:16", fps=24, beats=[beat])
    layout = compute_shot_layout(beat.shot_type, spec.aspect, beat=beat, width=360, height=640)

    # Pre-warm static layer & fonts như trong render_beat_to_mp4
    comp._prewarm_fonts(360, "9:16")
    b_hash = beat.content_hash(
        aspect=spec.aspect, fps=spec.fps, theme=spec.theme, domain=spec.domain
    )
    comp.layer_cache.get_or_bake(
        f"static:{b_hash}:360x640",
        lambda: bake_static_shot_layer(
            beat,
            layout,
            domain=spec.domain,
            theme=spec.theme,
            width=360,
            height=640,
            font_cache=comp.font_cache,
        ),
    )

    words = [("Ánh", 0.0, 0.25), ("sáng", 0.25, 0.5), ("tới", 0.5, 0.75), ("đây", 0.75, 1.0)]
    with patch.object(ImageFont, "truetype", wraps=ImageFont.truetype) as spy_tt:
        for f_idx in range(30):
            fr = comp.render_frame(
                beat,
                spec=spec,
                layout=layout,
                f_idx=f_idx,
                t_sec=f_idx / 30.0,
                mouth_open=0.3,
                word_timings=words,
                width=360,
                height=640,
            )
            fr.close()
            if f_idx == 0:
                spy_tt.reset_mock()
        assert spy_tt.call_count == 0
    assert comp.layer_cache.hit_rate >= 0.90
    comp.layer_cache.close()


def test_compositor_renders_valid_mp4_via_ffmpeg_pipe_without_library_media(
    tmp_path: Path,
) -> None:
    hw = detect_hardware(probe_fn=lambda: (False, "cpu test"))
    comp = DirtyRectCompositor(hw=hw)
    beat = BeatSpec(
        id="b001",
        narration="Kiểm thử pipe FFmpeg chế độ CI không cần thư viện ảnh.",
        duration_sec=0.45,
        shot_type="data_spotlight",
        board=BoardSpec(
            board_type="big_number",
            title="Mốc kiểm chứng",
            bullets=["Đạt chuẩn **100%** hiển thị"],
            takeaway="Chạy sạch trên Ubuntu CI",
            data={"number": "100%"},
        ),
    )
    spec = TimelineSpec(slug="ci-pipe", title="Pipe Test", aspect="9:16", fps=24, beats=[beat])
    out_mp4 = tmp_path / "beat_out.mp4"
    res = comp.render_beat_to_mp4(
        beat,
        spec,
        out_mp4,
        library_dir=tmp_path / "missing_lib",
        assets_dir=tmp_path / "missing_assets",
        width=270,
        height=480,
    )
    assert out_mp4.is_file()
    assert res["frames"] >= 10
    info = probe(out_mp4)
    v_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
    a_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    assert v_streams and a_streams
    assert v_streams[0]["pix_fmt"] == BEAT_PIX_FMT
    assert int(a_streams[0]["sample_rate"]) == BEAT_AUDIO_RATE
    assert int(a_streams[0]["channels"]) == BEAT_AUDIO_CHANNELS
    comp.layer_cache.close()
