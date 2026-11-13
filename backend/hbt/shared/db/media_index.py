"""Chỉ mục SQLite quản lý toàn bộ video đã xuất trong workspace/studio.db."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = REPO_ROOT / "workspace" / "studio.db"
PIPELINE_STAGES = ("draft", "rendered", "edited", "scheduled", "published")
VALID_ENGINES = ("core", "postv", "chatting", "clipper", "editor")


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Khởi tạo workspace/studio.db và bảng renders nếu chưa tồn tại."""
    target = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS renders (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            engine TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            cover_path TEXT DEFAULT '',
            duration_sec REAL DEFAULT 0.0,
            size_mb REAL DEFAULT 0.0,
            pipeline_stage TEXT NOT NULL DEFAULT 'rendered',
            source_credit TEXT DEFAULT '',
            scheduled_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def upsert_render(
    *,
    render_id: str,
    slug: str,
    title: str,
    engine: str,
    file_path: str | Path,
    cover_path: str | Path = "",
    duration_sec: float = 0.0,
    size_mb: float | None = None,
    pipeline_stage: str = "rendered",
    source_credit: str = "",
    scheduled_at: str = "",
    created_at: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Thêm mới hoặc cập nhật bản ghi video trong bảng renders."""
    if pipeline_stage not in PIPELINE_STAGES:
        raise ValueError(f"pipeline_stage không hợp lệ: {pipeline_stage}")
    fp = Path(file_path)
    computed_size = (
        round(fp.stat().st_size / (1024 * 1024), 2)
        if size_mb is None and fp.is_file()
        else float(size_mb or 0.0)
    )
    ts = created_at or datetime.now(timezone.utc).isoformat()
    conn = init_db(db_path)
    try:
        conn.execute(
            """
            INSERT INTO renders (
                id, slug, title, engine, file_path, cover_path,
                duration_sec, size_mb, pipeline_stage, source_credit,
                scheduled_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slug = excluded.slug,
                title = excluded.title,
                engine = excluded.engine,
                file_path = excluded.file_path,
                cover_path = excluded.cover_path,
                duration_sec = excluded.duration_sec,
                size_mb = excluded.size_mb,
                source_credit = CASE
                    WHEN excluded.source_credit != '' THEN excluded.source_credit
                    ELSE renders.source_credit
                END
            """,
            (
                render_id,
                slug,
                title,
                engine,
                str(fp),
                str(cover_path),
                float(duration_sec),
                computed_size,
                pipeline_stage,
                source_credit,
                scheduled_at,
                ts,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM renders WHERE id = ?", (render_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def list_renders(
    *,
    stage: str | None = None,
    engine: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Truy vấn danh sách video từ SQLite, lọc theo stage/engine nếu có."""
    conn = init_db(db_path)
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if stage:
            clauses.append("pipeline_stage = ?")
            params.append(stage)
        if engine:
            clauses.append("engine = ?")
            params.append(engine)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM renders {where} ORDER BY created_at DESC", params
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_stage(
    render_id: str,
    stage: str,
    scheduled_at: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Cập nhật giai đoạn Kanban (pipeline_stage) và giờ hẹn đăng."""
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"pipeline_stage không hợp lệ: {stage}")
    conn = init_db(db_path)
    try:
        if scheduled_at is not None:
            conn.execute(
                "UPDATE renders SET pipeline_stage = ?, scheduled_at = ? WHERE id = ?",
                (stage, scheduled_at, render_id),
            )
        else:
            conn.execute(
                "UPDATE renders SET pipeline_stage = ? WHERE id = ?",
                (stage, render_id),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM renders WHERE id = ?", (render_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_render(render_id: str, db_path: Path | None = None) -> bool:
    """Xoá bản ghi video khỏi chỉ mục SQLite."""
    conn = init_db(db_path)
    try:
        cur = conn.execute("DELETE FROM renders WHERE id = ?", (render_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def sync_renders_dir(renders_root: Path, db_path: Path | None = None) -> dict[str, int]:
    """Đồng bộ thư mục assets/renders/<engine>/<job_id>/ với SQLite."""
    added_or_updated = 0
    removed = 0
    existing_paths: set[str] = set()

    if renders_root.is_dir():
        for mp4 in renders_root.rglob("*.mp4"):
            if not mp4.is_file():
                continue
            existing_paths.add(str(mp4))
            rel_parts = mp4.relative_to(renders_root).parts
            engine = rel_parts[0] if len(rel_parts) >= 2 and rel_parts[0] in VALID_ENGINES else "core"
            job_id = rel_parts[1] if len(rel_parts) >= 3 else mp4.stem
            render_id = f"{engine}:{job_id}:{mp4.name}"
            cover_candidate = mp4.with_suffix(".jpg")
            cover_path = str(cover_candidate) if cover_candidate.is_file() else ""
            upsert_render(
                render_id=render_id,
                slug=job_id,
                title=mp4.stem,
                engine=engine,
                file_path=mp4,
                cover_path=cover_path,
                db_path=db_path,
            )
            added_or_updated += 1

    conn = init_db(db_path)
    try:
        rows = conn.execute("SELECT id, file_path FROM renders").fetchall()
        for r in rows:
            if r["file_path"] not in existing_paths and not Path(r["file_path"]).is_file():
                conn.execute("DELETE FROM renders WHERE id = ?", (r["id"],))
                removed += 1
        conn.commit()
    finally:
        conn.close()

    return {"synced": added_or_updated, "removed": removed}
