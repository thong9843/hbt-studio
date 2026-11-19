"""Kiểm thử PCM thực cho làm mượt giọng TTS, cắt tiếng ma, chống click & đồng bộ đồng hồ A/V."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from hbt.cinema.audio_director import mix_cinema_audio
from hbt.cinema.hardware import detect_hardware
from hbt.cinema.schema import BeatSpec, TimelineSpec
from hbt.stickv.audio import (
    GLOBAL_LEAD_SILENCE_S,
    align_beat_karaoke,
    clean_tts_wav,
    load_beat_spoken_segments,
    mix_stickv_audio,
    sanitize_tts_text,
    split_beat_sentences,
    synth_stickv_beats_audio,
)
from hbt.stickv.models import StickvBeat
from hbt.stickv.render import allocate_beat_frame_counts


def _write_pcm_wav(path: Path, samples: np.ndarray, *, sr: int = 24000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.clip(np.round(samples * 32767.0), -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(arr.tobytes())
    return path


def _read_pcm_float(path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return sr, data


def _tone(dur_ms: int, *, freq: float = 320.0, amp: float = 0.45, sr: int = 24000) -> np.ndarray:
    n = int(round(sr * dur_ms / 1000.0))
    t = np.arange(n, dtype=np.float32) / sr
    return (amp * np.sin(2.0 * math.pi * freq * t)).astype(np.float32)


def _zeros(dur_ms: int, *, sr: int = 24000) -> np.ndarray:
    return np.zeros(int(round(sr * dur_ms / 1000.0)), dtype=np.float32)


def test_clean_tts_wav_strips_isolated_ghost_tail_and_preserves_rolls(tmp_path: Path) -> None:
    """Xung nhiễu đuôi < 80ms sau >= 220ms im lặng (tiếng ma 'Nếu...') phải bị cắt sạch."""
    sr = 24000
    # 120ms đầu lặng + 420ms giọng thật + 300ms lặng + 50ms tiếng ma + 100ms lặng
    raw_sig = np.concatenate(
        [
            _zeros(120, sr=sr),
            _tone(420, freq=260.0, amp=0.5, sr=sr),
            _zeros(300, sr=sr),
            _tone(50, freq=520.0, amp=0.35, sr=sr),
            _zeros(100, sr=sr),
        ]
    )
    src = _write_pcm_wav(tmp_path / "ghost_tail.wav", raw_sig, sr=sr)
    out = tmp_path / "ghost_clean.wav"

    stats = clean_tts_wav(src, out)
    assert stats["cleaned"] is True
    assert stats["ghosts_removed"] == 1
    assert stats["pre_roll_ms"] >= 35.0
    assert stats["post_roll_ms"] >= 75.0
    # 35ms pre + 420ms speech + 75ms post = ~530ms (tiếng ma tại ~840ms đã mất 100%)
    assert 500.0 <= stats["cleaned_ms"] <= 570.0

    out_sr, out_sig = _read_pcm_float(out)
    assert out_sr == sr
    # 35ms đầu nằm trong vùng pre-roll không có tiếng nói lớn, từ 40ms trở đi giọng thật còn nguyên
    onset_idx = int(round(sr * 0.045))
    mid_idx = int(round(sr * 0.250))
    assert float(np.sqrt(np.mean(out_sig[onset_idx:mid_idx] ** 2))) > 0.25
    # 40ms cuối nằm trong post-roll đã êm dịu, không còn xung nhiễu
    tail_idx = int(round(sr * 0.040))
    assert float(np.max(np.abs(out_sig[-tail_idx:]))) < 0.02


def test_clean_tts_wav_protects_abrupt_onset_and_eliminates_boundary_clicks(
    tmp_path: Path,
) -> None:
    """Clip bắt đầu đột ngột tại t=0 vẫn có pre_roll >= 35ms & cosine fade 18ms/25ms chống click."""
    sr = 24000
    # Sóng cosine bắt đầu ngay biên độ cực đại 0.6 tại sample 0 (worst-case gây tiếng tách)
    n = int(round(sr * 0.40))
    t = np.arange(n, dtype=np.float32) / sr
    abrupt = (0.60 * np.cos(2.0 * math.pi * 220.0 * t)).astype(np.float32)
    src = _write_pcm_wav(tmp_path / "abrupt.wav", abrupt, sr=sr)
    out = tmp_path / "abrupt_clean.wav"

    stats = clean_tts_wav(src, out, pre_roll_ms=35, post_roll_ms=75, fade_in_ms=18, fade_out_ms=25)
    assert stats["pre_roll_ms"] >= 35.0
    assert stats["post_roll_ms"] >= 75.0

    _, sig = _read_pcm_float(out)
    # Điểm nối đầu và cuối phải về 0 (không có bậc nhảy biên độ gây click)
    assert abs(float(sig[0])) == 0.0
    assert abs(float(sig[-1])) == 0.0
    # Bước nhảy lớn nhất giữa 2 mẫu liên tiếp ở 2 đầu ghép không vượt ngưỡng sóng tự nhiên
    max_step = float(np.max(np.abs(np.diff(sig))))
    assert max_step < 0.045
    # 35ms pre-roll phía trước được giữ sạch
    pre_samples = int(round(sr * 0.034))
    assert float(np.max(np.abs(sig[:pre_samples]))) < 0.005


def test_sanitize_tts_text_and_merge_short_sentences() -> None:
    """Loại bỏ markdown thô & không tách mảnh < 5 từ thành lượt TTS rời rạc."""
    cleaned = sanitize_tts_text("  **Vi chấn thương**   cơ học   `12ms`   #tag  ")
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "#" not in cleaned
    assert "  " not in cleaned
    assert cleaned.endswith(".")

    # Mảnh < 5 từ ('Thật bất ngờ!') gộp vào câu kế cận cùng beat
    merged = split_beat_sentences(
        "Thật bất ngờ! Cơ bắp chỉ phát triển mạnh khi bạn ngủ sâu mỗi đêm."
    )
    assert len(merged) == 1
    assert merged[0].startswith("Thật bất ngờ!")

    # Hai câu đầy đủ (>= 5 từ mỗi câu) vẫn tách để giữ nhịp thở 200ms
    split = split_beat_sentences(
        "Não bộ tiêu thụ hai mươi phần trăm năng lượng cơ thể. "
        "Giấc ngủ sâu giúp dọn sạch độc tố chuyển hóa."
    )
    assert len(split) == 2


def test_global_lead_silence_aac_priming_guard_and_cumulative_av_clock(tmp_path: Path) -> None:
    """Beat đầu có 180ms khoảng đệm AAC priming & đồng hồ khung hình tích lũy lệch <= 1 frame."""
    sr = 24000

    class _Provider:
        def status(self) -> SimpleNamespace:
            return SimpleNamespace(ok=True, note="")

        def list_voices(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id="Thanh Bình")]

        def synthesize_many(self, items) -> None:
            for it in items:
                sig = np.concatenate([_zeros(40, sr=sr), _tone(600, sr=sr), _zeros(40, sr=sr)])
                _write_pcm_wav(it.out, sig, sr=sr)

    beats = [
        StickvBeat(id="b001", narration="Nhiều người nghĩ đau cơ mới là tập luyện hiệu quả."),
        StickvBeat(id="b002", narration="Thực tế sợi cơ chỉ to lên khi bạn nghỉ ngơi đủ."),
    ]
    wavs = synth_stickv_beats_audio(
        beats,
        tmp_path / "audio",
        voice_provider=_Provider(),
        voice_id="Thanh Bình",
        global_lead_s=GLOBAL_LEAD_SILENCE_S,
    )

    b0_wav, _ = wavs[0]
    _, b0_sig = _read_pcm_float(b0_wav)
    # 175ms đầu tiên của video phải im lặng hoàn toàn chống AAC 1024-sample priming nuốt chữ đầu
    lead_samples = int(round(sr * 0.175))
    assert float(np.max(np.abs(b0_sig[:lead_samples]))) == 0.0

    segs = load_beat_spoken_segments(b0_wav)
    assert len(segs) == 1
    assert segs[0][0] == pytest.approx(GLOBAL_LEAD_SILENCE_S, abs=0.005)
    timings = align_beat_karaoke(beats[0].narration, b0_wav, beats[0].duration_sec)
    assert timings[0][1] >= GLOBAL_LEAD_SILENCE_S - 0.005

    # Đồng hồ tích lũy A/V cho video dài 10 phút (120 beats lẻ ms) -> sai lệch tổng <= 1 frame
    rng = np.random.default_rng(2026)
    durations = [round(float(x), 3) for x in rng.uniform(2.13, 6.87, size=120)]
    for fps in (24, 30):
        frame_counts = allocate_beat_frame_counts(durations, fps)
        expected_total = int(round(sum(durations) * fps))
        assert abs(sum(frame_counts) - expected_total) <= 1


def test_mix_stickv_audio_and_cinema_audio_48khz_with_empty_library(tmp_path: Path) -> None:
    """Chạy mượt khi thiếu sạch library/ (mô phỏng Ubuntu CI), ra chuẩn 48000 Hz stereo."""
    sr = 24000
    w1 = _write_pcm_wav(
        tmp_path / "b1.wav",
        np.concatenate(
            [_zeros(50, sr=sr), _tone(400, sr=sr), _zeros(260, sr=sr), _tone(45, sr=sr)]
        ),
        sr=sr,
    )
    w2 = _write_pcm_wav(
        tmp_path / "b2.wav",
        np.concatenate([_zeros(50, sr=sr), _tone(400, freq=390.0, sr=sr), _zeros(80, sr=sr)]),
        sr=sr,
    )
    beats = [
        StickvBeat(id="b1", narration="Beat một.", sfx_tag="whoosh"),
        StickvBeat(id="b2", narration="Beat hai.", sfx_tag="none"),
    ]
    out_stickv = tmp_path / "mixed_stickv.wav"
    mix_stickv_audio(
        beats=beats,
        beat_wavs=[(w1, 1.0), (w2, 1.0)],
        topic="science",
        library_dir=tmp_path / "empty_lib",
        assets_dir=tmp_path / "empty_assets",
        out_wav=out_stickv,
    )
    assert out_stickv.is_file()
    with wave.open(str(out_stickv), "rb") as wf:
        assert wf.getframerate() == 48000
        assert wf.getnchannels() == 2

    # AudioDirector cũng phải lọc tiếng ma và chèn global_lead_s = 0.18s
    spec = TimelineSpec(
        slug="smooth-cinema",
        title="Cinema Smooth Audio",
        beats=[
            BeatSpec(id="b1", narration="Đoạn 1", duration_sec=1.0),
            BeatSpec(id="b2", narration="Đoạn 2", duration_sec=1.0),
        ],
    )
    out_cinema = tmp_path / "mixed_cinema.wav"
    res = mix_cinema_audio(
        spec,
        {"b1": w1, "b2": w2},
        out_cinema,
        library_dir=tmp_path / "empty_lib",
        work_dir=tmp_path / "cinema_work",
        hw=detect_hardware(probe_fn=lambda: (False, "cpu")),
    )
    assert res["global_lead_s"] == pytest.approx(GLOBAL_LEAD_SILENCE_S)
    assert res["ghosts_removed"] == 1
    assert out_cinema.is_file()
    with wave.open(str(out_cinema), "rb") as wf:
        assert wf.getframerate() == 48000
        assert wf.getnchannels() == 2
