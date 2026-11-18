"""Kiểm thử models, storage và sinh kịch bản theo lô cho StickV."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hbt.shared.llm import GEMINI_MODEL
from hbt.stickv.llm import (
    build_director_prompt,
    generate_stickv_script,
    parse_stickv_json_payload,
    sanitize_beats,
    split_raw_narration_to_beats,
)
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


def test_default_gemini_model_and_three_input_modes() -> None:
    assert GEMINI_MODEL == "gemini-3.1-flash-lite"

    prompt = build_director_prompt(idea="Tại sao trời xanh?")
    assert "5 chặng" in prompt
    assert "Tại sao trời xanh?" in prompt

    t_json, b_json = parse_stickv_json_payload(
        '```json\n{"title": "Test JSON", "beats": [{"narration": "Câu 1.", "pose": "shock"}]}\n```'
    )
    assert t_json == "Test JSON"
    assert len(b_json) == 1
    assert b_json[0].pose == "shock"

    t_raw, b_raw = split_raw_narration_to_beats(
        "Tại sao 90% người mới hay bỏ cuộc? Vì họ thiếu lộ trình rõ ràng.\nHãy kiên trì mỗi ngày!"
    )
    assert t_raw
    assert len(b_raw) >= 2
    assert b_raw[0].pose == "shock"
    assert b_raw[-1].pose == "happy"


def test_stickv_v7_schema_and_aliases() -> None:
    from hbt.stickv.models import StickvBeat, StickvProject

    proj = StickvProject(slug="cosmos-1", title="Hố đen", domain="cosmos")  # type: ignore[arg-type]
    assert proj.domain == "cosmos_mystery"

    beat = StickvBeat(
        id="b001",
        text="Não bộ tiêu thụ 20% năng lượng.",
        visual_type="bar_compare",
        interaction="hold_prop",
        prop_query="brain",
        anim_oneshot="idea_bulb",
        anim_loop="talk_excited",
        visual_data={"values": [{"label": "Não", "value": 20}]},
    )
    assert beat.narration == "Não bộ tiêu thụ 20% năng lượng."
    assert beat.board_type == "bar_compare"
    assert beat.interaction == "hold_prop"
    assert beat.prop_query == "brain"
    assert beat.anim_oneshot == "idea_bulb"
    assert beat.anim_loop == "talk_excited"


def test_v8_pose_diversity_and_chunked_grouping(tmp_path: Path) -> None:
    from hbt.stickv.llm import enforce_pose_diversity
    from hbt.stickv.models import StickvBeat
    from hbt.stickv.render import group_beats_into_chunks

    raw = [
        StickvBeat(id=f"b{i:03d}", chapter=1 + i // 4, narration=f"Beat {i}", pose="point_up")
        for i in range(6)
    ]
    diversified = enforce_pose_diversity(raw)
    for a, b in zip(diversified, diversified[1:], strict=False):
        assert a.pose != b.pose

    # 6 beats x 18s -> gom thành các cụm ~36s/cụm
    wavs = [(tmp_path / f"{b.id}.wav", 18.0) for b in diversified]
    chunks = group_beats_into_chunks(
        diversified,
        wavs,
        project_dir=tmp_path,
        library_dir=tmp_path,
        assets_dir=tmp_path,
        max_chunk_sec=40.0,
    )
    assert len(chunks) >= 3
    assert sum(len(items) for _, items in chunks) == 6
