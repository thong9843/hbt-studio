"""Bộ dựng video PostV (docs/postv/IMPLEMENT-POSTV.md mục 6)."""

import json

import numpy as np
import pytest
from PIL import Image

from hbt.pipeline import render as hbt_render
from hbt.pipeline.cancel import CancelToken, RenderCancelled
from hbt.pipeline.ffutil import media_duration, probe, run_ffmpeg
from hbt.pipeline.render import RenderError, RenderOptions
from hbt.postv import render as R
from hbt.postv.backgrounds import BackgroundLibrary
from hbt.postv.render import postv_outro_clip, render_postv
from hbt.sensitive import SensitiveWords
from tests.helpers import needs_ffmpeg, write_wav
from tests.test_postv_backgrounds import make_clip

LINES = [
    "Chuyện này thật khó tin.",
    "Có người đăng một bài rất lạ.",
    "Mình thấy bình luận này hay.",
    "Mình nghĩ ai cũng vậy.",
]
META = {"title": "Parkour 01", "source": "Tự quay", "license": "Tự quay", "url": "", "tags": []}


def speech(n):
    """Giọng giả: mỗi đoạn một câu dài 1,0 s, cách nhau 0,8 s (như test dựng HBT)."""
    parts = [("gap", 0.3)]
    for i in range(n):
        parts += [("tone", 1.0)] + ([("gap", 0.8)] if i < n - 1 else [])
    return parts


def body_len(n):
    """Độ dài giọng sau prep_voice: trễ 0,2 s + lời + 0,3 s lặng + đệm 1,6 s."""
    return 0.2 + 0.3 + n * 1.0 + (n - 1) * 0.8 + 0.3 + 1.6


