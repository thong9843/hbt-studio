"""Chỉ mục SQLite quản lý toàn bộ video đã xuất trong workspace/studio.db."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = REPO_ROOT / "workspace" / "studio.db"
PIPELINE_STAGES = ("draft", "rendered", "edited", "scheduled", "published")
VALID_ENGINES = ("core", "postv", "chatting", "clipper", "editor", "stickv")
_SKIP_DIR_PARTS = {"build", "chunks", ".git", "node_modules"}


def normalize_media_path(path: str | Path, base_dir: Path | None = None) -> str:
    """Chuẩn hoá đường dẫn thành POSIX tương đối theo base_dir."""
    raw = str(path or "").strip()
    if not raw:
        return ""
    p = Path(raw)
    root = (base_dir or REPO_ROOT).resolve()
    resolved = p.resolve() if p.is_absolute() else (root / p).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_media_path(stored_path: str | Path, base_dir: Path | None = None) -> Path:
    """Giải mã đường dẫn đã lưu (tương đối POSIX hoặc tuyệt đối cũ) thành Path thực tế."""
    raw = str(stored_path or "").strip()
    if not raw:
        return Path("")
    p = Path(raw)
    if p.is_absolute():
        return p
    return ((base_dir or REPO_ROOT).resolve() / p).resolve()


def _probe_video_duration(mp4: Path) -> float:
    """Đo nhanh thời lượng video bằng ffprobe (trả về 0.0 nếu không khả dụng)."""
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(mp4),
            ],
            capture_output=True,
            text=True,
            timeout=2.5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return round(max(0.0, float(proc.stdout.strip())), 3)
    except Exception:
        pass
    return 0.0


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
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Thêm mới hoặc cập nhật bản ghi video trong bảng renders, tránh trùng file_path."""
    if pipeline_stage not in PIPELINE_STAGES:
        raise ValueError(f"pipeline_stage không hợp lệ: {pipeline_stage}")
    norm_fp = normalize_media_path(file_path, base_dir=base_dir)
    norm_cover = normalize_media_path(cover_path, base_dir=base_dir) if cover_path else ""
    abs_fp = resolve_media_path(norm_fp, base_dir=base_dir)
    computed_size = (
        round(abs_fp.stat().st_size / (1024 * 1024), 2)
        if size_mb is None and abs_fp.is_file()
        else float(size_mb or 0.0)
    )
    ts = created_at or datetime.now(UTC).isoformat()
    conn = init_db(db_path)
    try:
        # Xoá bản ghi trùng file_path (khác id hoặc định dạng path cũ) để tránh UNIQUE constraint
        target_resolved = abs_fp.resolve()
        other_rows = conn.execute(
            "SELECT id, file_path, duration_sec FROM renders WHERE id != ?", (render_id,)
        ).fetchall()
        preserved_dur = float(duration_sec or 0.0)
        for er in other_rows:
            er_resolved = resolve_media_path(er["file_path"], base_dir=base_dir).resolve()
            if er["file_path"] == norm_fp or er_resolved == target_resolved:
                if preserved_dur <= 0.0 and float(er["duration_sec"] or 0.0) > 0.0:
                    preserved_dur = float(er["duration_sec"])
                conn.execute("DELETE FROM renders WHERE id = ?", (er["id"],))

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
                cover_path = CASE
                    WHEN excluded.cover_path != '' THEN excluded.cover_path
                    ELSE renders.cover_path
                END,
                duration_sec = CASE
                    WHEN excluded.duration_sec > 0 THEN excluded.duration_sec
                    ELSE renders.duration_sec
                END,
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
                norm_fp,
                norm_cover,
                preserved_dur,
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


def _deleted_renders_path(db_path: Path | None = None) -> Path:
    target = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    return target.parent / "deleted_renders.json"


def load_deleted_render_paths(db_path: Path | None = None) -> set[str]:
    """Đọc danh sách `file_path` đã xóa khỏi UI nhưng đang chờ hệ điều hành nhả khóa."""
    p = _deleted_renders_path(db_path)
    if not p.is_file():
        return set()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return {str(x).strip() for x in raw if str(x).strip()}
    except Exception:
        pass
    return set()


def _save_deleted_render_paths(paths: set[str], db_path: Path | None = None) -> None:
    p = _deleted_renders_path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(paths), ensure_ascii=False, indent=2), encoding="utf-8")


def record_deleted_render_path(file_path: str, db_path: Path | None = None) -> None:
    norm = str(file_path or "").strip()
    if not norm:
        return
    cur = load_deleted_render_paths(db_path)
    cur.add(norm)
    _save_deleted_render_paths(cur, db_path)


