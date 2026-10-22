import json

import pytest
from PIL import Image

from hbt.library import MusicLibrary
from hbt.sensitive import SensitiveStore, SensitiveWords
from hbt.storage import BadRequest, Conflict, NotFound, Storage, Unprocessable, slugify
from tests.helpers import needs_ffmpeg, write_wav


@pytest.fixture
def store(tmp_path):
    return Storage(tmp_path / "workspace")


def png(path, size=(64, 96), color=(200, 60, 40)):
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


# ---------------------------------------------------------------- slug
@pytest.mark.parametrize(
    "title, slug",
    [
        (
            "Vì sao muỗi đốt người này mà tha người kia?",
            "vi-sao-muoi-dot-nguoi-nay-ma-tha-nguoi-kia",
        ),
        ("Đường Đi — Hoàng Sa!", "duong-di-hoang-sa"),
        ("  --  ", "video"),
        ("A" * 100, "a" * 60),
    ],
)
def test_slugify(title, slug):
    assert slugify(title) == slug


def test_slugify_long_title_cuts_at_a_word_boundary():
    s = slugify("muoi " * 30)
    assert len(s) <= 60 and not s.endswith("-")


def test_unique_slug_gets_a_suffix(store):
    a = store.create("Muỗi")
    b = store.create("Muỗi")
    c = store.create("MUỖI!")
    assert (a.slug, b.slug, c.slug) == ("muoi", "muoi-2", "muoi-3")


# ---------------------------------------------------------------- CRUD
def test_create_makes_an_empty_draft(store):
    p = store.create("Vì sao vậy ta", series="Vì sao vậy ta?", scene_count=5)
    assert len(p.scenes) == 5 and p.voice is None and p.series == "Vì sao vậy ta?"
    assert p.settings.fps == 50 and p.settings.outro is True
    assert (store.project_dir(p.slug) / "images").is_dir()
    assert store.load(p.slug) == p
    assert len(p.render_problems()) == 1 + 5 * 2


@pytest.mark.parametrize("count", [2, 13])
def test_create_checks_scene_count(store, count):
    with pytest.raises(BadRequest, match="Số cảnh"):
        store.create("X", scene_count=count)


def test_create_rejects_blank_title(store):
    with pytest.raises(BadRequest):
        store.create("   ")


BAD_SLUGS = [
    "..", "../x", "a/b", "A", "", "a b", "con.", "x\\y", "-a", "a-", "a--b", "a.b", "a_b", "é",
    "con", "CON", "nul", "prn", "aux", "com1", "com9", "lpt1", "lpt9", "a" * 61,
]  # fmt: skip


@pytest.mark.parametrize("slug", BAD_SLUGS)
def test_bad_slugs_are_rejected_before_touching_the_disk(store, slug):
    with pytest.raises(Unprocessable, match="Slug không hợp lệ"):
        store.project_dir(slug)
    assert not store.exists(slug)
    for call in (store.load, store.delete, store.duplicate):
        with pytest.raises(Unprocessable):
            call(slug)
    assert not store.projects_dir.exists()  # chưa tạo gì


@pytest.mark.parametrize("slug", ["a", "muoi", "vi-sao-2", "a" * 60, "con-video", "com10", "nul2"])
def test_good_slugs_pass(store, slug):
    assert store.project_dir(slug).name == slug


@pytest.mark.parametrize("title", ["Con", "NUL", "COM1", "lpt9", "Aux", "PRN"])
def test_titles_that_slugify_to_a_windows_reserved_name_get_a_suffix(store, title):
    p = store.create(title)
    assert p.slug == title.lower() + "-video" and store.exists(p.slug)


def test_slug_is_at_most_60_characters_even_with_a_uniqueness_suffix(store):
    long_title = "muoi dot nguoi " * 12
    slugs = [store.create(long_title).slug for _ in range(12)]
    assert len(set(slugs)) == 12 and all(len(s) <= 60 for s in slugs)
    assert all(store.exists(s) for s in slugs)


def test_save_roundtrip_is_utf8_and_atomic(store):
    p = store.create("Muỗi")
    p.title = "Vì sao muỗi đốt người này?"
    p.scenes[0].voice = "Ngồi cùng một phòng, | mà chỉ mình bạn..."
    store.save(p.slug, p)
    raw = (store.project_dir(p.slug) / "project.json").read_text(encoding="utf-8")
    assert "Vì sao muỗi đốt người này?" in raw and "\\u" not in raw
    assert not list(store.project_dir(p.slug).glob("*.tmp"))
    assert store.load(p.slug).scenes[0].voice.startswith("Ngồi cùng")


