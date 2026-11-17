"""Kiểm thử models, storage và sinh kịch bản theo lô cho StickV."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hbt.stickv.llm import generate_stickv_script, sanitize_beats
from hbt.stickv.storage import (
    create_stickv_project,
    delete_stickv_project,
    list_stickv_projects,
    load_stickv_project,
)


def test_stickv_storage_crud(tmp_path: Path) -> None:
    proj = create_stickv_project(
        tmp_path,
        title="Vì sao não hay quên?",
        topic="science",
        aspect="9:16",
        theme="cream",
    )
    assert proj.slug == "vi-sao-nao-hay-quen"
    loaded = load_stickv_project(tmp_path, proj.slug)
    assert loaded.title == "Vì sao não hay quên?"
    assert len(list_stickv_projects(tmp_path)) == 1

    delete_stickv_project(tmp_path, proj.slug)
    assert list_stickv_projects(tmp_path) == []


def test_sanitize_beats_normalizes_invalid_fields() -> None:
    beats = sanitize_beats(
        [
            {
                "narration": "  Xin chào các bạn!  ",
                "pose": "unknown_pose",
                "motion": "warp",
                "sfx_tag": "laser",
                "board_type": "big_number",
                "board_title": "Thống kê",
                "board_data": {"value": "99%", "label": "Tỉ lệ"},
            }
        ]
    )
    assert len(beats) == 1
    assert beats[0].pose == "explain"
    assert beats[0].motion == "bounce"
    assert beats[0].sfx_tag == "whoosh"
    assert beats[0].board_data["value"] == "99%"


def test_generate_stickv_script_longform_batches(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_gemini(sys_p: str, usr_p: str, **kwargs):
        calls.append(usr_p)
        if "dàn ý" in usr_p:
            return (
                {
                    "title": "Lịch sử tiền tệ",
                    "chapters": [
                        {"chapter": 1, "heading": "Hàng đổi hàng", "summary": "Thời cổ đại"},
                        {"chapter": 2, "heading": "Tiền giấy", "summary": "Thời hiện đại"},
                    ],
                },
                {"llm_s": 0.2},
            )
        return (
            {
                "beats": [
                    {
                        "narration": "Con người từng đổi muối lấy gạo.",
                        "pose": "explain",
                        "board_type": "bullets",
                        "board_data": {"items": ["Muối", "Gạo"]},
                    }
                ]
            },
            {"llm_s": 0.3},
        )

    with patch("hbt.stickv.llm.generate_structured_json", side_effect=fake_gemini):
        title, beats, meta = generate_stickv_script(
            idea="Lịch sử tiền tệ",
            aspect="16:9",
            target_minutes=5.0,
        )

    assert title == "Lịch sử tiền tệ"
    assert meta["chapters"] == 2
    assert len(calls) == 3  # 1 outline + 2 chapters
    assert [b.chapter for b in beats] == [1, 2]
