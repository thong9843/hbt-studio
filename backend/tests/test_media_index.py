"""Tests cho SQLite Media Index (workspace/studio.db)."""

from __future__ import annotations

from pathlib import Path

from hbt.shared.db.media_index import (
    delete_render,
    init_db,
    list_renders,
    sync_renders_dir,
    update_stage,
    upsert_render,
)


def test_media_index_crud_and_sync(tmp_path: Path) -> None:
    db_path = tmp_path / "studio.db"
    renders_root = tmp_path / "assets" / "renders"
    job_dir = renders_root / "postv" / "job-001"
    job_dir.mkdir(parents=True)
    video_file = job_dir / "final.mp4"
    video_file.write_bytes(b"0" * 1024)

    conn = init_db(db_path)
    conn.close()
    assert db_path.is_file()

    stats = sync_renders_dir(renders_root, db_path=db_path)
    assert stats["synced"] == 1
    assert stats["removed"] == 0

    items = list_renders(db_path=db_path)
    assert len(items) == 1
    assert items[0]["engine"] == "postv"
    assert items[0]["pipeline_stage"] == "rendered"

    updated = update_stage(
        items[0]["id"],
        "scheduled",
        scheduled_at="2026-11-15T19:00:00",
        db_path=db_path,
    )
    assert updated is not None
    assert updated["pipeline_stage"] == "scheduled"
    assert updated["scheduled_at"] == "2026-11-15T19:00:00"

    upsert_render(
        render_id="clipper:c1:clip.mp4",
        slug="c1",
        title="Clip 1",
        engine="clipper",
        file_path=tmp_path / "clip.mp4",
        source_credit="Nguồn: @test",
        db_path=db_path,
    )
    assert len(list_renders(engine="clipper", db_path=db_path)) == 1
    assert delete_render("clipper:c1:clip.mp4", db_path=db_path) is True


def test_sync_renders_from_disk_all_four_engines_and_dedup(tmp_path: Path) -> None:
    import json

    from hbt.shared.db.media_index import sync_renders_from_disk

    ws = tmp_path / "workspace"
    renders_root = tmp_path / "assets" / "renders"
    db_path = ws / "studio.db"

    # 1. Core project
    core_dir = ws / "projects" / "core-demo" / "renders" / "j1"
    core_dir.mkdir(parents=True)
    core_mp4 = core_dir / "video.mp4"
    core_mp4.write_bytes(b"core-bytes")
    (core_dir / "meta.json").write_text(json.dumps({"duration": 42.5}), encoding="utf-8")

    # Ignored build/ & chunks/ mp4s
    (ws / "projects" / "core-demo" / "renders" / "build").mkdir(parents=True)
    (ws / "projects" / "core-demo" / "renders" / "build" / "tmp.mp4").write_bytes(b"skip")

    # 2. Chatting
    chat_dir = ws / "chatting" / "chat-demo" / "renders"
    chat_dir.mkdir(parents=True)
    (ws / "chatting" / "chat-demo" / "chat.json").write_text(
        json.dumps({"title": "Chat Demo"}), encoding="utf-8"
    )
    (chat_dir / "render_123.mp4").write_bytes(b"chat-bytes")

    # 3. StickV (with legacy duplicate ID already in DB)
    sv_dir = ws / "stickv" / "sv-demo" / "renders"
    sv_dir.mkdir(parents=True)
    (ws / "stickv" / "sv-demo" / "project.json").write_text(
        json.dumps({"title": "StickV Demo"}), encoding="utf-8"
    )
    sv_mp4 = sv_dir / "final.mp4"
    sv_mp4.write_bytes(b"stickv-bytes")
    upsert_render(
        render_id="stickv:sv-demo:final.mp4",
        slug="sv-demo",
        title="StickV Legacy",
        engine="stickv",
        file_path=sv_mp4,
        db_path=db_path,
        base_dir=tmp_path,
    )

    # 4. assets/renders/postv
    postv_dir = renders_root / "postv" / "pv-job"
    postv_dir.mkdir(parents=True)
    (postv_dir / "video.mp4").write_bytes(b"postv-bytes")

    stats = sync_renders_from_disk(renders_root, db_path=db_path, workspace_dir=ws)
    assert stats["synced"] == 4
    rows = list_renders(db_path=db_path)
    assert {r["engine"] for r in rows} == {"core", "postv", "chatting", "stickv"}
    assert all("\\" not in r["file_path"] for r in rows)
    core_row = next(r for r in rows if r["engine"] == "core")
    assert core_row["duration_sec"] == 42.5