def test_save_refuses_a_different_slug(store):
    p = store.create("Muỗi")
    other = p.model_copy(update={"slug": "khac"})
    with pytest.raises(BadRequest, match="slug"):
        store.save(p.slug, other)


def test_load_missing_and_corrupt(store):
    with pytest.raises(NotFound):
        store.load("khong-co")
    p = store.create("Muỗi")
    (store.project_dir(p.slug) / "project.json").write_text("{hỏng", encoding="utf-8")
    with pytest.raises(BadRequest, match="không hợp lệ"):
        store.load(p.slug)


def test_delete(store):
    p = store.create("Muỗi")
    store.delete(p.slug)
    assert not store.project_dir(p.slug).exists()
    with pytest.raises(NotFound):
        store.delete(p.slug)


def test_duplicate_copies_media_but_not_build_or_renders(store):
    p = store.create("Muỗi")
    d = store.project_dir(p.slug)
    png(d / "images" / "scene-01.png")
    (d / "build").mkdir()
    (d / "build" / "voice.wav").write_bytes(b"x")
    (d / "renders" / "j1").mkdir(parents=True)
    (d / "renders" / "j1" / "video.mp4").write_bytes(b"x")
    p.scenes[0].image = "images/scene-01.png"
    store.save(p.slug, p)

    copy = store.duplicate(p.slug)
    assert copy.slug == "muoi-ban-sao" and copy.title == "Muỗi (bản sao)"
    cd = store.project_dir(copy.slug)
    assert (cd / "images" / "scene-01.png").is_file()
    assert not (cd / "build").exists() and not (cd / "renders").exists()
    assert store.load(copy.slug).scenes[0].image == "images/scene-01.png"
    assert store.load(p.slug).slug == p.slug  # bản gốc không đổi
    assert store.duplicate(p.slug, title="Muỗi 2").slug == "muoi-2"


# ---------------------------------------------------------------- danh sách
def test_list_projects_fields_and_order(store):
    a = store.create("Một")
    b = store.create("Hai")
    d = store.project_dir(a.slug)
    png(d / "images" / "scene-01.png")
    a.scenes[0].image = "images/scene-01.png"
    store.save(a.slug, a)  # a sửa sau cùng → lên đầu
    (store.project_dir(b.slug) / "renders" / "job1").mkdir(parents=True)
    (store.project_dir(b.slug) / "renders" / "job1" / "video.mp4").write_bytes(b"x")
    (store.project_dir(b.slug) / "renders" / "job1" / "meta.json").write_text(
        json.dumps(
            {"preview": True, "fps": 30, "duration": 12.5, "created_at": "2026-10-21T01:00:00Z"}
        ),
        encoding="utf-8",
    )

    items = store.list_projects()
    by = {i["slug"]: i for i in items}
    assert [i["slug"] for i in items] == sorted(by, key=lambda s: by[s]["updated_at"], reverse=True)
    assert by["mot"]["thumb"] == "projects/mot/images/scene-01.png"
    assert by["hai"]["thumb"] is None and by["mot"]["last_render"] is None
    assert by["hai"]["last_render"] == {
        "job_id": "job1",
        "preview": True,
        "fps": 30,
        "duration": 12.5,
        "created_at": "2026-10-21T01:00:00Z",
        "video": "projects/hai/renders/job1/video.mp4",
    }
    assert set(by["mot"]) >= {"slug", "title", "updated_at", "thumb", "last_render"}


def test_list_projects_survives_a_broken_project(store):
    good = store.create("Tốt")
    bad = store.create("Hỏng")
    (store.project_dir(bad.slug) / "project.json").write_text("{", encoding="utf-8")
    items = {i["slug"]: i for i in store.list_projects()}
    assert "error" in items[bad.slug] and items[bad.slug]["title"] == bad.slug
    assert "error" not in items[good.slug]


def test_list_projects_empty_workspace(tmp_path):
    assert Storage(tmp_path / "nothing").list_projects() == []


