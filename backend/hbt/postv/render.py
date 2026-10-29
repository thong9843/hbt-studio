"""Bộ dựng video PostV (IMPLEMENT-POSTV.md mục 6).

Nền gameplay chạy liền, thẻ và phụ đề phủ lên bằng **một** lệnh ffmpeg (không trượt cả khung qua
Python như HBT). Dùng lại từ `pipeline/`: chuẩn hoá giọng, căn chữ, trộn nhạc, outro, bìa, đo độ
lớn; chép phần điều phối (D15). `pipeline/` không bị sửa (N1); khoá cache có `PIPELINE_VERSION` và
`POSTV_VERSION` (băm mã `postv/`), riêng nền chỉ có `BG_VERSION` nên đổi thẻ không dựng lại nền.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hbt.config import ALLOWED_FPS, BRAND_DIR, load_settings
from hbt.pipeline import audio, cache, cancel
from hbt.pipeline import whisper as _whisper
from hbt.pipeline.cancel import CancelToken, RenderCancelled
from hbt.pipeline.captions import write_ffconcat
from hbt.pipeline.ffutil import (
    FFmpegError,
    ffmpeg_exe,
    measure_lufs,
    media_duration,
    probe,
    run_ffmpeg,
)
from hbt.pipeline.render import (
    OUTRO_FILE,
    OUTRO_FILE_60,
    PIPELINE_VERSION,
    Alignment,
    ProgressFn,
    RenderError,
    RenderOptions,
    RenderResult,
    X,
    _Reporter,
    offsets_valid,
    quality_for,
    run_alignment,
    scene_offsets,
)
from hbt.pipeline.text import parse_voice
from hbt.pipeline.thumbnail import LOGO_FILE, render_cover, save_covers
from hbt.pipeline.whisper import WhisperConfig
from hbt.postv import bgbuild, captions, cardfx, censorfx, publish
from hbt.postv import card as _card
from hbt.postv import censor as _censor
from hbt.postv.backgrounds import BackgroundLibrary, background_problems
from hbt.postv.card import load_template
from hbt.postv.censor import CensorMatcher, compile_censor
from hbt.postv.models import PostvProject
from hbt.sensitive import SensitiveWords

POSTV_VERSION = hashlib.sha1(
    (
        cache.code_digest(sys.modules[__name__], bgbuild, cardfx, captions, censorfx, publish)
        + cache.code_digest(_card, _censor)
        + cache.file_digest(_card.TEMPLATE_DIR / "story_cards.json")
    ).encode()
).hexdigest()[:12]
ALIGN_START, ALIGN_END = 10.0, 25.0  # khung tiến độ của bước 3 (Căn chữ)
LONG_SECONDS = 120.0
MAX_PREVIEW_SECONDS = 60
CROSSFADE = audio.OUTRO_CROSSFADE


def postv_outro_clip(fps: int, brand_dir: Path) -> Path:
    """Clip outro theo fps: 50 → clip 50; 60 → clip 60; 30 → clip 60 (`fps=30` bỏ khung chẵn/lẻ
    đúng tỉ lệ 2:1, R6). Khác `outro_clip_for` của HBT vốn đưa 30 fps về clip 50."""
    folder = brand_dir / "outro"
    if fps == 50:
        return folder / OUTRO_FILE
    clip = folder / OUTRO_FILE_60
    return clip if clip.is_file() else folder / OUTRO_FILE


def load_postv(project_dir: Path) -> PostvProject:
    path = project_dir / "project.json"
    try:
        return PostvProject.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        raise RenderError(f"Không đọc được project PostV: {e}") from e


def voiced_tokens(project: PostvProject) -> tuple[list[dict], list[int], int]:
    """Token lời đọc của các đoạn có lời; mỗi đoạn là một "cảnh". Trả (tokens, scene_of, n)."""
    tokens: list[dict] = []
    scene_of: list[int] = []
    n = 0
    for seg in project.segments:
        if not seg.voice.strip():
            continue
        parsed = parse_voice(seg.voice)
        if not parsed:
            continue
        tokens += parsed
        scene_of += [n] * len(parsed)
        n += 1
    return tokens, scene_of, n


def voiced_segments(project: PostvProject):
    return [s for s in project.segments if s.voice.strip() and parse_voice(s.voice)]


def _run_with_progress(cmd: list[str], total: float, on_frac, partial: Path) -> None:
    """Chạy ffmpeg, đọc `-progress` để báo tiến độ; huỷ thì kill và xoá file dở."""
    err = tempfile.TemporaryFile()
    proc = subprocess.Popen(
        [*cmd, "-progress", "pipe:1", "-nostats"],
        stdout=subprocess.PIPE,
        stderr=err,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    token = cancel.current()
    if token is not None:
        token.track(proc)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    done = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                on_frac(min(max(done / max(total, 1e-3), 0.0), 1.0))
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if token is not None:
            token.untrack(proc)
    try:
        cancel.check_current()  # bộ mã hoá chết vì bị huỷ thì không phải lỗi mã hoá
        if proc.returncode != 0:
            err.seek(0)
            detail = err.read().decode("utf-8", errors="replace").strip()[-800:]
            raise RenderError(f"Bộ mã hoá lỗi (mã {proc.returncode}):\n{detail}")
    except BaseException:
        partial.unlink(missing_ok=True)  # không để lại video dang dở
        raise


def compose_postv(
    *,
    bg: Path,
    caption_concat: Path,
    caption_y: int,
    cards: list,
    tpl: dict,
    fps: int,
    width: int,
    height: int,
    frames: int,
    outro_clip: Path | None,
    audio_wav: Path,
    out_seconds: float,
    preset: str,
    crf: int,
    audio_bitrate: str,
    out: Path,
    on_frac,
) -> None:
    """Một lệnh ffmpeg: nền + thẻ (hiện dần/trượt/nảy) + phụ đề → thân; xfade 0,5 s với outro."""
    scale = width / 1080
    inputs: list[str | Path] = ["-i", bg, "-f", "concat", "-safe", "0", "-i", caption_concat]
    graph = ["[0:v]null[b0]"]
    prev, index = "b0", 2
    for k, (concat, asset, span, timing) in enumerate(cards):
        inputs += ["-f", "concat", "-safe", "0", "-i", concat]
        graph += cardfx.card_chain(
            index, f"c{k}", asset, span, timing, tpl, fps, scale, prev, f"b{k + 1}"
        )
        prev, index = f"b{k + 1}", index + 1
    cap = f"[1:v]fps={fps},format=rgba"
    if scale != 1.0:
        cap += f",scale=w='round(iw*{scale})':h='round(ih*{scale})':flags=lanczos"
    graph.append(cap + "[cap]")
    graph.append(
        f"[{prev}][cap]overlay=x=0:y={round(caption_y * scale)}:eof_action=pass:format=auto[ov]"
    )
    graph.append(f"[ov]fps={fps},trim=end_frame={frames},setpts=PTS-STARTPTS,format=yuv420p[body]")
    if outro_clip is not None:
        inputs += ["-i", outro_clip]
        graph.append(
            f"[{index}:v]fps={fps},scale={width}:{height}:flags=lanczos,setsar=1,"
            "format=yuv420p,setpts=PTS-STARTPTS[o]"
        )
        offset = (frames - fps * CROSSFADE) / fps
        graph.append(
            f"[body][o]xfade=transition=fade:duration={CROSSFADE}:offset={offset:.4f},"
            "format=yuv420p[v]"  # xfade có thể ra 4:4:4; profile high chỉ nhận 4:2:0
        )
        index += 1
    else:
        graph.append("[body]null[v]")
    inputs += ["-i", audio_wav]
    partial = out.with_name(out.stem + ".part.mp4")
    cmd = [
        ffmpeg_exe(), "-hide_banner", "-v", "error", "-y", *map(str, inputs),
        "-filter_complex", ";".join(graph), "-map", "[v]", "-map", f"{index}:a", "-r", str(fps),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-profile:v", "high",
        "-g", str(2 * fps), "-c:a", "aac", "-b:a", audio_bitrate,
        "-shortest", "-movflags", "+faststart", str(partial),
    ]  # fmt: skip
    out.with_name("compose.txt").write_text(  # để xem lại khi lỗi (không phải kết quả dựng)
        "\n".join(str(a) for a in cmd), encoding="utf-8"
    )
    token = cancel.current()
    if token is not None:
        token.check()
    _run_with_progress(cmd, out_seconds, on_frac, partial)
    cache.publish_atomic(partial, out)


def render_postv(
    project_dir: str | Path,
    options: RenderOptions | None = None,
    progress: ProgressFn | None = None,
    cancel_token: CancelToken | None = None,
    *,
    censor_words: SensitiveWords | None = None,
) -> RenderResult:
    """Dựng video PostV. `cancel_token.cancel()` (từ luồng khác) kill ffmpeg, ném RenderCancelled.

    `options.sensitive_words`: danh sách nhạy cảm HBT (chỉ lấy mức chặn); `censor_words`: danh sách
    từ che riêng của PostV. Cả hai thiếu thì không che."""
    with cancel.use_token(cancel_token):
        return _render_postv(project_dir, options, progress, censor_words)


def _render_postv(
    project_dir: str | Path,
    options: RenderOptions | None,
    progress: ProgressFn | None,
    censor_words: SensitiveWords | None,
) -> RenderResult:
    opts = options or RenderOptions()
    t_start = time.time()
    project_dir = Path(project_dir).resolve()
    settings = load_settings()
    library_dir = opts.library_dir or settings.library_dir
    brand_dir = opts.brand_dir or BRAND_DIR
    whisper_cfg = WhisperConfig(
        model=_whisper.effective_model(opts.whisper_model or "auto", settings.whisper_model),
        device=settings.whisper_device,
        timeout=opts.whisper_timeout or _whisper.DEFAULT_TIMEOUT,
        models_dir=settings.models_dir,
    )
    project = load_postv(project_dir)
    job_id = opts.job_id or time.strftime("%Y%m%d-%H%M%S") + ("-preview" if opts.preview else "")
    job_dir = project_dir / "renders" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    rep = _Reporter(job_dir / "log.txt", progress)
    warnings: list[str] = []

    def warn(msg: str) -> None:
        warnings.append(msg)
        rep.say("CẢNH BÁO: " + msg)

    # ---- 1. Kiểm tra (0–3)
    rep.at(0, "Kiểm tra")
    fps = opts.fps or project.settings.fps
    if fps not in ALLOWED_FPS:
        raise RenderError(f"fps phải là một trong {ALLOWED_FPS}, nhận {fps}")
    q = quality_for(opts.preview, fps)
    use_outro = project.settings.outro if opts.outro is None else opts.outro
    if opts.preview and opts.fps:
        rep.say("Chế độ Xem nhanh luôn dùng 30 fps, bỏ qua --fps")
    if opts.preview_seconds is not None:
        if not opts.preview:
            raise RenderError("preview_seconds chỉ dùng với chế độ Xem nhanh")
        if not 0 < opts.preview_seconds <= MAX_PREVIEW_SECONDS:
            raise RenderError(f"preview_seconds phải trong (0, {MAX_PREVIEW_SECONDS}] giây")
    problems = project.render_problems()
    library = BackgroundLibrary(library_dir)
    problems += background_problems(project.background.clip_ids, library)
    if problems:
        raise RenderError("Project chưa đủ để dựng:\n  - " + "\n  - ".join(problems))
    entries = library.list()
    chosen = [e for e in entries if e.id in project.background.clip_ids] or entries
    voice_src = project_dir / (project.voice.file or "")
    music_src = project_dir / project.music.file if project.music and project.music.file else None
    missing = [str(p) for p in (voice_src, music_src) if p is not None and not p.is_file()]
    if missing:
        raise RenderError("Thiếu file:\n  " + "\n  ".join(missing))
    tokens, scene_of, n_scenes = voiced_tokens(project)
    if not tokens:
        raise RenderError("Chưa có đoạn nào có lời đọc")
    segs = voiced_segments(project)
    censor_cfg = project.settings.censor
    matchers: list[CensorMatcher] = []
    if censor_cfg.enabled:
        matchers = compile_censor(
            *(w for w in (opts.sensitive_words, censor_words) if w is not None)
        )
    build = project_dir / "build"
    for sub in ("cards", "captions"):
        (build / sub).mkdir(parents=True, exist_ok=True)
    rep.say(
        f"Dựng {'Xem nhanh' if opts.preview else 'bản đẹp'} PostV: {q.width}x{q.height} @ "
        f"{q.fps} fps, {n_scenes} đoạn, outro {'có' if use_outro else 'không'}"
    )

    # ---- 2. Giọng (3–10)
    rep.at(3, "Chuẩn hoá giọng")
    voice_wav = build / "voice.wav"
    key = cache.digest("prep", voice_src, PIPELINE_VERSION)
    if cache.is_fresh(voice_wav, key):
        rep.say("voice.wav: dùng bản đã có")
    else:
        audio.prep_voice(voice_src, voice_wav)
        cache.mark(voice_wav, key)
    prepped_total = media_duration(voice_wav)
    voice_align = voice_wav
    if project.voice.trim_end is not None:  # cắt tay trước khi căn chữ; VieNeu không có đuôi thừa
        voice_end = project.voice.trim_end + audio.VOICE_DELAY
        content_end = prepped_total - audio.TAIL
        if voice_end >= content_end:
            raise RenderError(
                f"voice.trim_end = {project.voice.trim_end:g} giây nằm sau hết file giọng"
            )
        voice_align = build / "voice_cut.wav"
        key = cache.digest("cut", voice_wav, round(voice_end, 3), PIPELINE_VERSION)
        if not cache.is_fresh(voice_align, key):
            audio.trim_voice_tail(voice_wav, voice_align, voice_end)
            cache.mark(voice_align, key)
        prepped_total = media_duration(voice_align)

    # ---- 3. Căn chữ (10–25)
    rep.at(10, "Căn chữ")
    timing_path = build / "timing.json"
    key = cache.digest(
        "timing", voice_align, [t["disp"] for t in tokens], scene_of, project.settings.aligner,
        whisper_cfg.key_parts(), PIPELINE_VERSION,
    )  # fmt: skip
    if cache.is_fresh(timing_path, key):
        data = json.loads(timing_path.read_text(encoding="utf-8"))
        alignment = Alignment(
            [tuple(x) for x in data["times"]],
            data["aligner"], data["dropped"], data["warning"], data["info"],
        )  # fmt: skip
        rep.say(f"Mốc thời gian chữ: dùng bản đã có (aligner: {alignment.aligner})")
    else:
        alignment = run_alignment(
            tokens, scene_of, str(voice_align), prepped_total, project.settings.aligner,
            whisper_cfg, rep.say, lambda f: rep.tick(ALIGN_START + (ALIGN_END - ALIGN_START) * f),
        )  # fmt: skip
        timing_path.write_text(
            json.dumps(
                {
                    "aligner": alignment.aligner,
                    "dropped": alignment.dropped,
                    "warning": alignment.warning,
                    "info": alignment.info,
                    "times": alignment.times,
                }
            ),
            encoding="utf-8",
        )
        cache.mark(timing_path, key)
    times, aligner = alignment.times, alignment.aligner
    if alignment.warning:
        warn(alignment.warning)
    if aligner == "silence" and project.settings.aligner == "auto":
        reason = alignment.info.get("whisper_error", "Whisper không dùng được")
        warn(f"Whisper rơi về căn theo khoảng lặng ({reason}); phụ đề có thể kém chính xác")
    rep.say(f"Aligner đã dùng: {aligner}")
    total = media_duration(voice_align)
    rep.say(f"Phần có lời dài {total:.2f} giây")
    if total >= LONG_SECONDS:
        warn(f"Video dài {total:.0f} s, nên dưới {LONG_SECONDS:.0f} s (2 phút)")

    # ---- 3b. Che từ nhạy cảm (25)
    rep.at(25, "Che từ nhạy cảm")
    windows = censorfx.censor_windows(tokens, scene_of, times, matchers, total) if matchers else []
    masked = censorfx.masked_tokens(windows)
    voice_mix = voice_align
    sfx: list[tuple[Path, float, float]] = []
    if windows:
        voice_mix = build / "voice_censored.wav"
        key = cache.digest(
            "pv-mute", voice_align, [(round(w.start, 3), round(w.end, 3)) for w in windows],
            PIPELINE_VERSION, POSTV_VERSION,
        )  # fmt: skip
        if not cache.is_fresh(voice_mix, key):
            censorfx.mute_voice(voice_align, voice_mix, windows)
            cache.mark(voice_mix, key)
        sfx = censorfx.bleep_sfx(windows, build)
        rep.say(f"Che {len(windows)} khoảng: " + ", ".join(sorted({w.word for w in windows})))

    # ---- 4. Mốc đổi thẻ (25)
    rep.at(25, "Mốc đổi thẻ")
    offsets = scene_offsets(times, scene_of, n_scenes)
    if n_scenes > 1 and not offsets_valid(offsets):
        raise RenderError("Mốc chuyển đoạn không hợp lệ: có đoạn quá ngắn so với lời đọc")
    starts = cardfx.segment_starts(offsets, n_scenes, X)
    partial = (
        opts.preview_seconds if opts.preview_seconds and opts.preview_seconds < total else None
    )
    if partial:
        use_outro = False
        rep.say(f"Xem nhanh {partial:g} s đầu, không outro")
    spans = cardfx.plan_cards([cardfx.card_of(s) for s in segs], starts, total)
    if partial:
        spans = [s for s in spans if s.start < partial]

    # ---- 5. Nền (25–45)
    rep.at(25, "Nền")
    body_seconds = partial or total
    pieces = bgbuild.pick_pieces(
        chosen, library.root, body_seconds, project.background.seed, project.background.start_offset
    )
    if sum(e.duration for e in chosen) < body_seconds:
        warn("Nền ngắn hơn video nên phải nối lặp clip")
    bg = build / f"bg_{q.width}_{q.fps}.mp4"
    key = bgbuild.bg_key(pieces, q.width, q.height, q.fps, q.clip_preset, q.clip_crf)
    if cache.is_fresh(bg, key):
        rep.say("Nền: dùng bản đã có")
    else:
        bgbuild.build_background(pieces, q.width, q.height, q.fps, q.clip_preset, q.clip_crf, bg)
        cache.mark(bg, key)
    rep.tick(45)

    # ---- 6. Thẻ (45–50)
    rep.at(45, "Thẻ")
    tpl = load_template(project.template if project.template == "story_cards" else "story_cards")
    card_censor = matchers if censor_cfg.blur_card and matchers else None
    cards = []
    for k, span in enumerate(spans):
        timing = cardfx.card_timing(span, tpl, project.settings.card_animation, total)
        asset = cardfx.build_asset(
            project, span, tpl, card_censor, censor_cfg.text, project.settings.count_up,
            build / "cards", timing["bounce"],
        )  # fmt: skip
        concat = build / "cards" / f"c{k}.ffconcat"
        cardfx.write_card_concat(asset, timing["seconds"], concat)
        cards.append((concat, asset, span, timing))
        rep.tick(45 + 5 * (k + 1) / len(spans))
    rep.say(f"{len(cards)} thẻ")

    # ---- 7. Âm thanh (50–55)
    rep.at(50, "Âm thanh")
    music_start = 0.0
    music_start_source = None
    if music_src is not None:
        if project.music.start is not None:
            music_start, music_start_source = project.music.start, "manual"
        else:
            music_start = audio.pick_music_start(music_src, total)
            music_start_source = "auto"
        rep.say(f"Nhạc bắt đầu từ {music_start:.1f} s ({music_start_source})")
        if music_start + total > media_duration(music_src):
            warn("Nhạc ngắn hơn video")
    mix = build / "mix.wav"
    key = cache.digest(
        "mix", voice_mix, music_src, music_start, round(total, 3),
        [(round(at, 3), vol) for _, at, vol in sfx], PIPELINE_VERSION,
    )  # fmt: skip
    if not cache.is_fresh(mix, key):
        audio.mix_audio(voice_mix, music_src, music_start, total, mix, build, sfx)
        cache.mark(mix, key)
    final_audio, out_total, outro_clip = mix, total, None
    if partial:
        out_total = partial
        final_audio = build / "preview_audio.wav"
        audio.trim_with_fade(mix, partial, final_audio)
    elif use_outro:
        outro_clip = postv_outro_clip(fps, brand_dir)
        if not outro_clip.is_file():
            raise RenderError(f"Thiếu clip outro: {outro_clip}")
        outro_voice = library_dir / "outro" / "voice.wav"
        if not outro_voice.is_file():
            warn(f"Không có {outro_voice}; outro chỉ có tiếng ting")
            outro_voice = None
        outro_audio = build / "outro_audio.wav"
        key = cache.digest("outro", outro_voice, PIPELINE_VERSION)
        if not cache.is_fresh(outro_audio, key):
            audio.build_outro_audio(outro_voice, outro_audio, build)
            cache.mark(outro_audio, key)
        final_audio = build / "final_audio.wav"
        out_total = audio.join_audio(mix, outro_audio, final_audio)

    # ---- 8. Phụ đề (55–60)
    rep.at(55, "Phụ đề")
    cap_style = captions.style_for(
        project.style.caption.preset, project.style.caption.highlight_color
    )
    phrases = (
        captions.build_phrases(tokens, times, scene_of, masked) if project.settings.captions else []
    )
    timeline = captions.render_states(
        phrases, cap_style, censor_cfg.text, build / "captions", out_total + 1.0
    )
    concat = build / "captions.ffconcat"
    write_ffconcat(timeline, concat)
    srt = None
    if phrases and not partial:
        srt = job_dir / "captions.srt"
        captions.write_srt(phrases, srt)
    rep.say(f"{len(phrases)} cụm phụ đề, {len(timeline)} trạng thái")

    # ---- 9. Ghép cuối (60–98)
    rep.at(60, "Ghép cuối")
    video = job_dir / "video.mp4"
    compose_postv(
        bg=bg, caption_concat=concat, caption_y=captions.band_y(cap_style), cards=cards, tpl=tpl,
        fps=q.fps, width=q.width, height=q.height, frames=int(round(body_seconds * q.fps)),
        outro_clip=outro_clip, audio_wav=final_audio, out_seconds=out_total,
        preset=q.final_preset, crf=q.final_crf, audio_bitrate=q.audio_bitrate, out=video,
        on_frac=lambda f: rep.tick(60 + 38 * f),
    )  # fmt: skip

    # ---- 10. Kiểm tra đầu ra (98–100)
    rep.at(98, "Kiểm tra đầu ra")
    info = probe(video)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    duration = float(info["format"]["duration"])
    if (int(vs["width"]), int(vs["height"])) != (q.width, q.height):
        raise RenderError(f"Kích thước đầu ra sai: {vs['width']}x{vs['height']}")
    if vs["r_frame_rate"] != f"{q.fps}/1":
        raise RenderError(f"fps đầu ra sai: {vs['r_frame_rate']} (cần {q.fps})")
    if not has_audio:
        raise RenderError("Video đầu ra không có tiếng")
    if abs(duration - out_total) > 0.25:
        raise RenderError(f"Độ dài đầu ra {duration:.2f} s lệch dự kiến {out_total:.2f} s")
    lufs = None
    if not partial:
        lufs = measure_lufs(video)
        if not -15.0 <= lufs <= -13.0:
            warn(f"Độ lớn tổng {lufs:.1f} LUFS nằm ngoài khoảng −15…−13")
    cover = youtube_cover = None
    if project.thumbnail and not partial:
        try:
            cover, youtube_cover = _make_covers(
                project, project_dir, build, bg, total, brand_dir, job_dir
            )
            rep.say(f"Ảnh bìa: {cover.name}, {youtube_cover.name}")
        except RenderCancelled:
            raise
        except Exception as e:  # noqa: BLE001 — lỗi vẽ bìa không làm hỏng video
            warn(f"Không vẽ được ảnh bìa: {e}")
    publish_path = job_dir / "publish.txt"
    publish_path.write_text(publish.build_publish_text(project, chosen), encoding="utf-8")
    meta = {
        "kind": "postv",
        "job_id": job_id,
        "preview": q.preview,
        "fps": q.fps,
        "width": q.width,
        "height": q.height,
        "duration": round(duration, 3),
        "lufs": round(lufs, 2) if lufs is not None else None,
        "aligner": aligner,
        "aligner_info": alignment.info,
        "trimmed_tail": None,
        "trimmed_tail_seconds": None,
        "music_start": round(music_start, 3) if music_src is not None else None,
        "music_start_source": music_start_source,
        "preview_seconds": partial,
        "cover_9x16": cover.name if cover else None,
        "youtube_3x2": youtube_cover.name if youtube_cover else None,
        "music_sha256": cache.sha256_file(music_src) if music_src is not None else None,
        "background_ids": sorted({p.clip_id for p in pieces}),
        "censored_words": len(windows),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    rep.at(100, "Xong")
    rep.say(
        f"Xong: {video} — {duration:.2f} s, {q.fps} fps, "
        f"{f'{lufs:.1f} LUFS, ' if lufs is not None else ''}"
        f"{video.stat().st_size / 1e6:.1f} MB, aligner {aligner}"
    )
    return RenderResult(
        job_dir=job_dir, video=video, srt=srt, publish=publish_path, log=job_dir / "log.txt",
        fps=q.fps, width=q.width, height=q.height, duration=duration, lufs=lufs,
        aligner=aligner, aligner_info=alignment.info, seconds=time.time() - t_start,
        warnings=warnings, preview_seconds=partial, cover=cover, youtube_cover=youtube_cover,
    )  # fmt: skip


def _make_covers(
    project: PostvProject,
    project_dir: Path,
    build: Path,
    bg: Path,
    total: float,
    brand_dir: Path,
    out_dir: Path,
) -> tuple[Path, Path]:
    """Bìa: ảnh tải lên (cắt giữa) nếu có; không thì một khung nền lúc `min(3 s, total/2)`."""
    thumb = project.thumbnail
    if thumb.image:
        source = project_dir / thumb.image
        if not source.is_file():
            raise FileNotFoundError(f"Thiếu ảnh bìa {thumb.image}")
    else:
        source = build / "cover_frame.png"
        try:
            run_ffmpeg([
                "-ss", f"{min(3.0, total / 2):.2f}", "-i", bg, "-frames:v", "1", source,
            ])  # fmt: skip
        except FFmpegError as e:
            raise FileNotFoundError(f"Không trích được khung nền: {e}") from e
    image = render_cover(
        source, thumb.lines, thumb.series or project.series, thumb.accent, brand_dir / LOGO_FILE,
        fit_background=True,
    )  # fmt: skip
    return save_covers(image, out_dir)


__all__ = [
    "POSTV_VERSION",
    "compose_postv",
    "load_postv",
    "postv_outro_clip",
    "render_postv",
    "voiced_tokens",
]
