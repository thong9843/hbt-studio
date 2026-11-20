"""Che từ nhạy cảm khi dựng PostV (docs/postv/IMPLEMENT-POSTV.md mục 6b)."""

import subprocess

import numpy as np
import pytest

from hbt.pipeline.ffutil import ffmpeg_exe, media_duration
from hbt.pipeline.text import parse_voice
from hbt.postv import censorfx as C
from hbt.postv.censor import compile_censor
from hbt.postv.censorfx import (
    BLEEP_VOL,
    bleep_sfx,
    censor_windows,
    find_token_runs,
    masked_tokens,
    mute_voice,
    synth_bleep,
    token_core,
)
from hbt.sensitive import SensitiveWords
from tests.helpers import SR, needs_ffmpeg, write_wav


def matchers(*words):
    data = {"categories": [{"id": "tuc", "label": "Tục", "level": "block", "words": list(words)}]}
    return compile_censor(SensitiveWords.model_validate(data))


def toks(*texts):
    tokens, scene_of = [], []
    for si, t in enumerate(texts):
        ts = parse_voice(t)
        tokens += ts
        scene_of += [si] * len(ts)
    return tokens, scene_of


def runs(texts, *words):
    tokens, scene_of = toks(*texts)
    found = find_token_runs(tokens, scene_of, matchers(*words))
    return [(tokens[a]["disp"], tokens[b]["disp"], w) for a, b, w in found]


def test_token_core_strips_punctuation_and_case():
    assert token_core("Đéo!") == "đéo" and token_core("(đéo),") == "đéo" and token_core("...") == ""


def test_single_word_match_has_diacritics_and_word_boundaries():
    assert runs(["Thằng này đéo biết gì"], "đéo") == [("đéo", "đéo", "đéo")]
    assert runs(["Tôi đeo kính"], "đéo") == []  # không dấu thì không trùng
    assert runs(["Đéo, thật à"], "đéo") == [("Đéo,", "Đéo,", "đéo")]
    assert runs(["đéoooo"], "đéo") == []  # không phải ranh giới từ


def test_multi_word_phrase_and_longest_first():
    assert runs(["Nó nói thế đ éo gì"], "đ éo") == [("đ", "éo", "đ éo")]
    got = runs(["chết mẹ mày rồi"], "mẹ", "chết mẹ")
    assert got == [("chết", "mẹ", "chết mẹ")]  # từ dài thắng, không che hai lần


def test_match_does_not_cross_segment_edges():
    assert runs(["Tôi nói chết", "mẹ nó"], "chết mẹ") == []


def times_for(n, step=0.5):
    return [(i * step, i * step + 0.4) for i in range(n)]


def test_windows_pad_clamp_and_merge():
    tokens, scene_of = toks("a b đéo c đéo đéo d")
    ws = censor_windows(tokens, scene_of, times_for(len(tokens)), matchers("đéo"), 3.4)
    assert len(ws) == 2  # hai từ gần nhau (khoảng nới chồng nhau) gộp thành một khoảng
    first, second = ws
    assert first.start == pytest.approx(1.0 - C.PAD) and first.end == pytest.approx(1.4 + C.PAD)
    assert second.start == pytest.approx(2.0 - C.PAD) and second.end == pytest.approx(2.9 + C.PAD)
    assert masked_tokens(ws) == {2, 4, 5}


def test_multi_word_window_spans_first_to_last_token():
    tokens, scene_of = toks("nói đ éo thật")
    (w,) = censor_windows(tokens, scene_of, times_for(4), matchers("đ éo"), 10.0)
    assert (w.start, w.end) == (pytest.approx(0.5 - C.PAD), pytest.approx(1.4 + C.PAD))
    assert w.token_ids == (1, 2) and w.word == "đ éo"


def test_window_never_starts_before_zero():
    tokens, scene_of = toks("đéo biết")
    (w,) = censor_windows(tokens, scene_of, times_for(2), matchers("đéo"), 5.0)
    assert w.start == 0.0


def test_no_matches_no_windows():
    tokens, scene_of = toks("câu hoàn toàn sạch")
    assert censor_windows(tokens, scene_of, times_for(4), matchers("đéo"), 5.0) == []
    assert censor_windows(tokens, scene_of, times_for(4), [], 5.0) == []


def read(path):
    raw = subprocess.run(
        [
            ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(SR),
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, "<i2").astype(float) / 32768


def rms(x):
    return float(np.sqrt((x**2).mean())) if len(x) else 0.0


@needs_ffmpeg
def test_mute_voice_silences_only_the_windows(tmp_path):
    src = tmp_path / "v.wav"
    write_wav(src, [("tone", 4.0, 0.5)])
    tokens, scene_of = toks("a đéo b")
    times = [(0.2, 0.6), (1.5, 2.0), (3.0, 3.5)]
    ws = censor_windows(tokens, scene_of, times, matchers("đéo"), 4.0)
    out = tmp_path / "m.wav"
    mute_voice(src, out, ws)
    x = read(out)
    w = ws[0]
    inside = x[int((w.start + 0.01) * SR) : int((w.end - 0.01) * SR)]
    assert rms(inside) == 0.0
    assert rms(x[: int(1.0 * SR)]) > 0.2 and rms(x[int(2.5 * SR) :]) > 0.2
    assert media_duration(out) == pytest.approx(4.0, abs=0.05)


@needs_ffmpeg
def test_bleep_has_exact_length_and_a_1khz_tone(tmp_path):
    out = tmp_path / "b.wav"
    synth_bleep(0.5, out)
    assert media_duration(out) == pytest.approx(0.5, abs=0.03)
    x = read(out)
    assert rms(x) > 0.3 and abs(x[:30]).max() < abs(x[2000:2100]).max()  # fade-in 5 ms
    spectrum = np.abs(np.fft.rfft(x))
    assert abs(np.argmax(spectrum) * SR / len(x) - 1000) < 20


@needs_ffmpeg
def test_one_bleep_per_window_at_the_window_start(tmp_path):
    tokens, scene_of = toks("a đéo b đéo c")
    ws = censor_windows(tokens, scene_of, times_for(5), matchers("đéo"), 5.0)
    sfx = bleep_sfx(ws, tmp_path)
    assert len(sfx) == 2
    assert [round(at, 3) for _, at, _ in sfx] == [round(w.start, 3) for w in ws]
    assert all(vol == BLEEP_VOL == 0.35 for _, _, vol in sfx)
    assert all(p.is_file() for p, _, _ in sfx)
