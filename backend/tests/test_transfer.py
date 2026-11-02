import json
import zipfile
from pathlib import Path

import pytest

import cli
from hbt import transfer


def make_tree(root: Path) -> None:
    files = {
        "library/backgrounds/index.json": b'{"clips": 1}',
        "library/backgrounds/a.mp4": b"video-a",
        "library/music/index.json": b"[]",
        "library/music/m.mp3": b"music",
        "models/hf_vieneu/sub/w.bin": b"weights",
        "models/hf_vieneu/sub/w.bin.lock": b"skip",
        "workspace/samples/muoi/project.json": b"{}",
        "workspace/samples/muoi/__pycache__/x.pyc": b"skip",
        "library/outro/voice.wav": b"not-packed",
    }
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


TRACKED = {"library/backgrounds/index.json", "library/music/index.json"}


@pytest.fixture
def roots(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    make_tree(src)
    dst.mkdir()
    return src, dst, tmp_path / "out"


def test_pack_lists_only_media_groups_and_skips_locks(roots):
    src, _, out = roots
    manifest = transfer.pack(src, out)
    paths = {e["path"] for g in manifest["groups"].values() for e in g["files"]}
    assert "models/hf_vieneu/sub/w.bin" in paths and "library/music/m.mp3" in paths
    assert not any(p.endswith((".lock", ".pyc")) or "outro" in p for p in paths)
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == manifest
    with zipfile.ZipFile(out / "music.zip") as zf:
        assert sorted(zf.namelist()) == ["library/music/index.json", "library/music/m.mp3"]


def test_unpack_round_trip_keeps_tracked_files_and_index_needs_the_flag(roots):
    src, dst, out = roots
    transfer.pack(src, out)
    (dst / "library/music").mkdir(parents=True)
    (dst / "library/music/index.json").write_bytes(b"LOCAL")
    report = transfer.unpack(dst, out, tracked=TRACKED)
    assert (dst / "library/music/m.mp3").read_bytes() == b"music"
    assert (dst / "models/hf_vieneu/sub/w.bin").read_bytes() == b"weights"
    assert (dst / "library/music/index.json").read_bytes() == b"LOCAL"  # file git theo dõi
    assert not (dst / "library/backgrounds/index.json").exists()
    assert sorted(report.protected) == sorted(TRACKED)
    again = transfer.unpack(dst, out, tracked=TRACKED)  # chạy lại: không ghi gì
    assert again.written == [] and len(again.same) == 4
    with_index = transfer.unpack(dst, out, tracked=TRACKED, with_index=True)
    assert (dst / "library/music/index.json").read_bytes() == b"[]"
    assert sorted(with_index.written) == sorted(TRACKED)


def test_unpack_does_not_overwrite_a_different_untracked_file_without_force(roots):
    src, dst, out = roots
    transfer.pack(src, out)
    target = dst / "library/music/m.mp3"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"mine")
    report = transfer.unpack(dst, out, tracked=TRACKED, groups=["music"])
    assert report.differs == ["library/music/m.mp3"] and target.read_bytes() == b"mine"
    transfer.unpack(dst, out, tracked=TRACKED, groups=["music"], force=True)
    assert target.read_bytes() == b"music"


def test_unpack_rejects_a_zip_whose_content_no_longer_matches_the_sha256(roots):
    src, dst, out = roots
    manifest = transfer.pack(src, out, ["music"])
    manifest["groups"]["music"]["files"][1]["sha256"] = "0" * 64
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(transfer.TransferError, match="Sai sha256"):
        transfer.unpack(dst, out, tracked=set())
    assert not (dst / "library/music/m.mp3").exists()
    assert not list(dst.rglob("*.part"))


@pytest.mark.parametrize(
    "bad", ["../evil.txt", "/abs/x", "library/music/../../x", "C:/x", "other/a"]
)
def test_unpack_rejects_unsafe_or_foreign_paths(roots, bad):
    _, dst, out = roots
    out.mkdir()
    with zipfile.ZipFile(out / "g.zip", "w") as zf:
        zf.writestr("a.txt", "x")
    manifest = {"groups": {"g": {"zip": "g.zip", "files": [{"path": bad, "sha256": "0"}]}}}
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(transfer.TransferError):
        transfer.unpack(dst, out, tracked=set())


def test_unknown_group_and_missing_manifest(roots):
    src, dst, out = roots
    with pytest.raises(transfer.TransferError, match="Nhóm không có"):
        transfer.pack(src, out, ["nope"])
    with pytest.raises(transfer.TransferError, match="manifest"):
        transfer.unpack(dst, out, tracked=set())


def test_cli_parser_and_dry_run(monkeypatch, capsys, roots):
    src, _, _ = roots
    monkeypatch.setattr(cli, "REPO_ROOT", src)
    assert cli.main(["pack-media", "--dry-run", "--groups", "music"]) == 0
    assert "music: 2 file" in capsys.readouterr().out
    args = cli.build_parser().parse_args(["unpack-media", "x", "--with-index", "--force"])
    assert args.src == Path("x") and args.with_index and args.force
