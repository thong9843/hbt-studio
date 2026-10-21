import pytest
from PIL import Image

from hbt.pipeline import captions
from hbt.pipeline.captions import Phrase
from hbt.pipeline.text import parse_voice

YELLOW = (255, 212, 59, 255)


def tokens_of(*voices):
    tokens, scene_of = [], []
    for si, v in enumerate(voices):
        ts = parse_voice(v)
        tokens += ts
        scene_of += [si] * len(ts)
    return tokens, scene_of


def even_times(n, step=0.4, t0=1.0):
    return [(t0 + i * step, t0 + i * step + step * 0.9) for i in range(n)]


# ---------------------------------------------------------------- chia cụm
def test_phrases_follow_pipe_and_punctuation():
    tokens, scene_of = tokens_of("Một hai | ba bốn năm. Sáu bảy")
    groups = captions.split_phrases(tokens, scene_of)
    assert [[tokens[i]["disp"] for i in g] for g in groups] == [
        ["Một", "hai"],
        ["ba", "bốn", "năm."],
        ["Sáu", "bảy"],
    ]


def test_phrase_never_crosses_scene_boundary():
    tokens, scene_of = tokens_of("Một hai", "ba bốn")  # không có dấu câu giữa hai cảnh
    groups = captions.split_phrases(tokens, scene_of)
    assert len(groups) == 2
    assert {scene_of[i] for g in groups for i in g[:1]} == {0, 1}


@pytest.mark.parametrize("n, sizes", [(7, [7]), (8, [4, 4]), (9, [5, 4]), (15, [4, 4, 7])])
def test_long_phrases_are_halved(n, sizes):
    tokens, scene_of = tokens_of(" ".join(f"t{i}" for i in range(n)))
    groups = captions.split_phrases(tokens, scene_of)
    assert [len(g) for g in groups] == sizes
    assert all(len(g) <= captions.MAX_TOKENS for g in groups)
    assert [i for g in groups for i in g] == list(range(n))  # đủ và đúng thứ tự


# ---------------------------------------------------------------- thời điểm
def test_close_next_phrase_keeps_current_until_next_appears():
    tokens, scene_of = tokens_of("Một hai | ba bốn")
    times = [(1.0, 1.3), (1.4, 1.8), (2.1, 2.4), (2.5, 2.9)]  # khoảng cách 0,3 s < 0,6 s
    p1, p2 = captions.build_phrases(tokens, times, scene_of)
    assert p1.start == pytest.approx(1.0 - captions.LEAD)
    assert p1.end == pytest.approx(2.1 - captions.LEAD)  # đến lúc cụm sau hiện, không chồng
    assert p2.start == pytest.approx(2.1 - captions.LEAD)


def test_far_next_phrase_holds_a_quarter_second():
    tokens, scene_of = tokens_of("Một hai | ba bốn")
    times = [(1.0, 1.3), (1.4, 1.8), (3.0, 3.3), (3.4, 3.8)]  # khoảng cách 1,2 s ≥ 0,6 s
    p1, p2 = captions.build_phrases(tokens, times, scene_of)
    assert p1.end == pytest.approx(1.8 + captions.HOLD)
    assert p2.end == pytest.approx(3.8 + captions.HOLD)  # cụm cuối luôn giữ 0,25 s


def test_word_lights_from_its_start_to_next_word_start():
    tokens, scene_of = tokens_of("Một hai ba")
    times = [(1.0, 1.2), (1.5, 1.7), (2.0, 2.4)]
    (p,) = captions.build_phrases(tokens, times, scene_of)
    assert p.states == [
        (pytest.approx(0.95), pytest.approx(1.0), -1),
        (pytest.approx(1.0), pytest.approx(1.5), 0),
        (pytest.approx(1.5), pytest.approx(2.0), 1),
        (pytest.approx(2.0), pytest.approx(2.4 + captions.HOLD), 2),
    ]


def test_start_is_clamped_at_zero_and_times_never_go_backwards():
    tokens, scene_of = tokens_of("Một hai")
    (p,) = captions.build_phrases(tokens, [(0.02, 0.2), (0.1, 0.3)], scene_of)  # chữ 2 "lùi"
    assert p.start == 0.0
    assert p.word_starts[1] >= p.word_starts[0]
    assert all(lo <= hi for lo, hi, _ in p.states)


