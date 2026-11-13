"""API Video Editor hậu kỳ nhẹ (OpenCut-style) kết nối FFmpeg local."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hbt.shared.db.media_index import list_renders, upsert_render

router = APIRouter(prefix="/editor", tags=["editor"])

REPO_ROOT = Path(__file__).resolve().parents[3]
EDITOR_RENDERS_ROOT = REPO_ROOT / "assets" / "renders" / "editor"


class EditorProcessRequest(BaseModel):
    render_id: str = Field(..., description="ID video nguồn trong SQLite")
    trim_start: float = Field(default=0.0, ge=0.0)
    trim_end: float | None = Field(default=None, gt=0.0)
    remove_silence: bool = Field(default=False)
    volume: float = Field(default=1.0, ge=0.0, le=3.0)
    title: str | None = Field(default=None)


@router.post("/process")
def process_video(body: EditorProcessRequest) -> dict[str, Any]:
    """Cắt/ghép, xoá khoảng lặng, chỉnh âm lượng bằng FFmpeg local và lưu trạng thái 'edited'."""
    items = list_renders()
    source = next((i for i in items if i["id"] == body.render_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy video nguồn trong SQLite")

    src_path = Path(source["file_path"])
    if not src_path.is_file():
        raise HTTPException(status_code=404, detail="File video nguồn không tồn tại trên đĩa")

    job_id = time.strftime("%Y%m%d-%H%M%S")
    job_dir = EDITOR_RENDERS_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    out_file = job_dir / "final.mp4"

    cmd: list[str] = ["ffmpeg", "-y"]
    if body.trim_start > 0:
        cmd.extend(["-ss", str(body.trim_start)])
    if body.trim_end is not None and body.trim_end > body.trim_start:
        cmd.extend(["-t", str(body.trim_end - body.trim_start)])
    cmd.extend(["-i", str(src_path)])

    af_filters: list[str] = []
    if abs(body.volume - 1.0) > 0.01:
        af_filters.append(f"volume={body.volume:.2f}")
    if body.remove_silence:
        af_filters.append("silenceremove=stop_periods=-1:stop_duration=0.35:stop_threshold=-40dB")
    if af_filters:
        cmd.extend(["-af", ",".join(af_filters)])

    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", str(out_file)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not out_file.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi FFmpeg Editor: {(proc.stderr or '')[:200]}",
        )

    record = upsert_render(
        render_id=f"editor:{job_id}:final.mp4",
        slug=job_id,
        title=body.title or f"{source['title']} (Edited)",
        engine="editor",
        file_path=out_file,
        pipeline_stage="edited",
        source_credit=source.get("source_credit", ""),
    )
    return {"item": record}
