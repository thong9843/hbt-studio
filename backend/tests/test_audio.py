import wave

import numpy as np
import pytest

from hbt.pipeline import audio
from hbt.pipeline.ffutil import measure_lufs, media_duration, probe, run_ffmpeg
from tests.helpers import needs_ffmpeg, write_wav

# Giọng giả: hai câu cách nhau 0,8 s.
SPEECH = [("gap", 0.3), ("tone", 1.5), ("gap", 0.8), ("tone", 2.0), ("gap", 0.3)]


def stream(path):
    return probe(path)["streams"][0]


# ---------------------------------------------------------------- kế hoạch cắt đuôi (không FFmpeg)
def test_plan_no_extra_segment_returns_none():
    segs = [(0.2, 1.7), (2.5, 4.5)]
    assert audio.plan_tail_trim(4.4, segs, content_end=4.8) is None


def test_plan_extra_segment_is_cut():
    segs = [(0.2, 1.7), (2.5, 4.5), (5.3, 8.3)]
    plan = audio.plan_tail_trim(4.4, segs, content_end=8.6)
    assert plan is not None
    assert plan.voice_end == pytest.approx(4.4 + audio.VOICE_END_MARGIN)
    assert plan.segments_cut == 1
    assert plan.cut_seconds == pytest.approx(8.6 - 4.75)


def test_plan_over_eight_seconds_needs_confirmation():
    segs = [(0.2, 4.5), (6.0, 20.0)]
    with pytest.raises(audio.TailTrimNeedsConfirmation, match="giây"):
        audio.plan_tail_trim(4.4, segs, content_end=20.5)
    plan = audio.plan_tail_trim(4.4, segs, content_end=20.5, allow_long=True)
    assert plan.cut_seconds > audio.MAX_TRIM_SECONDS


# ---------------------------------------------------------------- giọng đọc
@needs_ffmpeg
def test_prep_voice_delay_pad_loudness(tmp_path):
    src, dst = tmp_path / "v.wav", tmp_path / "out.wav"
    dur = write_wav(src, SPEECH)
    audio.prep_voice(src, dst)
    s = stream(dst)
    assert s["channels"] == 1 and int(s["sample_rate"]) == 44100
    assert media_duration(dst) == pytest.approx(dur + audio.VOICE_DELAY + audio.TAIL, abs=0.05)
    assert measure_lufs(dst) == pytest.approx(-14.0, abs=1.5)


@needs_ffmpeg
def test_trim_tail_removes_extra_and_logs(tmp_path):
    src, prepped = tmp_path / "v.wav", tmp_path / "prepped.wav"
    # câu cuối kết thúc ở 4,6 s; sau đó 3 s quảng cáo.
    write_wav(src, SPEECH + [("gap", 0.6), ("tone", 3.0), ("gap", 0.3)])
    audio.prep_voice(src, prepped)
    last_end = 0.2 + 0.3 + 1.5 + 0.8 + 2.0  # = 4.8 trên mốc đã trễ 0,2 s
    logs = []
    out, plan = audio.trim_tail_if_needed(
        prepped, last_end, tmp_path / "trimmed.wav", log=logs.append
    )
    assert plan is not None and plan.segments_cut == 1
    assert out == tmp_path / "trimmed.wav"
    assert len(logs) == 1 and logs[0].startswith("Đã cắt 1 đoạn thừa ở cuối file giọng")
    assert "(" in logs[0] and "," in logs[0]  # số giây dạng 3,xx
    assert media_duration(out) == pytest.approx(plan.voice_end + audio.TAIL, abs=0.05)
    assert measure_lufs(out) == pytest.approx(-14.0, abs=1.5)


@needs_ffmpeg
def test_trim_tail_keeps_clean_file_untouched(tmp_path):
    src, prepped = tmp_path / "v.wav", tmp_path / "prepped.wav"
    write_wav(src, SPEECH)
    audio.prep_voice(src, prepped)
    logs = []
    out, plan = audio.trim_tail_if_needed(
        prepped, 0.2 + 0.3 + 1.5 + 0.8 + 2.0, tmp_path / "trimmed.wav", log=logs.append
    )
    assert plan is None and out == prepped and logs == []
    assert not (tmp_path / "trimmed.wav").exists()


