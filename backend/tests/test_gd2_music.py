"""Lưu `draft.json` và chọn nhạc theo `music_mood` (E5). Thư viện giả nằm trong tmp_path,
không bao giờ chạm `library/` thật; chọn nhạc chỉ đọc, không ghi index."""

import json

import pytest

from hbt.gd2.draft import split_draft
from hbt.gd2.music_pick import norm_mood, pick_music
from hbt.gd2.store import build_draft_doc, read_draft, write_draft
from hbt.storage import NotFound
from tests.gd2_kit import sample


def entry(id_, moods, file="a.mp3", **kw):
    return {
        "id": id_,
        "file": file,
        "title": id_,
        "artist": "ai đó",
        "source": "Pixabay",
        "license": "Pixabay",
        "moods": moods,
        **kw,
    }


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "library" / "music"
    root.mkdir(parents=True)
    for f in ("a.mp3", "b.mp3"):
        (root / f).write_bytes(b"ID3")

    def write(items):
        (root / "index.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return root

    return write


def snapshot(root):
    p = root / "index.json"
    return p.read_bytes(), p.stat().st_mtime_ns


def test_norm_mood():
    assert norm_mood("  Tò  Mò ") == "to mo"
    assert norm_mood("Đầy hồi hộp") == "day hoi hop"


def test_pick_by_mood_ignores_case_and_accents(lib):
    root = lib([entry("calm", ["trầm lắng"]), entry("curious", ["Tò Mò", "vui"], file="b.mp3")])
    pick = pick_music(root, "to mo")
    assert pick.entry.id == "curious" and pick.path.name == "b.mp3" and pick.warning is None
    assert pick_music(root, "TÒ MÒ").entry.id == "curious"


def test_first_match_in_index_order(lib):
    root = lib([entry("one", ["tò mò"]), entry("two", ["tò mò"], file="b.mp3")])
    assert pick_music(root, "tò mò").entry.id == "one"


def test_no_match_or_empty_mood_leaves_blank(lib):
    root = lib([entry("calm", ["trầm lắng"]), entry("nomood", [])])
    assert pick_music(root, "hồi hộp").entry is None
    assert pick_music(root, "").entry is None
    assert pick_music(root, "   ").entry is None


def test_missing_index_or_file(tmp_path, lib):
    assert pick_music(tmp_path / "nope", "tò mò").entry is None
    root = lib([entry("gone", ["tò mò"], file="missing.mp3")])
    assert pick_music(root, "tò mò").entry is None


def test_entry_without_id_skips_pick_and_never_writes(lib):
    bad = entry("x", ["tò mò"])
    del bad["id"]
    root = lib([bad, entry("curious", ["tò mò"])])
    before = snapshot(root)
    pick = pick_music(root, "tò mò")
    assert pick.entry is None and "thiếu id" in pick.warning
    assert snapshot(root) == before  # index không bị gán id / ghi lại


def test_pick_never_writes_index(lib):
    root = lib([entry("curious", ["tò mò"])])
    before = snapshot(root)
    pick_music(root, "tò mò")
    pick_music(root, "khác")
    assert snapshot(root) == before


def test_broken_index_warns(lib, tmp_path):
    root = lib([])
    (root / "index.json").write_text("{không phải json", encoding="utf-8")
    pick = pick_music(root, "tò mò")
    assert pick.entry is None and pick.warning


def test_path_escape_rejected(lib, tmp_path):
    (tmp_path / "library" / "outside.mp3").write_bytes(b"x")
    root = lib([entry("sneaky", ["tò mò"], file="../outside.mp3")])
    assert pick_music(root, "tò mò").entry is None  # MusicEntry từ chối '..'


def test_draft_doc_roundtrip(tmp_path):
    split = split_draft(sample())
    doc = build_draft_doc(split, [True, True, False])
    assert doc["draft"] == 1 and doc["images_approved"] is False
    assert doc["scenes"][2] == {
        "image_prompt": "person jogging at dusk near a pond, vertical 9:16",
        "image_prompt_ok": False,
    }
    write_draft(tmp_path, doc)
    assert not (tmp_path / "draft.json.tmp").exists()
    assert read_draft(tmp_path) == doc
    assert "Vì sao" in (tmp_path / "draft.json").read_text(encoding="utf-8")  # không escape


def test_read_missing_draft(tmp_path):
    with pytest.raises(NotFound):
        read_draft(tmp_path)