# ---------------------------------------------------------------- tài sản
def test_image_upload_renames_and_updates_project(store, tmp_path):
    p = store.create("Muỗi")
    rel, project = store.save_asset(
        p.slug, "image", png(tmp_path / "up.bin"), "a.png", scene_index=1
    )
    assert rel == "images/scene-02.png" and project.scenes[1].image == rel
    assert (store.project_dir(p.slug) / rel).is_file() and not (tmp_path / "up.bin").exists()
    assert store.load(p.slug).scenes[1].image == rel


def test_image_replacement_removes_the_old_file_with_another_extension(store, tmp_path):
    p = store.create("Muỗi")
    Image.new("RGB", (32, 32)).save(tmp_path / "a.jpg", format="JPEG")
    store.save_asset(p.slug, "image", tmp_path / "a.jpg", "a.jpg", scene_index=0)
    folder = store.project_dir(p.slug) / "images"
    assert (folder / "scene-01.jpg").is_file()
    store.save_asset(p.slug, "image", png(tmp_path / "b.png"), "b.png", scene_index=0)
    assert [f.name for f in folder.iterdir()] == ["scene-01.png"]


@pytest.mark.parametrize("scene_index", [None, -1, 3, 99])
def test_image_upload_needs_a_valid_scene(store, tmp_path, scene_index):
    p = store.create("Muỗi", scene_count=3)
    with pytest.raises(BadRequest, match="scene_index"):
        store.save_asset(p.slug, "image", png(tmp_path / "x.png"), "x.png", scene_index=scene_index)


def test_image_upload_rejects_non_images_and_other_formats(store, tmp_path):
    p = store.create("Muỗi")
    (tmp_path / "t.txt").write_text("không phải ảnh", encoding="utf-8")
    with pytest.raises(BadRequest, match="ảnh hợp lệ"):
        store.save_asset(p.slug, "image", tmp_path / "t.txt", "t.png", scene_index=0)
    Image.new("RGB", (8, 8)).save(tmp_path / "g.gif", format="GIF")
    with pytest.raises(BadRequest, match="PNG, JPG hoặc WEBP"):
        store.save_asset(p.slug, "image", tmp_path / "g.gif", "g.gif", scene_index=0)
    assert (tmp_path / "t.txt").exists()  # file lỗi không bị di chuyển


def test_unknown_kind(store, tmp_path):
    p = store.create("Muỗi")
    with pytest.raises(BadRequest, match="kind"):
        store.save_asset(p.slug, "video", tmp_path / "x", "x.mp4")


@needs_ffmpeg
def test_voice_and_music_upload(store, tmp_path):
    p = store.create("Muỗi")
    write_wav(tmp_path / "v.tmp", [("tone", 1.0)])
    rel, project = store.save_asset(p.slug, "voice", tmp_path / "v.tmp", "giong doc.WAV")
    assert (
        rel == "voice.wav" and project.voice.file == "voice.wav" and project.voice.trim_end is None
    )

    project.voice.trim_end = 3.0  # file giọng mới → điểm cắt cũ bị bỏ
    store.save(p.slug, project)
    write_wav(tmp_path / "v2.tmp", [("tone", 2.0)])
    _, project = store.save_asset(p.slug, "voice", tmp_path / "v2.tmp", "moi.wav")
    assert project.voice.trim_end is None

    write_wav(tmp_path / "m.tmp", [("tone", 2.0)], freq=220)
    rel, project = store.save_asset(p.slug, "music", tmp_path / "m.tmp", "nhac.wav")
    assert rel == "music.wav" and project.music.file == "music.wav"


@needs_ffmpeg
def test_audio_upload_validation(store, tmp_path):
    p = store.create("Muỗi")
    (tmp_path / "x.tmp").write_text("không phải âm thanh", encoding="utf-8")
    with pytest.raises(BadRequest, match="âm thanh hợp lệ"):
        store.save_asset(p.slug, "voice", tmp_path / "x.tmp", "x.mp3")
    write_wav(tmp_path / "ok.tmp", [("tone", 1.0)])
    with pytest.raises(BadRequest, match="Âm thanh phải là"):
        store.save_asset(p.slug, "voice", tmp_path / "ok.tmp", "x.exe")
    assert store.load(p.slug).voice is None


def test_conflict_is_a_storage_error():
    assert issubclass(Conflict, Exception) and Conflict("x").message == "x"


