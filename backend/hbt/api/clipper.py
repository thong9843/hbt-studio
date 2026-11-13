"""API Clipper & Reaction: trích xuất clip 9:16 kèm nhãn ghi nguồn cố định."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hbt.shared.db.media_index import upsert_render

router = APIRouter(prefix="/clipper", tags=["clipper"])

REPO_ROOT = Path(__file__).resolve().parents[3]
CLIPPER_RENDERS_ROOT = REPO_ROOT / "assets" / "renders" / "clipper"


class ClipperRequest(BaseModel):
    source_url: str = Field(..., min_length=5, description="Link video nguồn")
    source_credit: str = Field(..., min_length=1, description="Nhãn ghi nguồn (Nguồn: ...)")
    title: str = Field(default="Clip Reaction", description="Tiêu đề clip")
    start_sec: float = Field(default=0.0, ge=0.0)
    end_sec: float = Field(default=30.0, gt=0.0)
    karaoke_vi: bool = Field(default=True, description="Bật phụ đề karaoke tiếng Việt")


@router.post("/extract")
def extract_clip(body: ClipperRequest) -> dict[str, Any]:
    """Tải và cắt clip 9:16 từ link nguồn, đính nhãn 'Nguồn: ...' cố định và lưu vào SQLite."""
    if body.end_sec <= body.start_sec:
        raise HTTPException(status_code=422, detail="end_sec phải lớn hơn start_sec")

    job_id = time.strftime("%Y%m%d-%H%M%S")
    job_dir = CLIPPER_RENDERS_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    raw_file = job_dir / "source.mp4"
    out_file = job_dir / "final.mp4"

    credit_text = body.source_credit.strip()
    if not credit_text.lower().startswith("nguồn:"):
        credit_text = f"Nguồn: {credit_text}"

    # Tải video nguồn bằng yt-dlp nếu có
    dl = subprocess.run(
        ["yt-dlp", "-f", "mp4/best", "-o", str(raw_file), body.source_url],
        capture_output=True,
        text=True,
        check=False,
    )
    if dl.returncode != 0 or not raw_file.is_file():
        raise HTTPException(
            status_code=502,
            detail=f"Không tải được video nguồn bằng yt-dlp: {(dl.stderr or '')[:200]}",
        )

    duration = body.end_sec - body.start_sec
    safe_credit = credit_text.replace("'", "\\'").replace(":", "\\:")
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"drawtext=text='{safe_credit}':x=48:y=160:fontsize=30:fontcolor=white:"
        "box=1:boxcolor=black@0.55:boxborderw=10"
    )
    ff = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(body.start_sec),
            "-t",
            str(duration),
            "-i",
            str(raw_file),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            str(out_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if ff.returncode != 0 or not out_file.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi FFmpeg khi cắt clip: {(ff.stderr or '')[:200]}",
        )

    record = upsert_render(
        render_id=f"clipper:{job_id}:final.mp4",
        slug=job_id,
        title=body.title,
        engine="clipper",
        file_path=out_file,
        duration_sec=duration,
        pipeline_stage="rendered",
        source_credit=credit_text,
    )
    return {"item": record, "karaoke_vi": body.karaoke_vi}
