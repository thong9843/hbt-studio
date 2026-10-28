"""API khối JSON kịch bản và sao lưu (IMPLEMENT.md 13.B4.7)."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from hbt.backups import BACKUP_KEEP, create_backup, list_backups
from tests.test_api import client  # noqa: F401


def folder_of(client, slug):  # noqa: F811
    return client.tmp / "workspace" / "projects" / slug


def project_hash(client, slug):  # noqa: F811
    return hashlib.sha256((folder_of(client, slug) / "project.json").read_bytes()).hexdigest()


@pytest.fixture
def slug(client):  # noqa: F811
    return client.post("/api/projects", json={"title": "Muỗi", "scene_count": 4}).json()["slug"]


def cards(n=4, text="Mới"):
    return [
        {"punch": i == 0, "card": {"y": "upper", "lines": [{"text": f"{text} {i}", "size": "m"}]}}
        for i in range(n)
    ]


def check(client, slug, script, **kw):  # noqa: F811
    return client.post(f"/api/projects/{slug}/script/check", json={"script": script, **kw})


def apply(client, slug, script, base_hash, **kw):  # noqa: F811
    body = {"script": script, "base_hash": base_hash, **kw}
    return client.post(f"/api/projects/{slug}/script/apply", json=body)


# ------------------------------------------------------------------ check
def test_check_writes_nothing_and_returns_hash(client, slug):  # noqa: F811
    path = folder_of(client, slug) / "project.json"
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    r = check(client, slug, cards())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["errors"] == []
    assert body["base_hash"] == project_hash(client, slug)
    assert body["counts"] == {"json": 4, "project": 4, "after": 4}
    assert {"warnings", "diff", "realign_scenes"} <= set(body)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert not (folder_of(client, slug) / "backups").exists()  # kể cả sao lưu


def test_check_reports_errors_with_200(client, slug):  # noqa: F811
    r = check(client, slug, [{"pucnh": True}, {}, {}, {}])
    assert r.status_code == 200 and r.json()["ok"] is False
    assert r.json()["errors"][0]["code"] == "K4"
    assert check(client, slug, "{ không phải json").json()["errors"][0]["code"] == "K1"


def test_check_accepts_json_text_and_extra(client, slug):  # noqa: F811
    r = check(client, slug, json.dumps(cards(6)), extra="add")
    assert r.json()["ok"] is True and r.json()["counts"]["after"] == 6
    assert check(client, slug, cards(6)).json()["ok"] is False
    assert check(client, slug, cards(6), extra="xoa").status_code == 422


def test_bad_slug_and_unknown_project(client):  # noqa: F811
    assert check(client, "Sai Slug", cards()).status_code == 422
    assert check(client, "khong-co", cards()).status_code == 404
    assert apply(client, "khong-co", cards(), "x").status_code == 404
    assert client.get("/api/projects/khong-co/backups").status_code == 404


def test_check_requires_script(client, slug):  # noqa: F811
    assert client.post(f"/api/projects/{slug}/script/check", json={}).status_code == 422


# ------------------------------------------------------------------ apply
def test_apply_backs_up_then_writes(client, slug):  # noqa: F811
    old_bytes = (folder_of(client, slug) / "project.json").read_bytes()
    h = check(client, slug, cards()).json()["base_hash"]
    r = apply(client, slug, cards(), h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project"]["scenes"][1]["card"]["lines"][0]["text"] == "Mới 1"
    assert body["project"]["scenes"][0]["punch"] is True
    saved = json.loads((folder_of(client, slug) / "project.json").read_text(encoding="utf-8"))
    assert saved == body["project"]
    assert body["base_hash"] == project_hash(client, slug) != h
    backup = folder_of(client, slug) / "backups" / f"project-{body['backup_id']}.json"
    assert backup.read_bytes() == old_bytes
    meta = json.loads(backup.with_name(backup.stem + ".meta.json").read_text(encoding="utf-8"))
    assert meta["reason"] == "apply" and meta["created_at"].endswith("Z")
    assert client.get(f"/api/projects/{slug}").json() == body["project"]


def test_apply_with_stale_hash_is_409_and_writes_nothing(client, slug):  # noqa: F811
    h = check(client, slug, cards()).json()["base_hash"]
    p = client.get(f"/api/projects/{slug}").json()
    p["title"] = "Đã đổi sau khi kiểm"
    assert client.put(f"/api/projects/{slug}", json=p).status_code == 200
    after_put = (folder_of(client, slug) / "project.json").read_bytes()
    r = apply(client, slug, cards(), h)
    assert r.status_code == 409 and "kiểm lại" in r.json()["detail"]
    assert (folder_of(client, slug) / "project.json").read_bytes() == after_put
    assert not (folder_of(client, slug) / "backups").exists()
    assert apply(client, slug, cards(), "").status_code == 409


def test_apply_returns_new_hash_usable_for_next_apply(client, slug):  # noqa: F811
    h = check(client, slug, cards()).json()["base_hash"]
    first = apply(client, slug, cards(), h).json()
    assert apply(client, slug, cards(text="Hai"), h).status_code == 409  # hash cũ
    second = apply(client, slug, cards(text="Hai"), first["base_hash"])
    assert second.status_code == 200
    assert second.json()["project"]["scenes"][0]["card"]["lines"][0]["text"] == "Hai 0"


def test_apply_is_refused_while_rendering(client, slug, monkeypatch):  # noqa: F811
    h = check(client, slug, cards()).json()["base_hash"]
    before = (folder_of(client, slug) / "project.json").read_bytes()
    monkeypatch.setattr(client.app.state.hbt.jobs, "is_busy", lambda s: True)
    r = apply(client, slug, cards(), h)
    assert r.status_code == 409 and "dựng" in r.json()["detail"]
    assert (folder_of(client, slug) / "project.json").read_bytes() == before
    assert not (folder_of(client, slug) / "backups").exists()
    assert check(client, slug, cards()).status_code == 200  # kiểm vẫn được


def test_apply_with_errors_is_422_and_keeps_the_old_project(client, slug):  # noqa: F811
    h = check(client, slug, cards()).json()["base_hash"]
    before = (folder_of(client, slug) / "project.json").read_bytes()
    r = apply(client, slug, [{"image": "x.png"}, {}, {}, {}], h)
    assert r.status_code == 422
    assert "detail" in r.json() and r.json()["errors"][0]["code"] == "K4"
    assert (folder_of(client, slug) / "project.json").read_bytes() == before
    assert not (folder_of(client, slug) / "backups").exists()


def test_apply_with_extra_add_and_trim(client, slug):  # noqa: F811
    h = check(client, slug, cards(6), extra="add").json()["base_hash"]
    r = apply(client, slug, cards(6), h, extra="add")
    assert r.status_code == 200 and len(r.json()["project"]["scenes"]) == 6
    h2 = r.json()["base_hash"]
    r2 = apply(client, slug, cards(8), h2, extra="trim")
    assert r2.status_code == 200 and len(r2.json()["project"]["scenes"]) == 6


# ------------------------------------------------------------------ backups
def test_backups_list_newest_first(client, slug):  # noqa: F811
    assert client.get(f"/api/projects/{slug}/backups").json() == []
    ids = []
    for i in range(3):
        h = project_hash(client, slug)
        ids.append(apply(client, slug, cards(text=f"L{i}"), h).json()["backup_id"])
    listed = client.get(f"/api/projects/{slug}/backups").json()
    assert [b["id"] for b in listed] == ids[::-1]
    assert all(b["reason"] == "apply" and b["created_at"] for b in listed)


def test_restore_returns_data_before_apply_and_backs_up_current(client, slug):  # noqa: F811
    original = (folder_of(client, slug) / "project.json").read_bytes()
    h0 = project_hash(client, slug)
    applied = apply(client, slug, cards(), h0).json()
    applied_bytes = (folder_of(client, slug) / "project.json").read_bytes()

    r = client.post(f"/api/projects/{slug}/backups/{applied['backup_id']}/restore")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (folder_of(client, slug) / "project.json").read_bytes() == original
    assert body["project"] == json.loads(original) and body["base_hash"] == h0
    # bản vừa bị thay đã được sao lưu với reason "restore"
    kept = folder_of(client, slug) / "backups" / f"project-{body['backup_id']}.json"
    assert kept.read_bytes() == applied_bytes
    listed = {b["id"]: b for b in client.get(f"/api/projects/{slug}/backups").json()}
    assert listed[body["backup_id"]]["reason"] == "restore"
    assert listed[applied["backup_id"]]["reason"] == "apply"
    # khôi phục được cả bản "restore" (hoàn tác việc hoàn tác)
    back = client.post(f"/api/projects/{slug}/backups/{body['backup_id']}/restore")
    assert back.status_code == 200 and back.json()["project"] == applied["project"]


def test_restore_is_refused_while_rendering(client, slug, monkeypatch):  # noqa: F811
    bid = apply(client, slug, cards(), project_hash(client, slug)).json()["backup_id"]
    now = (folder_of(client, slug) / "project.json").read_bytes()
    monkeypatch.setattr(client.app.state.hbt.jobs, "is_busy", lambda s: True)
    r = client.post(f"/api/projects/{slug}/backups/{bid}/restore")
    assert r.status_code == 409
    assert (folder_of(client, slug) / "project.json").read_bytes() == now
    assert len(list_backups(folder_of(client, slug))) == 1  # không sao lưu thêm


@pytest.mark.parametrize(
    "bad", ["20261027", "20261027-101010.json", "2026-10-27", "abc", "1" * 8 + "-" + "2" * 5]
)
def test_restore_rejects_malformed_ids(client, slug, bad):  # noqa: F811
    r = client.post(f"/api/projects/{slug}/backups/{bad}/restore")
    assert r.status_code == 422, (bad, r.status_code)


def test_restore_ids_with_path_separators_never_reach_the_disk(client, slug):  # noqa: F811
    secret = folder_of(client, slug).parent / "secret.json"
    secret.write_text(json.dumps({"x": 1}), encoding="utf-8")
    for bad in ("..", "..%2F..%2Fsecret", "%2E%2E%2Fsecret", "..%5Csecret", "../secret"):
        r = client.post(f"/api/projects/{slug}/backups/{bad}/restore")
        assert r.status_code in (404, 422), (bad, r.status_code)
    assert not (folder_of(client, slug) / "backups").exists()


def test_restore_unknown_id_is_404(client, slug):  # noqa: F811
    r = client.post(f"/api/projects/{slug}/backups/20200101-000000/restore")
    assert r.status_code == 404


def test_restore_corrupt_or_foreign_backup_is_422(client, slug):  # noqa: F811
    folder = folder_of(client, slug)
    (folder / "backups").mkdir()
    (folder / "backups" / "project-20200101-000000.json").write_text("{hỏng", encoding="utf-8")
    foreign = json.loads((folder / "project.json").read_text(encoding="utf-8"))
    foreign["slug"] = "project-khac"
    (folder / "backups" / "project-20200101-000001.json").write_text(
        json.dumps(foreign), encoding="utf-8"
    )
    before = (folder / "project.json").read_bytes()
    for bid in ("20200101-000000", "20200101-000001"):
        assert client.post(f"/api/projects/{slug}/backups/{bid}/restore").status_code == 422
    assert (folder / "project.json").read_bytes() == before


def test_keeps_only_ten_backups_and_removes_pairs(client, slug):  # noqa: F811
    folder = folder_of(client, slug)
    start = datetime(2026, 10, 27, 8, 0, 0, tzinfo=UTC)
    ids = [create_backup(folder, "apply", now=start + timedelta(seconds=i)) for i in range(11)]
    assert len(set(ids)) == 11
    listed = [b["id"] for b in client.get(f"/api/projects/{slug}/backups").json()]
    assert len(listed) == BACKUP_KEEP == 10
    assert listed == ids[:0:-1]  # mới nhất trước, bản cũ nhất đã bị xoá
    names = sorted(p.name for p in (folder / "backups").iterdir())
    assert len(names) == 20  # 10 bản + 10 file phụ
    assert f"project-{ids[0]}.json" not in names and f"project-{ids[0]}.meta.json" not in names


def test_same_second_gets_numeric_suffix_and_sorts_correctly(client, slug):  # noqa: F811
    folder = folder_of(client, slug)
    t = datetime(2026, 10, 27, 8, 0, 0, tzinfo=UTC)
    ids = [create_backup(folder, "apply", now=t) for _ in range(3)]
    assert ids == ["20261027-080000", "20261027-080000-1", "20261027-080000-2"]
    later = create_backup(folder, "apply", now=t + timedelta(seconds=1))
    assert [b["id"] for b in list_backups(folder)] == [later, *ids[::-1]]


def test_numeric_suffix_sorts_numerically(client, slug):  # noqa: F811
    folder = folder_of(client, slug)
    t = datetime(2026, 10, 27, 8, 0, 0, tzinfo=UTC)
    ids = [create_backup(folder, "apply", now=t) for _ in range(10)]
    assert [b["id"] for b in list_backups(folder)][0] == ids[-1] == "20261027-080000-9"
    # "-10" phải đứng trước "-9", không phải sau
    create_backup(folder, "apply", now=t)
    assert list_backups(folder)[0]["id"] == "20261027-080000-10"


def test_missing_sidecar_gives_null_reason(client, slug):  # noqa: F811
    bid = apply(client, slug, cards(), project_hash(client, slug)).json()["backup_id"]
    (folder_of(client, slug) / "backups" / f"project-{bid}.meta.json").unlink()
    item = client.get(f"/api/projects/{slug}/backups").json()[0]
    assert item["id"] == bid and item["reason"] is None and item["created_at"]
    assert client.post(f"/api/projects/{slug}/backups/{bid}/restore").status_code == 200


def test_restore_still_works_when_the_backup_is_the_oldest_of_ten(client, slug):  # noqa: F811
    folder = folder_of(client, slug)
    t = datetime(2026, 10, 27, 8, 0, 0, tzinfo=UTC)
    ids = [create_backup(folder, "apply", now=t + timedelta(seconds=i)) for i in range(10)]
    oldest = ids[0]
    expected = (folder / "backups" / f"project-{oldest}.json").read_bytes()
    r = client.post(f"/api/projects/{slug}/backups/{oldest}/restore")
    assert r.status_code == 200  # sao lưu mới dọn mất bản này, nhưng đã đọc trước
    assert (folder / "project.json").read_bytes() == expected


# ------------------------------------------------------------------ nhân bản, dọn file tạm
def test_duplicate_does_not_copy_backups(client, slug):  # noqa: F811
    apply(client, slug, cards(), project_hash(client, slug))
    assert (folder_of(client, slug) / "backups").is_dir()
    copy = client.post(f"/api/projects/{slug}/duplicate").json()["slug"]
    assert copy != slug
    assert (folder_of(client, copy) / "project.json").is_file()
    assert not (folder_of(client, copy) / "backups").exists()
    assert (folder_of(client, slug) / "backups").is_dir()  # bản gốc còn nguyên


def test_clean_build_keeps_backups(client, slug):  # noqa: F811
    folder = folder_of(client, slug)
    bid = apply(client, slug, cards(), project_hash(client, slug)).json()["backup_id"]
    (folder / "build").mkdir()
    (folder / "build" / "tam.bin").write_bytes(b"x" * 100)
    r = client.post(f"/api/projects/{slug}/build/clean")
    assert r.status_code == 200 and r.json()["failed"] == 0
    assert not (folder / "build" / "tam.bin").exists()
    assert (folder / "backups" / f"project-{bid}.json").is_file()
    assert (folder / "backups" / f"project-{bid}.meta.json").is_file()
