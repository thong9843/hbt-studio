"""Unit test cho StickV/Core Adapters & API `/api/cinema` (hardware, preflight, sheet, beat)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from hbt.cinema.adapters import core_script_to_timeline, stickv_to_timeline
from hbt.config import Settings
from hbt.core.models import HbtCoreScript, HbtCoreSegment
from hbt.main import create_app
from hbt.stickv.models import StickvBeat, StickvProject


def _make_test_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        workspace_dir=tmp_path / "workspace",
        library_dir=tmp_path / "library",
        whisper_model="auto",
        whisper_device="cpu",
        default_fps=30,
        models_dir=tmp_path / "models",
        assets_dir=tmp_path / "assets",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_adapters_compile_stickv_and_core_scripts_to_preflighted_timeline() -> None:
    sv = StickvProject(
        slug="sv-demo",
        title="Bí Ẩn Giấc Ngủ",
        domain="psychology_story",
        aspect="9:16",
        beats=[
            StickvBeat(
                id="b001",
                chapter=1,
                narration="Vì sao não vẫn tiêu tốn 20% năng lượng khi bạn ngủ say?",
                pose="think_chin",
                emotion="curious",
                camera_shot="focus_board",
                board_title="Não khi ngủ",
                board_items=["Tiêu thụ **20%** năng lượng", "Giai đoạn **REM** xử lý ký ức"],
                takeaway="Não hoạt động mạnh lúc mơ",
            ),
            StickvBeat(
                id="b002",
                chapter=1,
                narration="Đừng quên đăng ký kênh để đón xem tập tiếp theo nhé!",
                pose="wave_hello",
                emotion="happy",
                camera_shot="focus_board",
                board_title="Kết luận",
                board_items=["Đăng ký kênh ngay"],
            ),
        ],
    )
    sv_spec = stickv_to_timeline(sv)
    assert sv_spec.source_engine == "stickv"
    assert sv_spec.preflight_passed is True
    assert sv_spec.beats[0].puppet.pose == "think_chin"
    assert sv_spec.beats[-1].board.board_type == "recap_card"

    core = HbtCoreScript(
        topic="history",
        title="Đấu Trường La Mã",
        segments=[
            HbtCoreSegment(
                order=1,
                title="KIẾN TRÚC BỀN VỮNG",
                text="Đấu trường La Mã đứng vững suốt 2000 năm nhờ bê tông núi lửa.",
                sticker="shock",
                punch=True,
            ),
            HbtCoreSegment(
                order=2,
                title="HỆ THỐNG THOÁT NƯỚC",
                text="Người La Mã xây cống ngầm thông minh dưới sàn đấu.",
                sticker="check",
            ),
        ],
    )
    core_spec = core_script_to_timeline(core)
    assert core_spec.source_engine == "core"
    assert core_spec.domain == "history_geo"
    assert core_spec.preflight_passed is True
    assert len(core_spec.beats) == 2
    assert core_spec.beats[0].shot_type != core_spec.beats[1].shot_type


def test_cinema_rest_api_endpoints_and_beat_cache_hit_and_traversal_guard(tmp_path: Path) -> None:
    client = _make_test_client(tmp_path)

    # 1. GET /api/cinema/hardware
    hw_res = client.get("/api/cinema/hardware")
    assert hw_res.status_code == 200
    hw_data = hw_res.json()
    assert hw_data["mode"] in ("cpu", "gpu")
    assert hw_data["nvenc_probed"] is True

    # 2. POST /api/cinema/preflight với StickV payload có lỗi y<0 và Anti-Parrot
    payload = {
        "stickv_project": {
            "slug": "api-test-sv",
            "title": "Kiểm thử API",
            "aspect": "9:16",
            "beats": [
                {
                    "id": "b001",
                    "chapter": 1,
                    "narration": "Trái Đất quay quanh Mặt Trời mất 365 ngày.",
                    "pose": "present_board",
                    "board_type": "bullets",
                    "board_title": "Chu kỳ quay",
                    "board_items": ["Trái Đất quay quanh Mặt Trời mất 365 ngày"],
                },
                {
                    "id": "b002",
                    "chapter": 1,
                    "narration": "Nhớ đăng ký kênh để xem thêm!",
                    "pose": "wave_hello",
                    "board_type": "bullets",
                    "board_title": "Chào tạm biệt",
                    "board_items": ["Đăng ký kênh"],
                },
            ],
        },
        "auto_fix": True,
    }
    pf_res = client.post("/api/cinema/preflight", json=payload)
    assert pf_res.status_code == 200
    pf_data = pf_res.json()
    assert pf_data["ok"] is True
    assert pf_data["repaired_spec"]["preflight_passed"] is True

    # 3. POST /api/cinema/contact-sheet & GET file
    cs_res = client.post("/api/cinema/contact-sheet", json=payload)
    assert cs_res.status_code == 200
    cs_data = cs_res.json()
    assert cs_data["ok"] is True
    assert cs_data["elapsed_ms"] < 2000.0
    img_res = client.get(cs_data["url"])
    assert img_res.status_code == 200
    assert img_res.headers["content-type"].startswith("image/jpeg")

    # 4. POST /api/cinema/render-beat (MISS lần 1 -> HIT lần 2)
    rb_payload = {
        "timeline": {
            "slug": "beat-api-demo",
            "title": "Beat Demo",
            "aspect": "9:16",
            "fps": 24,
            "beats": [
                {
                    "id": "b001",
                    "chapter": 1,
                    "narration": "Xin chào Cinema Core.",
                    "duration_sec": 0.45,
                    "shot_type": "data_spotlight",
                    "board": {
                        "board_type": "big_number",
                        "title": "Tốc độ",
                        "bullets": ["Nhanh **20x**"],
                        "data": {"number": "20x"},
                    },
                }
            ],
        },
        "beat_id": "b001",
        "preview": True,
    }
    miss_res = client.post("/api/cinema/render-beat", json=rb_payload)
    assert miss_res.status_code == 200
    miss_data = miss_res.json()
    assert miss_data["cache_hit"] is False
    vid_res = client.get(miss_data["url"])
    assert vid_res.status_code == 200
    assert vid_res.headers["content-type"] == "video/mp4"

    hit_res = client.post("/api/cinema/render-beat", json=rb_payload)
    assert hit_res.status_code == 200
    assert hit_res.json()["cache_hit"] is True

    # 5. Chặn path traversal
    assert client.get("/api/cinema/contact-sheet/..%2Fsecret.jpg").status_code in (400, 404)
    assert client.get("/api/cinema/beat-file/..%2Fevil.mp4").status_code in (400, 404)
