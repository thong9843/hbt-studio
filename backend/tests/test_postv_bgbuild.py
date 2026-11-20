"""Chọn và nối nền PostV (docs/postv/IMPLEMENT-POSTV.md mục 6, bước 5)."""

from pathlib import Path

import pytest

from hbt.pipeline.ffutil import probe
from hbt.postv import bgbuild
from hbt.postv.backgrounds import BackgroundEntry
from hbt.postv.bgbuild import PAD, Piece, bg_key, build_background, pick_pieces
from tests.helpers import needs_ffmpeg
from tests.test_postv_backgrounds import make_clip


def entry(clip_id, duration=40.0):
    return BackgroundEntry(
        id=clip_id, file=f"{clip_id}.mp4", title=clip_id, source="s", license="l",
        width=1080, height=1920, fps=60, duration=duration,
    )  # fmt: skip


CLIPS = [entry("a"), entry("b"), entry("c")]
ROOT = Path("lib")


def test_same_seed_same_pieces_and_other_seed_differs():
    one = pick_pieces(CLIPS, ROOT, 60, seed=7)
    assert one == pick_pieces(CLIPS, ROOT, 60, seed=7)
    assert one != pick_pieces(CLIPS, ROOT, 60, seed=8)


def test_pieces_cover_total_with_pad_and_use_allowed_lengths():
    pieces = pick_pieces(CLIPS, ROOT, 60, seed=1)
    assert sum(p.seconds for p in pieces) == pytest.approx(60 + PAD, abs=0.01)
    assert all(p.seconds in (7.5, 15.0) for p in pieces[:-1])
    assert pieces[-1].seconds <= 15.0


def test_piece_stays_inside_the_clip():
    short = [entry("s", duration=5.0)]
    for p in pick_pieces(short, ROOT, 30, seed=3):
        assert p.seconds <= 5.0 and p.start + p.seconds <= 5.0 + 1e-6
    for p in pick_pieces(CLIPS, ROOT, 90, seed=3):
        assert 0 <= p.start and p.start + p.seconds <= 40.0 + 1e-6


def test_neighbours_differ_when_there_are_other_clips():
    pieces = pick_pieces(CLIPS, ROOT, 200, seed=5)
    assert all(a.clip_id != b.clip_id for a, b in zip(pieces, pieces[1:], strict=False))


def test_start_offset_applies_to_first_piece_only():
    pieces = pick_pieces(CLIPS, ROOT, 40, seed=2, start_offset=3.0)
    assert pieces[0].start == 3.0
    assert any(p.start != 3.0 for p in pieces[1:])


def test_start_offset_is_clamped_to_the_clip():
    pieces = pick_pieces([entry("s", duration=10.0)], ROOT, 5, seed=1, start_offset=99)
    assert pieces[0].start + pieces[0].seconds <= 10.0 + 1e-6


def test_no_clips_is_an_error():
    with pytest.raises(ValueError):
        pick_pieces([], ROOT, 10, seed=1)


def test_bg_key_follows_pieces_size_and_bg_code(tmp_path, monkeypatch):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    piece = Piece("a", f, 1.0, 7.5)
    base = bg_key([piece], 1080, 1920, 60, "veryfast", 12)
    assert bg_key([Piece("a", f, 2.0, 7.5)], 1080, 1920, 60, "veryfast", 12) != base
    assert bg_key([piece], 540, 960, 30, "ultrafast", 23) != base
    monkeypatch.setattr(bgbuild, "BG_VERSION", "doi-ma-nen")
    assert bg_key([piece], 1080, 1920, 60, "veryfast", 12) != base


@needs_ffmpeg
def test_build_background_concats_to_size_fps_and_length(tmp_path):
    a = make_clip(tmp_path / "a.mp4", seconds=3, fps=30)
    b = make_clip(tmp_path / "b.mp4", seconds=3, fps=25)
    out = tmp_path / "bg.mp4"
    build_background(
        [Piece("a", a, 0.0, 1.5), Piece("b", b, 0.5, 1.5)], 270, 480, 30, "ultrafast", 30, out
    )
    info = probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"], v["r_frame_rate"]) == (270, 480, "30/1")
    assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.1)
    assert not any(s["codec_type"] == "audio" for s in info["streams"])
    assert not out.with_name("bg.part.mp4").exists()
