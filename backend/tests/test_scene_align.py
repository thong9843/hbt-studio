import pytest

from hbt.pipeline import scene_align
from hbt.pipeline.scene_align import AlignError, align_scenes, decide_tail, match_scenes
from hbt.pipeline.text import parse_voice
from tests.helpers import needs_ffmpeg, write_wav

ONE = "Xin chào các bạn."  # 1 cụm, trọng số ≈ 6,1
K = 0.16  # giây tiếng nói ứng với 1 đơn vị trọng số (khớp với ONE ≈ 1,0 s)
FIVE = "Một hai. Ba bốn. Năm sáu. Bảy tám. Chín mười."  # 5 cụm, mỗi cụm ≈ 0,5 s


def tokens_of(*voices):
    tokens, scene_of = [], []
    for si, v in enumerate(voices):
        ts = parse_voice(v)
        tokens += ts
        scene_of += [si] * len(ts)
    return tokens, scene_of


def timeline(parts, tmp_path, name="v.wav"):
    """parts: [("tone"|"gap", giây)] → (đường dẫn, tổng giây, [(đầu, cuối)] của các đoạn tone)."""
    wav = tmp_path / name
    total = write_wav(wav, parts)
    t, spans = 0.0, []
    for kind, dur, *_ in parts:
        if kind == "tone":
            spans.append((t, t + dur))
        t += dur
    return str(wav), total, spans


# ---------------------------------------------------------------- cấp 1
def test_match_scenes_assigns_consecutive_groups():
    # cảnh 2 dài gấp đôi nên nhận 2 đoạn (1,0 s + 1,0 s) thay vì một đoạn 0,5 s
    segs = [(0.0, 1.0), (1.5, 2.5), (3.0, 4.0), (4.5, 5.5)]
    cost, assign = match_scenes([6.0, 12.0, 6.0], [1, 2, 1], segs)
    assert assign == [(0, 1), (1, 2), (3, 1)]
    assert cost < 0.1


@pytest.mark.parametrize("long_after", [1, 2])
def test_match_scenes_prefers_a_long_pause_at_a_sentence_end(long_after):
    # 5 đoạn bằng nhau, 2 cảnh bằng nhau: hai cách chia (2+3 hoặc 3+2) có chi phí thời lượng
    # như nhau; khoảng nghỉ dài quyết định ranh giới nằm ở đâu.
    gaps = [0.3, 0.3, 0.3, 0.3]
    gaps[long_after] = 0.55
    segs, t = [], 0.0
    for g in [*gaps, 0]:
        segs.append((t, t + 1.0))
        t += 1.0 + g
    _, assign = match_scenes([12.0, 12.0], [2, 2], segs, ends_sentence=[True, True])
    assert assign[0][1] == long_after + 1  # cảnh đầu kết thúc ngay trước khoảng nghỉ dài
    # không có thông tin dấu câu thì không có ưu tiên (hành vi cũ)
    assert match_scenes([12.0, 12.0], [2, 2], segs)[1][0][1] in (2, 3)


def test_match_scenes_ignores_pauses_when_scene_does_not_end_a_sentence():
    segs = [(0.0, 1.0), (1.3, 2.3), (2.85, 3.85), (4.15, 5.15), (5.45, 6.45)]
    a = match_scenes([12.0, 12.0], [2, 2], segs, ends_sentence=[False, False])[1]
    b = match_scenes([12.0, 12.0], [2, 2], segs)[1]
    assert a == b


def test_match_scenes_needs_a_segment_per_scene():
    with pytest.raises(AlignError, match="3 cảnh"):
        match_scenes([6.0, 6.0, 6.0], [1, 1, 1], [(0, 1), (2, 3)])


# ------------------------------------------------------------ quyết định cắt đuôi (không FFmpeg)
SEGS = [(0.0, 1.0), (1.5, 2.5), (3.0, 5.0)]  # đoạn cuối dài 2,0 s


