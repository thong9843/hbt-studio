import pytest

from hbt.pipeline.textmatch import compile_words, find_hits, fold
from hbt.sensitive import SensitiveWords


def words(*items, level="warn"):
    return compile_words(
        SensitiveWords.model_validate({"categories": [{"id": "t", "level": level, "words": items}]})
    )


def hits(text, *items):
    return [m.word for m in find_hits(text, words(*items))]


def test_bia_is_caught_but_not_bia_with_accent():
    assert hits("Uống bia hơi", "bia") == ["bia"]
    assert hits("Cuốn sách có bìa đẹp", "bia") == []
    assert hits("Trang bìa và bia", "bia") == ["bia"]


@pytest.mark.parametrize("text", ["BIA", "Bia", "bIa"])
def test_case_insensitive(text):
    assert hits(text, "bia") == ["bia"]


def test_nfd_text_matches_nfc_keyword():
    assert hits("say xỉn", "say xỉn") == ["say xỉn"]  # hỏi gõ rời dấu
    assert hits("say xĩn", "say xỉn") == []  # ngã ≠ hỏi: không nhầm dấu
    assert hits("nhậu", "nhậu") == ["nhậu"]  # dấu mũ + nặng gõ rời
    assert hits("ma tuý", "ma tuý") == ["ma tuý"]


def test_word_boundaries():
    assert hits("biaxit", "bia") == []
    assert hits("nhà bia, quán", "bia") == ["bia"]
    assert hits("(bia)", "bia") == ["bia"]
    assert hits("bia…", "bia") == ["bia"]
    assert hits("súng", "súng") == ["súng"]
    assert hits("súng ống", "súng") == ["súng"]
    assert hits("vũ khí súng_hơi", "súng") == []  # gạch dưới là ký tự chữ


def test_multiword_phrases_and_whitespace():
    assert hits("Hoàng  Sa\nvà Trường Sa", "hoàng sa", "trường sa") == ["hoàng sa", "trường sa"]
    assert hits("đổ máu me", "máu me") == ["máu me"]
    assert hits("máu", "máu me") == []


@pytest.mark.parametrize(
    ("text", "keyword"),
    [
        ("hóa chất", "hoá chất"),
        ("hoá chất", "hóa chất"),
        ("ma túy", "ma tuý"),
        ("ma tuý", "ma túy"),
        ("thủy", "thuỷ"),
        ("thuỷ", "thủy"),
        ("khỏe", "khoẻ"),
        ("khoẻ", "khỏe"),
    ],
)
def test_tone_placement_variants_match_in_both_directions(text, keyword):
    assert hits(text, keyword) == [keyword]


def test_tone_placement_does_not_merge_different_words():
    assert fold("hóa") == fold("hoá")
    assert fold("quý") == "quý"  # u của "qu" không phải nguyên âm: dấu ở y giữ nguyên
    assert fold("hòa") == fold("hoà")
    assert fold("hòa") != fold("hóa")  # huyền ≠ sắc
    assert hits("xóa", "xoá") == ["xoá"]
    assert hits("xoa", "xoá") == []


def test_variant_inside_a_longer_word_is_not_a_match():
    assert hits("hóa chất độc", "hoá chất") == ["hoá chất"]
    assert hits("hóachất", "hoá chất") == []


def test_each_keyword_reported_once_even_if_repeated():
    assert hits("bia bia bia", "bia") == ["bia"]


def test_matcher_keeps_category_level_and_hint():
    sw = SensitiveWords.model_validate(
        {"categories": [{"id": "map", "level": "block", "words": ["bản đồ"], "hint": "xem lại"}]}
    )
    (m,) = find_hits("Tấm bản đồ", compile_words(sw))
    assert (m.word, m.category, m.level, m.hint) == ("bản đồ", "map", "block", "xem lại")
