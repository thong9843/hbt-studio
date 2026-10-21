import pytest

from hbt.pipeline import text
from hbt.pipeline.text import parse_voice


def disp(tokens):
    return [t["disp"] for t in tokens]


def test_pipe_starts_a_new_chunk():
    tokens = parse_voice("Ngồi cùng | một phòng")
    assert disp(tokens) == ["Ngồi", "cùng", "một", "phòng"]
    assert [t["chunk_start"] for t in tokens] == [True, False, True, False]


def test_punctuation_ends_phrase_and_starts_chunk():
    tokens = parse_voice("Một hai. Ba bốn, năm sáu?")
    assert [t["phrase_end"] for t in tokens] == [False, True, False, True, False, True]
    assert [t["chunk_start"] for t in tokens] == [True, False, True, False, True, False]
    assert [t["sentence_end"] for t in tokens] == [False, True, False, False, False, True]


def test_braces_with_spaces_stay_one_token():
    tokens = parse_voice("gấp 100{một trăm} lần")
    assert disp(tokens) == ["gấp", "100", "lần"]
    assert tokens[1]["syl"] == ["mot", "tram"]


def test_braces_keep_trailing_punctuation_for_display():
    tokens = parse_voice("Comment{com men}, cho mình")
    assert tokens[0]["disp"] == "Comment,"
    assert tokens[0]["syl"] == ["com", "men"]
    assert tokens[0]["phrase_end"] is True and tokens[1]["chunk_start"] is True


def test_number_without_spoken_form_is_still_matched():
    (tok,) = parse_voice("100")
    assert tok["disp"] == "100" and tok["syl"] == ["100"]


def test_symbol_only_token_gets_placeholder_syllable():
    (tok,) = parse_voice("—")
    assert tok["syl"] == ["_"]


def test_unclosed_brace_does_not_swallow_the_text():
    tokens = parse_voice("a {b c")
    assert disp(tokens) == ["a", "{b", "c"]


def test_pipe_inside_braces_is_not_a_separator():
    assert disp(parse_voice("x{a | b} y")) == ["x", "y"]


@pytest.mark.parametrize(
    "raw, expected",
    [("Đường", "duong"), ("Hoàng Sa!", "hoangsa"), ("ĐÔ-thị 2", "dothi2"), ("", "")],
)
def test_norm_strips_diacritics_and_symbols(raw, expected):
    assert text.norm(raw) == expected


def test_display_drops_trailing_comma_but_keeps_question_mark():
    assert text.display("khác,") == "khác"
    assert text.display("vậy?") == "vậy?"
    assert text.display("lần.") == "lần"


def test_weight_grows_with_syllables_and_phrase_end():
    short, long_, end = (parse_voice(w)[0] for w in ("ba", "ba{ba ba ba}", "ba."))
    assert text.weight(long_) > text.weight(short)
    assert text.weight(end) == pytest.approx(text.weight(short) + 0.35)
