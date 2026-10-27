import pytest

from hbt.models import Project
from hbt.pipeline import lint
from hbt.sensitive import SensitiveWords


def project_with_voices(voices):
    voices = [*voices, *[""] * (3 - len(voices))]  # project cần ít nhất 3 cảnh
    return Project.model_validate(
        {
            "slug": "demo",
            "title": "Demo",
            "voice": "voice.mp3",
            "scenes": [{"image": f"images/{i}.png", "voice": v} for i, v in enumerate(voices)],
        }
    )


def test_voice_text_drops_markup():
    assert (
        lint.voice_text("Xin chào, | các bạn! 100{một trăm} lần")
        == "Xin chào, các bạn! 100một trăm lần"
    )


def test_count_joins_scenes_with_one_space():
    p = project_with_voices(["ab | cd", "ef", "gh"])
    assert lint.voice_char_count(p) == len("ab cd ef gh")


def exact(n):
    """Ba cảnh, tổng đúng n ký tự (kể cả 2 dấu cách nối cảnh)."""
    body = n - 2
    a, b = body // 3, body // 3
    c = body - a - b
    return project_with_voices(["a" * a, "b" * b, "c" * c])


def test_750_characters_no_warning():
    p = exact(750)
    assert lint.voice_char_count(p) == 750
    assert lint.lint_project(p) == []


def test_751_characters_warns():
    p = exact(751)
    assert lint.voice_char_count(p) == 751
    (issue,) = lint.lint_project(p)
    assert issue.level == "warn" and issue.category == "voice_length"
    assert "751" in issue.message and issue.scene_index is None


@pytest.mark.parametrize("n", [100, 749])
def test_short_voice_is_clean(n):
    assert lint.lint_project(exact(n)) == []


# ---------------------------------------------------------------- từ nhạy cảm (mục 7, 10b)
def words(**cats):
    levels = {"alcohol": "warn", "drugs": "block"}
    return SensitiveWords.model_validate(
        {
            "categories": [
                {"id": cid, "level": levels.get(cid, "warn"), "words": ws, "hint": "gợi ý"}
                for cid, ws in cats.items()
            ]
        }
    )


DEFAULT_WORDS = words(alcohol=["bia", "rượu"], drugs=["ma tuý"], chemical=["hoá chất"])


def full_project(**over):
    base = {
        "slug": "demo",
        "title": "Demo",
        "voice": "voice.mp3",
        "scenes": [
            {
                "image": "a.png",
                "card": {"lines": [{"text": "Uống BIA", "size": "l"}, {"text": "an toàn"}]},
                "labels": [{"text": "rượu", "x": 10, "y": 10}],
                "voice": "Ngày xưa | người ta nhậu bia.",
            },
            {"image": "b.png", "card": {"lines": [{"text": "Cuốn sách bìa đẹp"}]}, "voice": "Ổn."},
            {"image": "c.png", "voice": "Hết."},
        ],
        "publish": {"hook": "Hóa chất nguy hiểm?", "hashtags": []},
    }
    base.update(over)
    return Project.model_validate(base)


def sensitive(issues):
    return [i for i in issues if i.category != "number_reading"]


def test_bia_is_flagged_but_bia_with_accent_is_not():
    issues = sensitive(lint.lint_project(full_project(), DEFAULT_WORDS))
    flagged = {(i.scene_index, i.field, i.word) for i in issues}
    assert (0, "card.lines", "bia") in flagged
    assert (0, "labels", "rượu") in flagged
    assert (0, "voice", "bia") in flagged
    assert not any(i.scene_index == 1 for i in issues)  # "bìa" ở cảnh 2 không bị bắt


def test_hook_and_thumbnail_lines_are_scanned_with_scene_none():
    project = full_project(thumbnail={"scene": 1, "lines": ["Quán BIA", "hơi"]})
    issues = lint.lint_project(project, DEFAULT_WORDS)
    by_field = {i.field: i for i in issues if i.scene_index is None and i.word}
    assert by_field["publish.hook"].word == "hoá chất"  # "Hóa chất" khớp "hoá chất"
    assert by_field["thumbnail.lines"].word == "bia"
    assert by_field["thumbnail.lines"].category == "alcohol"


