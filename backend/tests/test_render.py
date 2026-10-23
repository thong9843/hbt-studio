import hashlib
import json
import subprocess

import numpy as np
import pytest
from PIL import Image

from hbt.pipeline import ffutil, render
from hbt.pipeline.ffutil import measure_lufs, media_duration, probe, run_ffmpeg
from hbt.pipeline.render import RenderError, RenderOptions, render_project
from tests.helpers import needs_ffmpeg, write_wav

# ---------------------------------------------------------------- toán học chuyển động (4b)


@pytest.mark.parametrize("fn", [render.smoothstep, render.ease_in_out_cubic])
def test_easing_endpoints_and_monotonic(fn):
    assert fn(0) == 0 and fn(1) == 1
    xs = [i / 100 for i in range(101)]
    ys = [fn(x) for x in xs]
    assert all(b >= a for a, b in zip(ys, ys[1:], strict=False))
    assert fn(-1) == 0 and fn(2) == 1  # kẹp ngoài [0, 1]


def test_easing_values():
    assert render.smoothstep(0.5) == 0.5
    assert render.ease_in_out_cubic(0.5) == 0.5
    assert render.ease_in_out_cubic(0.25) == pytest.approx(4 * 0.25**3)


@pytest.mark.parametrize("fps, frames", [(30, 12), (50, 20), (60, 24)])
def test_transition_is_0_4_seconds(fps, frames):
    assert render.transition_frames(fps) == frames


def test_zoom_expressions():
    odd, st = render.zoom_expr(1, 100, 50, punch=False)
    even, _ = render.zoom_expr(2, 100, 50, punch=False)
    assert odd.startswith("1+0.08*") and even.startswith("1.08-0.08*")
    assert "(3-2*" in odd and st == 0.3  # smoothstep
    punch, st = render.zoom_expr(1, 100, 50, punch=True)
    assert "if(lt(on,22)," in punch and "1.18-0.18*" in punch and "pow(1-" in punch
    assert st == 0.15
    assert "if(lt(on,13)," in render.zoom_expr(3, 100, 30, punch=True)[0]


def test_offsets_and_durations_cover_total():
    first, last = [0.5, 5.0, 9.0], [4.0, 8.0, 12.0]
    offsets = render.compute_offsets(first, last)
    assert offsets == pytest.approx([4.5 - 0.2, 8.5 - 0.2])
    durs = render.clip_durations(offsets, 13.0)
    assert durs == pytest.approx([4.7, 4.4, 4.7])
    # các clip chồng nhau đúng X ở mỗi lần chuyển → tổng dài đúng bằng `total`
    assert sum(durs) - (len(durs) - 1) * render.X == pytest.approx(13.0)


def test_quality_modes():
    full = render.quality_for(False, 50)
    assert (full.width, full.height, full.fps, full.clip_crf, full.final_crf) == (
        1080,
        1920,
        50,
        12,
        16,
    )
    prev = render.quality_for(True, 50)
    assert (prev.width, prev.height, prev.fps, prev.final_preset) == (540, 960, 30, "veryfast")
    assert (prev.final_crf, prev.audio_bitrate) == (30, "96k")
    assert (full.final_crf, full.audio_bitrate) == (16, "192k")


def test_slide_frame_moves_from_a_to_b():
    a = np.zeros((8, 40, 3), np.uint8)
    b = np.full((8, 40, 3), 255, np.uint8)
    tn = 20
    means = [render.slide_frame(a, b, lb, tn).mean() for lb in range(tn)]
    assert means[0] < 10 and means[-1] > 245
    assert all(y >= x for x, y in zip(means, means[1:], strict=False))
    first = render.slide_frame(a, b, 10, tn)
    assert first.shape == a.shape and first.dtype == np.uint8
    # nhoè chuyển động: có cột trung gian (không chỉ 0/255) ở giữa quá trình
    assert len({int(v) for v in first[0, :, 0]}) > 2


# ---------------------------------------------------------------- clip cảnh


