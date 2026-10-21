from hbt.models import Project
from hbt.pipeline import cache
from hbt.pipeline.publish import build_publish_text


def project(**kw):
    base = {
        "slug": "demo",
        "title": "Vì sao muỗi đốt?",
        "series": "Vì sao vậy ta?",
        "voice": "voice.mp3",
        "music": {"file": "m.mp3", "credit": "The Wacky Sprint – nkbloom (Pixabay)"},
        "publish": {
            "hook": "Bạn có phải người được muỗi yêu? 🦟",
            "hashtags": ["muoi", "#khoahoc"],
        },
        "scenes": [{"image": f"i{i}.png", "voice": "Xin chào."} for i in range(3)],
    }
    base.update(kw)
    return Project.model_validate(base)


def test_publish_text_matches_spec():
    assert build_publish_text(project()) == (
        "[TikTok]\n"
        "Bạn có phải người được muỗi yêu? 🦟\n"
        "#muoi #khoahoc\n"
        "\n"
        "[YouTube Shorts]\n"
        "Title: Vì sao muỗi đốt? #shorts\n"
        'Description: Bạn có phải người được muỗi yêu? 🦟 Series "Vì sao vậy ta?". '
        "Nhạc: The Wacky Sprint – nkbloom (Pixabay)\n"
    )


def test_publish_text_without_music_or_series():
    text = build_publish_text(project(music=None, series=""))
    assert "Nhạc" not in text and "Series" not in text
    assert text.splitlines()[-1] == "Description: Bạn có phải người được muỗi yêu? 🦟"


def test_publish_text_thumbnail_block():
    thumb = {"scene": 1, "lines": ["BẠN CÓ PHẢI", "NGƯỜI ĐƯỢC", "MUỖI YÊU?"], "series": "S"}
    text = build_publish_text(project(thumbnail=thumb))
    assert text.endswith(
        "[Thumbnail]\n"
        "Dòng chữ bìa: BẠN CÓ PHẢI / NGƯỜI ĐƯỢC / MUỖI YÊU?\n"
        "TikTok: cover_9x16.jpg\n"
        "YouTube Shorts: youtube_3x2.jpg\n"
    )


def test_digest_depends_on_file_content_not_name(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("x", encoding="utf-8")
    b.write_text("x", encoding="utf-8")
    assert cache.digest(a, 1) == cache.digest(b, 1)
    b.write_text("y", encoding="utf-8")
    assert cache.digest(a, 1) != cache.digest(b, 1)
    assert cache.digest({"b": 1, "a": 2}) == cache.digest({"a": 2, "b": 1})


def test_is_fresh_roundtrip(tmp_path):
    art = tmp_path / "out.wav"
    assert not cache.is_fresh(art, "k1")
    art.write_bytes(b"data")
    assert not cache.is_fresh(art, "k1")  # chưa có khoá
    cache.mark(art, "k1")
    assert cache.is_fresh(art, "k1") and not cache.is_fresh(art, "k2")
    art.unlink()
    assert not cache.is_fresh(art, "k1")
