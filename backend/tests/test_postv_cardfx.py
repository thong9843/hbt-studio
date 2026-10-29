"""Thẻ theo đoạn và hiệu ứng thẻ PostV (docs/postv/IMPLEMENT-POSTV.md mục 6, D20, D21)."""

import subprocess

import numpy as np
import pytest
from PIL import Image

from hbt.pipeline.ffutil import ffmpeg_exe
from hbt.postv.card import load_template
from hbt.postv.cardfx import (
    CardSpan,
    bounce_scale,
    build_asset,
    card_chain,
    card_of,
    card_timing,
    count_schedule,
    plan_cards,
    segment_starts,
    write_card_concat,
)
from hbt.postv.models import PostvProject, PostvSegment
from tests.helpers import needs_ffmpeg

TPL = load_template()
FEW = {**TPL, "anim": {**TPL["anim"], "count": {**TPL["anim"]["count"], "steps": 6}}}
FPS = 20


def project(**post):
    return PostvProject.model_validate(
        {
            "slug": "t",
            "title": "T",
            "post": {"handle": "a", "age": "5 giờ", "text": "Bài gốc để thử.", **post},
            "comments": [
                {"id": "c1", "handle": "b", "text": "Bình luận một", "likes": 2400, "replies": 12},
                {"id": "c2", "handle": "c", "text": "Bình luận hai"},
            ],
        }
    )


def seg(role, card=None, ref=None):
    return PostvSegment(role=role, card=card, ref=ref, voice="x")


def post_span(start=0.0, end=6.0, fresh=True, handoff=False):
    return CardSpan("post", None, start, end, fresh, handoff)


# ------------------------------------------------------------------ kế hoạch thẻ
def test_card_of_follows_role_unless_set():
    assert card_of(seg("hook")) == ("hook", None)
    assert card_of(seg("post")) == ("post", None)
    assert card_of(seg("comment", ref="c1")) == ("comment", "c1")
    assert card_of(seg("commentary")) == ("none", None)
    assert card_of(seg("commentary", card="post")) == ("post", None)
    assert card_of(seg("post", card="none")) == ("none", None)


def test_plan_merges_same_card_and_keeps_until_other_or_none():
    items = [("hook", None), ("post", None), ("post", None), ("none", None), ("comment", "c1")]
    spans = plan_cards(items, [0, 3, 6, 9, 12], 15)
    assert [(s.kind, s.ref, s.start, s.end) for s in spans] == [
        ("hook", None, 0, 3),
        ("post", None, 3, 9),
        ("comment", "c1", 12, 15),
    ]


def test_plan_marks_fresh_and_handoff():
    items = [("hook", None), ("post", None), ("none", None), ("comment", "c1"), ("comment", "c2")]
    spans = plan_cards(items, [0, 3, 6, 9, 12], 15)
    assert [(s.fresh, s.handoff) for s in spans] == [
        (True, True),  # hook → post liền nhau
        (False, False),  # post → mờ ra vì đoạn sau không có thẻ
        (True, True),  # comment c1 hiện ra sau khoảng trống, c2 nối tiếp
        (False, False),
    ]


def test_two_comments_with_different_refs_are_two_cards():
    spans = plan_cards([("comment", "c1"), ("comment", "c2")], [0, 4], 8)
    assert [s.ref for s in spans] == ["c1", "c2"]


def test_segment_starts_use_middle_of_the_pause():
    assert segment_starts([2.0, 5.0], 3, 0.4) == [0.0, 2.2, 5.2]


# ------------------------------------------------------------------ thời gian và hiệu ứng
def test_smooth_enter_slides_and_change_does_not():
    a = card_timing(post_span(2, 8), TPL, "smooth", 20)
    b = card_timing(post_span(2, 8, fresh=False), TPL, "smooth", 20)
    assert (a["in"], a["slide"], a["out"], a["bounce"]) == (0.35, 24.0, 0.25, False)
    assert (b["in"], b["slide"]) == (0.3, 0.0)
    assert a["seconds"] == pytest.approx(6.0 + 0.25)


def test_hook_always_bounces_and_bounce_mode_applies_to_fresh_cards():
    hook = CardSpan("hook", None, 0, 3, True, False)
    assert card_timing(hook, TPL, "smooth", 20)["bounce"] is True
    assert card_timing(post_span(3, 9), TPL, "smooth", 20)["bounce"] is False
    assert card_timing(post_span(3, 9), TPL, "bounce", 20)["bounce"] is True
    assert card_timing(post_span(3, 9, fresh=False), TPL, "bounce", 20)["bounce"] is False


