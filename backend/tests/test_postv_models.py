"""Mô hình PostV và union với project HBT (docs/postv/IMPLEMENT-POSTV.md mục 3)."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from hbt.models import Project
from hbt.postv.models import POSTV_FPS, AnyProject, PostvProject, project_kind

adapter = TypeAdapter(AnyProject)


def video(**extra):
    return {"slug": "muoi", "title": "Muỗi", "scenes": [{}, {}, {}], **extra}


def postv(**extra):
    return {"kind": "postv", "slug": "bai-dem-khuya", "title": "Bài đêm khuya", **extra}


def test_union_picks_type_by_kind():
    assert isinstance(adapter.validate_python(video()), Project)
    assert isinstance(adapter.validate_python(postv()), PostvProject)


def test_project_without_kind_is_video_and_keeps_its_shape():
    old = video()
    parsed = adapter.validate_python(old)
    assert project_kind(old) == "video" and project_kind(parsed) == "video"
    assert "kind" not in parsed.model_dump(mode="json")  # project cũ không đổi


def test_unknown_kind_falls_back_to_video():
    assert project_kind({"kind": "khac"}) == "video"
    with pytest.raises(ValidationError):  # thiếu `scenes` → lỗi của project HBT
        adapter.validate_python({"kind": "khac", "slug": "a", "title": "A"})


def test_postv_defaults():
    p = PostvProject.model_validate(postv())
    assert p.kind == "postv" and p.version == 1
    assert p.settings.fps == POSTV_FPS == 60
    assert p.settings.censor.enabled and p.settings.censor.text == "blur"
    assert p.settings.card_animation == "smooth" and p.template == "story_cards"
    assert p.voice.engine == "vieneu" and p.background.mode == "auto"
    assert p.segments == [] and p.comments == []
    assert p.style.caption.preset == "hbt" and p.style.caption.highlight_color is None


def test_postv_roundtrip_keeps_kind():
    p = PostvProject.model_validate(postv(post={"handle": "user1", "likes": 27600}))
    data = json.loads(json.dumps(p.model_dump(mode="json")))
    assert data["kind"] == "postv"
    again = adapter.validate_python(data)
    assert isinstance(again, PostvProject) and again.post.likes == 27600


@pytest.mark.parametrize("fps", [24, 25, 45, 120])
def test_fps_must_be_allowed(fps):
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(settings={"fps": fps}))


@pytest.mark.parametrize("fps", [30, 50, 60])
def test_fps_allowed(fps):
    assert PostvProject.model_validate(postv(settings={"fps": fps})).settings.fps == fps


@pytest.mark.parametrize("slug", ["", "Có Dấu", "con", "a/b", "-a", "a" * 61])
def test_slug_checked_like_hbt(slug):
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(slug=slug))


def test_comment_ids_unique_and_parent_known():
    two = [{"id": "c1", "text": "a"}, {"id": "c1", "text": "b"}]
    with pytest.raises(ValidationError, match="trùng"):
        PostvProject.model_validate(postv(comments=two))
    with pytest.raises(ValidationError, match="không có"):
        PostvProject.model_validate(postv(comments=[{"id": "c1", "parent": "c9"}]))
    ok = [{"id": "c1"}, {"id": "c2", "parent": "c1"}]
    assert len(PostvProject.model_validate(postv(comments=ok)).comments) == 2


def test_segment_ref_must_exist():
    seg = [{"role": "comment", "ref": "c7", "voice": "x"}]
    with pytest.raises(ValidationError, match="c7"):
        PostvProject.model_validate(postv(segments=seg))
    ok = PostvProject.model_validate(
        postv(comments=[{"id": "c7"}], segments=[{"role": "comment", "ref": "c7"}])
    )
    assert ok.segments[0].card is None  # theo role; mốc dựng quyết định sau


@pytest.mark.parametrize("bad", [{"role": "khac"}, {"role": "post", "card": "to"}])
def test_segment_values(bad):
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(segments=[bad]))


def test_stats_are_non_negative_integers():
    assert PostvProject.model_validate(postv(post={"views": 619000, "shares": 0})).post.shares == 0
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(post={"likes": -1}))
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(comments=[{"id": "c1", "likes": -5}]))


def test_limits_on_segments_and_comments():
    segs = [{"role": "commentary", "voice": "x"}] * 41
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(segments=segs))
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(comments=[{"id": f"c{i}"} for i in range(201)]))


def test_caption_color_and_voice_trim():
    style = {"caption": {"highlight_color": "#38E178"}}
    assert (
        PostvProject.model_validate(postv(style=style)).style.caption.highlight_color == "#38E178"
    )
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(style={"caption": {"highlight_color": "xanh"}}))
    with pytest.raises(ValidationError):
        PostvProject.model_validate(postv(voice={"trim_end": 0}))


def test_render_problems():
    p = PostvProject.model_validate(postv())
    assert p.render_problems() == [
        "Chưa có chữ bài gốc",
        "Chưa có đoạn nào có lời đọc",
        "Chưa có file giọng đọc",
    ]
    ready = PostvProject.model_validate(
        postv(
            post={"text": "Nội dung"},
            segments=[{"role": "post", "voice": "Xin chào"}],
            voice={"engine": "file", "file": "voice.wav"},
        )
    )
    assert ready.render_problems() == []


def test_missing_commentary_is_not_a_problem():
    """Chủ dự án chốt chỉ nhắc (K-24): thiếu commentary không chặn dựng."""
    p = PostvProject.model_validate(
        postv(
            post={"text": "x"},
            segments=[{"role": "post", "voice": "a"}],
            voice={"engine": "file", "file": "voice.wav"},
        )
    )
    assert all("commentary" not in x for x in p.render_problems())
