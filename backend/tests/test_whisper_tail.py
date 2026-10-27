"""Cắt đuôi file giọng bằng Whisper (IMPLEMENT.md 4d.1): chỉ cắt khi token cuối khớp thật."""

import pytest

from hbt.pipeline import audio, render
from hbt.pipeline.audio import TailTrimNeedsConfirmation, plan_tail_trim
from hbt.pipeline.render import render_project
from tests.helpers import needs_ffmpeg
from tests.test_render import body_len, make_project
from tests.test_whisper_align import FakeWhisper

# Giọng giả của make_project(n=3), thời gian sau prep_voice: lời kết thúc ở 5,1 s; đuôi thừa bắt đầu
# sau khoảng lặng 0,8 s, tức 5,9 s.
LAST_END = 5.1
AD = [("quang", 5.9, 7.0), ("cao", 7.0, 8.9)]
TAIL_AUDIO = [("gap", 0.8), ("tone", 3.0)]


# ---------------------------------------------------------------- kế hoạch cắt
def test_whisper_hearing_words_after_voice_end_counts_as_extra():
    plan = plan_tail_trim(LAST_END, [], 9.0, heard_end=8.9)
    assert plan is not None
    assert plan.voice_end == pytest.approx(LAST_END + 0.35)
    assert plan.cut_seconds == pytest.approx(9.0 - LAST_END - 0.35)


def test_words_ending_within_the_margin_are_not_extra():
    assert plan_tail_trim(LAST_END, [], 9.0, heard_end=LAST_END + 0.3) is None
    assert plan_tail_trim(LAST_END, [], 9.0, heard_end=None) is None


def test_trim_voice_tail_pad_is_configurable(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        audio, "run_ffmpeg", lambda args: seen.update(af=args[args.index("-af") + 1])
    )
    audio.trim_voice_tail("a.wav", "b.wav", 5.45, pad=1.25)
    assert "atrim=end=5.450" in seen["af"] and "apad=pad_dur=1.250" in seen["af"]
    assert "afade=t=out:st=5.370:d=0.08" in seen["af"]
    audio.trim_voice_tail("a.wav", "b.wav", 5.45)
    assert f"apad=pad_dur={audio.TAIL:.3f}" in seen["af"]


# ---------------------------------------------------------------- dựng đầu-cuối
@pytest.fixture
def whisper(monkeypatch):
    def install(**kw):
        fake = FakeWhisper(**kw)
        monkeypatch.setattr(render, "run_whisper", fake)
        return fake

    return install


@needs_ffmpeg
def test_extra_tail_is_cut_and_padded_to_1_6_s_after_the_last_word(tmp_path, whisper):
    whisper(extra=AD)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False, tail=TAIL_AUDIO)
    res = render_project(pdir, opts)
    assert res.aligner == "whisper"
    assert "Đã cắt 1 đoạn thừa ở cuối file giọng" in res.log.read_text("utf-8")
    assert res.duration == pytest.approx(LAST_END + 1.6, abs=0.15)
    assert not res.warnings


@needs_ffmpeg
def test_no_extra_tail_means_no_cut_and_no_warning(tmp_path, whisper):
    whisper()
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    res = render_project(pdir, opts)
    assert "Đã cắt" not in res.log.read_text("utf-8")
    assert not res.warnings
    assert res.duration == pytest.approx(body_len(3), abs=0.15)


@needs_ffmpeg
def test_unmatched_last_token_is_never_cut_only_warned(tmp_path, whisper):
    whisper(extra=AD, drop_last=True)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False, tail=TAIL_AUDIO)
    res = render_project(pdir, opts)
    assert any(w.startswith("Có thể có đoạn thừa ở cuối file giọng") for w in res.warnings)
    assert "Đã cắt" not in res.log.read_text("utf-8")
    assert res.duration == pytest.approx(body_len(3, tail=3.8), abs=0.15)


@needs_ffmpeg
def test_unmatched_last_token_without_extra_audio_is_silent(tmp_path, whisper):
    whisper(drop_last=True)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False)
    res = render_project(pdir, opts)
    assert not res.warnings and "Đã cắt" not in res.log.read_text("utf-8")


LONG_AD = [("quang", 5.9, 7.0), ("cao", 7.0, 15.0)]
LONG_TAIL = [("gap", 0.8), ("tone", 9.0)]


@needs_ffmpeg
def test_trim_longer_than_8_s_needs_confirmation(tmp_path, whisper):
    whisper(extra=LONG_AD)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False, tail=LONG_TAIL)
    with pytest.raises(TailTrimNeedsConfirmation, match="> 8 giây"):
        render_project(pdir, opts)


@needs_ffmpeg
def test_long_trim_goes_ahead_once_confirmed(tmp_path, whisper):
    whisper(extra=LONG_AD)
    pdir, opts = make_project(tmp_path, aligner="auto", outro=False, tail=LONG_TAIL)
    opts.allow_long_trim = True
    res = render_project(pdir, opts)
    assert "Đã cắt 1 đoạn thừa ở cuối file giọng" in res.log.read_text("utf-8")
    assert res.duration == pytest.approx(LAST_END + 1.6, abs=0.15)


@needs_ffmpeg
def test_manual_trim_end_wins_over_whisper_trimming(tmp_path, whisper):
    whisper()
    pdir, opts = make_project(
        tmp_path,
        aligner="auto",
        outro=False,
        tail=TAIL_AUDIO,
        voice={"file": "voice.wav", "trim_end": 4.9 + 0.4},
    )
    res = render_project(pdir, opts)
    log = res.log.read_text("utf-8")
    assert "Cắt đuôi giọng theo voice.trim_end" in log and "đoạn thừa" not in log
    assert not res.warnings
