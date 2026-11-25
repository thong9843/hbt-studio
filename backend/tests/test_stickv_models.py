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


def test_v9_meaningful_boards_anti_parrot_cta_recap_and_emotion_diversity() -> None:
    from hbt.stickv.llm import _enforce_meaningful_boards, enforce_pose_diversity
    from hbt.stickv.models import StickvBeat

    # 1. Alias bullets & takeaway trên StickvBeat + default emotion="auto"
    aliased = StickvBeat(
        id="b001",
        narration="Cơ chế bức xạ Hawking làm hố đen bốc hơi.",
        pose="present_board",
        bullets=["**Bức xạ Hawking** tạo cặp hạt ảo"],
        takeaway="Hố đen không hoàn toàn bất tử",
    )
    assert aliased.emotion == "auto"
    assert aliased.board_data["items"] == ["**Bức xạ Hawking** tạo cặp hạt ảo"]
    assert aliased.board_data["takeaway"] == "Hố đen không hoàn toàn bất tử"

    # 2. Anti-Parrot (>70% word overlap) + cliché filtering + CTA end-beat -> recap_card
    raw_beats = [
        StickvBeat(
            id="b001",
            narration="Ánh sáng Mặt Trời mất tám phút để truyền tới Trái Đất qua chân không.",
            pose="present_board",
            emotion="confident",
            board_type="bullets",
            board_title="Mở đầu video",
            board_data={
                "items": [
                    "Ánh sáng Mặt Trời mất tám phút để truyền tới Trái Đất qua chân không",
                    "Hãy tìm hiểu nhé",
                ],
                "takeaway": "Ánh sáng đi 300.000 km/s",
            },
        ),
        StickvBeat(
            id="b002",
            narration="Nếu Mặt Trời biến mất đột ngột, ta vẫn thấy nắng trong 8 phút.",
            pose="present_board",
            emotion="confident",
            board_type="bullets",
            board_title="Độ trễ ánh sáng",
            board_data={
                "items": ["**Độ trễ 8 phút** dù trọng lực đổi tức thì"],
                "takeaway": "Sóng hấp dẫn truyền với tốc độ ánh sáng",
            },
        ),
        StickvBeat(
            id="b003",
            narration=(
                "Cảm ơn bạn đã xem, đừng quên đăng ký kênh và bình luận cảm nghĩ bên dưới nhé!"
            ),
            pose="present_board",
            emotion="confident",
            board_type="bullets",
            board_title="Kết luận",
            board_data={"items": ["Đăng ký kênh ngay"]},
        ),
    ]

    enforced = _enforce_meaningful_boards(raw_beats)
    assert enforced[0].board_title == ""  # Đã xóa tiêu đề sáo rỗng "Mở đầu video"
    assert all("tìm hiểu" not in it.lower() for it in enforced[0].board_data["items"])
    # Beat 0 chống nhại lời thoại -> đã rút gọn từ khóa **...** ngắn hơn câu gốc
    first_item = enforced[0].board_data["items"][0]
    assert "**" in first_item and len(first_item) < len(raw_beats[0].narration)
    assert enforced[0].board_data["items"] != raw_beats[0].board_data["items"]

    # Beat cuối CTA bắt buộc chuyển thành recap_card 3 ý cốt lõi
    assert enforced[-1].board_type == "recap_card"
    assert enforced[-1].board_title == "TÓM TẮT 3 Ý CỐT LÕI"
    assert len(enforced[-1].board_data["items"]) >= 2

    # 3. enforce_pose_diversity phải chống trùng cả pose lẫn emotion liên tiếp
    diversified = enforce_pose_diversity(enforced)
    for a, b in zip(diversified, diversified[1:], strict=False):
        assert a.pose != b.pose
        assert a.emotion != b.emotion


