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