def test_issue_carries_level_category_hint_and_word():
    (issue,) = [i for i in lint.lint_project(full_project(), DEFAULT_WORDS) if i.field == "labels"]
    assert (issue.level, issue.category, issue.hint, issue.word) == (
        "warn",
        "alcohol",
        "gợi ý",
        "rượu",
    )
    assert '"rượu"' in issue.message


def test_voice_scans_displayed_and_spoken_text_in_braces():
    w = words(drugs=["ma tuý", "cần sa"])
    # chữ đọc trong {} cũng bị quét; phần hiển thị và phần đọc nối nhau bằng dấu cách
    p = project_with_voices(["Loại ma{cần} sa", "Giá 5{ma túy} đấy"])
    found = {(i.scene_index, i.word) for i in lint.lint_project(p, w) if i.level == "block"}
    assert found == {(0, "cần sa"), (1, "ma tuý")}
    p = project_with_voices(["Mua 2{cần sa} đi"])
    assert [i.word for i in lint.lint_project(p, w) if i.level == "block"] == ["cần sa"]


def test_pipe_does_not_glue_words_together():
    p = project_with_voices(["nhậu|rượu", "ma|tuý"])
    w = words(alcohol=["rượu", "nhậu"], drugs=["ma tuý"])
    got = {(i.scene_index, i.word) for i in lint.lint_project(p, w)}
    assert got == {(0, "rượu"), (0, "nhậu"), (1, "ma tuý")}


def test_without_a_word_list_only_length_and_numbers_are_checked():
    assert lint.lint_project(full_project()) == []


def test_each_word_once_per_field_and_scene():
    p = project_with_voices(["bia bia bia"])
    assert len(lint.lint_project(p, words(alcohol=["bia"]))) == 1


# ---------------------------------------------------------------- số chưa ghi cách đọc
def numbers(*voices):
    """Mỗi cảnh có số chưa ghi cách đọc cho đúng một dòng: (cảnh, "1, 100")."""
    return [
        (i.scene_index, i.word)
        for i in lint.lint_project(project_with_voices(list(voices)))
        if i.category == "number_reading"
    ]


def test_bare_numbers_are_one_info_line_per_scene_listing_the_numbers():
    p = project_with_voices(["Có 1 con muỗi, 100 con kiến, năm 2026."])
    (issue,) = [i for i in lint.lint_project(p) if i.category == "number_reading"]
    assert issue.level == "info" and issue.field == "voice" and issue.scene_index == 0
    assert issue.word == "1, 100, 2026"
    assert issue.message == "Số chưa ghi cách đọc: 1, 100, 2026."
    assert "100{một trăm}" in issue.hint


def test_numbers_with_spoken_form_are_fine():
    assert numbers("Có 100{một trăm} con", "Chiếm 50%{năm mươi phần trăm} ", "1{một}.") == []


def test_number_with_separators_is_one_number_and_repeats_are_collapsed():
    assert numbers("Giá 1.000 đồng, rồi 3,5 kg, lại 1.000") == [(0, "1.000, 3,5")]


def test_numbers_are_reported_once_per_scene():
    assert numbers("hai 2", "ba 3 và 2", "bốn") == [(0, "2"), (1, "3, 2")]


def test_only_bare_numbers_are_listed_when_a_scene_mixes_both():
    assert numbers("100{một trăm} và 7 và 8{tám}") == [(0, "7")]


def test_number_inside_braces_is_not_double_reported():
    assert numbers("100{một trăm lẻ 1}") == []


def test_default_list_catches_bia_and_not_bia_with_accent(tmp_path):
    from hbt.sensitive import SensitiveStore

    default = SensitiveStore(tmp_path).load()
    flagged = lint.lint_project(project_with_voices(["Quán bia", "Bìa sách"]), default)
    assert [(i.scene_index, i.word) for i in flagged] == [(0, "bia")]