# ---------------------------------------------------------------- vị trí
@pytest.mark.parametrize(
    "caption_y, bottom, expected",
    [
        (None, None, 1420),
        (None, 1100, 1420),
        (None, 1101, 230),
        (None, 600, 1420),
        (500, 1500, 500),
    ],
)
def test_caption_y(caption_y, bottom, expected):
    assert captions.caption_y_for(caption_y, bottom) == expected


# ---------------------------------------------------------------- vẽ và ghép
def phrase(words, states, scene=0):
    return Phrase(
        scene=scene,
        token_ids=list(range(len(words))),
        words=words,
        word_starts=[],
        first_start=0,
        last_end=0,
        start=states[0][0],
        end=states[-1][1],
        states=states,
    )


def test_render_states_timeline_is_gapless_and_cached(tmp_path):
    p1 = phrase(["Xin", "chào"], [(0.5, 1.0, -1), (1.0, 1.5, 0), (1.5, 2.0, 1)])
    p2 = phrase(["Tạm", "biệt"], [(3.0, 3.4, 0)])
    out = tmp_path / "caps"
    timeline = captions.render_states([p1, p2], [1420], out, total=5.0)
    assert sum(d for _, d in timeline) == pytest.approx(5.0)
    assert all(d > 0 for _, d in timeline)
    blank = out / "blank.png"
    assert timeline[0] == (blank, pytest.approx(0.5))  # trước cụm đầu: trong suốt
    assert timeline[-1][0] == blank and timeline[-1][1] == pytest.approx(5.0 - 3.4)

    pngs = {p for p, _ in timeline if p != blank}
    assert len(pngs) == 4  # 3 trạng thái cụm 1 + 1 trạng thái cụm 2
    for png in pngs | {blank}:
        with Image.open(png) as im:
            assert im.size == (1080, 1920) and im.mode == "RGBA"

    mtimes = {p: p.stat().st_mtime_ns for p in pngs}
    captions.render_states([p1, p2], [1420], out, total=5.0)
    assert {p: p.stat().st_mtime_ns for p in pngs} == mtimes  # không vẽ lại


def test_highlight_only_when_a_word_is_active(tmp_path):
    p = phrase(["Xin", "chào"], [(0.0, 0.1, -1), (0.1, 0.6, 0)])
    timeline = captions.render_states([p], [1420], tmp_path, total=0.6)
    idle, active = (Image.open(path).convert("RGBA") for path, _ in timeline[:2])
    assert YELLOW not in {c for _, c in idle.getcolors(maxcolors=1_000_000)}
    assert YELLOW in {c for _, c in active.getcolors(maxcolors=1_000_000)}


def test_caption_y_changes_the_picture(tmp_path):
    p = phrase(["Xin", "chào"], [(0.0, 0.5, 0)])
    low = captions.render_states([p], [1420], tmp_path / "a", total=0.5)[0][0]
    high = captions.render_states([p], [230], tmp_path / "b", total=0.5)[0][0]
    assert Image.open(low).getbbox()[1] > 1000
    assert Image.open(high).getbbox()[3] < 600


def test_ffconcat_repeats_last_file(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "it's.png"
    timeline = [(a, 0.5), (b, 1.25)]
    f = tmp_path / "c.ffconcat"
    captions.write_ffconcat(timeline, f)
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "ffconcat version 1.0"
    assert lines[2] == "duration 0.500000" and lines[4] == "duration 1.250000"
    assert lines[3].endswith("it'\\''s.png'") and lines[5] == lines[3]
    assert "\\" not in lines[1].replace("\\'", "")  # đường dẫn dùng dấu /


def test_srt(tmp_path):
    p = phrase(["Xin", "chào!"], [(0.5, 1.0, -1), (1.0, 3725.123, 1)])
    f = tmp_path / "c.srt"
    captions.write_srt([p, p], f)
    text = f.read_text(encoding="utf-8")
    assert text.startswith("1\n00:00:00,500 --> 01:02:05,123\nXin chào!\n\n2\n")