def test_handoff_fades_over_the_change_time_and_last_card_ends_before_total():
    hook = CardSpan("hook", None, 0, 3, True, True)
    assert card_timing(hook, TPL, "smooth", 20)["out"] == 0.3
    last = card_timing(post_span(10, 20), TPL, "smooth", 20)
    assert last["visible"] == pytest.approx(10 - 0.25)
    assert last["seconds"] == pytest.approx(10)


def test_bounce_scale_follows_the_keyframes():
    cfg = TPL["anim"]["bounce"]
    assert bounce_scale(0, cfg) == pytest.approx(0.92)
    assert bounce_scale(0.18, cfg) == pytest.approx(1.04)  # đỉnh tại 60 % của 0,3 s
    assert bounce_scale(0.3, cfg) == 1.0 and bounce_scale(5, cfg) == 1.0
    assert 0.92 < bounce_scale(0.09, cfg) < 1.04 and 1.0 < bounce_scale(0.24, cfg) < 1.04


def test_count_schedule_goes_from_zero_to_full_in_about_a_second():
    sched = count_schedule(TPL["anim"]["count"])
    assert sched[0] == (0.0, 0.0) and sched[-1][1] == 1.0
    assert sched[-1][0] == pytest.approx(1.2)
    times = [t for t, _ in sched]
    scales = [s for _, s in sched]
    assert times == sorted(times) and scales == sorted(scales) and len(sched) == 25


# ------------------------------------------------------------------ ảnh trạng thái
def test_asset_counts_up_and_ends_at_the_final_numbers(tmp_path):
    p = project(likes=12000, replies=340, shares=560)
    asset = build_asset(p, post_span(), FEW, None, "blur", True, tmp_path / "cards")
    assert 3 <= len(asset.states) <= 7  # vài chục trạng thái, đã gộp các trạng thái giống nhau
    times = [t for _, t in asset.states]
    assert times[0] == 0.0 and times == sorted(times)
    first, last = (np.asarray(Image.open(asset.states[i][0])) for i in (0, -1))
    assert first.shape == last.shape == (asset.h, asset.w, 4)
    assert (first != last).any()
    assert 0 < asset.x < 1080 and 0 < asset.y < 1920 and asset.w <= FEW["card"]["w"] + 2


def test_asset_is_one_state_when_not_counting(tmp_path):
    p = project(likes=12000, replies=340, shares=560)
    assert len(build_asset(p, post_span(), FEW, None, "blur", False, tmp_path).states) == 1
    hook = CardSpan("hook", None, 0, 3)
    assert len(build_asset(p, hook, FEW, None, "blur", True, tmp_path).states) == 1
    assert len(build_asset(project(), post_span(), FEW, None, "blur", True, tmp_path).states) == 1


def test_asset_is_cached_by_content_not_by_time(tmp_path):
    p = project(likes=500, replies=3, shares=2)
    a = build_asset(p, post_span(), FEW, None, "blur", True, tmp_path)
    stamp = {s.stat().st_mtime_ns for s, _ in a.states}
    b = build_asset(p, post_span(40, 50, False, True), FEW, None, "blur", True, tmp_path)
    assert a == b and {s.stat().st_mtime_ns for s, _ in b.states} == stamp
    other = project(likes=501, replies=3, shares=2)
    c = build_asset(other, post_span(), FEW, None, "blur", True, tmp_path)
    assert c.states[0][0] != a.states[0][0]


def test_bounce_asset_has_one_fixed_canvas_and_a_growing_then_settling_card(tmp_path):
    p = project(likes=500, replies=3, shares=2)
    asset = build_asset(p, post_span(), FEW, None, "blur", False, tmp_path, bounce=True)
    plain = build_asset(p, post_span(), FEW, None, "blur", False, tmp_path)
    sizes = {Image.open(path).size for path, _ in asset.states}
    assert sizes == {(asset.w, asset.h)} and asset.w >= plain.w * 1.04 and asset.h >= plain.h * 1.04
    assert asset.w % 2 == 0 and asset.h % 2 == 0 and len(asset.states) >= 8
    widths = []
    for path, _ in asset.states:
        cols = np.nonzero(np.asarray(Image.open(path))[..., 3].sum(axis=0))[0]
        widths.append(int(cols.max() - cols.min()) + 1)
    assert widths[0] < max(widths) and widths[-1] == plain.w  # nhỏ hơn → to nhất → về cỡ gốc
    # tâm khung trùng tâm thẻ gốc
    assert asset.x + asset.w / 2 == pytest.approx(plain.x + plain.w / 2, abs=1)
    assert asset.y + asset.h / 2 == pytest.approx(plain.y + plain.h / 2, abs=1)


