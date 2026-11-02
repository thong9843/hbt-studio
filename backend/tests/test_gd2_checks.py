"""Cảnh báo K16–K18 (IMPLEMENT-GD2 mục 3)."""

from hbt.gd2.checks import (
    check_prompts,
    check_sources_for_numbers,
    full_prompt,
    numbers_of,
    spoken_numbers,
)
from hbt.gd2.service import check_draft
from tests.gd2_kit import codes, sample

SRC = [{"id": "s1", "claim": "Muỗi phát hiện CO2 từ xa khoảng 10 m", "url": "u"}]


def test_numbers_normalised():
    assert numbers_of("tăng 27,6% và 1.000 người") == {"276", "1000"}
    assert spoken_numbers("Cao 10{mười} mét, nặng 2,5 kg") == ["10", "25"]
    assert spoken_numbers("100{một trăm} lần") == ["100"]


def test_k16_number_without_source():
    out = check_sources_for_numbers(["Muỗi bay xa 10{mười} mét.", "Sống 15 ngày."], SRC)
    assert codes(out) == ["K16"]
    assert out[0]["scene_index"] == 1 and "15" in out[0]["message"]


def test_k16_braces_ignored_and_no_substring_match():
    # chữ số chỉ nằm trong {…} thì không tính
    assert check_sources_for_numbers(["Ăn kem {1000} lần."], []) == []
    # 1 không khớp 10 (so theo số, không so chuỗi con)
    assert codes(check_sources_for_numbers(["Có 1 con muỗi."], SRC)) == ["K16"]
    # không nguồn nào, có số
    assert codes(check_sources_for_numbers(["Có 10 con."], [])) == ["K16"]
    # một số lặp lại chỉ báo một lần mỗi cảnh
    assert len(check_sources_for_numbers(["7 và 7 và 7."], [])) == 1


def test_k17_forbidden_words_word_boundary():
    warns, ok = check_prompts(
        [
            "a mosquito, add text on top",
            "context of a contextual map",
            "Vietnam map with pins",
            "bản đồ Việt Nam",
            "a calm lake, vertical 9:16",
        ]
    )
    by_scene = {w["scene_index"]: w["message"] for w in warns if w["code"] == "K17"}
    assert "text" in by_scene[0]
    assert by_scene[1].endswith("map")  # 'context' không bị bắt, 'map' thì có
    assert "vietnam map" in by_scene[2]
    assert "bản đồ" in by_scene[3]
    assert 4 not in by_scene and all(ok)


def test_k18_missing_or_empty():
    warns, ok = check_prompts([None, "", "  ", "ok prompt"])
    assert codes(warns) == ["K18", "K18", "K18"]
    assert ok == [False, False, False, True]


def test_full_prompt_appends_negative():
    assert full_prompt("a cat. ").endswith("no map, no Vietnam map")
    assert full_prompt("a cat").startswith("a cat. no text")


def test_draft_with_warnings_still_ok():
    d = sample()
    d["scenes"][0]["image_prompt"] = "hand holding a map"
    d["scenes"][1]["voice"] = "Muỗi sống 15 ngày."
    del d["scenes"][2]["image_prompt"]
    r = check_draft(d, None)
    assert r.ok
    assert {"K16", "K17", "K18"} <= set(codes(r.warnings))
    assert r.prompt_ok == [True, True, False]
