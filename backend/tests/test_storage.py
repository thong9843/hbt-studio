import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from hbt.library import MusicLibrary
from hbt.models import Thumbnail
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


def test_duplicate_copies_media_but_not_build_or_renders(store, tmp_path):
    p = store.create("Muỗi")
    rel, _ = store.save_asset(p.slug, "image", png(tmp_path / "img.png"), "a.png", scene_index=0)
    d = store.project_dir(p.slug)
    (d / "build").mkdir()
    (d / "build" / "voice.wav").write_bytes(b"x")
    (d / "renders" / "j1").mkdir(parents=True)
    (d / "renders" / "j1" / "video.mp4").write_bytes(b"x")

    copy = store.duplicate(p.slug)
    assert copy.slug == "muoi-ban-sao" and copy.title == "Muỗi (bản sao)"
    cd = store.project_dir(copy.slug)
    assert (cd / rel).is_file()
    assert not (cd / "build").exists() and not (cd / "renders").exists()
    assert store.load(copy.slug).scenes[0].image == rel
    assert store.load(p.slug).slug == p.slug  # bản gốc không đổi
    assert store.duplicate(p.slug, title="Muỗi 2").slug == "muoi-2"


# ---------------------------------------------------------------- danh sách
def test_list_projects_fields_and_order(store, tmp_path):
    a = store.create("Một")
    b = store.create("Hai")
    rel, _ = store.save_asset(a.slug, "image", png(tmp_path / "img.png"), "a.png", scene_index=0)
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
    assert by["mot"]["thumb"] == f"projects/mot/{rel}"
    assert by["hai"]["thumb"] is None and by["mot"]["last_render"] is None
    assert by["hai"]["last_render"] == {
        "job_id": "job1",
        "preview": True,
        "fps": 30,
        "duration": 12.5,
        "render_seconds": None,  # bản dựng cũ chưa có hai trường của B′
        "align_cached": None,
        "trimmed_tail_seconds": None,
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
    f = png(tmp_path / "up.bin")
    expected_hash = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    rel, project = store.save_asset(p.slug, "image", f, "a.png", scene_index=1)
    assert rel == f"images/{expected_hash}.png" and project.scenes[1].image == rel
    assert (store.project_dir(p.slug) / rel).is_file() and not (tmp_path / "up.bin").exists()
    assert store.load(p.slug).scenes[1].image == rel


def test_image_replacement_removes_the_old_file_with_another_extension(store, tmp_path):
    p = store.create("Muỗi")
    Image.new("RGB", (32, 32)).save(tmp_path / "a.jpg", format="JPEG")
    rel_a, _ = store.save_asset(p.slug, "image", tmp_path / "a.jpg", "a.jpg", scene_index=0)
    folder = store.project_dir(p.slug) / "images"
    assert (folder / Path(rel_a).name).is_file()
    rel_b, _ = store.save_asset(p.slug, "image", png(tmp_path / "b.png"), "b.png", scene_index=0)
    assert [f.name for f in folder.iterdir()] == [Path(rel_b).name]


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
    assert e.id == "the-wacky-sprint"
    assert e.file == "the-wacky-sprint.wav" and (lib.root / e.file).is_file()
    write_wav(tmp_path / "b.tmp", [("tone", 1.0)])
    e2 = lib.add(tmp_path / "b.tmp", "y.wav", meta)
    assert e2.file == "the-wacky-sprint-2.wav" and e2.id == "the-wacky-sprint-2"
    assert [i.file for i in lib.list()] == [e.file, e2.file]
    raw = json.loads(lib.index_path.read_text(encoding="utf-8"))
    assert raw[0]["moods"] == ["vui", "tinh nghịch"] and raw[0]["bpm"] is None


def _entry(**over):
    base = {"id": "a", "file": "a.mp3", "title": "A", "artist": "B", "source": "S", "license": "L"}
    return {**base, **over}


def _lib_with_index(tmp_path, data):
    lib = MusicLibrary(tmp_path / "library")
    lib.root.mkdir(parents=True)
    lib.index_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return lib


def test_music_id_strips_vietnamese_marks_and_d(tmp_path):
    item = _entry(title="Đường về nhà")
    del item["id"]
    lib = _lib_with_index(tmp_path, [item])
    assert [e.id for e in lib.list()] == ["duong-ve-nha"]


def test_music_missing_ids_assigned_in_order_and_saved_once(tmp_path):
    items = [_entry(file=f"{i}.mp3", title="Bài hay") for i in range(3)]
    for it in items:
        del it["id"]
    lib = _lib_with_index(tmp_path, items)
    assert [e.id for e in lib.list()] == ["bai-hay", "bai-hay-2", "bai-hay-3"]
    saved = json.loads(lib.index_path.read_text(encoding="utf-8"))
    assert [e["id"] for e in saved] == ["bai-hay", "bai-hay-2", "bai-hay-3"]
    before = lib.index_path.read_text(encoding="utf-8")
    assert [e.id for e in lib.list()] == ["bai-hay", "bai-hay-2", "bai-hay-3"]
    assert lib.index_path.read_text(encoding="utf-8") == before  # lần sau không ghi lại


def test_music_assigned_id_avoids_existing_ids(tmp_path):
    keep = _entry(id="bai-hay", file="k.mp3", title="Khác")
    new = _entry(file="n.mp3", title="Bài hay")
    del new["id"]
    lib = _lib_with_index(tmp_path, [new, keep])
    assert [e.id for e in lib.list()] == ["bai-hay-2", "bai-hay"]


def test_music_duplicate_ids_rejected(tmp_path):
    lib = _lib_with_index(tmp_path, [_entry(), _entry(file="b.mp3")])
    with pytest.raises(BadRequest, match="trùng"):
        lib.list()


@pytest.mark.parametrize(
    "file",
    ["funny/the-wacky-sprint.mp3", "a/b/c.ogg", "x.flac", "x.aac", "x.opus"],
)
def test_music_file_relative_paths_allowed(tmp_path, file):
    lib = _lib_with_index(tmp_path, [_entry(file=file)])
    assert lib.list()[0].file == file


@pytest.mark.parametrize(
    "file",
    [
        "/etc/x.mp3",
        "\\x.mp3",
        "C:\\x.mp3",
        "C:/x.mp3",
        "C:x.mp3",
        "../x.mp3",
        "a/../x.mp3",
        "a\\b.mp3",
        "a//b.mp3",
        "./x.mp3",
        "x.exe",
        "x",
        "",
    ],
)
def test_music_file_rejects_absolute_drive_dotdot_backslash(tmp_path, file):
    lib = _lib_with_index(tmp_path, [_entry(file=file)])
    with pytest.raises(BadRequest, match="index.json"):
        lib.list()


def test_music_find_by_id(tmp_path):
    lib = _lib_with_index(tmp_path, [_entry(id="a", file="sub/a.mp3")])
    (lib.root / "sub").mkdir()
    (lib.root / "sub" / "a.mp3").write_bytes(b"x")
    entry, path = lib.find("a")
    assert entry.id == "a" and path == (lib.root / "sub" / "a.mp3").resolve()
    with pytest.raises(NotFound):
        lib.find("khong-co")
    for bad in ("A", "a.mp3", "../a", "a/b", "C:", ""):
        with pytest.raises(Unprocessable):
            lib.find(bad)
    (lib.root / "sub" / "a.mp3").unlink()
    with pytest.raises(NotFound):
        lib.find("a")


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


def test_scene_image_is_named_by_content_hash(store, tmp_path):
    p = store.create("Muỗi")
    img_a = png(tmp_path / "a.png", color=(10, 20, 30))
    ha = hashlib.sha256(img_a.read_bytes()).hexdigest()[:16]
    rel_a, _ = store.save_asset(p.slug, "image", img_a, "a.png", scene_index=0)
    assert rel_a == f"images/{ha}.png"

    img_b = png(tmp_path / "b.png", color=(40, 50, 60))
    hb = hashlib.sha256(img_b.read_bytes()).hexdigest()[:16]
    rel_b, _ = store.save_asset(p.slug, "image", img_b, "b.png", scene_index=7)
    assert rel_b == f"images/{hb}.png"


def test_reorder_and_upload_preserves_other_image_hashes(store, tmp_path):
    p = store.create("Muỗi", scene_count=3)
    imgs = [png(tmp_path / f"c{i}.png", color=(i * 50 + 10, 100, 150)) for i in range(3)]
    rels = []
    for i, img in enumerate(imgs):
        r, _ = store.save_asset(p.slug, "image", img, f"c{i}.png", scene_index=i)
        rels.append(r)

    images_dir = store.project_dir(p.slug) / "images"

    def content_hash(rel):
        return hashlib.sha256((images_dir / Path(rel).name).read_bytes()).hexdigest()

    before = {r: content_hash(r) for r in rels}  # băm NỘI DUNG file trên đĩa

    # Đổi thứ tự: [2, 0, 1]
    p_reordered = store.reorder_scenes(p.slug, [2, 0, 1])
    assert [s.image for s in p_reordered.scenes] == [rels[2], rels[0], rels[1]]

    # Tải ảnh mới cho cảnh 0 (vốn là cảnh 2 cũ)
    new_img = png(tmp_path / "new.png", color=(255, 255, 255))
    new_hash = hashlib.sha256(new_img.read_bytes()).hexdigest()[:16]
    new_rel, p_updated = store.save_asset(p.slug, "image", new_img, "new.png", scene_index=0)
    assert new_rel == f"images/{new_hash}.png"

    # Hash ảnh của cảnh 1 và cảnh 2 không đổi
    assert p_updated.scenes[1].image == rels[0]
    assert p_updated.scenes[2].image == rels[1]
    # ...và nội dung file trên đĩa của hai cảnh đó đúng bằng trước khi đổi thứ tự
    assert content_hash(p_updated.scenes[1].image) == before[rels[0]]
    assert content_hash(p_updated.scenes[2].image) == before[rels[1]]
    # tên file khớp với hash nội dung thật (không chỉ được đặt lúc lưu)
    for scene in p_updated.scenes:
        assert Path(scene.image).stem == content_hash(scene.image)[:16]


def test_delete_scene_removes_unreferenced_image_and_keeps_others(store, tmp_path):
    p = store.create("Muỗi", scene_count=4)
    imgs = [png(tmp_path / f"img{i}.png", color=(i * 40 + 20, 80, 120)) for i in range(4)]
    rels = []
    for i, img in enumerate(imgs):
        r, _ = store.save_asset(p.slug, "image", img, f"img{i}.png", scene_index=i)
        rels.append(r)

    images_dir = store.project_dir(p.slug) / "images"
    assert (images_dir / Path(rels[1]).name).is_file()

    # Xoá cảnh 1
    p_after = store.delete_scene(p.slug, 1)
    assert len(p_after.scenes) == 3

    # Ảnh của cảnh bị xoá bị dọn khỏi thư mục images/
    assert not (images_dir / Path(rels[1]).name).exists()

    # Ảnh của các cảnh khác còn nguyên
    for idx in (0, 2, 3):
        assert (images_dir / Path(rels[idx]).name).is_file()


def test_delete_scene_clamps_thumbnail_and_enforces_limits(store):
    p = store.create("Muỗi", scene_count=4)
    p.thumbnail = Thumbnail(scene=4, lines=["A", "B"], series="", accent="#FFD43B")
    store.save(p.slug, p)

    # Xoá cảnh 0 -> thumbnail.scene giảm từ 4 xuống 3
    p = store.delete_scene(p.slug, 0)
    assert len(p.scenes) == 3
    assert p.thumbnail.scene == 3

    # Số cảnh hiện tại là 3 (MIN_SCENES = 3), xoá tiếp sẽ báo lỗi
    with pytest.raises(BadRequest, match="ít nhất 3 cảnh"):
        store.delete_scene(p.slug, 0)


def test_legacy_scene_01_migrates_on_load(store, tmp_path):
    p = store.create("Muỗi", scene_count=3)
    folder = store.project_dir(p.slug)
    images_dir = folder / "images"

    img_file = png(images_dir / "scene-01.png", color=(123, 45, 67))
    content_hash = hashlib.sha256(img_file.read_bytes()).hexdigest()[:16]

    # Ghi đè project.json với dạng cũ "images/scene-01.png"
    p.scenes[0].image = "images/scene-01.png"
    # Ghi trực tiếp vào file json mà không qua save() để giữ nguyên tên cũ
    (folder / "project.json").write_text(json.dumps(p.model_dump(mode="json")), encoding="utf-8")

    # Mở project: tự chuyển sang hash
    loaded = store.load(p.slug)
    assert loaded.scenes[0].image == f"images/{content_hash}.png"
    assert (images_dir / f"{content_hash}.png").is_file()
    assert not (images_dir / "scene-01.png").exists()

    # Đọc lại ảnh xem đúng màu không
    pix = Image.open(images_dir / f"{content_hash}.png").getpixel((0, 0))
    assert pix == (123, 45, 67)


def test_load_does_not_read_images_that_are_already_hash_named(store, tmp_path, monkeypatch):
    p = store.create("Mười hai", scene_count=12)
    for i in range(12):
        img = png(tmp_path / f"m{i}.png", color=(i * 20, 90, 140))
        store.save_asset(p.slug, "image", img, f"m{i}.png", scene_index=i)
    images_dir = store.project_dir(p.slug) / "images"
    assert len(list(images_dir.iterdir())) == 12

    reads = []
    real_read_bytes = Path.read_bytes

    def spy(self):
        if images_dir in self.parents:
            reads.append(self.name)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    monkeypatch.setattr("hbt.storage.content_hash_16", lambda data: pytest.fail("đã băm ảnh"))
    loaded = store.load(p.slug)
    assert len(loaded.scenes) == 12 and reads == []


def test_load_still_migrates_a_scene_name_image(store, tmp_path):
    p = store.create("Cũ", scene_count=3)
    folder = store.project_dir(p.slug)
    (folder / "images").mkdir(exist_ok=True)
    png(folder / "images" / "scene-01.png")
    p.scenes[0].image = "images/scene-01.png"
    (folder / "project.json").write_text(p.model_dump_json(), encoding="utf-8")
    loaded = store.load(p.slug)
    assert loaded.scenes[0].image != "images/scene-01.png"
    assert (folder / loaded.scenes[0].image).is_file()


def test_cleanup_only_removes_app_named_unreferenced_images(store, tmp_path, caplog):
    p = store.create("Dọn", scene_count=3)
    keep = png(tmp_path / "k.png", color=(10, 20, 30))
    rel, _ = store.save_asset(p.slug, "image", keep, "k.png", scene_index=0)
    images_dir = store.project_dir(p.slug) / "images"
    (images_dir / "0123456789abcdef.png").write_bytes(b"x")  # tên hash, không ai dùng
    (images_dir / "scene-02.jpg").write_bytes(b"x")  # dạng cũ, không ai dùng
    (images_dir / "ghi-chu.txt").write_text("của tôi", encoding="utf-8")
    (images_dir / "anh-cua-toi.png").write_bytes(b"x")

    with caplog.at_level("WARNING"):
        store.save(p.slug, store.load(p.slug))

    names = {f.name for f in images_dir.iterdir()}
    assert names == {Path(rel).name, "ghi-chu.txt", "anh-cua-toi.png"}
    assert "ghi-chu.txt" in caplog.text and "anh-cua-toi.png" in caplog.text


def test_upload_normalises_extension_so_load_does_not_rehash(store, tmp_path, monkeypatch):
    p = store.create("Đuôi hoa", scene_count=3)
    Image.new("RGB", (32, 32), (9, 9, 9)).save(tmp_path / "x.bin", format="JPEG")
    rel_jpg, _ = store.save_asset(p.slug, "image", tmp_path / "x.bin", "ANH.JPEG", scene_index=0)
    rel_png, _ = store.save_asset(
        p.slug, "image", png(tmp_path / "y.bin"), "ANH.PNG", scene_index=1
    )
    assert rel_jpg.endswith(".jpg") and rel_png.endswith(".png")

    monkeypatch.setattr("hbt.storage.content_hash_16", lambda data: pytest.fail("đã băm lại ảnh"))
    loaded = store.load(p.slug)
    assert [s.image for s in loaded.scenes][:2] == [rel_jpg, rel_png]
