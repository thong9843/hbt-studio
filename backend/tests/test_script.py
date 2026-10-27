"""Khối JSON kịch bản (IMPLEMENT.md 13.B4): đọc, gộp, kiểm K1–K12."""

from __future__ import annotations

import copy
import json
import unicodedata
from pathlib import Path

import pytest

from hbt.models import Project
from hbt.script import TEXT_W, check_script, parse_script
from hbt.sensitive import Category, SensitiveWords

DATA = Path(__file__).parent / "data"


def make_project(n: int = 4, **over) -> Project:
    data = {
        "slug": "thu",
        "title": "Thử",
        "series": "Hay Biết Tuốt",
        "scenes": [
            {
                "image": f"images/{i}.png",
                "voice": f"Lời cảnh {i + 1}.",
                "card": {"y": "top", "lines": [{"text": f"Cũ {i + 1}", "size": "m"}]},
                "labels": [{"text": "NHÃN", "x": 100, "y": 200}],
                "caption_y": 1300,
            }
            for i in range(n)
        ],
        "thumbnail": {"scene": 1, "lines": ["A", "B"]},
        "publish": {"hook": "cũ", "hashtags": ["cu"]},
    }
    data.update(over)
    return Project.model_validate(data)


def scene(text: str = "Mới", size: str = "m", **kw) -> dict:
    return {"card": {"y": "upper", "lines": [{"text": text, "size": size, "color": "ink"}]}, **kw}


def codes(items: list[dict]) -> list[str]:
    return [i["code"] for i in items]


def run(raw, project: Project | None = None, **kw):
    return check_script(project or make_project(), raw, **kw)


# ------------------------------------------------------------------ đọc, nhận dạng, gộp
def test_full_and_short_forms_give_same_result():
    cards = [scene(f"Thẻ {i}", punch=True) for i in range(4)]
    short = run(cards)
    full = run({"hbt_script": 1, "scenes": cards})
    assert short.ok and full.ok
    assert short.merged == full.merged
    assert short.diff == full.diff


def test_json_text_is_accepted_and_k1_reports_line_column():
    ok = run(json.dumps([scene()] * 4))
    assert ok.ok
    bad = run('{\n  "scenes": [\n    {"voice": }\n  ]\n}')
    assert codes(bad.errors) == ["K1"]
    assert "dòng 3" in bad.errors[0]["message"]
    assert not bad.ok and bad.merged is None


def test_absent_fields_are_kept():
    p = make_project()
    res = run([{"punch": True}] * 4, p)
    assert res.ok
    first = res.merged.scenes[0]
    assert first.punch is True
    assert first.voice == "Lời cảnh 1."
    assert first.card.lines[0].text == "Cũ 1"
    assert first.labels[0].text == "NHÃN"
    assert first.caption_y == 1300
    assert first.image == "images/0.png"
    assert res.merged.thumbnail == p.thumbnail
    assert res.merged.publish == p.publish


def test_card_replaces_whole_block():
    res = run([{"card": {"y": 300, "lines": [{"text": "Một"}]}}] * 4)
    card = res.merged.scenes[0].card
    assert card.y == 300
    assert [ln.text for ln in card.lines] == ["Một"]
    assert (card.lines[0].size, card.lines[0].color) == ("m", "ink")  # mặc định điền đủ


def test_empty_labels_clears_and_caption_y_null_is_auto():
    res = run([{"labels": [], "caption_y": None}] * 4)
    assert res.ok
    assert res.merged.scenes[0].labels == []
    assert res.merged.scenes[0].caption_y is None
    fields = {d["field"] for d in res.diff if d["scene_index"] == 0}
    assert fields == {"labels", "caption_y"}


def test_null_is_invalid_elsewhere():
    for bad in ({"voice": None}, {"punch": None}, {"card": None}, {"labels": None}):
        res = run([bad] * 4)
        assert not res.ok and codes(res.errors)[0] == "K3", bad
    assert not run({"scenes": [], "publish": None}).ok
    assert not run({"scenes": [], "thumbnail": None}).ok