@pytest.mark.parametrize(
    "costs, segs, guard, expected",
    [
        ({0: 3.0, 1: 1.8}, SEGS, 1, 1),  # giảm 1,2 và đoạn cuối 2,0 s → tự cắt
        ({0: 3.0, 1: 2.0}, SEGS, 1, 1),  # giảm đúng 1,0 → vẫn cắt
        ({0: 3.0, 1: 2.1}, SEGS, 1, 0),  # giảm 0,9 → giữ + cảnh báo
        ({0: 3.0, 1: 1.0}, [(0, 1), (1.5, 2.5), (3.0, 4.0)], 1, 0),  # đoạn cuối 1,0 s < 1,5 s
        ({0: 3.0, 1: 3.5}, SEGS, 1, 0),  # bỏ làm xấu đi → giữ, không cảnh báo
        ({0: 3.0}, SEGS, 0, 0),  # điều kiện bảo vệ: không có đoạn dư
    ],
)
def test_decide_tail_conditions(costs, segs, guard, expected):
    drop, warning = decide_tail(costs, segs, guard)
    assert drop == expected
    if expected:
        assert warning is None


def test_decide_tail_warning_text_and_cases():
    _, warn = decide_tail({0: 3.0, 1: 2.1}, SEGS, 1)
    assert warn == "Có thể có đoạn thừa ở cuối file giọng (2,00 giây), chưa cắt"
    assert decide_tail({0: 3.0, 1: 3.5}, SEGS, 1) == (0, None)
    assert decide_tail({0: 3.0}, SEGS, 0) == (0, None)
    # nhiều đoạn: chọn phương án rẻ nhất, độ dài cảnh báo tính từ đoạn bị bỏ đầu tiên
    drop, _ = decide_tail({0: 4.0, 1: 3.0, 2: 1.5}, SEGS, 2)
    assert drop == 2


# ---------------------------------------------------------------- căn 2 cấp (cần FFmpeg)
@needs_ffmpeg
def test_scene_with_five_phrases_but_three_clear_segments(tmp_path):
    """8 cảnh; cảnh 5 có 5 cụm nhưng chỉ 3 đoạn tiếng rõ ràng (nghỉ 0,2 s < 0,25 s ở giữa)."""
    scenes = [ONE] * 4 + [FIVE] + [ONE] * 3
    tokens, scene_of = tokens_of(*scenes)
    phrase = 0.5
    parts = [("gap", 0.3)]
    for si in range(8):
        if si != 4:
            parts += [("tone", 1.0), ("gap", 0.8)]
            continue
        parts += [("tone", phrase), ("gap", 0.7)]  # p1
        parts += [("tone", phrase), ("gap", 0.2), ("tone", phrase), ("gap", 0.7)]  # p2 + p3
        parts += [("tone", phrase), ("gap", 0.2), ("tone", phrase), ("gap", 0.8)]  # p4 + p5
    wav, total, _ = timeline(parts, tmp_path)

    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 0 and res.warning is None
    assert res.refined_scenes == [4]  # chỉ cảnh 5 phải hạ ngưỡng khoảng lặng

    ids5 = [i for i, s in enumerate(scene_of) if s == 4]
    scene_start = 0.3 + 4 * 1.8
    c_end = scene_start + (phrase + 0.7) + (2 * phrase + 0.2 + 0.7) + (2 * phrase + 0.2)
    last_phrase = [i for i in ids5 if tokens[i]["disp"] in ("Chín", "mười.")]
    assert res.times[last_phrase[0]][0] == pytest.approx(c_end - phrase, abs=0.1)
    assert res.times[last_phrase[-1]][1] == pytest.approx(c_end, abs=0.1)
    first_phrase = [i for i in ids5 if tokens[i]["disp"] in ("Một", "hai.")]
    assert res.times[first_phrase[0]][0] == pytest.approx(scene_start, abs=0.1)
    ends = [res.times[i] for i in ids5]
    assert all(a <= b for a, b in ends)
    assert all(ends[i][1] <= ends[i + 1][0] + 1e-6 for i in range(len(ends) - 1))
    # mỗi cảnh còn lại bắt đầu đúng đoạn tone của nó
    for si in (0, 1, 2, 3):
        first = next(i for i, s in enumerate(scene_of) if s == si)
        assert res.times[first][0] == pytest.approx(0.3 + si * 1.8, abs=0.1)


@needs_ffmpeg
def test_clean_voice_is_never_cut(tmp_path):
    tokens, scene_of = tokens_of(ONE, ONE, ONE)
    parts = [("gap", 0.3), ("tone", 1.0), ("gap", 0.8), ("tone", 1.0), ("gap", 0.8)]
    wav, total, _ = timeline([*parts, ("tone", 1.0), ("gap", 0.5)], tmp_path)
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 0 and res.warning is None
    assert res.times[-1][1] == pytest.approx(0.3 + 1.0 + 0.8 + 1.0 + 0.8 + 1.0, abs=0.1)


