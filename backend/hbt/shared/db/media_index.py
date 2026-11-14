"""Chỉ mục SQLite quản lý toàn bộ video đã xuất trong workspace/studio.db."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
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
    ts = created_at or datetime.now(UTC).isoformat()
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


def sync_renders_dir(
    renders_root: Path,
    db_path: Path | None = None,
    *,
    workspace_dir: Path | None = None,
) -> dict[str, int]:
    """Đồng bộ thư mục assets/renders/<engine>/<job_id>/ và workspace với SQLite."""
    added_or_updated = 0
    removed = 0
    existing_paths: set[str] = set()

    def _index_mp4(
        mp4: Path,
        *,
        engine: str,
        slug: str,
        title: str,
        duration_sec: float = 0.0,
        publish_text: str = "",
    ) -> None:
        nonlocal added_or_updated
        resolved_str = str(mp4.resolve())
        if resolved_str in existing_paths:
            return
        existing_paths.add(resolved_str)
        render_id = f"{engine}:{slug}:{mp4.parent.name}:{mp4.name}"
        cover_candidate = mp4.parent / "cover_9x16.jpg"
        if not cover_candidate.is_file():
            cover_candidate = mp4.with_suffix(".jpg")
        cover_path = str(cover_candidate.resolve()) if cover_candidate.is_file() else ""
        mtime_iso = datetime.fromtimestamp(mp4.stat().st_mtime, tz=UTC).isoformat()
        upsert_render(
            render_id=render_id,
            slug=slug,
            title=title or slug,
            engine=engine,
            file_path=mp4.resolve(),
            cover_path=cover_path,
            duration_sec=duration_sec,
            source_credit=publish_text,
            created_at=mtime_iso,
            db_path=db_path,
        )
        added_or_updated += 1

    if renders_root.is_dir():
        for mp4 in renders_root.rglob("*.mp4"):
            if not mp4.is_file() or mp4.name.endswith(".part.mp4") or mp4.name.endswith(".tmp.mp4"):
                continue
            rel_parts = mp4.relative_to(renders_root).parts
            engine = (
                rel_parts[0] if len(rel_parts) >= 2 and rel_parts[0] in VALID_ENGINES else "core"
            )
            job_id = rel_parts[1] if len(rel_parts) >= 3 else mp4.stem
            pub_file = mp4.parent / "publish.txt"
            pub_txt = (
                pub_file.read_text(encoding="utf-8", errors="ignore").strip()
                if pub_file.is_file()
                else ""
            )
            dur = 0.0
            meta_file = mp4.parent / "meta.json"
            if meta_file.is_file():
                try:
                    mdata = json.loads(meta_file.read_text(encoding="utf-8"))
                    dur = float(mdata.get("duration", 0.0) or 0.0)
                except Exception:
                    pass
            _index_mp4(
                mp4,
                engine=engine,
                slug=job_id,
                title=pub_txt.splitlines()[0][:80] if pub_txt else mp4.stem,
                duration_sec=dur,
                publish_text=pub_txt,
            )

    if workspace_dir is not None and workspace_dir.is_dir():
        # Quét workspace/projects/<slug>/renders/<job_id>/video.mp4 (HBT Core & PostV)
        projects_dir = workspace_dir / "projects"
        if projects_dir.is_dir():
            for pdir in projects_dir.iterdir():
                if not pdir.is_dir():
                    continue
                rdir = pdir / "renders"
                if not rdir.is_dir():
                    continue
                proj_title = pdir.name
                proj_engine = "core"
                pjson = pdir / "project.json"
                if pjson.is_file():
                    try:
                        pdata = json.loads(pjson.read_text(encoding="utf-8"))
                        proj_title = str(pdata.get("title") or pdir.name)
                        if pdata.get("kind") == "postv" or "post" in pdata:
                            proj_engine = "postv"
                    except Exception:
                        pass
                for jdir in rdir.iterdir():
                    if not jdir.is_dir():
                        continue
                    vmp4 = jdir / "video.mp4"
                    if not vmp4.is_file():
                        continue
                    pub_file = jdir / "publish.txt"
                    pub_txt = (
                        pub_file.read_text(encoding="utf-8", errors="ignore").strip()
                        if pub_file.is_file()
                        else ""
                    )
                    dur = 0.0
                    meta_file = jdir / "meta.json"
                    if meta_file.is_file():
                        try:
                            mdata = json.loads(meta_file.read_text(encoding="utf-8"))
                            dur = float(mdata.get("duration", 0.0) or 0.0)
                        except Exception:
                            pass
                    _index_mp4(
                        vmp4,
                        engine=proj_engine,
                        slug=pdir.name,
                        title=proj_title,
                        duration_sec=dur,
                        publish_text=pub_txt,
                    )

        # Quét workspace/chatting/<slug>/renders/render_*.mp4 (Chatting)
        chatting_dir = workspace_dir / "chatting"
        if chatting_dir.is_dir():
            for cdir in chatting_dir.iterdir():
                if not cdir.is_dir():
                    continue
                rdir = cdir / "renders"
                if not rdir.is_dir():
                    continue
                chat_title = cdir.name
                cjson = cdir / "chat.json"
                if cjson.is_file():
                    try:
                        cdata = json.loads(cjson.read_text(encoding="utf-8"))
                        chat_title = str(cdata.get("title") or cdir.name)
                    except Exception:
                        pass
                for mp4 in rdir.glob("*.mp4"):
                    if not mp4.is_file():
                        continue
                    dur = 0.0
                    meta_candidate = rdir / f"{mp4.stem}.json"
                    if meta_candidate.is_file():
                        try:
                            mdata = json.loads(meta_candidate.read_text(encoding="utf-8"))
                            dur = float(mdata.get("duration", 0.0) or 0.0)
                        except Exception:
                            pass
                    _index_mp4(
                        mp4,
                        engine="chatting",
                        slug=cdir.name,
                        title=chat_title,
                        duration_sec=dur,
                        publish_text=f"{chat_title}\n#HayBietTuot #Chatting #Shorts",
                    )

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
