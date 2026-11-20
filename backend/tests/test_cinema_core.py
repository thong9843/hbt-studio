"""Unit test cho Lõi Cinema Core: Schema, Hardware Probe, LayerCache, BeatCache và WarmTTSPool."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import Image

from hbt.cinema.cache import (
    BEAT_AUDIO_CHANNELS,
    BEAT_AUDIO_RATE,
    BEAT_PIX_FMT,
    BEAT_VIDEO_TIMESCALE,
    BeatCache,
    build_normalized_beat_flags,
)
from hbt.cinema.hardware import (
    CPU_LAYER_CACHE_MB,
    GPU_LAYER_CACHE_MB,
    detect_hardware,
    reset_hardware_cache,
)
from hbt.cinema.layer_cache import FontCache, LayerCache
from hbt.cinema.schema import BeatSpec, BoardSpec, TimelineSpec
from hbt.pipeline.ffutil import ffmpeg_exe, probe
from hbt.shared.tts.worker_pool import WarmTTSPool


def _make_sample_beat(beat_id: str = "b001", narration: str = "Xin chào") -> BeatSpec:
    return BeatSpec(
        id=beat_id,
        chapter=1,
        narration=narration,
        duration_sec=1.5,
        shot_type="desk_wide",
        board=BoardSpec(title="Thử nghiệm", bullets=["Ý chính **1**"], takeaway="Chốt lại"),
    )


def test_timeline_spec_and_beat_content_hash_determinism() -> None:
    b1 = _make_sample_beat()
    b2 = _make_sample_beat()
    assert b1.content_hash() == b2.content_hash()

    b3 = b1.model_copy(update={"narration": "Lời thoại đã thay đổi"})
    assert b3.content_hash() != b1.content_hash()
    assert b1.content_hash(aspect="16:9") != b1.content_hash(aspect="9:16")

    spec = TimelineSpec(slug="test-slug", title="Kiểm thử Cinema", beats=[b1])
    assert spec.width == 1080
    assert spec.height == 1920
    assert spec.total_duration_sec == 1.5


def test_hardware_probe_fallback_cpu_and_gpu_switch() -> None:
    reset_hardware_cache()
    cpu_prof = detect_hardware(probe_fn=lambda: (False, "no nvidia device"))
    assert cpu_prof.mode == "cpu"
    assert cpu_prof.video_encoder == "libx264"
    assert cpu_prof.layer_cache_mb == CPU_LAYER_CACHE_MB
    assert cpu_prof.ffmpeg_threads == 2
    assert "-threads" in cpu_prof.ffmpeg_resource_clamp

    gpu_prof = detect_hardware(probe_fn=lambda: (True, None))
    assert gpu_prof.mode == "gpu"
    assert gpu_prof.video_encoder == "h264_nvenc"
    assert gpu_prof.layer_cache_mb == GPU_LAYER_CACHE_MB
    assert gpu_prof.ffmpeg_threads == 0

    real_prof = detect_hardware(force_refresh=True)
    assert real_prof.nvenc_probed is True
    assert real_prof.video_encoder in ("libx264", "h264_nvenc")


def test_layer_cache_enforces_ram_cap_closes_evicted_images_and_tracks_hits() -> None:
    closed_keys: list[str] = []

    # Mỗi ảnh 200x200 RGBA = 160,000 bytes; trần 350,000 bytes chứa tối đa 2 ảnh
    cache = LayerCache(max_bytes=350_000)

    def _make_tracked(tag: str) -> Image.Image:
        img = Image.new("RGBA", (200, 200), (10, 20, 30, 255))
        orig_close = img.close

        def _wrapped_close() -> None:
            closed_keys.append(tag)
            orig_close()

        img.close = _wrapped_close  # type: ignore[method-assign]
        return img

    cache.get_or_bake("k1", lambda: _make_tracked("k1"))
    cache.get_or_bake("k2", lambda: _make_tracked("k2"))
    # Đọc lại k1 nhiều lần -> hit rate cao, đồng thời đẩy k2 xuống cuối LRU
    for _ in range(18):
        assert cache.get("k1") is not None

    # Thêm k3 -> phải evict k2 và gọi k2.close()
    cache.get_or_bake("k3", lambda: _make_tracked("k3"))
    assert "k2" in closed_keys
    assert cache.current_bytes <= 350_000
    assert cache.evictions == 1
    assert cache.hit_rate >= 0.85

    cache.close()
    assert "k1" in closed_keys
    assert "k3" in closed_keys
    assert cache.current_bytes == 0


def test_font_cache_reuses_loaded_fonts(tmp_path: Path) -> None:
    fc = FontCache()
    f1 = fc.get_font(None, 24)
    f2 = fc.get_font(None, 24)
    assert f1 is f2
    assert fc.stats()["hits"] == 1


def _render_synthetic_normalized_mp4(out_mp4: Path, *, color: str, fps: int = 30) -> None:
    import subprocess

    hw = detect_hardware(probe_fn=lambda: (False, "force cpu for deterministic test"))
    flags = build_normalized_beat_flags(fps=fps, hw=hw)
    cmd = [
        ffmpeg_exe(),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=320x240:r={fps}:d=0.4",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        "0.4",
        *flags,
        str(out_mp4),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr


def test_beat_cache_normalizes_streams_and_concats_copy(tmp_path: Path) -> None:
    cache = BeatCache(tmp_path / "beat_cache")
    src1 = tmp_path / "b1_src.mp4"
    src2 = tmp_path / "b2_src.mp4"
    _render_synthetic_normalized_mp4(src1, color="red", fps=30)
    _render_synthetic_normalized_mp4(src2, color="blue", fps=30)

    k1 = "a" * 32
    k2 = "b" * 32
    cached1 = cache.store_from_file(k1, src1)
    cached2 = cache.store_from_file(k2, src2)
    assert cache.lookup(k1) == cached1
    assert cache.lookup(k2) == cached2

    joined = tmp_path / "joined.mp4"
    cache.concat_cached_beats([cached1, cached2], joined, work_dir=tmp_path / "work")
    assert joined.is_file()

    info = probe(joined)
    v_streams = [s for s in info["streams"] if s.get("codec_type") == "video"]
    a_streams = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    assert v_streams and a_streams
    assert v_streams[0]["pix_fmt"] == BEAT_PIX_FMT
    assert v_streams[0]["time_base"] == f"1/{BEAT_VIDEO_TIMESCALE}"
    assert int(a_streams[0]["sample_rate"]) == BEAT_AUDIO_RATE
    assert int(a_streams[0]["channels"]) == BEAT_AUDIO_CHANNELS
    assert float(info["format"]["duration"]) >= 0.70


def test_warm_tts_pool_fallback_and_persistent_resident_worker_with_ttl(tmp_path: Path) -> None:
    # 1. CI fallback khi thiếu .venv-tts / weights
    ci_pool = WarmTTSPool(models_dir=tmp_path / "empty_models", venv_dir=tmp_path / "no_venv")
    assert ci_pool.is_available() is False
    fb_wav = tmp_path / "fallback.wav"
    ci_pool.synthesize("Xin chào HBT Studio", "Thanh Bình", fb_wav)
    assert fb_wav.is_file() and fb_wav.stat().st_size > 44

    # 2. Worker thường trú thật: tái sử dụng cùng 1 PID giữa các lần gọi và tự tắt khi quá idle_ttl
    dummy_worker = tmp_path / "dummy_tts_worker.py"
    dummy_worker.write_text(
        "\n".join(
            [
                "import json, os, sys, wave",
                "from pathlib import Path",
                "boot = json.dumps({'ok': True, 'ready': True, 'pid': os.getpid()})",
                "sys.stdout.write(boot + '\\n')",
                "sys.stdout.flush()",
                "for line in sys.stdin:",
                "    line = line.strip()",
                "    if not line:",
                "        continue",
                "    req = json.loads(line)",
                "    cmd = req.get('cmd')",
                "    if cmd == 'shutdown':",
                "        sys.stdout.write(json.dumps({'ok': True, 'bye': True}) + '\\n')",
                "        sys.stdout.flush()",
                "        break",
                "    if cmd == 'synth':",
                "        out = Path(req['out'])",
                "        out.parent.mkdir(parents=True, exist_ok=True)",
                "        with wave.open(str(out), 'wb') as wf:",
                "            wf.setnchannels(1)",
                "            wf.setsampwidth(2)",
                "            wf.setframerate(24000)",
                "            wf.writeframes(b'\\x00\\x00' * 2400)",
                "        sys.stdout.write(json.dumps({'ok': True, 'pid': os.getpid()}) + '\\n')",
                "        sys.stdout.flush()",
            ]
        ),
        encoding="utf-8",
    )

    with WarmTTSPool(
        models_dir=tmp_path,
        idle_ttl_sec=0.35,
        reaper_interval_sec=0.05,
        worker_cmd=[sys.executable, "-u", str(dummy_worker)],
    ) as pool:
        assert pool.is_available() is True
        w1 = tmp_path / "out1.wav"
        w2 = tmp_path / "out2.wav"
        pool.synthesize("Câu thứ nhất", "Thanh Bình", w1)
        pid_first = pool.worker_pid
        pool.synthesize("Câu thứ hai", "Thanh Bình", w2)
        pid_second = pool.worker_pid

        assert w1.is_file() and w2.is_file()
        assert pid_first is not None
        assert pid_first == pid_second
        assert pool.spawn_count == 1
        assert pool.is_warm is True

        # Chờ reaper hết TTL tự giải phóng RAM
        deadline = time.monotonic() + 2.5
        while pool.is_warm and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pool.is_warm is False
        assert pool.worker_pid is None