def delete_render(render_id: str, db_path: Path | None = None) -> bool:
    """Xoá bản ghi video khỏi chỉ mục SQLite."""
    conn = init_db(db_path)
    try:
        cur = conn.execute("DELETE FROM renders WHERE id = ?", (render_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _is_valid_render_mp4(mp4: Path) -> bool:
    if not mp4.is_file():
        return False
    if mp4.name.endswith((".part.mp4", ".tmp.mp4")):
        return False
    return not any(part in _SKIP_DIR_PARTS for part in mp4.parts)


def _read_render_sidecars(mp4: Path) -> tuple[float, str, str, dict[str, Any]]:
    """Đọc thời lượng, publish.txt, cover ảnh và meta.json cạnh file mp4."""
    dur = 0.0
    meta: dict[str, Any] = {}
    for meta_file in (mp4.parent / "meta.json", mp4.with_suffix(".json")):
        if meta_file.is_file():
            try:
                mdata = json.loads(meta_file.read_text(encoding="utf-8"))
                if isinstance(mdata, dict):
                    meta = mdata
                    dur = float(mdata.get("duration") or mdata.get("duration_sec") or 0.0)
                    break
            except Exception:
                pass

    pub_file = mp4.parent / "publish.txt"
    pub_txt = (
        pub_file.read_text(encoding="utf-8", errors="ignore").strip() if pub_file.is_file() else ""
    )

    cover_path = ""
    for cand in (
        mp4.parent / "cover_9x16.jpg",
        mp4.parent / "thumbnail.jpg",
        mp4.with_suffix(".jpg"),
    ):
        if cand.is_file():
            cover_path = str(cand)
            break

    return dur, pub_txt, cover_path, meta


def _infer_project_meta(pdir: Path) -> tuple[str, str]:
    """Đọc title và engine (core|postv) từ workspace/projects/<slug>/project.json."""
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
    return proj_title, proj_engine


def sync_renders_from_disk(
    renders_root: Path | None = None,
    db_path: Path | None = None,
    *,
    workspace_dir: Path | None = None,
) -> dict[str, int]:
    """Quét đệ quy toàn bộ video thành phẩm của 4 động cơ trên đĩa và đồng bộ vào studio.db."""
    added_or_updated = 0
    removed = 0
    base_dir = (
        workspace_dir.parent.resolve()
        if workspace_dir is not None
        else (
            renders_root.parent.parent.resolve()
            if renders_root is not None and renders_root.parent.name == "assets"
            else REPO_ROOT
        )
    )
    existing_resolved: set[Path] = set()

    # Thử dọn các file đã đánh dấu xóa nhưng từng bị Windows khóa (WinError 32)
    pending_deleted = load_deleted_render_paths(db_path)
    still_locked: set[str] = set()
    for norm_p in pending_deleted:
        abs_p = resolve_media_path(norm_p, base_dir=base_dir)
        if not abs_p.is_file():
            continue
        try:
            abs_p.unlink(missing_ok=True)
        except PermissionError:
            still_locked.add(norm_p)
        except OSError:
            still_locked.add(norm_p)
    if pending_deleted != still_locked:
        _save_deleted_render_paths(still_locked, db_path)

    # Đọc cache duration từ DB hiện có để tránh chạy ffprobe lặp lại
    cached_durs: dict[Path, float] = {}
    conn = init_db(db_path)
    try:
        for row in conn.execute("SELECT file_path, duration_sec FROM renders").fetchall():
            if float(row["duration_sec"] or 0.0) > 0.0:
                cached_durs[resolve_media_path(row["file_path"], base_dir=base_dir).resolve()] = (
                    float(row["duration_sec"])
                )
    finally:
        conn.close()

    def _index_mp4(
        mp4: Path,
        *,
        engine: str,
        slug: str,
        title: str,
        duration_sec: float = 0.0,
        publish_text: str = "",
        cover_path: str = "",
    ) -> None:
        nonlocal added_or_updated
        resolved = mp4.resolve()
        if resolved in existing_resolved:
            return
        if normalize_media_path(resolved, base_dir=base_dir) in still_locked:
            return
        existing_resolved.add(resolved)
        dur = duration_sec if duration_sec > 0.0 else cached_durs.get(resolved, 0.0)
        if dur <= 0.0:
            dur = _probe_video_duration(resolved)
        render_id = f"{engine}:{slug}:{mp4.parent.name}:{mp4.name}"
        mtime_iso = datetime.fromtimestamp(mp4.stat().st_mtime, tz=UTC).isoformat()
        upsert_render(
            render_id=render_id,
            slug=slug,
            title=title or slug,
            engine=engine,
            file_path=resolved,
            cover_path=cover_path,
            duration_sec=dur,
            source_credit=publish_text,
            created_at=mtime_iso,
            db_path=db_path,
            base_dir=base_dir,
        )
        added_or_updated += 1

    # 1. assets/renders/<engine>/.../*.mp4
    if renders_root is not None and renders_root.is_dir():
        for mp4 in renders_root.rglob("*.mp4"):
            if not _is_valid_render_mp4(mp4):
                continue
            rel_parts = mp4.relative_to(renders_root).parts
            engine = (
                rel_parts[0] if len(rel_parts) >= 2 and rel_parts[0] in VALID_ENGINES else "core"
            )
            job_id = rel_parts[1] if len(rel_parts) >= 3 else mp4.stem
            dur, pub_txt, cover_p, meta = _read_render_sidecars(mp4)
            title = str(meta.get("title") or "").strip() or (
                pub_txt.splitlines()[0][:80] if pub_txt else mp4.stem
            )
            _index_mp4(
                mp4,
                engine=engine,
                slug=job_id,
                title=title,
                duration_sec=dur,
                publish_text=pub_txt,
                cover_path=cover_p,
            )

    if workspace_dir is not None and workspace_dir.is_dir():
        # 2. workspace/projects/<slug>/renders/**/*.mp4 (HBT Core & PostV)
        projects_dir = workspace_dir / "projects"
        if projects_dir.is_dir():
            for pdir in projects_dir.iterdir():
                rdir = pdir / "renders"
                if not (pdir.is_dir() and rdir.is_dir()):
                    continue
                proj_title, proj_engine = _infer_project_meta(pdir)
                for mp4 in rdir.rglob("*.mp4"):
                    if not _is_valid_render_mp4(mp4):
                        continue
                    dur, pub_txt, cover_p, meta = _read_render_sidecars(mp4)
                    m_eng = str(meta.get("engine") or meta.get("kind") or "").lower()
                    engine = m_eng if m_eng in VALID_ENGINES else proj_engine
                    _index_mp4(
                        mp4,
                        engine=engine,
                        slug=pdir.name,
                        title=str(meta.get("title") or proj_title),
                        duration_sec=dur,
                        publish_text=pub_txt,
                        cover_path=cover_p,
                    )

        # 3. workspace/chatting/<slug>/renders/**/*.mp4 (Chatting)
        chatting_dir = workspace_dir / "chatting"
        if chatting_dir.is_dir():
            for cdir in chatting_dir.iterdir():
                rdir = cdir / "renders"
                if not (cdir.is_dir() and rdir.is_dir()):
                    continue
                chat_title = cdir.name
                cjson = cdir / "chat.json"
                if cjson.is_file():
                    try:
                        cdata = json.loads(cjson.read_text(encoding="utf-8"))
                        chat_title = str(cdata.get("title") or cdir.name)
                    except Exception:
                        pass
                for mp4 in rdir.rglob("*.mp4"):
                    if not _is_valid_render_mp4(mp4):
                        continue
                    dur, pub_txt, cover_p, _ = _read_render_sidecars(mp4)
                    _index_mp4(
                        mp4,
                        engine="chatting",
                        slug=cdir.name,
                        title=chat_title,
                        duration_sec=dur,
                        publish_text=pub_txt or f"{chat_title}\n#HayBietTuot #Chatting #Shorts",
                        cover_path=cover_p,
                    )

        # 4. workspace/stickv/<slug>/renders/**/*.mp4 (StickV)
        stickv_dir = workspace_dir / "stickv"
        if stickv_dir.is_dir():
            for sdir in stickv_dir.iterdir():
                rdir = sdir / "renders"
                if not (sdir.is_dir() and rdir.is_dir()):
                    continue
                sv_title = sdir.name
                sjson = sdir / "project.json"
                if sjson.is_file():
                    try:
                        sdata = json.loads(sjson.read_text(encoding="utf-8"))
                        sv_title = str(sdata.get("title") or sdir.name)
                    except Exception:
                        pass
                for mp4 in rdir.rglob("*.mp4"):
                    if not _is_valid_render_mp4(mp4):
                        continue
                    dur, pub_txt, cover_p, _ = _read_render_sidecars(mp4)
                    _index_mp4(
                        mp4,
                        engine="stickv",
                        slug=sdir.name,
                        title=sv_title,
                        duration_sec=dur,
                        publish_text=pub_txt,
                        cover_path=cover_p,
                    )

    conn = init_db(db_path)
    try:
        rows = conn.execute("SELECT id, file_path FROM renders").fetchall()
        for r in rows:
            resolved_r = resolve_media_path(r["file_path"], base_dir=base_dir).resolve()
            if resolved_r not in existing_resolved and not resolved_r.is_file():
                conn.execute("DELETE FROM renders WHERE id = ?", (r["id"],))
                removed += 1
        conn.commit()
    finally:
        conn.close()

    return {"synced": added_or_updated, "removed": removed}


def sync_renders_dir(
    renders_root: Path,
    db_path: Path | None = None,
    *,
    workspace_dir: Path | None = None,
) -> dict[str, int]:
    """Alias tương thích ngược cho sync_renders_from_disk."""
    return sync_renders_from_disk(renders_root, db_path=db_path, workspace_dir=workspace_dir)
