"""Unit test cho phông nền động 5 domain & tương tác sân khấu 2.5D."""

from __future__ import annotations

from PIL import Image, ImageChops

from hbt.stickv.backdrops import VALID_DOMAINS, BackdropRenderer, normalize_domain
from hbt.stickv.models import StickvBeat
from hbt.stickv.stage import render_animated_beat_frame


def test_normalize_domain_aliases() -> None:
    assert normalize_domain("cosmos") == "cosmos_mystery"
    assert normalize_domain("physics_science") == "physics_science"
    assert normalize_domain("unknown_x") == "paper_classic"
    assert normalize_domain(None) == "paper_classic"


def test_all_five_domains_render_and_loop_4s() -> None:
    for dom in VALID_DOMAINS:
        gen = BackdropRenderer(dom, 360, 640)
        try:
            f0 = gen.render_frame(0.0)
            f1 = gen.render_frame(1.25)
            f4 = gen.render_frame(4.0)
            assert f0.size == (360, 640)
            assert f0.mode == "RGB"
            # Chu kỳ lặp 4.0s khớp nhau
            diff = ImageChops.difference(f0, f4).getbbox()
            assert diff is None
            # Khung tại t=1.25s có chuyển động khác t=0.0s
            assert ImageChops.difference(f0, f1).getbbox() is not None
            f0.close()
            f1.close()
            f4.close()
        finally:
            gen.close()


def test_stage_interactions_hold_prop_point_chart_versus_split() -> None:
    bg = Image.new("RGB", (540, 960), (250, 247, 240))
    char = Image.new("RGBA", (180, 320), (20, 20, 20, 255))
    prop = Image.new("RGBA", (120, 120), (217, 35, 46, 255))

    try:
        # 1. hold_prop
        b_prop = StickvBeat(id="b1", narration="Não bộ", motion="bounce")
        object.__setattr__(b_prop, "interaction", "hold_prop")
        out1 = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=b_prop,
            aspect="9:16",
            t_sec=0.3,
            mouth_open=0.5,
            word_timings=[("Não", 0.0, 0.5)],
            prop_img=prop,
            domain="physics_science",
        )
        assert out1.size == (540, 960)
        out1.close()

        # 2. point_chart (bar_compare)
        b_chart = StickvBeat(
            id="b2",
            narration="So sánh tốc độ",
            board_type="bullets",
            board_title="Tốc độ",
            board_data={
                "values": [{"label": "Ánh sáng", "value": 300}, {"label": "Âm thanh", "value": 1}]
            },
        )
        object.__setattr__(b_chart, "interaction", "point_chart")
        object.__setattr__(b_chart, "board_type", "bar_compare")
        out2 = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=b_chart,
            aspect="9:16",
            t_sec=0.8,
            mouth_open=0.3,
            word_timings=[],
            draw_board=True,
            duration_sec=2.0,
        )
        assert out2.size == (540, 960)
        out2.close()

        # 3. versus_split
        b_vs = StickvBeat(
            id="b3",
            narration="Trái hay phải",
            board_data={"left_label": "Mặt Trời", "right_label": "Mặt Trăng"},
        )
        object.__setattr__(b_vs, "interaction", "versus_split")
        out3 = render_animated_beat_frame(
            bg_img=bg,
            char_img=char,
            beat=b_vs,
            aspect="16:9",
            t_sec=0.5,
            mouth_open=0.2,
            word_timings=[],
        )
        assert out3.size == (540, 960)
        out3.close()
    finally:
        bg.close()
        char.close()
        prop.close()
