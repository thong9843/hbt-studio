import json

import pytest
from pydantic import ValidationError

from hbt.models import Music, Project, Voice, load_project


def scene(**kw):
    return {"image": "images/scene-01.png", "voice": "Xin chào | các bạn.", **kw}


def project(**kw):
    base = {
        "slug": "demo",
        "title": "Demo",
        "voice": "voice.mp3",
        "scenes": [scene(), scene(), scene()],
    }
    base.update(kw)
    return base


def test_minimal_project_gets_defaults():
    p = Project.model_validate(project())
    assert p.settings.fps == 50
    assert p.settings.outro is True
    assert p.settings.aligner == "auto"
    assert p.music is None
    assert p.scenes[0].card.y == "top"
    assert p.scenes[0].punch is False


def test_unknown_fields_are_ignored():
    p = Project.model_validate(project(_notes={"a": "b"}))
    assert not hasattr(p, "_notes")


@pytest.mark.parametrize("count", [2, 13])
def test_scene_count_limits(count):
    with pytest.raises(ValidationError):
        Project.model_validate(project(scenes=[scene()] * count))


@pytest.mark.parametrize("count", [3, 12])
def test_scene_count_ok(count):
    assert len(Project.model_validate(project(scenes=[scene()] * count)).scenes) == count


@pytest.mark.parametrize("fps", [45, 24, 0])
def test_rejects_odd_fps(fps):
    with pytest.raises(ValidationError):
        Project.model_validate(project(settings={"fps": fps}))


@pytest.mark.parametrize("fps", [30, 50, 60])
def test_accepts_allowed_fps(fps):
    assert Project.model_validate(project(settings={"fps": fps})).settings.fps == fps


def test_draft_may_have_no_image_voice_or_script():
    p = Project.model_validate({"slug": "demo", "title": "T", "scenes": [{} for _ in range(3)]})
    assert p.voice is None and p.scenes[0].image == "" and p.scenes[0].voice == ""
    assert p.model_dump()["voice"] is None


def test_render_problems_lists_everything_missing():
    p = Project.model_validate({"slug": "demo", "title": "T", "scenes": [{}, {}, {}]})
    problems = p.render_problems()
    assert problems[0] == "Chưa có file giọng đọc"
    assert "Cảnh 1: chưa có ảnh" in problems and "Cảnh 3: lời đọc đang trống" in problems
    assert len(problems) == 1 + 3 * 2


def test_render_problems_empty_when_complete_and_markup_only_script_counts_as_empty():
    full = project()
    assert Project.model_validate(full).render_problems() == []
    markup_only = project(scenes=[scene(voice=" | "), scene(), scene()])
    assert Project.model_validate(markup_only).render_problems() == ["Cảnh 1: lời đọc đang trống"]


@pytest.mark.parametrize(
    "slug", ["Muoi", "muoi dot", "-a", "a--b", "", "../x", "a/b", "con", "nul", "com1", "a" * 61]
)
def test_bad_slug(slug):
    with pytest.raises(ValidationError):
        Project.model_validate(project(slug=slug))


def test_card_validation():
    ok = scene(card={"y": 100, "lines": [{"text": "A", "size": "xl", "color": "#aabbcc"}]})
    Project.model_validate(project(scenes=[ok, scene(), scene()]))
    for card in (
        {"y": "bottom"},
        {"y": 2000},
        {"lines": [{"text": "A", "size": "xxl"}]},
        {"lines": [{"text": "A", "color": "red"}]},
    ):
        with pytest.raises(ValidationError):
            Project.model_validate(project(scenes=[scene(card=card), scene(), scene()]))


def test_theme_requires_hex():
    with pytest.raises(ValidationError):
        Project.model_validate(project(theme={"primary": "teal"}))


def test_thumbnail_rules():
    ok = {"scene": 1, "lines": ["A", "B", "C"], "series": "S", "accent": "#FFD43B"}
    assert Project.model_validate(project(thumbnail=ok)).thumbnail.scene == 1
    for bad in (
        {**ok, "lines": ["A"]},
        {**ok, "lines": ["A", "B", "C", "D"]},
        {**ok, "scene": 4},
        {**ok, "scene": 0},
    ):
        with pytest.raises(ValidationError):
            Project.model_validate(project(thumbnail=bad))


def test_load_project_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path)
    (tmp_path / "project.json").write_text("{không phải json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        load_project(tmp_path)


def test_load_project_roundtrip(tmp_path):
    (tmp_path / "project.json").write_text(json.dumps(project()), encoding="utf-8")
    assert load_project(tmp_path).slug == "demo"


def test_voice_accepts_string_or_object():
    assert Project.model_validate(project()).voice == Voice(file="voice.mp3")
    obj = Project.model_validate(project(voice={"file": "v.wav", "trim_end": 41.5}))
    assert obj.voice.file == "v.wav" and obj.voice.trim_end == 41.5


@pytest.mark.parametrize("trim_end", [0, -1])
def test_voice_trim_end_must_be_positive(trim_end):
    with pytest.raises(ValidationError):
        Project.model_validate(project(voice={"file": "v.wav", "trim_end": trim_end}))


def test_voice_serializes_back_to_a_plain_string_when_untrimmed():
    assert Project.model_validate(project()).model_dump()["voice"] == "voice.mp3"
    trimmed = Project.model_validate(project(voice={"file": "v.wav", "trim_end": 3.5}))
    assert trimmed.model_dump()["voice"] == {"file": "v.wav", "trim_end": 3.5}


@pytest.mark.parametrize("start", [None, 0, 12.5])
def test_music_start_accepts_null_and_non_negative(start):
    assert Music(file="m.mp3", start=start).start == start


@pytest.mark.parametrize("start", [-1, "abc"])
def test_music_start_rejects_negative_and_non_numbers(start):
    with pytest.raises(ValidationError):
        Music(file="m.mp3", start=start)


# --- thumbnail.image (bìa từ ảnh tải lên)
def thumb(**kw):
    return {"scene": 1, "lines": ["BẠN CÓ PHẢI", "MUỖI YÊU?"], **kw}


def test_thumbnail_image_defaults_to_none_for_old_project_json():
    p = Project.model_validate(project(thumbnail=thumb()))
    assert p.thumbnail.image is None


@pytest.mark.parametrize("name", ["png", "jpg", "jpeg", "webp"])
def test_thumbnail_image_accepts_cover_names(name):
    p = Project.model_validate(project(thumbnail=thumb(image=f"images/cover.{name}")))
    assert p.thumbnail.image == f"images/cover.{name}"


@pytest.mark.parametrize(
    "bad",
    [
        "images/scene-01.png",
        "images/../cover.png",
        "../images/cover.png",
        "/images/cover.png",
        "C:/images/cover.png",
        r"imagesver.png",
        "images/cover.gif",
        "images/cover.png/x",
        "cover.png",
        "",
    ],
)
def test_thumbnail_image_rejects_other_paths(bad):
    with pytest.raises(ValidationError):
        Project.model_validate(project(thumbnail=thumb(image=bad)))
