import pytest

from hbt.pipeline import align
from hbt.pipeline.text import parse_voice
from tests.helpers import needs_ffmpeg, write_wav

SCRIPT = "Một hai ba bốn. | Năm sáu bảy tám chín mười. | Mười một mười hai."


def segments_of(tokens, res, phrase_sizes):
    """Chia kết quả theo cụm để so với từng đoạn tiếng."""
    out, i = [], 0
    for n in phrase_sizes:
        out.append(res[i : i + n])
        i += n
    return out


@needs_ffmpeg
def test_align_silence_places_each_phrase_in_its_segment(tmp_path):
    wav = tmp_path / "v.wav"
    total = write_wav(
        wav,
        [("gap", 0.3), ("tone", 1.2), ("gap", 0.7), ("tone", 2.4), ("gap", 0.7), ("tone", 1.0)]
        + [("gap", 0.5)],
    )
    tokens = parse_voice(SCRIPT)
    res = align.align_silence(tokens, str(wav), total)
    groups = segments_of(tokens, res, [4, 6, 4])
    bounds = [(0.3, 1.5), (2.2, 4.6), (5.3, 6.3)]
    for grp, (s, e) in zip(groups, bounds, strict=True):
        assert grp[0][0] == pytest.approx(s, abs=0.1)
        assert grp[-1][1] == pytest.approx(e, abs=0.1)
        assert all(a < b for a, b in grp)
    flat = [x for g in groups for x in g]
    assert all(flat[i][1] <= flat[i + 1][0] + 1e-6 for i in range(len(flat) - 1))


@needs_ffmpeg
def test_silence_ex_drops_trailing_extra_segment(tmp_path):
    # Độ dài tiếng tỉ lệ với số âm tiết của từng cụm (như giọng thật).
    base = [("gap", 0.3), ("tone", 1.13), ("gap", 0.7), ("tone", 1.75), ("gap", 0.7)]
    base += [("tone", 1.21)]
    tokens = parse_voice(SCRIPT)

    clean = tmp_path / "clean.wav"
    total = write_wav(clean, base + [("gap", 0.5)])
    _, dropped = align.align_silence_ex(tokens, str(clean), total)
    assert dropped == 0

    # Đoạn thừa dài 4 s sau câu cuối (quảng cáo) → bị bỏ, câu cuối không bị kéo dài sang đó.
    ad = tmp_path / "ad.wav"
    total = write_wav(ad, base + [("gap", 0.8), ("tone", 4.0), ("gap", 0.5)])
    res, dropped = align.align_silence_ex(tokens, str(ad), total)
    assert dropped == 1
    assert res[-1][1] == pytest.approx(0.3 + 1.13 + 0.7 + 1.75 + 0.7 + 1.21, abs=0.1)


@needs_ffmpeg
def test_silence_ex_never_drops_when_segments_do_not_outnumber_phrases(tmp_path):
    # 3 cụm nhưng giọng chỉ có 2 đoạn (hai cụm liền nhau không nghỉ): không có đoạn "dư" để bỏ,
    # dù bỏ đoạn cuối có thể cho chi phí thấp hơn. Hồi quy từ tập "muỗi" (22 cụm / 20 đoạn).
    wav = tmp_path / "v.wav"
    total = write_wav(wav, [("gap", 0.3), ("tone", 2.9), ("gap", 0.7), ("tone", 1.2), ("gap", 0.5)])
    tokens = parse_voice(SCRIPT)
    res, dropped = align.align_silence_ex(tokens, str(wav), total)
    assert dropped == 0
    assert res[-1][1] == pytest.approx(0.3 + 2.9 + 0.7 + 1.2, abs=0.1)  # câu cuối vẫn còn


def test_split_phrases_follows_punctuation():
    tokens = parse_voice("Một hai. Ba bốn năm, sáu")
    assert align.split_phrases(tokens) == [[0, 1], [2, 3, 4], [5]]


@needs_ffmpeg
def test_silence_ex_without_drop_matches_reference_behaviour(tmp_path):
    wav = tmp_path / "v.wav"
    total = write_wav(
        wav, [("gap", 0.3), ("tone", 1.2), ("gap", 0.7), ("tone", 2.4), ("gap", 0.7), ("tone", 1.0)]
    )
    tokens = parse_voice(SCRIPT)
    assert align.align_silence_ex(tokens, str(wav), total, max_drop=0)[0] == align.align_silence(
        tokens, str(wav), total
    )


def test_align_whisper_matches_and_interpolates(monkeypatch):
    tokens = parse_voice("Xin chào các bạn. | Tôi là Thong.")
    # Whisper "nghe" thiếu âm tiết "cac" và "toi" → phải nội suy giữa hai điểm neo.
    heard = [
        ("xin", 0.5, 0.8),
        ("chao", 0.8, 1.1),
        ("ban", 1.6, 2.0),
        ("la", 3.0, 3.2),
        ("thong", 3.2, 3.8),
    ]
    monkeypatch.setattr(align, "whisper_syllables", lambda wav, prompt, size="large-v3": heard)
    res = align.align_whisper(tokens, "ignored.wav")
    assert len(res) == len(tokens) == 7
    assert res[0] == (0.5, 0.8)  # "Xin"
    assert res[1] == (0.8, 1.1)  # "chào"
    assert res[2][0] >= 1.1 and res[2][1] <= 1.6  # "các" nội suy giữa chào và bạn
    assert res[3] == (1.6, 2.0)  # "bạn."
    assert res[-1] == (3.2, 3.8)  # "Thong."
    assert all(a <= b for a, b in res)


def test_align_whisper_without_speech_raises(monkeypatch):
    monkeypatch.setattr(align, "whisper_syllables", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="Whisper"):
        align.align_whisper(parse_voice("Xin chào."), "x.wav")


def test_align_auto_falls_back_to_silence(monkeypatch):
    calls = []

    def boom(*a, **k):
        raise ModuleNotFoundError("faster_whisper")

    monkeypatch.setattr(align, "align_whisper", boom)
    monkeypatch.setattr(align, "align_silence", lambda t, w, total: calls.append("silence") or [])
    logs = []
    align.align([], "x.wav", 1.0, method="auto", log=logs.append)
    assert calls == ["silence"]
    assert "ModuleNotFoundError" in logs[0]
    with pytest.raises(ModuleNotFoundError):
        align.align([], "x.wav", 1.0, method="whisper", log=logs.append)
