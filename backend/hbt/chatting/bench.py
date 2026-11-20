"""Đo hiệu năng Ollama viết kịch bản Chatting (chatting-bench) theo §5."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from hbt.chatting.llm import OllamaClient


def run_bench(
    sample_file: Path,
    model: str | None = None,
    runs: int = 3,
) -> dict[str, Any]:
    """Chạy đo benchmark nhiều lượt và tính trung vị llm_s."""
    if not sample_file.is_file():
        raise FileNotFoundError(f"File mẫu không tồn tại: {sample_file}")

    content = sample_file.read_text(encoding="utf-8").strip()
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    title = lines[0][:60] if lines else "Bài mẫu benchmark"
    body = "\n".join(lines[1:]) if len(lines) > 1 else content

    client = OllamaClient(model=model)
    status = client.check_status()
    if not status["ollama_running"]:
        return {
            "ok": False,
            "error": "Ollama chưa chạy trên http://127.0.0.1:11434",
            "model": client.model,
        }
    if not status["model_available"]:
        return {
            "ok": False,
            "error": f"Model '{client.model}' chưa có trong Ollama (chưa pull)",
            "model": client.model,
        }

    timings_list: list[float] = []
    tokens_list: list[int] = []

    for r in range(runs):
        print(f"Lượt {r + 1}/{runs}...")
        _, timings = client.generate_chat(title=title, body=body, platform="messenger")
        timings_list.append(timings["llm_s"])
        tokens_list.append(timings["llm_tokens"])

    median_s = statistics.median(timings_list)
    avg_tokens = statistics.mean(tokens_list) if tokens_list else 0

    return {
        "ok": True,
        "model": client.model,
        "runs": runs,
        "median_llm_s": round(median_s, 2),
        "min_llm_s": round(min(timings_list), 2),
        "max_llm_s": round(max(timings_list), 2),
        "avg_tokens": round(avg_tokens, 1),
    }