@needs_ffmpeg
def test_long_last_segment_is_not_cut_when_it_is_real_speech(tmp_path):
    # đoạn cuối dài 2,6 s nhưng đúng là câu cuối của kịch bản: số đoạn = số cụm → bị chặn
    tokens, scene_of = tokens_of(ONE, ONE, "Hẹn gặp lại các bạn nhé trong video sau.")
    parts = [("gap", 0.3), ("tone", 1.0), ("gap", 0.8), ("tone", 1.0), ("gap", 0.8)]
    wav, total, _ = timeline([*parts, ("tone", 2.6), ("gap", 0.5)], tmp_path)
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 0
    assert res.times[-1][1] == pytest.approx(0.3 + 1.0 + 0.8 + 1.0 + 0.8 + 2.6, abs=0.1)


def eight_scenes_with_tail(tmp_path, tail):
    """8 cảnh, mỗi cảnh một cụm 1,0 s, rồi một đoạn `tail` giây ở cuối file."""
    tokens, scene_of = tokens_of(*[ONE] * 8)
    parts = [("gap", 0.3)]
    for _ in range(8):
        parts += [("tone", 1.0), ("gap", 0.8)]
    parts += [("tone", tail), ("gap", 0.4)] if tail else []
    wav, total, _ = timeline(parts, tmp_path)
    return tokens, scene_of, wav, total


@needs_ffmpeg
def test_three_second_tail_is_cut_when_conditions_hold(tmp_path):
    tokens, scene_of, wav, total = eight_scenes_with_tail(tmp_path, 3.0)
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 1 and res.warning is None
    assert res.times[-1][1] == pytest.approx(0.3 + 8 * 1.8 - 0.8, abs=0.1)


@needs_ffmpeg
def test_short_tail_is_kept_not_cut(tmp_path):
    tokens, scene_of, wav, total = eight_scenes_with_tail(tmp_path, 1.0)  # đuôi < 1,5 s
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 0


@needs_ffmpeg
def test_voice_without_tail_is_never_cut(tmp_path):
    tokens, scene_of, wav, total = eight_scenes_with_tail(tmp_path, 0)
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 0 and res.warning is None


@needs_ffmpeg
def test_tail_on_a_short_script_is_warned_not_cut(tmp_path):
    # 3 cảnh: chi phí chỉ giảm khoảng 0,5 (< 1,0) nên không tự cắt, chỉ cảnh báo
    tokens, scene_of = tokens_of(ONE, ONE, ONE)
    parts = [("gap", 0.3), ("tone", 1.0), ("gap", 0.8), ("tone", 1.0), ("gap", 0.8)]
    parts += [("tone", 1.0), ("gap", 0.9), ("tone", 3.0), ("gap", 0.4)]
    wav, total, _ = timeline(parts, tmp_path)
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.dropped == 0
    assert res.warning == "Có thể có đoạn thừa ở cuối file giọng (3,00 giây), chưa cắt"


@needs_ffmpeg
def test_fewer_segments_than_scenes_falls_back_to_finer_levels(tmp_path):
    # các cảnh nối liền nhau bằng khoảng nghỉ 0,2 s (< 0,25 s): thô chỉ có 1 đoạn cho 3 cảnh
    tokens, scene_of = tokens_of(ONE, ONE, ONE)
    parts = [("gap", 0.3), ("tone", 1.0), ("gap", 0.2), ("tone", 1.0), ("gap", 0.2), ("tone", 1.0)]
    wav, total, _ = timeline([*parts, ("gap", 0.5)], tmp_path)
    res = align_scenes(tokens, scene_of, wav, total)
    assert res.times[4][0] == pytest.approx(0.3 + 1.2, abs=0.15)  # cảnh 2 bắt đầu ở đoạn thứ hai


def test_levels_go_from_coarse_to_fine():
    durs = [d for d, _ in scene_align.LEVELS]
    noise = [float(n.removesuffix("dB")) for _, n in scene_align.LEVELS]
    assert durs == sorted(durs, reverse=True) and durs[0] == 0.25 and durs[-1] == 0.08
    assert noise == sorted(noise) and noise[0] == -38 and noise[-1] == -34