def test_version_must_be_1():
    assert run({"hbt_script": 1, "scenes": [{}] * 4}).ok
    res = run({"hbt_script": 2, "scenes": [{}] * 4})
    assert not res.ok and res.errors[0]["field"] == "hbt_script"


def test_unknown_field_is_error_k4():
    res = run([{"pucnh": True}, {}, {}, {}])
    assert [(e["code"], e["scene_index"]) for e in res.errors] == [("K4", 0)]
    assert "pucnh" in res.errors[0]["message"]
    nested = run([{"card": {"lines": [{"text": "a", "colour": "x"}]}}] * 4)
    assert codes(nested.errors) == ["K4"] * 4
    assert run({"scenes": [], "extra_top": 1}).errors[0]["code"] == "K4"


@pytest.mark.parametrize("name", ["image", "music", "settings", "title", "slug", "series", "theme"])
def test_forbidden_field_in_scene_or_root(name):
    res = run([{name: "x"}, {}, {}, {}])
    assert codes(res.errors) == ["K4"] and "không đổi được" in res.errors[0]["message"]
    root = run({"scenes": [{}] * 4, name: "x"})
    assert codes(root.errors) == ["K4"] and "không đổi được" in root.errors[0]["message"]


def test_root_voice_file_is_forbidden_but_scene_voice_is_allowed():
    assert not run({"scenes": [{}] * 4, "voice": "voice.mp3"}).ok
    assert run([{"voice": "Lời mới."}] * 4).ok


@pytest.mark.parametrize(
    "bad",
    [
        {"card": {"y": "giua"}},
        {"card": {"y": 2000}},
        {"card": {"lines": [{"text": "a", "size": "xxl"}]}},
        {"card": {"lines": [{"text": "a", "color": "red"}]}},
        {"card": {"lines": [{"size": "m"}]}},
        {"labels": [{"text": "a", "x": 1}]},
        {"labels": "nhãn"},
        {"punch": "true"},
        {"punch": 1},
        {"caption_y": "auto"},
        {"caption_y": 1.5},
        {"voice": 5},
    ],
)
def test_k3_wrong_values(bad):
    res = run([bad] + [{}] * 3)
    assert not res.ok
    assert codes(res.errors) == ["K3"], res.errors
    assert res.errors[0]["scene_index"] == 0


def test_k3_valid_values_pass():
    ok = [
        {"card": {"y": y, "lines": [{"text": "a", "size": s, "color": c}]}}
        for y in ("top", "upper", "middle", "lower", 0, 1920)
        for s in ("s", "m", "l", "xl")
        for c in ("ink", "primary", "accent", "#a1B2c3")
    ]
    for i in range(0, len(ok), 4):
        assert run(ok[i : i + 4]).ok


def test_root_must_be_object_or_array():
    for raw in (5, "5", None, True):
        res = run(raw)
        assert not res.ok and res.errors[0]["code"] in ("K1", "K3")


# ------------------------------------------------------------------ chuẩn hoá
def test_nfc_everywhere():
    decomposed = unicodedata.normalize("NFD", "Muỗi đốt")
    assert decomposed != "Muỗi đốt"
    raw = {
        "scenes": [
            {"voice": decomposed, "card": {"lines": [{"text": decomposed}]}},
            {},
            {},
            {},
        ],
        "publish": {"hook": decomposed, "hashtags": [decomposed]},
    }
    res = run(raw)
    assert res.ok
    scene0 = res.merged.scenes[0]
    assert scene0.voice == "Muỗi đốt"
    assert scene0.card.lines[0].text == "Muỗi đốt"
    assert res.merged.publish.hook == "Muỗi đốt"
    assert res.merged.publish.hashtags == ["Muỗi đốt"]


