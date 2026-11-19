"""Unit test cho PreflightQualityGate (AABB Auto-Reflow, Anti-Parrot, Pacing) & Contact Sheet."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from hbt.cinema.contact_sheet import render_contact_sheet
from hbt.cinema.preflight import PreflightQualityGate, word_overlap_ratio
from hbt.cinema.schema import AspectRatio, BBox, BeatSpec, BoardSpec, PuppetSpec, TimelineSpec


def _build_toxic_spec(aspect: AspectRatio) -> TimelineSpec:
    """Tạo kịch bản độc hại đủ mọi lỗi: y<0, đè Karaoke, vượt Safe-Zone, Anti-Parrot & lặp shot."""
    return TimelineSpec(
        slug=f"toxic-{aspect.replace(':', 'x')}",
        title="Video Kiểm Định Độc Hại",
        aspect=aspect,
        theme="cream",
        beats=[
            BeatSpec(
                id="b001",
                chapter=1,
                narration=(
                    "Hạch hạnh nhân Amygdala phản ứng trong 12ms nhanh gấp hai mươi lần vỏ não."
                ),
                duration_sec=4.0,
                shot_type="desk_wide",
                board=BoardSpec(
                    board_type="bullets",
                    title="Amygdala phản ứng",
                    bullets=["Hạch hạnh nhân Amygdala phản ứng trong 12ms nhanh gấp hai mươi lần"],
                    takeaway="Phản ứng bản năng xảy ra trong 12ms",
                    # Lỗi y < 0 và đè vào karaoke
                    bbox=BBox(x=40, y=-85, w=990, h=1060),
                ),
                puppet=PuppetSpec(
                    enabled=True,
                    pose="present_board",
                    bbox=BBox(x=100, y=920, w=600, h=950),  # Lỗi đè Karaoke + tràn đáy Safe-Zone
                ),
                karaoke_bbox=BBox(x=60, y=890, w=950, h=140),
            ),
            BeatSpec(
                id="b002",
                chapter=1,
                narration="Ánh sáng Mặt Trời mất tám phút để truyền tới Trái Đất qua chân không.",
                duration_sec=3.5,
                shot_type="desk_wide",  # Lỗi lặp 2 shot_type liên tiếp
                board=BoardSpec(
                    board_type="bullets",
                    title="Độ trễ ánh sáng",
                    bullets=["Ánh sáng Mặt Trời mất tám phút để truyền tới Trái Đất"],
                    bbox=BBox(x=56, y=130, w=960, h=700),
                ),
                puppet=PuppetSpec(enabled=True, pose="point_up"),
            ),
            BeatSpec(
                id="b003",
                chapter=1,
                narration="Nhưng thật ra sóng hấp dẫn cũng truyền đúng bằng vận tốc ánh sáng.",
                duration_sec=3.5,
                shot_type="desk_wide",  # Lỗi lặp 3 shot_type liên tiếp
                board=BoardSpec(
                    board_type="bullets",
                    title="Tốc độ vũ trụ",
                    bullets=["Vận tốc **299.792 km/s** không thể vượt qua"],
                    takeaway="Mọi tương tác đều bị giới hạn tốc độ c",
                ),
                puppet=PuppetSpec(enabled=True, pose="think_chin"),
            ),
            BeatSpec(
                id="b004",
                chapter=2,
                narration="Cảm ơn bạn đã xem, nhớ đăng ký kênh và bình luận cảm nghĩ bên dưới nhé!",
                duration_sec=3.0,
                shot_type="desk_wide",
                board=BoardSpec(
                    board_type="bullets",
                    title="Đăng ký kênh",
                    bullets=["Nhớ bấm đăng ký kênh ngay"],
                ),
                puppet=PuppetSpec(enabled=True, pose="wave_hello"),
            ),
        ],
    )


@pytest.mark.parametrize("aspect", ["9:16", "16:9"])
def test_preflight_detects_all_violations_and_auto_reflows_cleanly(aspect: AspectRatio) -> None:
    gate = PreflightQualityGate()
    toxic = _build_toxic_spec(aspect)

    # Kiểm định thô (auto_fix=False) phải bắt đủ lỗi
    dry = gate.validate_and_reflow(toxic, auto_fix=False)
    assert dry.ok is False
    codes = {e.code for e in dry.errors}
    assert "NEGATIVE_COORD" in codes
    assert "ANTI_PARROT" in codes
    assert "REPEATED_SHOT_TYPE" in codes
    assert "CTA_RECAP_REQUIRED" in codes

    # Chạy Auto-Reflow -> 0 lỗi còn sót & preflight_passed = True
    fixed = gate.validate_and_reflow(toxic, auto_fix=True)
    assert fixed.ok is True
    assert fixed.errors == []
    assert fixed.fixed_count >= 5
    assert fixed.repaired_spec.preflight_passed is True

    # Chạy kiểm định lại trên repaired_spec phải đạt 100% sạch
    recheck = gate.validate_and_reflow(fixed.repaired_spec, auto_fix=False)
    assert recheck.ok is True
    assert recheck.errors == []

    # Xác minh từng bất biến trên tất cả beat
    beats = fixed.repaired_spec.beats
    for prev_b, cur_b in zip(beats, beats[1:], strict=False):
        assert prev_b.shot_type != cur_b.shot_type

    for b in beats:
        assert b.board.bbox is not None and b.board.bbox.y >= 0
        assert b.karaoke_bbox is not None and b.karaoke_bbox.y >= 0
        assert not b.board.bbox.intersects(b.karaoke_bbox)
        if b.puppet.enabled and b.puppet.bbox is not None:
            assert b.puppet.bbox.y >= 0
            assert not b.puppet.bbox.intersects(b.karaoke_bbox)
            assert not b.board.bbox.intersects(b.puppet.bbox)
        if b.board.board_type not in ("none", "recap_card", "big_number", "counter_grow"):
            joined = f"{b.board.title} {' '.join(b.board.bullets)}"
            assert word_overlap_ratio(b.narration, joined) <= 0.65

    assert beats[-1].board.board_type == "recap_card"
    assert beats[-1].board.title == "TÓM TẮT 3 Ý CỐT LÕI"
    assert len(beats[-1].board.bullets) >= 2


def test_contact_sheet_renders_16_beats_under_two_seconds(tmp_path: Path) -> None:
    beats = [
        BeatSpec(
            id=f"b{i + 1:03d}",
            chapter=(i // 4) + 1,
            narration=f"Phân đoạn kiểm chứng tốc độ xuất contact sheet số {i + 1}.",
            duration_sec=2.5,
            shot_type=["desk_wide", "card_hero", "data_spotlight", "puppet_closeup"][i % 4],  # type: ignore[arg-type]
            board=BoardSpec(
                title=f"Ý chính #{i + 1}",
                bullets=[f"Dữ liệu số **{i + 10}%**"],
                takeaway=f"Kết luận {i + 1}",
            ),
        )
        for i in range(16)
    ]
    spec = TimelineSpec(slug="bench-sheet", title="Thử Nghiệm 16 Beats", aspect="9:16", beats=beats)
    report = PreflightQualityGate().validate_and_reflow(spec, auto_fix=True)

    out_jpg = tmp_path / "contact_sheet.jpg"
    meta = render_contact_sheet(report.repaired_spec, out_jpg, preflight_report=report)
    assert out_jpg.is_file()
    assert meta["beats_rendered"] == 16
    assert meta["elapsed_ms"] < 2000.0
    with Image.open(out_jpg) as img:
        assert img.format == "JPEG"
        assert img.width > 800 and img.height > 800