def make_postv(tmp_path, *, n=4, lines=None, thumbnail=False, **settings):
    pdir = tmp_path / "proj"
    pdir.mkdir()
    texts = lines or LINES[:n]
    roles = ["hook", "post", "comment", "commentary", "commentary"][:n]
    write_wav(pdir / "voice.wav", [*speech(n), ("gap", 0.3)])
    project = {
        "version": 1,
        "kind": "postv",
        "slug": "demo",
        "title": "Demo",
        "series": "Loạt thử",
        "source": {"url": "https://example.test/bai", "note": ""},
        "post": {
            "handle": "nguoi_a",
            "age": "5 giờ",
            "text": "Một bài viết thử nghiệm khá dài.",
            "likes": 1200,
            "replies": 34,
            "shares": 56,
        },  # fmt: skip
        "comments": [{"id": "c1", "handle": "nguoi_b", "text": "Bình luận thử", "likes": 90}],
        "segments": [
            {"role": r, "voice": t, "ref": "c1" if r == "comment" else None}
            for r, t in zip(roles, texts, strict=True)
        ],
        "voice": {"engine": "file", "file": "voice.wav"},
        "settings": {"aligner": "silence", "outro": False, **settings},
        "publish": {"hook": "Xin chào", "hashtags": ["demo"]},
    }
    if thumbnail:
        project["thumbnail"] = {"lines": ["TIÊU ĐỀ", "THỬ"]}
    (pdir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    brand, library = tmp_path / "brand", tmp_path / "library"
    (brand / "outro").mkdir(parents=True)
    (library / "outro").mkdir(parents=True)
    for name, fps in ((hbt_render.OUTRO_FILE, 50), (hbt_render.OUTRO_FILE_60, 60)):
        run_ffmpeg([
            "-f", "lavfi", "-i", f"color=c=red:s=270x480:r={fps}:d=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", brand / "outro" / name,
        ])  # fmt: skip
    Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(brand / "hbt-logo-mark.png")
    write_wav(library / "outro" / "voice.wav", [("tone", 2.65, 0.5)], freq=300)
    lib = BackgroundLibrary(library)
    lib.add(make_clip(tmp_path / "bg1.mp4", seconds=6, fps=30), "bg1.mp4", META)
    opts = RenderOptions(preview=True, library_dir=library, brand_dir=brand)
    return pdir, opts


def edit(pdir, fn):
    path = pdir / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- không cần ffmpeg
def test_outro_clip_per_fps(tmp_path):
    brand = tmp_path
    (brand / "outro").mkdir()
    for name in (hbt_render.OUTRO_FILE, hbt_render.OUTRO_FILE_60):
        (brand / "outro" / name).write_bytes(b"x")
    assert postv_outro_clip(50, brand).name == "outro_4s_50fps.mp4"
    assert postv_outro_clip(60, brand).name == "outro_4s_60fps.mp4"
    assert postv_outro_clip(30, brand).name == "outro_4s_60fps.mp4"  # khác outro_clip_for
    assert hbt_render.outro_clip_for(30, brand).name == "outro_4s_50fps.mp4"


def test_postv_version_is_a_hash_that_follows_the_postv_code():
    assert len(R.POSTV_VERSION) == 12 and R.POSTV_VERSION != hbt_render.PIPELINE_VERSION


def test_bg_key_ignores_postv_version(tmp_path, monkeypatch):
    from hbt.postv import bgbuild

    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    piece = bgbuild.Piece("a", f, 1.0, 7.5)
    base = bgbuild.bg_key([piece], 1080, 1920, 60, "veryfast", 12)
    monkeypatch.setattr(R, "POSTV_VERSION", "doi-ma-the-hoac-phu-de")
    assert bgbuild.bg_key([piece], 1080, 1920, 60, "veryfast", 12) == base


def test_voiced_tokens_skip_empty_segments():
    from hbt.postv.models import PostvProject

    p = PostvProject.model_validate(
        {
            "slug": "x", "title": "x",
            "segments": [
                {"role": "hook", "voice": "Một hai"},
                {"role": "post", "voice": "  "},
                {"role": "commentary", "voice": "Ba bốn năm"},
            ],
        }
    )  # fmt: skip
    tokens, scene_of, n = R.voiced_tokens(p)
    assert (len(tokens), scene_of, n) == (5, [0, 0, 1, 1, 1], 2)


@needs_ffmpeg
def test_missing_pieces_are_reported_before_any_work(tmp_path):
    pdir, opts = make_postv(tmp_path)
    edit(pdir, lambda d: d["voice"].update(file=None))
    with pytest.raises(RenderError, match="Chưa có file giọng"):
        render_postv(pdir, opts)
    edit(pdir, lambda d: d["voice"].update(file="voice.wav"))
    edit(pdir, lambda d: d.update(background={"clip_ids": ["khong-co"]}))
    with pytest.raises(RenderError, match="khong-co"):
        render_postv(pdir, opts)


@needs_ffmpeg
def test_empty_background_library_is_an_error(tmp_path):
    pdir, opts = make_postv(tmp_path)
    (opts.library_dir / "backgrounds" / "index.json").write_text("[]", encoding="utf-8")
    with pytest.raises(RenderError, match="Chưa có clip nền"):
        render_postv(pdir, opts)


@needs_ffmpeg
def test_invalid_options_are_rejected(tmp_path):
    pdir, opts = make_postv(tmp_path)
    opts.preview_seconds = 5
    opts.preview = False
    with pytest.raises(RenderError, match="preview_seconds"):
        render_postv(pdir, opts)
    opts.preview, opts.fps = False, 45
    with pytest.raises(RenderError, match="fps"):
        render_postv(pdir, opts)


# ---------------------------------------------------------------- dựng thật (ngắn)
def frames_of(video, w, h):
    import subprocess

    from hbt.pipeline.ffutil import ffmpeg_exe

    raw = subprocess.run(
        [ffmpeg_exe(), "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


@needs_ffmpeg
@pytest.mark.slow
def test_preview_render_end_to_end(tmp_path):
    pdir, opts = make_postv(tmp_path)
    steps = []
    res = render_postv(pdir, opts, progress=lambda p, s, m: steps.append((p, s)))
    info = probe(res.video)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (vs["width"], vs["height"], vs["r_frame_rate"]) == (540, 960, "30/1")
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert res.duration == pytest.approx(body_len(4), abs=0.1)
    assert res.aligner == "silence" and (res.width, res.height, res.fps) == (540, 960, 30)
    assert res.srt.read_text(encoding="utf-8").count(" --> ") >= 4
    publish = res.publish.read_text(encoding="utf-8")
    assert "Nguồn: https://example.test/bai" in publish and "[Ghi công]" in publish
    assert "Nền: Parkour 01" in publish
    meta = json.loads((res.job_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "postv" and meta["background_ids"] == ["parkour-01"]
    percents = [p for p, _ in steps]
    assert percents == sorted(percents) and percents[0] == 0 and percents[-1] == 100
    assert {s for _, s in steps} >= {"Kiểm tra", "Căn chữ", "Nền", "Thẻ", "Ghép cuối", "Xong"}
    frames = frames_of(res.video, 540, 960)
    first_card = frames[int(1.0 * 30)]  # thẻ tiêu đề đã hiện: có điểm ảnh gần trắng
    assert (first_card > 240).all(axis=2).sum() > 3000


@needs_ffmpeg
@pytest.mark.slow
def test_full_render_with_outro_cover_and_cache(tmp_path):
    pdir, opts = make_postv(tmp_path, thumbnail=True, outro=True)
    opts.preview, opts.fps = False, 30
    res = render_postv(pdir, opts)
    assert (res.width, res.height, res.fps) == (1080, 1920, 30)
    assert res.duration == pytest.approx(body_len(4) + 4.0 - 0.5, abs=0.1)
    assert res.cover is not None and res.cover.is_file() and res.youtube_cover.is_file()
    assert res.lufs is not None
    # dựng lại: nền và mốc chữ dùng bản đã có
    again = render_postv(pdir, opts)
    log = again.log.read_text(encoding="utf-8")
    assert "Nền: dùng bản đã có" in log and "Mốc thời gian chữ: dùng bản đã có" in log
    assert media_duration(again.video) == pytest.approx(res.duration, abs=0.05)


@needs_ffmpeg
@pytest.mark.slow
def test_censor_mutes_voice_and_blurs_caption(tmp_path):
    lines = [*LINES[:3], "Thằng đó đéo biết gì cả."]
    pdir, opts = make_postv(tmp_path, lines=lines)
    words = SensitiveWords.model_validate(
        {"categories": [{"id": "tuc", "label": "Tục", "level": "block", "words": ["đéo"]}]}
    )
    res = render_postv(pdir, opts, censor_words=words)
    assert "đéo" not in res.srt.read_text(encoding="utf-8")
    assert "***" in res.srt.read_text(encoding="utf-8")
    assert "Che 1 khoảng" in res.log.read_text(encoding="utf-8")
    assert (pdir / "build" / "voice_censored.wav").is_file()
    edit(pdir, lambda d: d["settings"].update(censor={"enabled": False}))
    res2 = render_postv(pdir, opts, censor_words=words)
    assert "đéo" in res2.srt.read_text(encoding="utf-8")
    assert "Che 1 khoảng" not in res2.log.read_text(encoding="utf-8")


@needs_ffmpeg
@pytest.mark.slow
def test_cancel_leaves_no_video(tmp_path):
    pdir, opts = make_postv(tmp_path)
    token = CancelToken()

    def progress(pct, step, msg):
        if step == "Ghép cuối":
            token.cancel()

    with pytest.raises(RenderCancelled):
        render_postv(pdir, opts, progress=progress, cancel_token=token)
    renders = list((pdir / "renders").glob("*"))
    assert not any((d / "video.mp4").exists() or (d / "video.part.mp4").exists() for d in renders)
