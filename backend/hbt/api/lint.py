"""Kiểm tra nội dung: POST /projects/{slug}/lint và danh sách từ nhạy cảm (/settings)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from hbt.api.deps import State
from hbt.pipeline.lint import lint_project
from hbt.sensitive import SensitiveWords

router = APIRouter(tags=["lint"])


@router.post("/projects/{slug}/lint")
def lint(slug: str, state: State):
    """Kết quả kiểm tra. M2 mới có quy tắc độ dài lời đọc; bộ kiểm tra từ nhạy cảm thêm ở M4."""
    project = state.storage.load(slug)
    issues = [asdict(i) for i in lint_project(project)]
    counts = {
        level: sum(1 for i in issues if i["level"] == level) for level in ("info", "warn", "block")
    }
    return {
        "issues": issues,
        "counts": counts,
        "blocked": counts["block"] > 0,
        "problems": project.render_problems(),  # còn thiếu gì để dựng được
    }


@router.get("/settings/sensitive-words", response_model=SensitiveWords)
def get_sensitive_words(state: State):
    return state.sensitive.load()


@router.put("/settings/sensitive-words", response_model=SensitiveWords)
def put_sensitive_words(body: SensitiveWords, state: State):
    return state.sensitive.save(body)
