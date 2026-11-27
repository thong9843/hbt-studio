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
    # 100% beat chuyển sang Visual-First (pinned_photo + tiêu đề ngắn 3-6 từ, xóa văn mẫu)
    for b in enforced:
        assert b.board_type == "pinned_photo"
        assert b.board_items == [] and b.takeaway == ""
        w_cnt = len(b.board_title.split())
        assert 3 <= w_cnt <= 6
        low_t = b.board_title.lower()
        assert "mở đầu video" not in low_t and "tóm tắt 3 ý cốt lõi" not in low_t
        assert "kết luận" not in low_t and "..." not in b.board_title

    # 3. enforce_pose_diversity phải chống trùng cả pose lẫn emotion liên tiếp
    diversified = enforce_pose_diversity(enforced)
    for a, b in zip(diversified, diversified[1:], strict=False):
        assert a.pose != b.pose
        assert a.emotion != b.emotion


def test_phase9_visual_first_prompt_no_text_wall_and_tts_friendly() -> None:
    from hbt.stickv.llm import (
        _enforce_meaningful_boards,
        build_director_prompt,
        shorten_visual_title,
    )
    from hbt.stickv.models import StickvBeat

    prompt = build_director_prompt(idea="Vì sao đau cơ sau khi tập gym?")
    assert "VISUAL-FIRST" in prompt
    assert "pinned_photo" in prompt
    assert "3-6 từ" in prompt
    assert "VieNeu-TTS" in prompt or "vận động viên chạy đường dài" in prompt
    assert "không chữ" in prompt and "không mũi tên" in prompt

    short_fb = shorten_visual_title(
        "**Mở đầu video**", fallback_narration="Cơ bắp phục hồi khi ngủ sâu."
    )
    assert 3 <= len(short_fb.split()) <= 6 and "mở đầu" not in short_fb.lower()
    trimmed = shorten_visual_title("Tại sao nền móng yếu và sụt lún nhanh hơn dự kiến...")
    assert 3 <= len(trimmed.split()) <= 6
    assert "..." not in trimmed and not trimmed.lower().endswith("và")

    raw_beats = [
        StickvBeat(
            id="b001",
            narration=(
                "Nhiều người nghĩ đau nhức cơ bắp sau buổi tập là dấu hiệu tốt nhất để tăng cơ."
            ),
            board_type="bullets",
            board_title="Đau nhức cơ bắp sau buổi tập kéo dài",
            board_data={"items": ["..."], "takeaway": "DOMS chỉ là viêm tạm thời"},
        ),
        StickvBeat(
            id="b002",
            narration="Cơ bắp tăng trưởng nhờ áp lực cơ học và phục hồi trong giấc ngủ sâu.",
            board_type="myth_vs_fact",
            board_title="Giải mã tăng cơ",
            board_data={"myth": "Đau là tốt", "fact": "Ngủ đủ giấc"},
        ),
        StickvBeat(
            id="b003",
            narration="Cảm ơn bạn đã xem, nhớ bấm đăng ký kênh và bình luận trải nghiệm nhé!",
            board_type="recap_card",
            board_title="TÓM TẮT 3 Ý CỐT LÕI",
            board_data={"items": ["Đăng ký kênh ngay"]},
        ),
    ]

    enforced = _enforce_meaningful_boards(raw_beats)
    banned_boilerplate = (
        "chu kỳ phục hồi",
        "quy luật tự nhiên",
        "phân tích cơ chế",
        "tóm tắt 3 ý cốt lõi",
    )
    for b in enforced:
        assert b.board_type == "pinned_photo"
        assert 3 <= len(b.board_title.split()) <= 6
        blob = f"{b.board_title} {b.board_data}".lower()
        for bad in banned_boilerplate:
            assert bad not in blob


