"""API Kanban Pipeline & SQLite Media Index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hbt.shared.db.media_index import (
    PIPELINE_STAGES,
    list_renders,
    sync_renders_dir,
    update_stage,
)

router = APIRouter(prefix="/kanban", tags=["kanban"])

REPO_ROOT = Path(__file__).resolve().parents[3]
RENDERS_ROOT = REPO_ROOT / "assets" / "renders"


class StageUpdateRequest(BaseModel):
    pipeline_stage: str = Field(..., description="Giai đoạn Kanban mới")
    scheduled_at: str | None = Field(default=None, description="Giờ hẹn đăng (ISO)")


@router.get("/renders")
def get_kanban_renders(stage: str | None = None, engine: str | None = None) -> dict[str, Any]:
    """Đồng bộ assets/renders/ vào SQLite và trả về danh sách video theo giai đoạn."""
    sync_stats = sync_renders_dir(RENDERS_ROOT)
    items = list_renders(stage=stage, engine=engine)
    counts = {s: 0 for s in PIPELINE_STAGES}
    for item in items:
        st = item.get("pipeline_stage")
        if st in counts:
            counts[st] += 1
    return {"items": items, "counts": counts, "sync": sync_stats}


@router.patch("/renders/{render_id:path}/stage")
def patch_render_stage(render_id: str, body: StageUpdateRequest) -> dict[str, Any]:
    """Cập nhật giai đoạn Kanban (và giờ hẹn đăng nếu có) vào SQLite."""
    if body.pipeline_stage not in PIPELINE_STAGES:
        raise HTTPException(
            status_code=422, detail=f"Giai đoạn không hợp lệ: {body.pipeline_stage}"
        )
    updated = update_stage(render_id, body.pipeline_stage, scheduled_at=body.scheduled_at)
    if updated is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy video trong chỉ mục")
    return {"item": updated}