def test_comment_asset_uses_the_comment_numbers(tmp_path):
    span = CardSpan("comment", "c1", 0, 6, True, False)
    assert len(build_asset(project(), span, FEW, None, "blur", True, tmp_path).states) > 1


def concat_seconds(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return sum(float(x.split()[1]) for x in lines if x.startswith("duration"))


def test_concat_file_lasts_exactly_the_requested_time(tmp_path):
    p = project(likes=12000, replies=340, shares=560)
    asset = build_asset(p, post_span(), FEW, None, "blur", True, tmp_path)
    full, short = tmp_path / "c.ffconcat", tmp_path / "s.ffconcat"
    write_card_concat(asset, 6.25, full)
    write_card_concat(asset, 0.5, short)  # ngắn hơn lúc chạy số: chỉ giữ các trạng thái đầu
    assert concat_seconds(full) == pytest.approx(6.25, abs=1e-5)
    assert concat_seconds(short) == pytest.approx(0.5, abs=1e-5)
    assert full.read_text(encoding="utf-8").splitlines()[-1].startswith("file ")


# ------------------------------------------------------------------ chạy thật bằng ffmpeg
def run_chain(tmp_path, span, mode, total=5.0, scale=0.25):
    timing = card_timing(span, TPL, mode, total)
    asset = build_asset(
        project(), span, TPL, None, "blur", False, tmp_path / "cards", timing["bounce"]
    )
    concat = tmp_path / "c.ffconcat"
    write_card_concat(asset, timing["seconds"], concat)
    w, h = int(1080 * scale), int(1920 * scale)
    chain = card_chain(1, "c0", asset, span, timing, TPL, FPS, scale, "bg", "out")
    out = tmp_path / "o.mp4"
    subprocess.run(
        [
            ffmpeg_exe(), "-v", "error", "-y",
            "-f", "lavfi", "-i", f"color=c=0x3050A0:s={w}x{h}:r={FPS}:d={total}",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-filter_complex", ";".join(["[0:v]null[bg]", *chain]),
            "-map", "[out]", "-t", str(total), "-pix_fmt", "yuv420p", str(out),
        ],
        check=True,
    )  # fmt: skip
    raw = subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-i", str(out), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


BG = np.array([0x30, 0x50, 0xA0])


def white(frame):
    return (frame > 235).all(axis=2)


def ink(frame):
    """Điểm ảnh khác màu nền (kể cả lúc thẻ đang hiện dần, còn mờ)."""
    return np.abs(frame.astype(int) - BG).sum(axis=2) > 30


def at(frames, t):
    return frames[int(t * FPS)]


@needs_ffmpeg
def test_card_fades_in_stays_then_fades_out(tmp_path):
    frames = run_chain(tmp_path, post_span(1.0, 3.5), "smooth")
    count = {t: int(white(at(frames, t)).sum()) for t in (0.8, 1.1, 2.5, 3.6, 4.5)}
    assert count[0.8] == 0 and count[4.5] == 0
    assert count[1.1] < count[2.5] and count[3.6] < count[2.5] and count[2.5] > 500


@needs_ffmpeg
def test_smooth_enter_slides_down_into_place(tmp_path):
    frames = run_chain(tmp_path, post_span(1.0, 4.0), "smooth", scale=0.5)

    def top(frame):
        rows = np.nonzero(ink(frame).sum(axis=1) > 20)[0]
        return rows.min() if len(rows) else None

    assert top(at(frames, 1.1)) < top(at(frames, 2.5))  # đang trượt xuống dần


@needs_ffmpeg
def test_hook_bounces_then_settles(tmp_path):
    frames = run_chain(tmp_path, CardSpan("hook", None, 1.0, 4.0, True, False), "smooth")

    def width(frame):
        cols = np.nonzero(white(frame).sum(axis=0) > 3)[0]
        return int(cols.max() - cols.min()) if len(cols) else 0

    settled = width(at(frames, 3.0))
    assert settled > 0 and width(at(frames, 1.15)) != settled
    assert width(at(frames, 2.0)) == settled
