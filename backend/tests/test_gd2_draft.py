"""JSON nháp `hbt_draft: 1`: tách trường và K13–K15 (IMPLEMENT-GD2 mục 2, 3)."""

import json

from hbt.gd2.draft import split_draft
from hbt.gd2.service import check_draft
from hbt.script import parse_script
from tests.gd2_kit import SAMPLE, codes, sample


def test_sample_is_valid_and_splits():
    s = split_draft(sample())
    assert s.errors == []
    assert s.topic.startswith("Vì sao muỗi")
    assert s.series_hint == "Vì sao…" and s.music_mood == "tò mò"
    assert s.sources[0]["id"] == "s1"
    assert len(s.prompts) == 3 and s.prompts[1].startswith("person breathing")
    # phần còn lại là khối hbt_script hợp lệ của M5 (không còn trường nháp)
    assert s.script["hbt_script"] == 1
    assert "topic" not in s.script and "hbt_draft" not in s.script and "sources" not in s.script
    assert all("image_prompt" not in sc for sc in s.script["scenes"])
    script, issues = parse_script(s.script)
    assert issues == [] and script is not None


def test_string_input_and_k1_with_line_col():
    assert split_draft(json.dumps(SAMPLE, ensure_ascii=False)).errors == []
    bad = split_draft('{\n  "hbt_draft": 1,\n  "topic": \n}')
    assert codes(bad.errors) == ["K1"] and "dòng" in bad.errors[0]["message"]
    assert bad.script is None


def test_k13_version_and_topic():
    assert "K13" in codes(split_draft(sample(hbt_draft=2)).errors)
    assert "K13" in codes(split_draft(sample(hbt_draft=True)).errors)
    d = sample()
    del d["hbt_draft"]
    assert "K13" in codes(split_draft(d).errors)
    assert "K13" in codes(split_draft(sample(topic="  ")).errors)
    d = sample()
    del d["topic"]
    assert "K13" in codes(split_draft(d).errors)
    assert codes(split_draft([1, 2]).errors) == ["K13"]


def test_k14_sources_shape():
    def errs(sources):
        return split_draft(sample(sources=sources)).errors

    assert errs([]) == []
    assert codes(errs("s1")) == ["K14"]
    assert "K14" in codes(errs(["s1"]))
    assert "K14" in codes(errs([{"id": "s1", "claim": "x"}]))  # thiếu url
    assert "K14" in codes(errs([{"id": "s1", "claim": " ", "url": "u"}]))
    dup = [{"id": "s1", "claim": "a", "url": "u"}, {"id": "s1", "claim": "b", "url": "v"}]
    assert any("trùng" in e["message"] for e in errs(dup))


def test_k15_types():
    assert codes(split_draft(sample(music_mood=5)).errors) == ["K15"]
    assert codes(split_draft(sample(series_hint=[])).errors) == ["K15"]
    d = sample()
    d["scenes"][1]["image_prompt"] = 7
    errs = split_draft(d).errors
    assert codes(errs) == ["K15"] and errs[0]["scene_index"] == 1


def test_missing_prompt_is_not_an_error_here():
    d = sample()
    del d["scenes"][0]["image_prompt"]
    s = split_draft(d)
    assert s.errors == [] and s.prompts[0] is None


def test_unknown_key_is_k4():
    d = sample()
    d["scenes"][0]["pucnh"] = True
    r = check_draft(d, None)
    assert not r.ok and "K4" in codes(r.errors)
    d = sample(music={"file": "x.mp3"})  # trường cấm của M5
    assert "K4" in codes(check_draft(d, None).errors)
    d = sample(color="red")  # khoá lạ ở gốc
    assert "K4" in codes(check_draft(d, None).errors)


def test_check_draft_ok_for_sample():
    r = check_draft(sample(), None)
    assert r.ok and r.script_check is not None and r.script_check.counts["after"] == 3
    assert codes(r.warnings) == []
    assert r.to_dict()["scenes"] == 3 and r.to_dict()["music_match"] is None


def test_scene_count_out_of_range_is_k2():
    d = sample()
    d["scenes"] = d["scenes"][:2]
    r = check_draft(d, None)
    assert "K2" in codes(r.errors)
    d["scenes"] = d["scenes"] * 5  # 10 cảnh: hợp lệ
    assert check_draft(d, None).ok
    d["scenes"] = d["scenes"] * 2  # 20 cảnh
    assert "K2" in codes(check_draft(d, None).errors)


def test_m5_rules_still_apply():
    d = sample()
    d["scenes"][0]["card"]["lines"][0]["size"] = "huge"
    assert "K3" in codes(check_draft(d, None).errors)
    d = sample()
    d["scenes"][0]["voice"] = "x" * 800
    assert "K9" in codes(check_draft(d, None).warnings)
    assert "K11" in codes(
        check_draft(sample(thumbnail={"scene": 9, "lines": ["A", "B"]}), None).errors
    )


def test_nfc_normalised():
    d = sample(topic="Muỗi")  # chữ tổ hợp
    assert split_draft(d).topic == "Muỗi"