@needs_ffmpeg
def test_trim_tail_over_eight_seconds_stops(tmp_path):
    src, prepped = tmp_path / "v.wav", tmp_path / "prepped.wav"
    write_wav(src, SPEECH + [("gap", 0.6), ("tone", 9.0), ("gap", 0.3)])
    audio.prep_voice(src, prepped)
    with pytest.raises(audio.TailTrimNeedsConfirmation):
        audio.trim_tail_if_needed(prepped, 4.8, tmp_path / "t.wav", log=print)
    out, plan = audio.trim_tail_if_needed(
        prepped, 4.8, tmp_path / "t.wav", log=lambda _: None, allow_long=True
    )
    assert plan.cut_seconds > 8 and out.exists()


# ---------------------------------------------------------------- chọn đoạn nhạc
@needs_ffmpeg
def test_music_start_skips_quiet_intro(tmp_path):
    f = tmp_path / "m.wav"
    write_wav(f, [("tone", 5, 0.02), ("tone", 20, 0.4)])
    assert audio.pick_music_start(f, video_total=10) == 5.0


@needs_ffmpeg
def test_music_start_never_before_two_seconds(tmp_path):
    f = tmp_path / "m.wav"
    write_wav(f, [("tone", 20, 0.4)])
    assert audio.pick_music_start(f, video_total=10) == 2.0


@needs_ffmpeg
def test_music_start_moves_back_when_too_short(tmp_path):
    f = tmp_path / "m.wav"
    write_wav(f, [("tone", 5, 0.02), ("tone", 10, 0.4)])  # còn 10 s kể từ giây 5, video 12 s
    assert audio.pick_music_start(f, video_total=12) == pytest.approx(3.0)
    assert audio.pick_music_start(f, video_total=40) == 0.0


# ---------------------------------------------------------------- trộn âm thanh
@needs_ffmpeg
def test_mix_with_music_and_whoosh(tmp_path):
    voice, music, whoosh = tmp_path / "v.wav", tmp_path / "m.wav", tmp_path / "w.wav"
    total = write_wav(voice, SPEECH + [("gap", 6.0)])
    write_wav(music, [("tone", 30, 0.4)], freq=220)
    audio.synth_whoosh(whoosh)
    assert media_duration(whoosh) == pytest.approx(0.7, abs=0.05)
    out = tmp_path / "mix.wav"
    audio.mix_audio(voice, music, 2.0, total, out, tmp_path, sfx=[(whoosh, 1.0, audio.WHOOSH_VOL)])
    s = stream(out)
    assert s["channels"] == 2 and int(s["sample_rate"]) == 44100
    assert media_duration(out) == pytest.approx(total, abs=0.05)
    # Tín hiệu giả rất thưa nên loudnorm một lượt chưa chạm đúng −14 (độ lớn thật: golden test).
    assert measure_lufs(out) == pytest.approx(-14.0, abs=2.5)


@needs_ffmpeg
def test_mix_music_is_ducked_under_voice(tmp_path):

    voice, music = tmp_path / "v.wav", tmp_path / "m.wav"
    # 4 s giọng rồi 8 s im lặng (cửa sổ đo nằm trước đoạn nhạc mờ ra ở 2,5 s cuối);
    # nhạc liên tục → lúc có giọng nhạc phải nhỏ hơn lúc chỉ có nhạc.
    total = write_wav(voice, [("gap", 0.2), ("tone", 3.8), ("gap", 8.0)])
    write_wav(music, [("tone", 30, 0.4)], freq=220)
    out = tmp_path / "mix.wav"
    audio.mix_audio(voice, music, 0.0, total, out, tmp_path)
    during, after = tmp_path / "during.wav", tmp_path / "after.wav"
    run_ffmpeg(["-i", out, "-ss", "2.0", "-t", "1.5", during])
    run_ffmpeg(["-i", out, "-ss", "7.5", "-t", "1.5", after])

    # Chỉ so phần nhạc: lọc hẹp quanh 220 Hz, loại 440 Hz của giọng giả.
    def music_level(p):
        f = tmp_path / ("f_" + p.name)
        run_ffmpeg(["-i", p, "-af", "bandpass=f=220:width_type=h:width=60", f])
        return measure_lufs(f)

    # loudnorm tổng làm gain chuyển chậm nên chênh khoảng 3 dB; chỉ cần chứng tỏ có ducking.
    assert music_level(during) < music_level(after) - 2