def test_no_boilerplate_empty_comparison_or_fake_100_percent() -> None:
    """Visual-First loại sạch caption mẫu, bảng chữ dài và ép 100% beat dùng ảnh + tiêu đề ngắn."""
    payload = """{
      "title": "Những địa điểm bí ẩn trên Trái Đất",
      "primary_entity_en": "Bermuda Triangle",
      "beats": [
        {
          "narration": "Tam giác quỷ Bermuda rộng 500.000 km² nằm ở Đại Tây Dương.",
          "board_type": "pinned_photo",
          "board_title": "PHÂN TÍCH CƠ CHẾ",
          "prop_query": "ocean mystery",
          "board_data": {"caption": "PHÂN TÍCH CƠ CHẾ", "pin_style": "pin"}
        },
        {
          "narration": "Đá biết đi tại Thung lũng Chết tự trượt dài trên nền bùn đóng băng.",
          "board_type": "big_number",
          "board_title": "Đá biết đi California",
          "board_data": {"label": "Hiện tượng trượt đá", "sub": "Di chuyển trên lớp băng mỏng"}
        },
        {
          "narration": "Hồ Natron ở Tanzania có độ pH cao tới 10,5 khiến xác động vật hóa đá.",
          "board_type": "comparison",
          "board_title": "So sánh độ kiềm",
          "board_data": {"left_title": "Trước", "right_title": "Sau"}
        },
        {
          "narration": "Hãy bấm đăng ký kênh để khám phá thêm nhiều bí ẩn địa lý thú vị nhé!",
          "board_type": "recap_card",
          "board_title": "Tổng kết"
        }
      ]
    }"""
    _, beats = parse_stickv_json_payload(payload)
    assert all(b.board_type == "pinned_photo" for b in beats)
    assert "phân tích cơ chế" not in beats[0].board_data["caption"].lower()
    assert "tổng kết" not in beats[-1].board_title.lower()
    for b in beats:
        assert 3 <= len(b.board_title.split()) <= 6
        assert b.board_items == [] and b.takeaway == ""
        assert b.image_prompt and "no text" in b.image_prompt.lower()


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


def test_multi_location_beat_entity_no_umbrella_override_and_late_photo_balance() -> None:
    """Video đa địa điểm không bị ghép đè 'Mysterious Places' và có ảnh ở nửa sau (60%-85%)."""
    payload = """{
      "title": "Những địa điểm bí ẩn trên Trái Đất",
      "primary_entity_en": "Mysterious Places",
      "beats": [
        {
          "narration": "Tam giác quỷ Bermuda rộng lớn ở Đại Tây Dương.",
          "board_type": "pinned_photo",
          "board_title": "Tam giác Bermuda",
          "beat_entity_en": "Bermuda Triangle",
          "prop_query": "Bermuda Triangle aerial ocean"
        },
        {"narration": "Nhiều giả thuyết siêu nhiên xuất hiện.", "board_type": "myth_vs_fact",
         "board_data": {"myth": "Quái vật biển", "fact": "Bão nhiệt đới và hải lưu"}},
        {
          "narration": "Đá biết đi tại Racetrack Playa, California tự trượt dài trên cát.",
          "board_type": "pinned_photo",
          "board_title": "Đá biết đi California",
          "prop_query": "Racetrack Playa sailing stones"
        },
        {"narration": "Lớp băng mỏng ban đêm giảm ma sát.", "board_type": "bullets",
         "board_data": {"items": ["Đêm xuống dưới 0°C", "Gió nhẹ đẩy đá 300 kg"]}},
        {"narration": "Hồ Natron ở Tanzania có độ pH 10,5.", "board_type": "big_number",
         "board_data": {"value": "pH 10,5", "label": "Độ kiềm Hồ Natron"}},
        {"narration": "Mắt Sahara hay cấu trúc Richat rộng 40 km nhìn rõ từ vũ trụ.",
         "board_type": "bullets",
         "board_title": "Mắt Sahara — Cấu trúc Richat",
         "beat_entity_en": "Richat Structure Sahara",
         "prop_query": "Richat Structure Sahara satellite",
         "board_data": {"items": ["Đường kính 40 km", "Hình thành do xói mòn địa chất"]}},
        {"narration": "Tóm lại mọi bí ẩn đều có lời giải khoa học.", "board_type": "recap_card"},
        {"narration": "Hãy đăng ký kênh ngay hôm nay!", "board_type": "recap_card"}
      ]
    }"""
    _, beats = parse_stickv_json_payload(payload)
    assert len(beats) == 8
    # 1. Không ghép đè "Mysterious Places" vào beat "Racetrack Playa sailing stones"
    b2 = beats[2]
    assert "mysterious places" not in (b2.prop_query or "").lower()
    assert "racetrack playa" in (b2.prop_query or "").lower()
    assert "racetrack playa" in b2.beat_entity_en.lower()
    # 2. Chế độ Visual-First: toàn bộ nửa sau đều là pinned_photo & giữ nguyên thực thể Richat
    late_photos = [b for b in beats[4:7] if b.board_type == "pinned_photo"]
    assert len(late_photos) == 3
    assert any(b.beat_entity_en == "Richat Structure Sahara" for b in late_photos)
