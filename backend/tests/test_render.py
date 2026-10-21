import json

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
    assert (prev.width, prev.height, prev.fps, prev.final_preset) == (540, 960, 30, "ultrafast")


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

SCRIPT = ["Xin chào các bạn.", "Hôm nay mình học.", "Hẹn gặp lại nhé."]
SPEECH = [("gap", 0.3), ("tone", 1.0), ("gap", 0.8), ("tone", 1.0), ("gap", 0.8), ("tone", 1.0)]
BODY = 0.2 + 0.3 + 1.0 + 0.8 + 1.0 + 0.8 + 1.0 + 0.3 + 1.6  # giọng sau prep_voice (có đệm đuôi)


def make_project(tmp_path, *, tail=(), outro_voice=True, aligner="silence", **settings):
    pdir = tmp_path / "proj"
    (pdir / "images").mkdir(parents=True)
    for i, color in enumerate([(220, 90, 70), (60, 140, 160), (240, 200, 80)], 1):
        Image.new("RGB", (540, 960), color).save(pdir / "images" / f"s{i}.png")
    write_wav(pdir / "voice.wav", [*SPEECH, *tail, ("gap", 0.3)])
    project = {
        "version": 1,
        "slug": "demo",
        "title": "Demo",
        "series": "Loạt thử",
        "voice": "voice.wav",
        "settings": {"aligner": aligner, **settings},
        "scenes": [
            {
                "image": f"images/s{i}.png",
                "voice": text,
                "card": {"lines": [{"text": f"Cảnh {i}", "size": "l", "color": "accent"}]},
            }
            for i, text in enumerate(SCRIPT, 1)
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
    pdir, opts = make_project(tmp_path, tail=[("gap", 0.8), ("tone", 4.0)], outro=False)
    res = render_project(pdir, opts)
    log = res.log.read_text(encoding="utf-8")
    assert "Đã cắt 1 đoạn thừa ở cuối file giọng" in log
    # chữ cuối kết thúc ở 5,3 s (đã trễ 0,2 s) → giọng giữ đến +0,35 s, rồi đệm 1,6 s
    assert res.duration == pytest.approx(
        0.2 + 0.3 + 1.0 + 0.8 + 1.0 + 0.8 + 1.0 + 0.35 + 1.6, abs=0.15
    )


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