def test_hashtags_drop_hash_and_spaces():
    res = run(
        {"scenes": [{}] * 4, "publish": {"hook": "H", "hashtags": ["#muoi", " #hbt ", "ok", "#"]}}
    )
    assert res.merged.publish.hashtags == ["muoi", "hbt", "ok"]
    assert res.merged.publish.hook == "H"


def test_publish_and_thumbnail_replace_whole_block():
    raw = {
        "scenes": [{}] * 4,
        "publish": {"hashtags": ["moi"]},
        "thumbnail": {"scene": 2, "lines": ["X", "Y", "Z"], "series": "S"},
    }
    res = run(raw)
    assert res.ok
    assert res.merged.publish.hook == ""  # thay cả khối, không giữ hook cũ
    assert res.merged.thumbnail.scene == 2 and res.merged.thumbnail.series == "S"
    assert {d["field"] for d in res.diff if d["scene_index"] is None} == {"publish", "thumbnail"}


# ------------------------------------------------------------------ K5–K9
def test_k5_per_size_limits():
    def warn5(text, size):
        return [w for w in run([scene(text, size)] + [{}] * 3).warnings if w["code"] == "K5"]

    assert warn5("“được muỗi yêu”?", "l")  # 16 > 15
    assert warn5("gấp 100 lần", "xl")  # 11 > 10
    assert not warn5("15/10", "xl")
    assert not warn5("a" * 10, "xl") and warn5("a" * 11, "xl")
    assert not warn5("a" * 15, "l") and warn5("a" * 16, "l")
    assert not warn5("a" * 22, "m") and warn5("a" * 23, "m")
    assert not warn5("a" * 26, "s") and warn5("a" * 27, "s")


def test_k5_counts_nfc_characters():
    # 10 ký tự sau NFC nhưng 15 code point khi tách dấu
    text = unicodedata.normalize("NFD", "ĐẠI DƯƠNG!")
    assert len(text) > 10
    res = run([scene(text, "xl")] + [{}] * 3)
    assert not [w for w in res.warnings if w["code"] == "K5"]


def test_k6_single_word_too_wide_is_error():
    res = run([scene("Â" * 30, "xl")] + [{}] * 3)
    assert not res.ok
    assert [e["code"] for e in res.errors] == ["K6"]
    assert str(TEXT_W) in res.errors[0]["message"]
    assert res.errors[0]["scene_index"] == 0 and res.errors[0]["field"] == "card.lines[0]"
    assert res.merged is None


def test_k6b_wrapped_line_is_warning_only():
    res = run([scene("Nhiều chữ nhiều chữ nhiều chữ nhiều chữ", "xl")] + [{}] * 3)
    assert res.ok
    w = [w for w in res.warnings if w["code"] == "K6b"]
    assert len(w) == 1 and "tự xuống hàng" in w[0]["message"]
    assert not [e for e in res.errors if e["code"] == "K6"]


def test_k7_line_count_and_accent():
    def w7(lines):
        card = {"card": {"lines": [{"text": t, "size": "s", "color": c} for t, c in lines]}}
        return [w for w in run([card] + [{}] * 3).warnings if w["code"] == "K7"]

    assert w7([])  # 0 dòng
    assert w7([("a", "ink")] * 4)  # > 3 dòng
    assert not w7([("a", "ink")] * 3)
    assert w7([("a", "accent"), ("b", "accent")])
    assert not w7([("a", "accent"), ("b", "primary")])


@pytest.mark.parametrize("ch", ["|", "{", "}"])
def test_k8_special_characters_in_card(ch):
    res = run([scene(f"a{ch}b")] + [{}] * 3)
    assert res.ok and "K8" in codes(res.warnings)


def test_k9_total_voice_limit():
    def run_voice(n):
        project = make_project(4)
        return run([{"voice": "a" * n}, {"voice": ""}, {"voice": ""}, {"voice": ""}], project)

    # 4 cảnh nối bằng dấu cách: 3 dấu cách cho 3 cảnh rỗng
    over = [
        w for w in run_voice(751 - 3).warnings if w["field"] == "voice" and "750" in w["message"]
    ]
    ok = [w for w in run_voice(750 - 3).warnings if w["field"] == "voice" and "750" in w["message"]]
    assert not ok
    assert over