@needs_ffmpeg
def test_mix_without_music_is_stereo_minus_14(tmp_path):
    voice = tmp_path / "v.wav"
    total = write_wav(voice, SPEECH + [("gap", 1.6)])
    out = tmp_path / "mix.wav"
    audio.mix_audio(voice, None, 0.0, total, out, tmp_path)
    assert stream(out)["channels"] == 2
    assert media_duration(out) == pytest.approx(total, abs=0.05)
    assert measure_lufs(out) == pytest.approx(-14.0, abs=1.0)


# ---------------------------------------------------------------- outro
@needs_ffmpeg
def test_synth_ting_matches_the_recorded_parameters(tmp_path):
    out = tmp_path / "ting.wav"
    audio.synth_ting(out)
    s = stream(out)
    assert s["channels"] == 2 and int(s["sample_rate"]) == 44100
    assert media_duration(out) == pytest.approx(0.9, abs=0.03)
    # tắt dần exp(−5t): đoạn cuối nhỏ hơn hẳn đoạn đầu (so RMS, đoạn quá ngắn để đo LUFS)
    with wave.open(str(out)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    sr = 44100 * 2  # hai kênh xen kẽ
    first, last = data[: int(0.3 * sr)], data[-int(0.3 * sr) :]
    rms = lambda x: float(np.sqrt((x**2).mean()))  # noqa: E731
    assert rms(last) < rms(first) / 5


@needs_ffmpeg
def test_outro_audio_with_voice_is_4s_and_minus_14(tmp_path):
    voice = tmp_path / "ov.wav"
    write_wav(voice, [("tone", 2.65, 0.5)], freq=300)
    out = tmp_path / "outro.wav"
    measured = audio.build_outro_audio(voice, out, tmp_path)
    assert measured is not None
    assert media_duration(out) == pytest.approx(4.0, abs=0.03)
    assert stream(out)["channels"] == 2
    assert measure_lufs(out) == pytest.approx(-14.0, abs=1.0)


@needs_ffmpeg
def test_outro_audio_without_voice_still_builds(tmp_path):
    out = tmp_path / "outro.wav"
    assert audio.build_outro_audio(None, out, tmp_path) is None
    assert media_duration(out) == pytest.approx(4.0, abs=0.03)
    assert measure_lufs(out) < -14.0  # chỉ có tiếng ting, không bị kéo lên −14 LUFS


@needs_ffmpeg
@pytest.mark.slow
def test_outro_audio_length_is_deterministic(tmp_path):
    # Hồi quy: cách cũ (`apad=whole_dur`) đôi khi chỉ ra 2,05 s khi không có lời; dựng nhiều lần.
    voice = tmp_path / "ov.wav"
    write_wav(voice, [("tone", 2.65, 0.5)], freq=300)
    for i in range(6):
        work = tmp_path / f"w{i}"
        work.mkdir()
        for name, v in (("novoice", None), ("voice", voice)):
            out = work / f"{name}.wav"
            audio.build_outro_audio(v, out, work)
            assert media_duration(out) == pytest.approx(4.0, abs=0.03), (i, name)


@needs_ffmpeg
def test_join_audio_crossfades_half_second(tmp_path):
    body, outro, out = tmp_path / "b.wav", tmp_path / "o.wav", tmp_path / "j.wav"
    write_wav(body, [("tone", 6.0)])
    write_wav(outro, [("tone", 4.0)], freq=300)
    # acrossfade cần cùng số kênh: tạo stereo như bản thật

    b2, o2 = tmp_path / "b2.wav", tmp_path / "o2.wav"
    run_ffmpeg(["-i", body, "-ac", "2", b2])
    run_ffmpeg(["-i", outro, "-ac", "2", o2])
    assert audio.join_audio(b2, o2, out) == pytest.approx(6.0 + 4.0 - 0.5, abs=0.03)
