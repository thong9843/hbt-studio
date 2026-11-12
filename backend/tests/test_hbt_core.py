"""Kiểm thử toàn diện đợt Nâng cấp HBT Core (Nhiệm vụ 1 & Nhiệm vụ 2).

Bao gồm:
1. VieNeu-TTS tự động sinh giọng từng phân đoạn, tính mốc micro-giây chính xác và bắn SSE
   `{step: "voice", current, total, percent}`.
2. Nhạc nền BGM thông minh quét `library/music/` theo `topic` (`history / fun / science / mystery`)
   và nối dài bằng `acrossfade=d=2.0`.
3. Âm thanh hiệu ứng SFX quét `library/sfx/` (whoosh, pop) tự động chèn khi chuyển thẻ kem.
4. Kẹp chuẩn tài nguyên FFmpeg (`-threads 2`, `-filter_threads 2`, `-preset veryfast`, `-crf 22`,
   `-max_muxing_queue_size 512`) và giải phóng RAM Pillow (`.close()` + `gc.collect()`).
5. Chế độ V1 (Bán tự động / JSON Thủ công, 0 token, offline 100%) & Chế độ V2 (1-Click Prompt
   tích hợp Gemini 1.5 Flash API kèm cơ chế tự động fallback về V1 khi lỗi/hết quota).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from hbt.config import REPO_ROOT
from hbt.core.audio import (
    build_acrossfade_filter_graph,
    build_topic_bgm_playlist,
    resolve_sfx_file,
    scan_music_by_topic,
    scan_sfx_library,
)
from hbt.core.gemini_client import (
    BACKEND_DIR,
    GEMINI_ENDPOINT,
    MODELS,
    SYSTEM_PROMPT,
    GeminiClientError,
    build_gemini_headers,
    build_gemini_payload,
    build_gemini_url,
    generate_script_from_prompt,
    is_valid_gemini_api_key,
    load_gemini_api_key,
    resolve_candidate_env_paths,
)
from hbt.core.gemini_client import (
    REPO_ROOT as GEMINI_REPO_ROOT,
)
from hbt.core.models import HbtCoreScript, HbtCoreSegment
from hbt.core.render import (
    FFMPEG_ENCODE_CLAMP,
    FFMPEG_RESOURCE_CLAMP,
    build_core_scene_layers_safe,
    render_hbt_core_auto,
)
from hbt.core.voice import synthesize_core_segments
from tests.test_api import client  # noqa: F401


# ---------------------------------------------------------------------------
# 1. Kiểm thử VieNeu-TTS phân đoạn + mốc micro-giây + SSE {step: "voice", current, total, percent}
# ---------------------------------------------------------------------------
def test_vieneu_segment_voice_microseconds_and_sse(tmp_path: Path) -> None:
    segments = [
        HbtCoreSegment(
            order=1,
            text="Vì sao bầu trời lại có màu xanh vào ban ngày?",
            image="a.png",
            sfx="whoosh",
        ),
        HbtCoreSegment(
            order=2,
            text="Ánh sáng mặt trời bị tán xạ Rayleigh trong khí quyển.",
            image="b.png",
            sfx="pop",
        ),
        HbtCoreSegment(
            order=3,
            text="Bước sóng ngắn màu xanh lam tán xạ mạnh hơn màu đỏ.",
            image="c.png",
            sfx="whoosh",
        ),
    ]
    sse_events: list[dict[str, Any]] = []

    combined_wav, timings = synthesize_core_segments(
        segments,
        tmp_path,
        voice_provider=None,
        on_sse_event=lambda ev: sse_events.append(ev),
    )

    assert combined_wav.is_file()
    assert combined_wav.stat().st_size > 1000
    assert len(timings) == 3

    # Kiểm tra sự kiện SSE {step: "voice", current, total, percent}
    assert len(sse_events) == 3
    assert sse_events[0]["step"] == "voice"
    assert sse_events[0]["current"] == 1
    assert sse_events[0]["total"] == 3
    assert sse_events[0]["percent"] == 33

    assert sse_events[2]["step"] == "voice"
    assert sse_events[2]["current"] == 3
    assert sse_events[2]["total"] == 3
    assert sse_events[2]["percent"] == 100

    # Kiểm tra mốc micro-giây chính xác và liên tục
    assert timings[0].start_us == 0
    assert timings[0].duration_us > 1_000_000  # > 1 giây
    assert timings[0].end_us == timings[0].duration_us
    assert timings[1].start_us > timings[0].end_us  # cách nhau khoảng nghỉ SEGMENT_GAP_US
    assert timings[2].start_us > timings[1].end_us


# ---------------------------------------------------------------------------
# 2. Kiểm thử BGM thông minh theo topic & acrossfade=d=2.0 + SFX từ library/sfx/
# ---------------------------------------------------------------------------
def test_smart_bgm_acrossfade_and_sfx_scanning() -> None:
    lib_dir = REPO_ROOT / "library"
    for topic in ("history", "fun", "science", "mystery"):
        tracks = scan_music_by_topic(lib_dir, topic=topic, seed=42)
        assert len(tracks) > 0, f"Phải quét được nhạc cho chủ đề {topic}"

    playlist = build_topic_bgm_playlist(lib_dir, target_duration_s=180.0, topic="history", seed=7)
    assert len(playlist) >= 2

    fc, out_label = build_acrossfade_filter_graph(len(playlist), target_duration_s=180.0)
    assert "acrossfade=d=2.0" in fc
    assert out_label == "[bgm]"

    sfx_list = scan_sfx_library(lib_dir)
    assert len(sfx_list) > 0
    whoosh_path = resolve_sfx_file(lib_dir, "whoosh")
    pop_path = resolve_sfx_file(lib_dir, "pop")
    assert whoosh_path is not None and whoosh_path.is_file()
    assert pop_path is not None and pop_path.is_file()


# ---------------------------------------------------------------------------
# 3. Kiểm thử kẹp tài nguyên FFmpeg & quản lý RAM Pillow (.close() + gc.collect())
# ---------------------------------------------------------------------------
def test_ffmpeg_clamping_flags_and_pillow_gc_collect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "-threads" in FFMPEG_RESOURCE_CLAMP
    assert "2" in FFMPEG_RESOURCE_CLAMP
    assert "-filter_threads" in FFMPEG_RESOURCE_CLAMP
    assert "-preset" in FFMPEG_ENCODE_CLAMP
    assert "veryfast" in FFMPEG_ENCODE_CLAMP
    assert "-crf" in FFMPEG_ENCODE_CLAMP
    assert "22" in FFMPEG_ENCODE_CLAMP
    assert "-max_muxing_queue_size" in FFMPEG_ENCODE_CLAMP
    assert "512" in FFMPEG_ENCODE_CLAMP

    import gc

    from PIL import Image

    gc_calls = 0
    orig_collect = gc.collect

    def tracked_collect(*args: Any, **kwargs: Any) -> int:
        nonlocal gc_calls
        gc_calls += 1
        return orig_collect(*args, **kwargs)

    monkeypatch.setattr(gc, "collect", tracked_collect)

    src_img = tmp_path / "src.png"
    im = Image.new("RGB", (600, 800), (80, 120, 160))
    im.save(src_img)
    im.close()

    base_out = tmp_path / "base.png"
    card_out = tmp_path / "card.png"
    build_core_scene_layers_safe(
        {
            "card": {
                "y": "top",
                "lines": [{"text": "Thẻ kem kiểm thử", "size": "m", "color": "ink"}],
            },
            "voice": "Lời thoại kiểm thử giải phóng bộ nhớ Pillow.",
        },
        src_img,
        base_out,
        card_out,
        {"primary": "#8B261D", "accent": "#E6A100"},
    )
    assert base_out.is_file()
    assert card_out.is_file()
    assert gc_calls >= 1


# ---------------------------------------------------------------------------
# 4. Kiểm thử Gemini Client (Chế độ V2): Payload chuẩn chống lỗi 400, đọc .env, Fallback V1
# ---------------------------------------------------------------------------
def test_gemini_client_payload_and_env_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('GEMINI_API_KEY="AIzaSyTestKey123456"\n', encoding="utf-8")

    # Kiểm tra danh sách đường dẫn đa tầng (Multi-path Resolver chỉ đọc từ .env)
    cands = resolve_candidate_env_paths()
    assert cands == [
        Path(GEMINI_REPO_ROOT) / ".env",
        Path(BACKEND_DIR) / ".env",
    ]

    key = load_gemini_api_key(env_file=env_file)
    assert key == "AIzaSyTestKey123456"
    assert is_valid_gemini_api_key(key) is True
    captured = capsys.readouterr().out
    assert (
        "[GEMINI_CONFIG] Đã tìm thấy GEMINI_API_KEY: True (Độ dài: 19, Bắt đầu bằng AIzaSy: True)"
        in captured
    )

    # Key không bắt đầu bằng AIzaSy hoặc rỗng -> không gửi request, bật fallback_v1=True ngay
    assert is_valid_gemini_api_key("") is False
    assert is_valid_gemini_api_key("invalid-key-without-prefix") is False
    with pytest.raises(GeminiClientError) as invalid_exc:
        generate_script_from_prompt(
            "Làm video vì sao về Đấu trường La Mã",
            api_key="invalid-key-without-prefix",
        )
    assert invalid_exc.value.fallback_v1 is True

    # Nếu file .env chỉ chứa key mẫu placeholder, tự động trả về rỗng và bật fallback_v1=True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    placeholder_env = tmp_path / "placeholder.env"
    placeholder_env.write_text("GEMINI_API_KEY=AIzaSy_your_gemini_api_key_here\n", encoding="utf-8")
    empty_key = load_gemini_api_key(env_file=placeholder_env)
    assert empty_key == ""
    with pytest.raises(GeminiClientError) as exc_info:
        generate_script_from_prompt(
            "Làm video vì sao về Đấu trường La Mã",
            env_file=placeholder_env,
        )
    assert exc_info.value.fallback_v1 is True

    user_prompt = "Làm video vì sao về Đấu trường La Mã"
    payload = build_gemini_payload(user_prompt, system_prompt=SYSTEM_PROMPT)
    assert payload == {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
        },
    }


def test_gemini_client_success_and_error_fallback(tmp_path: Path) -> None:
    captured_requests: list[httpx.Request] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        mock_script = {
            "title": "Vì sao Đấu trường La Mã bền vững?",
            "topic": "history",
            "segments": [
                {
                    "order": 1,
                    "text": "Đấu trường La Mã được xây bằng bê tông núi lửa đặc biệt.",
                    "image": "scene-01.png",
                    "sfx": "whoosh",
                },
                {
                    "order": 2,
                    "text": "Cấu trúc vòm giúp phân tán trọng lực đồng đều.",
                    "image": "scene-02.png",
                    "sfx": "pop",
                },
            ],
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(mock_script, ensure_ascii=False)}]}}
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    script = generate_script_from_prompt(
        "Làm video vì sao về Đấu trường La Mã",
        api_key="AIzaSyTestKeyXyz123",
        transport=transport,
    )
    assert script.title == "Vì sao Đấu trường La Mã bền vững?"
    assert script.topic == "history"
    assert len(script.segments) == 2
    assert str(captured_requests[0].url) == GEMINI_ENDPOINT
    assert "?key=" not in str(captured_requests[0].url)
    assert captured_requests[0].headers.get("x-goog-api-key") == "AIzaSyTestKeyXyz123"
    assert captured_requests[0].headers.get("content-type") == "application/json"

    # Kiểm thử lỗi Quota 429 -> ném GeminiClientError có fallback_v1=True
    quota_transport = httpx.MockTransport(
        lambda req: httpx.Response(429, json={"error": {"message": "Resource exhausted"}})
    )
    with pytest.raises(GeminiClientError) as exc_info:
        generate_script_from_prompt(
            "Làm video vì sao về Đấu trường La Mã",
            api_key="AIzaSyTestKeyXyz123",
            transport=quota_transport,
        )
    assert exc_info.value.fallback_v1 is True
    assert exc_info.value.status_code == 429


def test_gemini_client_url_normalization_and_404_model_fallback() -> None:
    # 1. Đảm bảo URL endpoint sạch (không gắn ?key=) và không bao giờ lặp "models/models/..."
    assert MODELS == [
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro",
    ]
    url1 = build_gemini_url("gemini-1.5-flash")
    url2 = build_gemini_url("models/gemini-1.5-flash")
    url3 = build_gemini_url("models/models/gemini-2.0-flash")
    assert (
        url1
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    )
    assert url2 == url1
    assert "?key=" not in url1
    assert "models/models/" not in url3
    assert (
        url3
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    )
    assert build_gemini_headers("  AIzaSyHeaderKey  ") == {
        "Content-Type": "application/json",
        "x-goog-api-key": "AIzaSyHeaderKey",
    }

    # 2. Nếu model đầu tiên (gemini-1.5-flash) và thứ hai (gemini-2.0-flash) trả về 404,
    # tự động thử sang model kế tiếp (gemini-1.5-flash-latest) và nhận status_code == 200
    called_urls: list[str] = []
    statuses: list[int] = []
    sent_headers: list[str] = []

    def fallback_404_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        called_urls.append(url_str)
        sent_headers.append(request.headers.get("x-goog-api-key", ""))
        if len(called_urls) < 3:
            resp = httpx.Response(
                404,
                json={"error": {"message": "model is not found for API version v1beta"}},
            )
            statuses.append(resp.status_code)
            return resp

        mock_script = {
            "title": "Vì sao Đấu trường La Mã vĩ đại?",
            "topic": "history",
            "segments": [
                {
                    "order": 1,
                    "text": "Đấu trường La Mã là biểu tượng kiến trúc cổ đại.",
                    "image": "scene-01.png",
                    "sfx": "whoosh",
                }
            ],
        }
        resp = httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(mock_script, ensure_ascii=False)}]}}
                ]
            },
        )
        statuses.append(resp.status_code)
        return resp

    script = generate_script_from_prompt(
        "Làm video vì sao về Đấu trường La Mã",
        api_key="AIzaSyFallbackTestKey",
        transport=httpx.MockTransport(fallback_404_handler),
    )
    assert statuses == [404, 404, 200]
    assert statuses[-1] == 200
    assert len(called_urls) == 3
    assert all(h == "AIzaSyFallbackTestKey" for h in sent_headers)
    assert (
        called_urls[0]
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    )
    assert (
        called_urls[1]
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    )
    assert (
        called_urls[2]
        == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    )
    assert script.title == "Vì sao Đấu trường La Mã vĩ đại?"


# ---------------------------------------------------------------------------
# 5. Kiểm thử API V1 & V2 và toàn bộ pipeline dựng video tự động
# ---------------------------------------------------------------------------
def test_hbt_core_v1_and_v2_api_endpoints(
    client: Any,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. GET /api/hbt-core/assets
    assets_res = client.get("/api/hbt-core/assets")
    assert assets_res.status_code == 200
    assets_data = assets_res.json()
    assert set(assets_data["topics"]) == {"history", "fun", "science", "mystery"}
    assert "whoosh" in assets_data["sfx_presets"]

    # 2. POST /api/hbt-core/v1/check (Offline 100%, 0 token)
    v1_payload = {
        "title": "Bí ẩn vùng tam giác Бермуда",
        "topic": "mystery",
        "segments": [
            {
                "order": 1,
                "text": "Nhiều tàu thuyền và máy bay từng biến mất bí ẩn tại vùng biển này.",
                "image": "scene-01.png",
                "sfx": "whoosh",
            },
            {
                "order": 2,
                "text": "Các nhà khoa học giải thích bằng dòng hải lưu mạnh và thời tiết cực đoan.",
                "image": "scene-02.png",
                "sfx": "pop",
            },
        ],
    }
    check_res = client.post("/api/hbt-core/v1/check", json={"script": json.dumps(v1_payload)})
    assert check_res.status_code == 200
    assert check_res.json()["ok"] is True
    assert check_res.json()["segments_count"] == 2

    # 3. POST /api/hbt-core/v2/prompt khi thiếu key / lỗi API -> trả về fallback_v1=True
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("hbt.core.gemini_client.load_gemini_api_key", lambda env_file=None: "")
    v2_fail_res = client.post(
        "/api/hbt-core/v2/prompt",
        json={"prompt": "Làm video vì sao về Đấu trường La Mã", "auto_render": False},
    )
    assert v2_fail_res.status_code == 401
    v2_fail_json = v2_fail_res.json()
    assert v2_fail_json["success"] is False
    assert v2_fail_json["fallback_v1"] is True
    assert "error" in v2_fail_json
    assert "message" in v2_fail_json

    # 3b. POST /api/hbt-core/v2/prompt khi xảy ra ngoại lệ bất ngờ -> KHÔNG crash 500,
    # trả JSON có cấu trúc fallback_v1=True
    def _raise_unexpected(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Simulated unexpected crash in V2")

    monkeypatch.setattr("hbt.api.core.generate_script_from_prompt", _raise_unexpected)
    v2_exc_res = client.post(
        "/api/hbt-core/v2/prompt",
        json={"prompt": "Làm video vì sao về Đấu trường La Mã", "auto_render": False},
    )
    assert v2_exc_res.status_code != 500
    v2_exc_json = v2_exc_res.json()
    assert v2_exc_json["success"] is False
    assert v2_exc_json["fallback_v1"] is True
    assert "Simulated unexpected crash in V2" in v2_exc_json["error"]
    assert "Chế độ V1" in v2_exc_json["message"]

    # 4. POST /api/hbt-core/v2/prompt thành công khi mock Gemini
    monkeypatch.setattr(
        "hbt.api.core.generate_script_from_prompt",
        lambda prompt, topic_hint=None: HbtCoreScript.model_validate(v1_payload),
    )
    v2_ok_res = client.post(
        "/api/hbt-core/v2/prompt",
        json={"prompt": "Làm video vì sao về vùng tam giác Bermuda", "auto_render": False},
    )
    assert v2_ok_res.status_code == 200
    v2_data = v2_ok_res.json()
    assert v2_data["ok"] is True
    assert v2_data["mode"] == "v2"
    assert v2_data["script"]["title"] == "Bí ẩn vùng tam giác Бермуда"


def test_hbt_core_full_auto_render_pipeline(tmp_path: Path) -> None:
    project_dir = tmp_path / "projects" / "dau-truong-la-ma"
    project_dir.mkdir(parents=True, exist_ok=True)

    script = HbtCoreScript(
        title="Vì sao Đấu trường La Mã bền vững?",
        topic="history",
        segments=[
            HbtCoreSegment(
                order=1,
                text="Đấu trường La Mã được xây dựng bằng bê tông tro núi lửa siêu bền.",
                image="scene-01.png",
                sfx="whoosh",
            ),
            HbtCoreSegment(
                order=2,
                text="Hệ thống cổng vòm phân tán lực giúp đứng vững qua nhiều thế kỷ.",
                image="scene-02.png",
                sfx="pop",
            ),
        ],
    )

    events: list[tuple[float, str, str, dict[str, Any]]] = []

    def on_progress(pct: float, step: str, msg: str, **extra: Any) -> None:
        events.append((pct, step, msg, extra))

    res = render_hbt_core_auto(
        project_dir=project_dir,
        script=script,
        preview=True,
        fps=30,
        progress=on_progress,
    )

    assert res.video.is_file()
    assert res.video.stat().st_size > 1000
    assert res.publish.is_file()
    assert len(res.timings) == 2
    assert len(res.bgm_tracks) >= 1
    assert len(res.sfx_used) == 2

    # Đảm bảo đã bắn sự kiện tiến trình step="voice" có current, total, percent
    voice_events = [ev for ev in events if ev[1] == "voice"]
    assert len(voice_events) == 2
    assert voice_events[0][3]["current"] == 1
    assert voice_events[0][3]["total"] == 2
    assert voice_events[1][3]["percent"] == 100