def test_k9_empty_voice_warning_only_for_touched_scenes():
    res = run([{"voice": " | "}, {"punch": True}, {}, {}])
    empty = [w for w in res.warnings if w["code"] == "K9" and "trống" in w["message"]]
    assert [w["scene_index"] for w in empty] == [0]


SENSITIVE = SensitiveWords(
    categories=[
        Category(id="drug", level="block", words=["ma tuý"]),
        Category(id="beer", level="warn", words=["bia"]),
    ]
)


def test_k10_sensitive_words_on_merged_project():
    res = run([scene("Ma tuý"), {"voice": "Uống bia"}, {}, {}], words=SENSITIVE)
    assert res.ok
    k10 = [w for w in res.warnings if w["code"] == "K10"]
    assert {(w["scene_index"], w["level"]) for w in k10} == {(0, "block"), (1, "warn")}
    assert "chặn xuất" in next(w for w in k10 if w["level"] == "block")["message"]


# ------------------------------------------------------------------ K11, K12
def test_k11_thumbnail_rules():
    one = run({"scenes": [{}] * 4, "thumbnail": {"scene": 1, "lines": ["A"]}})
    assert codes(one.errors) == ["K11"]
    four = run({"scenes": [{}] * 4, "thumbnail": {"scene": 1, "lines": list("ABCD")}})
    assert codes(four.errors) == ["K11"]
    three = run({"scenes": [{}] * 4, "thumbnail": {"scene": 1, "lines": list("ABC")}})
    assert three.ok
    far = run({"scenes": [{}] * 4, "thumbnail": {"scene": 5, "lines": ["A", "B"]}})
    assert codes(far.errors) == ["K11"] and far.errors[0]["field"] == "thumbnail.scene"
    # thêm cảnh làm cảnh bìa hợp lệ
    grown = run({"scenes": [{}] * 5, "thumbnail": {"scene": 5, "lines": ["A", "B"]}}, extra="add")
    assert grown.ok


def test_k12_project_that_is_invalid_after_merge_is_rejected():
    broken = make_project().model_copy(update={"slug": "BAD SLUG"})  # bỏ qua validate
    res = check_script(broken, [{}] * 4)
    assert not res.ok and "K12" in codes(res.errors)
    assert res.merged is None


def test_k12_does_not_duplicate_k11():
    res = run({"scenes": [{}] * 4, "thumbnail": {"scene": 9, "lines": ["A", "B"]}})
    assert codes(res.errors) == ["K11"]


# ------------------------------------------------------------------ lệch số cảnh
def test_fewer_scenes_apply_first_n_with_warning():
    res = run([scene("Một", punch=True), scene("Hai")])
    assert res.ok
    assert codes(res.warnings).count("K2") == 1
    assert res.counts == {"json": 2, "project": 4, "after": 4}
    assert res.merged.scenes[0].card.lines[0].text == "Một"
    assert res.merged.scenes[1].card.lines[0].text == "Hai"
    assert res.merged.scenes[2].card.lines[0].text == "Cũ 3"
    assert res.merged.scenes[3].card.lines[0].text == "Cũ 4"


def test_more_scenes_is_error_unless_extra():
    cards = [scene(f"T{i}") for i in range(6)]
    res = run(cards)
    assert not res.ok and codes(res.errors) == ["K2"]
    assert res.counts == {"json": 6, "project": 4, "after": 4}

    added = run(cards, extra="add")
    assert added.ok and len(added.merged.scenes) == 6
    assert added.counts["after"] == 6
    new = added.merged.scenes[5]
    assert new.card.lines[0].text == "T5" and new.image == "" and new.voice == ""
    assert [d for d in added.diff if d["field"] == "scene"][0]["scene_index"] == 4

    trimmed = run(cards, extra="trim")
    assert trimmed.ok and len(trimmed.merged.scenes) == 4
    assert "K2" in codes(trimmed.warnings)
    assert trimmed.merged.scenes[3].card.lines[0].text == "T3"


