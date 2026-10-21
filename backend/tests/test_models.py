import json

import pytest
from pydantic import ValidationError

from hbt.models import Project, load_project


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


def test_empty_voice_rejected():
    with pytest.raises(ValidationError):
        Project.model_validate(project(scenes=[scene(voice=" | "), scene(), scene()]))


@pytest.mark.parametrize("slug", ["Muoi", "muoi dot", "-a", "a--b", ""])
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
