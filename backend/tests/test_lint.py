import pytest

from hbt.models import Project
from hbt.pipeline import lint


def project_with_voices(voices):
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
    assert "751" in issue.message and issue.scene is None


@pytest.mark.parametrize("n", [100, 749])
def test_short_voice_is_clean(n):
    assert lint.lint_project(exact(n)) == []