def test_scene_count_after_merge_must_be_3_to_12():
    res = run([scene()] * 13, make_project(12), extra="add")
    assert not res.ok and codes(res.errors) == ["K2"]
    assert run([scene()] * 3, make_project(3)).ok
    assert run([scene()] * 12, make_project(12)).ok


def test_extra_is_ignored_when_counts_are_not_larger():
    assert run([scene()] * 4, extra="add").counts["after"] == 4
    assert run([scene()] * 2, extra="trim").ok


# ------------------------------------------------------------------ khác biệt và căn lại
def test_diff_lists_only_changed_fields():
    project = make_project()
    same_card = project.scenes[1].card.model_dump(mode="json")
    res = run([{"punch": True}, {"card": same_card}, {"voice": "Lời cảnh 3."}, {}], project)
    assert res.ok
    assert [(d["scene_index"], d["field"]) for d in res.diff] == [(0, "punch")]
    d = res.diff[0]
    assert (d["before"], d["after"]) == (False, True)


def test_realign_scenes_only_for_changed_voice():
    res = run(
        [{"voice": "Lời cảnh 1."}, {"voice": "Khác hẳn."}, {"punch": True}, {"voice": "Mới | đây"}]
    )
    assert res.realign_scenes == [1, 3]
    assert [d["field"] for d in res.diff if d["scene_index"] == 1] == ["voice"]


def test_realign_includes_added_scene_with_voice():
    res = run([{}] * 4 + [{"voice": "Cảnh thêm."}], extra="add")
    assert res.realign_scenes == [4]


def test_result_dict_shape_and_project_not_mutated():
    project = make_project()
    before = copy.deepcopy(project.model_dump())
    res = run([scene(punch=True)] * 4, project)
    out = res.to_dict()
    assert set(out) == {"ok", "errors", "warnings", "diff", "counts", "realign_scenes"}
    assert out["ok"] is True and out["counts"] == {"json": 4, "project": 4, "after": 4}
    assert project.model_dump() == before
    json.dumps(out)  # tuần tự hoá được


def test_parse_script_returns_scenes_for_array():
    script, issues = parse_script([{"punch": True}])
    assert not issues and script.scenes[0].punch is True


# ------------------------------------------------------------------ đối chiếu import_cards.py (X3)
def test_matches_import_cards_on_dao_phuc_sinh():
    """`dao-phuc-sinh.expected.json` sinh MỘT LẦN từ workspace/import_cards.py (ngoài repo) trên
    `dao-phuc-sinh.cards.json`; `card` và `punch` sau gộp phải giống."""
    cards = json.loads((DATA / "dao-phuc-sinh.cards.json").read_text(encoding="utf-8"))
    expected = json.loads((DATA / "dao-phuc-sinh.expected.json").read_text(encoding="utf-8"))
    project = make_project(8)
    res = run(cards, project)
    assert res.ok, res.errors
    got = [{"punch": s.punch, "card": s.card.model_dump(mode="json")} for s in res.merged.scenes]
    want = []
    for e in expected:
        norm = Project.model_validate(
            {
                **project.model_dump(mode="json"),
                "scenes": [{"card": e["card"], "punch": e["punch"]}] * 3,
            }
        ).scenes[0]
        want.append({"punch": norm.punch, "card": norm.card.model_dump(mode="json")})
    assert got == want
    # import_cards.py chỉ báo "tự xuống hàng" ở cảnh 6 (chỉ số 5), và không có dòng nào tràn
    assert [w["scene_index"] for w in res.warnings if w["code"] == "K6b"] == [5]
    assert "K6" not in codes(res.errors)