# ---------------------------------------------------------------- thư viện nhạc
@needs_ffmpeg
def test_music_library_add_and_list(tmp_path):
    lib = MusicLibrary(tmp_path / "library")
    assert lib.list() == []
    write_wav(tmp_path / "a.tmp", [("tone", 1.0)])
    meta = {
        "title": "The Wacky Sprint",
        "artist": "nkbloom",
        "source": "Pixabay",
        "license": "Pixabay Content License",
        "moods": ["vui", "tinh nghịch"],
    }
    e = lib.add(tmp_path / "a.tmp", "x.wav", meta)
    assert e.file == "the-wacky-sprint.wav" and (lib.root / e.file).is_file()
    write_wav(tmp_path / "b.tmp", [("tone", 1.0)])
    e2 = lib.add(tmp_path / "b.tmp", "y.wav", meta)
    assert e2.file == "the-wacky-sprint-2.wav"
    assert [i.file for i in lib.list()] == [e.file, e2.file]
    raw = json.loads(lib.index_path.read_text(encoding="utf-8"))
    assert raw[0]["moods"] == ["vui", "tinh nghịch"] and raw[0]["bpm"] is None


@needs_ffmpeg
def test_music_library_requires_credit_fields(tmp_path):
    lib = MusicLibrary(tmp_path / "library")
    write_wav(tmp_path / "a.tmp", [("tone", 1.0)])
    with pytest.raises(BadRequest, match="artist"):
        lib.add(tmp_path / "a.tmp", "x.wav", {"title": "Chỉ có tên"})
    assert lib.list() == [] and (tmp_path / "a.tmp").exists()


# ---------------------------------------------------------------- từ nhạy cảm
def test_sensitive_words_default_and_user_override(tmp_path):
    s = SensitiveStore(tmp_path / "ws")
    default = s.load()
    ids = [c.id for c in default.categories]
    assert ids[:2] == ["alcohol", "blood"] and "map" in ids
    assert next(c for c in default.categories if c.id == "drugs").level == "block"
    assert "bia" in next(c for c in default.categories if c.id == "alcohol").words

    custom = SensitiveWords.model_validate(
        {"categories": [{"id": "rieng", "level": "warn", "words": [" từ ", "khác"]}]}
    )
    s.save(custom)
    again = s.load()
    assert again.categories[0].words == ["từ", "khác"] and len(again.categories) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"categories": [{"id": "A b", "level": "warn", "words": []}]},
        {"categories": [{"id": "x", "level": "nặng", "words": []}]},
        {"categories": [{"id": "x", "level": "warn", "words": [" "]}]},
        {"categories": [{"id": "x", "level": "warn"}, {"id": "x", "level": "info"}]},
    ],
)
def test_sensitive_words_validation(bad):
    with pytest.raises(ValueError):
        SensitiveWords.model_validate(bad)


# ---------------------------------------------------------------- chỉ số cảnh <-> tên file ảnh
from hbt.storage import scene_image_stem, scene_index_from_stem  # noqa: E402


@pytest.mark.parametrize(
    "index, stem", [(0, "scene-01"), (1, "scene-02"), (8, "scene-09"), (11, "scene-12")]
)
def test_scene_index_and_image_stem_convert_both_ways(index, stem):
    assert scene_image_stem(index) == stem  # API từ 0 -> tên file từ 1
    assert scene_index_from_stem(stem) == index  # và ngược lại


def test_scene_stem_round_trip_for_every_valid_scene():
    for index in range(12):
        assert scene_index_from_stem(scene_image_stem(index)) == index


@pytest.mark.parametrize("bad", ["scene-00", "scene-1", "scene_01", "scene-ab", "voice", ""])
def test_scene_index_from_stem_rejects_other_names(bad):
    with pytest.raises(ValueError):
        scene_index_from_stem(bad)


def test_scene_index_zero_is_stored_as_scene_01(store, tmp_path):
    p = store.create("Muỗi")
    rel, _ = store.save_asset(p.slug, "image", png(tmp_path / "a.png"), "a.png", scene_index=0)
    assert rel == "images/scene-01.png"
    rel, _ = store.save_asset(p.slug, "image", png(tmp_path / "b.png"), "b.png", scene_index=7)
    assert rel == "images/scene-08.png"
