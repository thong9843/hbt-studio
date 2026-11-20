"""Phụ đề PostV: tách cụm 1–3 từ, trạng thái, che từ (docs/postv/IMPLEMENT-POSTV.md mục 6, 6b)."""

import numpy as np
from PIL import Image

from hbt.pipeline.text import parse_voice
from hbt.postv import captions as C
from hbt.postv.captions import (
    BAND,
    CapPhrase,
    build_phrases,
    render_state,
    render_states,
    split_short,
    style_for,
    write_srt,
)


def toks(*texts):
    tokens, scene_of = [], []
    for si, t in enumerate(texts):
        ts = parse_voice(t)
        tokens += ts
        scene_of += [si] * len(ts)
    return tokens, scene_of


def even_times(n, step=0.4):
    return [(i * step, i * step + step * 0.9) for i in range(n)]


def test_split_short_never_exceeds_three_words_and_splits_evenly():
    for n, expect in [(1, [1]), (3, [3]), (4, [2, 2]), (5, [3, 2]), (7, [3, 2, 2]), (9, [3, 3, 3])]:
        tokens, scene_of = toks(" ".join(["từ"] * n))
        assert [len(g) for g in split_short(tokens, scene_of)] == expect


def test_split_short_breaks_at_punctuation_and_segment_edges():
    tokens, scene_of = toks("Một hai, ba bốn năm.", "Sáu bảy")
    groups = split_short(tokens, scene_of)
    assert [[tokens[i]["disp"] for i in g] for g in groups] == [
        ["Một", "hai,"],
        ["ba", "bốn", "năm."],
        ["Sáu", "bảy"],
    ]


def test_phrases_have_monotone_times_and_a_state_per_word():
    tokens, scene_of = toks("Đây là câu thử nghiệm đầu tiên.")
    phrases = build_phrases(tokens, even_times(len(tokens)), scene_of)
    assert all(len(p.words) <= 3 for p in phrases)
    for p in phrases:
        assert p.start <= p.first_start <= p.last_end <= p.end
        acts = [s[2] for s in p.states]
        assert acts == sorted(acts) and acts[-1] == len(p.words) - 1 and acts[0] >= -1


def test_masked_flags_follow_token_ids():
    tokens, scene_of = toks("Một hai ba bốn")
    phrases = build_phrases(tokens, even_times(4), scene_of, masked_tokens={1})
    flags = [m for p in phrases for m in p.masked]
    assert flags == [False, True, False, False]


def test_style_presets_and_highlight_override():
    hbt, sample = style_for("hbt"), style_for("sample")
    assert hbt.active == (255, 212, 59) and not hbt.upper and hbt.y == 1400
    assert sample.upper and sample.active == (56, 225, 120) and sample.y == 1459
    assert sample.y <= 1500
    assert style_for("hbt", "#ff0000").active == (255, 0, 0)


def draw(tmp_path, words, act, masked=None, mode="blur", name="s.png", preset="hbt"):
    path = tmp_path / name
    render_state(words, act, masked or [False] * len(words), style_for(preset), mode, path)
    return np.asarray(Image.open(path))


def test_state_is_a_band_with_vietnamese_text_in_active_color(tmp_path):
    arr = draw(tmp_path, ["Nghiêm", "trọng", "quá"], 1)
    assert arr.shape == (BAND, 1080, 4)
    assert arr[..., 3].max() == 255
    visible = arr[arr[..., 3] == 255][:, :3]
    yellow = ((abs(visible.astype(int) - (255, 212, 59)).sum(axis=1)) < 30).sum()
    white = ((visible > 240).all(axis=1)).sum()
    assert yellow > 200 and white > 200  # từ đang đọc vàng, các từ khác trắng


def test_state_without_active_word_has_no_highlight_color(tmp_path):
    arr = draw(tmp_path, ["Một", "hai"], -1)
    visible = arr[arr[..., 3] == 255][:, :3]
    assert ((abs(visible.astype(int) - (255, 212, 59)).sum(axis=1)) < 30).sum() == 0


def test_uppercase_preset_draws_more_ink_than_lowercase(tmp_path):
    a = draw(tmp_path, ["đây", "là"], 0, name="a.png", preset="hbt")[..., 3].astype(bool).sum()
    b = draw(tmp_path, ["đây", "là"], 0, name="b.png", preset="sample")[..., 3].astype(bool).sum()
    assert a > 0 and b > 0 and a != b


def test_masked_word_is_blurred_and_stars_replace_it(tmp_path):
    plain = draw(tmp_path, ["đéo", "sao"], -1, name="p.png")
    blurred = draw(tmp_path, ["đéo", "sao"], -1, masked=[True, False], name="b.png")
    stars = draw(tmp_path, ["đéo", "sao"], -1, masked=[True, False], mode="stars", name="s.png")
    # chữ bị mờ: vùng bên trái khác bản rõ, và không còn pixel đặc kín quanh nét chữ
    left = slice(0, 540)
    assert (plain[:, left] != blurred[:, left]).any()
    assert (blurred[:, left, 3] == 255).sum() < (plain[:, left, 3] == 255).sum()
    assert (stars != plain).any() and (stars != blurred).any()
    right = slice(620, 1080)
    assert (plain[:, right] == blurred[:, right]).all()  # từ không che giữ nguyên


def test_timeline_covers_total_and_reuses_png_files(tmp_path):
    tokens, scene_of = toks("Một hai ba bốn năm sáu")
    phrases = build_phrases(tokens, even_times(6), scene_of)
    style = style_for("hbt")
    tl = render_states(phrases, style, "blur", tmp_path, 6.0)
    assert abs(sum(d for _, d in tl) - 6.0) < 1e-6
    files = {p for p, _ in tl}
    mtimes = {p: p.stat().st_mtime_ns for p in files}
    render_states(phrases, style, "blur", tmp_path, 6.0)
    assert {p: p.stat().st_mtime_ns for p in files} == mtimes
    assert all(Image.open(p).size == (1080, BAND) for p in files)


def test_srt_writes_stars_for_masked_words(tmp_path):
    p = CapPhrase(0, [0, 1], ["đéo", "sao"], [0.5, 1.0], 0.5, 1.6, 0.45, 1.9, [], [True, False])
    out = tmp_path / "c.srt"
    write_srt([p], out)
    text = out.read_text(encoding="utf-8")
    assert "*** sao" in text and "đéo" not in text and "00:00:00,450 --> 00:00:01,900" in text
    assert C.STARS == "***"