@needs_ffmpeg
def test_scene_clip_full_quality_frame_count(tmp_path):
    base, card = tmp_path / "b.png", tmp_path / "t.png"
    Image.new("RGB", (1080, 1920), (200, 80, 60)).save(base)
    Image.new("RGBA", (1080, 1920), (0, 0, 0, 0)).save(card)
    out = tmp_path / "c.mp4"
    q = render.quality_for(False, 50)
    n = render.scene_clip(base, card, 1.0, 1, q, False, out)
    assert n == round(1.0 * 50) == 50
    vs = probe(out)["streams"][0]
    assert (vs["width"], vs["height"], vs["r_frame_rate"], vs["nb_frames"]) == (
        1080,
        1920,
        "50/1",
        "50",
    )


# ---------------------------------------------------------------- dựng đầu-cuối (Xem nhanh)

SENTENCES = ["Xin chào các bạn.", "Hôm nay mình học.", "Hẹn gặp lại nhé."]
COLORS = [(220, 90, 70), (60, 140, 160), (240, 200, 80), (120, 90, 200)]


def speech(n):
    """Giọng giả: mỗi cảnh một câu dài 1,0 s, cách nhau 0,8 s."""
    parts = [("gap", 0.3)]
    for i in range(n):
        parts += [("tone", 1.0)] + ([("gap", 0.8)] if i < n - 1 else [])
    return parts


def body_len(n, tail=0.0):
    """Độ dài giọng sau prep_voice: trễ 0,2 s + lời + 0,3 s lặng + đệm 1,6 s (+ đuôi thừa)."""
    return 0.2 + 0.3 + n * 1.0 + (n - 1) * 0.8 + tail + 0.3 + 1.6


BODY = body_len(3)