def test_phase9_meaningful_boards_anti_parrot_55_rich_myth_and_single_recap() -> None:
    from hbt.stickv.llm import (
        ANTI_PARROT_THRESHOLD,
        _enforce_meaningful_boards,
        _word_overlap_ratio,
        build_director_prompt,
    )
    from hbt.stickv.models import StickvBeat

    assert ANTI_PARROT_THRESHOLD == 0.55
    prompt = build_director_prompt(idea="Vì sao đau cơ sau khi tập gym?")
    assert "55%" in prompt
    assert "DUY NHẤT 1 RECAP" in prompt

    raw_beats = [
        # Beat 0: Tiêu đề & item trùng >55% lời thoại (nhưng <70% kiểu cũ)
        StickvBeat(
            id="b001",
            narration=(
                "Nhiều người nghĩ đau nhức cơ bắp sau buổi tập là dấu hiệu tốt nhất để tăng cơ."
            ),
            board_type="bullets",
            board_title="Đau nhức cơ bắp sau buổi tập",
            board_data={
                "items": [
                    "Đau nhức cơ bắp sau buổi tập là dấu hiệu tăng cơ",
                    "Nhiều người nghĩ đau nhức sau buổi tập là tốt",
                ],
                "takeaway": "DOMS chỉ là phản ứng viêm tạm thời sau tải mới",
            },
        ),
        # Beat 1: myth_vs_fact thưa chữ (3 chữ cụt lủn) -> phải được làm đầy đặn có cơ chế
        StickvBeat(
            id="b002",
            narration="Cơ bắp tăng trưởng nhờ áp lực cơ học và phục hồi trong giấc ngủ sâu.",
            board_type="myth_vs_fact",
            board_title="Giải mã tăng cơ",
            board_data={
                "myth": "Đau là tốt",
                "fact": "Ngủ đủ giấc",
                "takeaway": "Áp lực cơ học kết hợp giấc ngủ 8 giờ mới quyết định phì đại sợi cơ",
            },
        ),
        # Beat 2 (tổng kết) + Beat 3 (CTA) -> PHẢI dùng chung DUY NHẤT 1 recap_card giống hệt nhau
        StickvBeat(
            id="b003",
            narration="Tóm lại, bạn chỉ cần ghi nhớ 3 nguyên tắc vàng để tập luyện thông minh.",
            board_type="recap_card",
            board_title="TỔNG KẾT NHANH",
            board_data={
                "items": [
                    "**DOMS không đo hiệu quả:** Đau cơ chỉ là viêm vi mô tạm thời.",
                    "**Tải tăng tiến:** Kích thích cơ học ổn định mới làm sợi cơ dày lên.",
                    "**Phục hồi khi ngủ:** Ngủ sâu 8 giờ tối ưu tổng hợp protein.",
                ],
                "takeaway": "Tập thông minh và phục hồi đủ thay vì chạy theo cảm giác đau",
            },
        ),
        StickvBeat(
            id="b004",
            narration="Cảm ơn bạn đã xem, nhớ bấm đăng ký kênh và bình luận trải nghiệm nhé!",
            board_type="recap_card",
            board_title="BẢNG TÓM TẮT KHÁC BỊ TRÙNG",
            board_data={
                "items": ["Đăng ký kênh ngay", "Bình luận phía dưới"],
            },
        ),
    ]

    enforced = _enforce_meaningful_boards(raw_beats)

    # 1. Anti-Parrot <= 55% trên cả board_title lẫn từng item
    b0 = enforced[0]
    assert _word_overlap_ratio(b0.narration, b0.board_title) <= 0.55
    for it in b0.board_data["items"]:
        assert _word_overlap_ratio(b0.narration, it) <= 0.55
    assert len(b0.board_data["items"]) == 3

    # 2. myth_vs_fact được làm đầy đặn (>= 8 từ mỗi ô, có **tiêu đề:** giải thích)
    b1 = enforced[1]
    assert len(b1.board_data["myth"].split()) >= 8
    assert len(b1.board_data["fact"].split()) >= 8
    assert "**" in b1.board_data["myth"] and "**" in b1.board_data["fact"]

    # 3. Hai beat cuối (tổng kết + CTA) dùng chung DUY NHẤT 1 bảng recap_card giống hệt nhau
    assert enforced[-2].board_type == "recap_card"
    assert enforced[-1].board_type == "recap_card"
    assert enforced[-2].board_title == "TÓM TẮT 3 Ý CỐT LÕI"
    assert enforced[-1].board_title == "TÓM TẮT 3 Ý CỐT LÕI"
    assert enforced[-2].board_data["items"] == enforced[-1].board_data["items"]
    assert enforced[-2].takeaway == enforced[-1].takeaway
    assert len(enforced[-1].board_data["items"]) == 3
    assert all("đăng ký" not in it.lower() for it in enforced[-1].board_data["items"])


def test_llm_anchors_primary_entity_en_into_pinned_photo_queries() -> None:
    """Hậu xử lý llm.py luôn neo `primary_entity_en` và loại từ rác khỏi `prop_query`."""
    payload = """{
      "title": "Bí mật Tháp Nghiêng Pisa",
      "primary_entity_en": "Leaning Tower of Pisa",
      "beats": [
        {
          "narration": "Các kỹ sư đã đo độ lệch của công trình.",
          "pose": "point_up",
          "board_type": "pinned_photo",
          "board_title": "GIẢI PHÁP KỸ THUẬT",
          "prop_query": "architect blueprint ruler",
          "image_prompt": "A 2D architect drawing curved lines on a tower"
        },
        {
          "narration": "Nền đất bùn non khiến móng lún lệch.",
          "pose": "think_chin",
          "board_type": "pinned_photo",
          "board_title": "ĐỊA CHẤT",
          "prop_query": "soft ground clay foundation"
        }
      ]
    }"""
    title, beats = parse_stickv_json_payload(payload)
    assert title == "Bí mật Tháp Nghiêng Pisa"
    assert len(beats) == 2

    q0 = (beats[0].prop_query or "").lower()
    assert "leaning tower of pisa" in q0
    assert "ruler" not in q0 and "blueprint" not in q0
    assert "leaning tower of pisa" in (beats[0].image_prompt or "").lower()

    q1 = (beats[1].prop_query or "").lower()
    assert "leaning tower of pisa" in q1
    assert "clay" in q1 and "foundation" in q1
    assert "leaning tower of pisa" in (beats[1].image_prompt or "").lower()