def make_project(
    tmp_path, *, n=3, tail=(), outro_voice=True, aligner="silence", voice=None, **settings
):
    pdir = tmp_path / "proj"
    (pdir / "images").mkdir(parents=True)
    for i in range(n):
        Image.new("RGB", (540, 960), COLORS[i % len(COLORS)]).save(
            pdir / "images" / f"s{i + 1}.png"
        )
    write_wav(pdir / "voice.wav", [*speech(n), *tail, ("gap", 0.3)])
    project = {
        "version": 1,
        "slug": "demo",
        "title": "Demo",
        "series": "Loạt thử",
        "voice": voice or "voice.wav",
        "settings": {"aligner": aligner, **settings},
        "scenes": [
            {
                "image": f"images/s{i + 1}.png",
                "voice": SENTENCES[i % len(SENTENCES)],
                "card": {"lines": [{"text": f"Cảnh {i + 1}", "size": "l", "color": "accent"}]},
            }
            for i in range(n)
        ],
        "publish": {"hook": "Xin chào", "hashtags": ["demo"]},
    }
    (pdir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    brand, library = tmp_path / "brand", tmp_path / "library"
    (brand / "outro").mkdir(parents=True)
    (library / "outro").mkdir(parents=True)
    run_ffmpeg([
        "-f", "lavfi", "-i", "color=c=red:s=270x480:r=50:d=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", brand / "outro" / render.OUTRO_FILE,
    ])  # fmt: skip
    if outro_voice:
        write_wav(library / "outro" / "voice.wav", [("tone", 2.65, 0.5)], freq=300)
    return pdir, RenderOptions(preview=True, library_dir=library, brand_dir=brand)


@needs_ffmpeg
def test_preview_render_end_to_end(tmp_path):
    pdir, opts = make_project(tmp_path)
    steps = []
    res = render_project(pdir, opts, progress=lambda p, s, m: steps.append((p, s)))

    vs = next(s for s in probe(res.video)["streams"] if s["codec_type"] == "video")
    assert (vs["width"], vs["height"], vs["r_frame_rate"]) == (540, 960, "30/1")
    assert any(s["codec_type"] == "audio" for s in probe(res.video)["streams"])
    # phần có lời + outro 4,0 s − hoà trộn 0,5 s
    assert res.duration == pytest.approx(BODY + 4.0 - 0.5, abs=0.1)
    assert res.aligner == "silence"
    assert (res.width, res.height, res.fps) == (540, 960, 30)

    assert res.srt.read_text(encoding="utf-8").count(" --> ") == 3
    assert "[YouTube Shorts]" in res.publish.read_text(encoding="utf-8")
    log = res.log.read_text(encoding="utf-8")
    assert "Aligner đã dùng: silence" in log
    percents = [p for p, _ in steps]
    assert percents == sorted(percents) and percents[0] == 0 and percents[-1] == 100
    assert {s for _, s in steps} >= {"Kiểm tra", "Căn chữ", "Clip từng cảnh", "Ghép cuối", "Xong"}


@needs_ffmpeg
def test_render_without_outro(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    res = render_project(pdir, opts)
    assert res.duration == pytest.approx(BODY, abs=0.1)
    assert abs(media_duration(res.video) - BODY) < 0.1


@needs_ffmpeg
def test_outro_option_overrides_project_setting(tmp_path):
    pdir, opts = make_project(tmp_path, outro=True)
    opts.outro = False
    assert render_project(pdir, opts).duration == pytest.approx(BODY, abs=0.1)


@needs_ffmpeg
def test_render_without_outro_voice_still_builds(tmp_path):
    pdir, opts = make_project(tmp_path, outro_voice=False)
    res = render_project(pdir, opts)
    assert res.duration == pytest.approx(BODY + 3.5, abs=0.1)
    assert any("ting" in w for w in res.warnings)


@needs_ffmpeg
def test_render_trims_extra_tail_and_logs(tmp_path):
    # 8 cảnh + đuôi thừa 3 s: đủ điều kiện tự cắt (chi phí giảm ≥ 1,0, đoạn cuối ≥ 1,5 s)
    pdir, opts = make_project(tmp_path, n=8, tail=[("gap", 0.8), ("tone", 3.0)], outro=False)
    res = render_project(pdir, opts)
    log = res.log.read_text(encoding="utf-8")
    assert "Đã cắt 1 đoạn thừa ở cuối file giọng" in log
    # giọng giữ đến chữ cuối + 0,35 s rồi đệm lại 1,6 s
    assert res.duration == pytest.approx(0.2 + 0.3 + 8 + 7 * 0.8 + 0.35 + 1.6, abs=0.15)
    assert not res.warnings


@needs_ffmpeg
def test_short_script_with_tail_warns_and_keeps_audio(tmp_path):
    pdir, opts = make_project(tmp_path, tail=[("gap", 0.8), ("tone", 3.0)], outro=False)
    res = render_project(pdir, opts)
    assert any(w.startswith("Có thể có đoạn thừa ở cuối file giọng") for w in res.warnings)
    assert "Đã cắt" not in res.log.read_text(encoding="utf-8")
    assert res.duration == pytest.approx(body_len(3, tail=3.8), abs=0.15)


@needs_ffmpeg
def test_voice_trim_end_cuts_before_alignment(tmp_path):
    speech_end = 0.3 + 3 + 2 * 0.8  # giây trên file gốc
    pdir, opts = make_project(
        tmp_path,
        tail=[("gap", 0.8), ("tone", 3.0)],
        outro=False,
        voice={"file": "voice.wav", "trim_end": speech_end + 0.4},
    )
    res = render_project(pdir, opts)
    assert "Cắt đuôi giọng theo voice.trim_end = 5,30 giây" in res.log.read_text(encoding="utf-8")
    assert not res.warnings
    assert res.duration == pytest.approx(speech_end + 0.4 + 0.2 + 1.6, abs=0.15)
    # phụ đề cuối vẫn nằm đúng cuối lời (không bị kéo sang đoạn đã cắt)
    last_cue = res.srt.read_text(encoding="utf-8").strip().splitlines()[-2]
    end = last_cue.split(" --> ")[1]
    assert end.startswith("00:00:05")


@needs_ffmpeg
def test_voice_trim_end_beyond_the_file_is_an_error(tmp_path):
    pdir, opts = make_project(tmp_path, voice={"file": "voice.wav", "trim_end": 99})
    with pytest.raises(RenderError, match="trim_end"):
        render_project(pdir, opts)


def add_music(pdir, parts, start=None):
    """Gắn nhạc giả `music.wav` (parts như write_wav) vào project.json."""
    write_wav(pdir / "music.wav", parts)
    path = pdir / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["music"] = {"file": "music.wav", "start": start, "credit": "Bài thử"}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def read_meta(res):
    return json.loads((res.job_dir / "meta.json").read_text(encoding="utf-8"))


@needs_ffmpeg
def test_manual_music_start_is_used_and_recorded(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    add_music(pdir, [("tone", 5, 0.02), ("tone", 40, 0.4)], start=3.0)
    res = render_project(pdir, opts)
    meta = read_meta(res)
    assert meta["music_start"] == 3.0 and meta["music_start_source"] == "manual"
    assert meta["music_sha256"] == hashlib.sha256((pdir / "music.wav").read_bytes()).hexdigest()
    assert "Nhạc bắt đầu từ 3.0 s (đặt tay)" in res.log.read_text(encoding="utf-8")
    assert not res.warnings


@needs_ffmpeg
def test_auto_music_start_is_picked_and_recorded(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    add_music(pdir, [("tone", 5, 0.02), ("tone", 40, 0.4)])
    res = render_project(pdir, opts)
    meta = read_meta(res)
    assert meta["music_start"] == 5.0 and meta["music_start_source"] == "auto"
    assert "Nhạc bắt đầu từ 5.0 s (tự chọn" in res.log.read_text(encoding="utf-8")


@needs_ffmpeg
def test_no_music_records_no_music_start(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    meta = read_meta(render_project(pdir, opts))
    assert meta["music_start"] is None and meta["music_start_source"] is None
    assert meta["music_sha256"] is None


@needs_ffmpeg
def test_warns_when_music_is_shorter_than_video_but_still_renders(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    add_music(pdir, [("tone", 5, 0.4)], start=0.0)  # video dài khoảng 7 s
    res = render_project(pdir, opts)
    assert any(w.startswith("Nhạc ngắn hơn video") for w in res.warnings)
    assert res.video.is_file()


@needs_ffmpeg
def test_second_render_reuses_cache(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    render_project(pdir, opts)
    res = render_project(pdir, opts)
    log = res.log.read_text(encoding="utf-8")
    assert "Dùng lại 3 clip đã có" in log
    assert "voice.wav: dùng bản đã có" in log and "Mốc thời gian chữ: dùng bản đã có" in log


@needs_ffmpeg
def test_missing_files_are_reported(tmp_path):
    pdir, opts = make_project(tmp_path)
    (pdir / "images" / "s2.png").unlink()
    with pytest.raises(RenderError, match=r"Thiếu file:\n.*s2\.png"):
        render_project(pdir, opts)


@needs_ffmpeg
def test_incomplete_draft_is_rejected_with_a_list(tmp_path):
    pdir, opts = make_project(tmp_path)
    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    data["scenes"][1]["image"] = ""
    data["scenes"][2]["voice"] = ""
    (pdir / "project.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RenderError) as e:
        render_project(pdir, opts)
    assert "Project chưa đủ để dựng" in str(e.value)
    assert "Cảnh 2: chưa có ảnh" in str(e.value) and "Cảnh 3: lời đọc đang trống" in str(e.value)


@needs_ffmpeg
def test_rejects_unsupported_fps(tmp_path):
    pdir, opts = make_project(tmp_path)
    opts.fps = 45
    with pytest.raises(RenderError, match="fps"):
        render_project(pdir, opts)


@needs_ffmpeg
def test_measured_loudness_is_reported(tmp_path):
    pdir, opts = make_project(tmp_path, outro=False)
    res = render_project(pdir, opts)
    assert res.lufs == pytest.approx(measure_lufs(res.video), abs=0.05)


def test_ffmpeg_missing_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(ffutil.shutil, "which", lambda _: None)
    with pytest.raises(ffutil.FFmpegError, match="FFmpeg"):
        ffutil.ffmpeg_exe()


def test_ffmpeg_not_found_error_carries_the_install_hint(monkeypatch, tmp_path):
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    for call in (lambda: ffutil.run_ffmpeg(["-version"]), lambda: ffutil.probe("x.mp4")):
        with pytest.raises(ffutil.FFmpegNotFound) as e:
            call()
        assert "winget install Gyan.FFmpeg" in str(e.value) and "README.md" in str(e.value)
    assert issubclass(ffutil.FFmpegNotFound, ffutil.FFmpegError)


# ---------------------------------------------------------------- Xem nhanh 10 s đầu (d)
BODY8 = body_len(8)


def frame_at(video, t):
    cmd = [
        ffutil.ffmpeg_exe(), "-v", "error", "-ss", str(t), "-i", str(video),
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]  # fmt: skip
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.uint8).astype(np.float64)


def pcm(video):
    cmd = [
        ffutil.ffmpeg_exe(), "-v", "error", "-i", str(video),
        "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-",
    ]  # fmt: skip
    data = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0


def rms(x):
    return float(np.sqrt((x**2).mean())) if len(x) else 0.0


@needs_ffmpeg
def test_head_preview_renders_only_the_first_seconds(tmp_path):
    pdir, opts = make_project(tmp_path, n=8)  # outro bật theo project, phải bị bỏ
    add_music(pdir, [("tone", 5, 0.02), ("tone", 60, 0.4)])
    opts.preview_seconds = 10
    res = render_project(pdir, opts)
    log = res.log.read_text(encoding="utf-8")
    meta = read_meta(res)

    assert res.duration == pytest.approx(10.0, abs=0.2)
    vs = next(s for s in probe(res.video)["streams"] if s["codec_type"] == "video")
    assert (vs["width"], vs["height"], vs["r_frame_rate"]) == (540, 960, "30/1")
    assert res.srt is None and not (res.job_dir / "captions.srt").exists()
    assert res.lufs is None and meta["lufs"] is None
    assert res.preview_seconds == 10 and meta["preview_seconds"] == 10
    built = len(list((pdir / "build" / "clips").glob("c*.mp4")))
    assert 3 <= built < 8 and f"dựng {built}/8 cảnh, không outro" in log
    assert "Phần có lời dài" in log and f"{BODY8:.2f}" in log  # căn chữ trên cả video
    assert meta["music_start"] == 5.0 and meta["music_start_source"] == "auto"


@needs_ffmpeg
def test_head_preview_matches_the_full_preview_and_fades_out(tmp_path):
    pdir, opts = make_project(tmp_path, n=8, outro=False)
    add_music(pdir, [("tone", 5, 0.02), ("tone", 60, 0.4)])
    opts.preview_seconds = 10
    head = render_project(pdir, opts)
    opts.preview_seconds = None
    full = render_project(pdir, opts)  # clip cắt dở của bản 10 s không được dùng lại cho bản đủ
    assert full.duration == pytest.approx(BODY8, abs=0.15)
    assert full.preview_seconds is None and read_meta(full)["preview_seconds"] is None

    for t in (0.5, 3.0, 6.0, 9.5):  # cùng khung hình (sai khác nhỏ do mã hoá)
        diff = np.abs(frame_at(head.video, t) - frame_at(full.video, t)).mean()
        assert diff < 3.0, (t, diff)
    a, b = read_meta(head), read_meta(full)
    assert (a["music_start"], a["music_start_source"]) == (
        b["music_start"],
        b["music_start_source"],
    )
    assert a["music_sha256"] == b["music_sha256"]

    audio = pcm(head.video)
    assert rms(audio[-400:]) < 0.25 * rms(audio[8 * 4000 : 9 * 4000])  # 0,05 s cuối đã nhỏ dần


@needs_ffmpeg
def test_preview_seconds_not_shorter_than_the_video_renders_the_whole_video(tmp_path):
    pdir, opts = make_project(tmp_path)  # lời đọc khoảng 7 s, outro bật
    opts.preview_seconds = 10
    res = render_project(pdir, opts)
    assert res.duration == pytest.approx(BODY + 4.0 - 0.5, abs=0.1)  # có outro như xem nhanh đủ
    assert res.preview_seconds is None and read_meta(res)["preview_seconds"] is None
    assert res.srt is not None and res.lufs is not None


@needs_ffmpeg
@pytest.mark.parametrize(("preview", "seconds"), [(False, 10), (True, 0), (True, -1), (True, 61)])
def test_preview_seconds_is_validated(tmp_path, preview, seconds):
    pdir, opts = make_project(tmp_path)
    opts.preview, opts.preview_seconds = preview, seconds
    with pytest.raises(RenderError, match="preview_seconds"):
        render_project(pdir, opts)
