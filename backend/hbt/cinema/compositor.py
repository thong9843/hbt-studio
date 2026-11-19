"""Bộ dựng khung hình Dirty-Rect + Pipe thẳng FFmpeg (CPU kẹp tài nguyên / GPU NVENC)."""

from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from hbt.cinema.cache import BeatCache, build_normalized_beat_flags
from hbt.cinema.hardware import HardwareProfile, detect_hardware
from hbt.cinema.layer_cache import FontCache, LayerCache
from hbt.cinema.motion import ease_out_back, ease_out_cubic
from hbt.cinema.preflight import PreflightQualityGate
from hbt.cinema.schema import BeatSpec, TimelineSpec
from hbt.cinema.shots import FONT_EXTRABOLD, ShotLayout, bake_static_shot_layer, compute_shot_layout
from hbt.cinema.transitions import apply_transition
from hbt.pipeline.cancel import CancelToken
from hbt.pipeline.ffutil import FFmpegError, ffmpeg_exe
from hbt.shared.pipeline.watermark import (
    WatermarkSettings,
    build_watermark_overlay_filter,
    render_watermark_png,
)
from hbt.stickv.audio import align_beat_karaoke, extract_wav_rms_envelope
from hbt.stickv.puppet import PuppetRig, is_puppet_ready


def _draw_procedural_stickman(
    frame_rgba: Image.Image,
    beat: BeatSpec,
    box_tuple: tuple[int, int, int, int],
    *,
    t_sec: float,
    mouth_open: float,
) -> None:
    """Nhân vật Stickman vector Pillow dự phòng sạch 100% khi chạy CI thiếu binary library."""
    x0, y0, x1, y1 = box_tuple
    bw = max(40, x1 - x0)
    bh = max(80, y1 - y0)
    cx = (x0 + x1) // 2
    bob = int(round(abs(math.sin(t_sec * 5.0)) * min(10.0, bh * 0.02)))
    head_r = max(14, int(round(min(bw, bh) * 0.14)))
    head_cy = y0 + int(round(bh * 0.22)) - bob

    ink = (15, 23, 42, 255)
    tie_col = (217, 35, 46, 255)
    lw = max(2, int(round(head_r * 0.16)))
    draw = ImageDraw.Draw(frame_rgba)

    # Bóng đổ dưới chân
    foot_y = y1 - max(6, int(round(bh * 0.05)))
    draw.ellipse(
        (cx - head_r * 2, foot_y - 6, cx + head_r * 2, foot_y + 8),
        fill=(15, 23, 42, 42),
    )

    # Đầu & biểu cảm
    draw.ellipse(
        (cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r),
        fill=(255, 255, 255, 255),
        outline=ink,
        width=lw,
    )
    eye_dx = max(4, int(head_r * 0.35))
    eye_y = head_cy - max(2, int(head_r * 0.12))
    er = max(2, head_r // 7)
    draw.ellipse((cx - eye_dx - er, eye_y - er, cx - eye_dx + er, eye_y + er), fill=ink)
    draw.ellipse((cx + eye_dx - er, eye_y - er, cx + eye_dx + er, eye_y + er), fill=ink)

    m_w = max(4, int(head_r * 0.38))
    m_h = max(2, int(round((0.15 + 0.35 * mouth_open) * head_r)))
    my = head_cy + int(head_r * 0.34)
    draw.rounded_rectangle((cx - m_w, my - m_h // 2, cx + m_w, my + m_h), radius=2, fill=ink)

    # Thân + cà vạt đỏ HBT
    neck_y = head_cy + head_r
    hip_y = y0 + int(round(bh * 0.68)) - bob // 2
    draw.line([(cx, neck_y), (cx, hip_y)], fill=ink, width=lw + 1)
    draw.polygon(
        [(cx, neck_y + 4), (cx - lw * 2, hip_y - 10), (cx, hip_y - 2), (cx + lw * 2, hip_y - 10)],
        fill=tie_col,
    )

    # Tay động nhẹ theo dáng pose
    sh_y = neck_y + max(6, int((hip_y - neck_y) * 0.16))
    arm_span = int(bw * 0.28)
    raise_r = int(round((1.0 if "point" in beat.puppet.pose else 0.2) * head_r * 1.4))
    draw.line([(cx, sh_y), (cx - arm_span, sh_y + head_r)], fill=ink, width=lw)
    draw.line([(cx, sh_y), (cx + arm_span, sh_y + head_r - raise_r)], fill=ink, width=lw)

    # Chân
    leg_dx = max(10, int(bw * 0.16))
    draw.line([(cx, hip_y), (cx - leg_dx, foot_y)], fill=ink, width=lw)
    draw.line([(cx, hip_y), (cx + leg_dx, foot_y)], fill=ink, width=lw)


class DirtyRectCompositor:
    """Bộ ghép khung hình tốc độ cao: pre-bake lớp tĩnh + cache dải Karaoke theo word chunk."""

    def __init__(
        self,
        *,
        hw: HardwareProfile | None = None,
        layer_cache: LayerCache | None = None,
        font_cache: FontCache | None = None,
    ) -> None:
        self.hw = hw or detect_hardware()
        self.layer_cache = layer_cache or LayerCache(max_mb=self.hw.layer_cache_mb)
        self.font_cache = font_cache or FontCache()

    def _prewarm_fonts(self, width: int, aspect: str) -> None:
        scale = width / (1080.0 if aspect == "9:16" else 1920.0)
        k_size = max(14, int(round((40 if aspect == "9:16" else 36) * scale)))
        self.font_cache.get_font(FONT_EXTRABOLD, k_size)

    def _bake_karaoke_strip(
        self,
        chunk: list[tuple[str, float, float]],
        active_local_idx: int,
        *,
        strip_w: int,
        strip_h: int,
        font_size: int,
    ) -> Image.Image:
        strip = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(strip)
        font = self.font_cache.get_font(FONT_EXTRABOLD, font_size)

        space_w = max(6, int(round(font_size * 0.34)))
        widths: list[int] = []
        for word, _, _ in chunk:
            bb = draw.textbbox((0, 0), word, font=font)
            widths.append(max(4, bb[2] - bb[0]))
        total_w = sum(widths) + space_w * max(0, len(chunk) - 1)

        pad_x = max(12, int(round(font_size * 0.52)))
        bg_w = min(strip_w, total_w + pad_x * 2)
        bx0 = (strip_w - bg_w) // 2
        draw.rounded_rectangle(
            (bx0, 4, bx0 + bg_w, strip_h - 4),
            radius=max(10, strip_h // 4),
            fill=(15, 23, 42, 165),
        )

        cur_x = (strip_w - total_w) // 2
        text_y = max(6, (strip_h - font_size) // 2 - 4)
        for local_i, ((word, _, _), ww) in enumerate(zip(chunk, widths, strict=True)):
            if local_i == active_local_idx:
                draw.rounded_rectangle(
                    (cur_x - 8, text_y - 4, cur_x + ww + 8, text_y + font_size + 6),
                    radius=max(6, font_size // 4),
                    fill=(255, 212, 59, 255),
                )
                draw.text((cur_x, text_y), word, font=font, fill=(15, 23, 42, 255))
            else:
                draw.text(
                    (cur_x, text_y),
                    word,
                    font=font,
                    fill=(248, 250, 252, 255),
                    stroke_width=max(2, font_size // 12),
                    stroke_fill=(15, 23, 42, 255),
                )
            cur_x += ww + space_w
        return strip

    def _get_karaoke_layer(
        self,
        beat: BeatSpec,
        word_timings: list[tuple[str, float, float]],
        t_sec: float,
        layout: ShotLayout,
        *,
        width: int,
    ) -> Image.Image | None:
        if not word_timings:
            return None
        active_idx = 0
        for idx, (_w, st, et) in enumerate(word_timings):
            if st <= t_sec <= et:
                active_idx = idx
                break
            if t_sec > et:
                active_idx = idx

        win_size = 5 if layout.aspect == "9:16" else 7
        chunk_idx = active_idx // win_size
        chunk = word_timings[chunk_idx * win_size : (chunk_idx + 1) * win_size]
        if not chunk:
            return None

        local_idx = active_idx - chunk_idx * win_size
        strip_w = max(120, int(round(layout.karaoke_box.w)))
        strip_h = max(36, int(round(layout.karaoke_box.h * 0.58)))
        scale = width / (1080.0 if layout.aspect == "9:16" else 1920.0)
        font_size = max(14, int(round((40 if layout.aspect == "9:16" else 36) * scale)))

        key = f"kar:{beat.id}:{width}:{strip_w}x{strip_h}:{chunk_idx}:{local_idx}"
        return self.layer_cache.get_or_bake(
            key,
            lambda: self._bake_karaoke_strip(
                chunk,
                local_idx,
                strip_w=strip_w,
                strip_h=strip_h,
                font_size=font_size,
            ),
        )

    def render_frame(
        self,
        beat: BeatSpec,
        *,
        spec: TimelineSpec,
        layout: ShotLayout,
        f_idx: int,
        t_sec: float,
        mouth_open: float,
        word_timings: list[tuple[str, float, float]],
        width: int,
        height: int,
        puppet_rig: PuppetRig | None = None,
    ) -> Image.Image:
        """Tổng hợp 1 frame RGB bằng tái sử dụng lớp pre-baked từ `LayerCache`."""
        b_hash = beat.content_hash(
            aspect=spec.aspect,
            fps=spec.fps,
            theme=spec.theme,
            domain=spec.domain,
        )
        static_key = f"static:{b_hash}:{width}x{height}"
        static_layer = self.layer_cache.get_or_bake(
            static_key,
            lambda: bake_static_shot_layer(
                beat,
                layout,
                domain=spec.domain,
                theme=spec.theme,
                width=width,
                height=height,
                font_cache=self.font_cache,
            ),
        )

        # Pop-in nhẹ khi vào beat bằng easing
        frame = static_layer.copy()
        try:
            if beat.puppet.enabled:
                px0 = int(round(layout.puppet_box.x))
                py0 = int(round(layout.puppet_box.y))
                px1 = int(round(layout.puppet_box.x2))
                py1 = int(round(layout.puppet_box.y2))
                entry_u = ease_out_back(min(1.0, t_sec / 0.28)) if t_sec < 0.28 else 1.0
                dy_entry = int(round((1.0 - entry_u) * max(12, height * 0.03)))

                if puppet_rig is not None:
                    p_img = puppet_rig.render_frame(f_idx, t_sec)
                    try:
                        target_h = max(48, py1 - py0)
                        ratio = target_h / max(1, p_img.height)
                        tw = max(32, int(round(p_img.width * ratio)))
                        scaled = p_img.resize((tw, target_h), Image.Resampling.BILINEAR)
                        try:
                            dx = px0 + max(0, (px1 - px0 - tw) // 2)
                            frame.alpha_composite(scaled, (dx, py0 + dy_entry))
                        finally:
                            scaled.close()
                    finally:
                        p_img.close()
                else:
                    _draw_procedural_stickman(
                        frame,
                        beat,
                        (px0, py0 + dy_entry, px1, py1 + dy_entry),
                        t_sec=t_sec,
                        mouth_open=mouth_open,
                    )

            k_layer = self._get_karaoke_layer(beat, word_timings, t_sec, layout, width=width)
            if k_layer is not None:
                kx = int(round(layout.karaoke_box.x + (layout.karaoke_box.w - k_layer.width) / 2))
                ky = int(round(layout.karaoke_box.y + (layout.karaoke_box.h - k_layer.height) / 2))
                pop = ease_out_cubic(min(1.0, t_sec / 0.18)) if t_sec < 0.18 else 1.0
                if pop > 0.05:
                    frame.alpha_composite(k_layer, (kx, ky))

            return frame.convert("RGB")
        finally:
            frame.close()

    def render_beat_to_mp4(
        self,
        beat: BeatSpec,
        spec: TimelineSpec,
        out_mp4: Path,
        *,
        wav_path: Path | None = None,
        library_dir: Path | None = None,
        assets_dir: Path | None = None,
        width: int | None = None,
        height: int | None = None,
        prev_tail_frame: Image.Image | None = None,
        cancel: CancelToken | None = None,
    ) -> dict[str, Any]:
        """Render 1 beat hoàn chỉnh ra MP4 chuẩn hóa luồng bằng pipe thẳng vào FFmpeg."""
        target_w = int(width or spec.width)
        target_h = int(height or spec.height)
        fps = int(spec.fps)
        dur = max(0.35, float(beat.duration_sec))
        n_frames = max(1, int(round(dur * fps)))

        layout = compute_shot_layout(
            beat.shot_type,
            spec.aspect,
            beat=beat,
            width=target_w,
            height=target_h,
        )
        self._prewarm_fonts(target_w, spec.aspect)

        # Pre-bake lớp tĩnh trước vòng lặp frame để cache hit trên toàn bộ khung hình
        b_hash = beat.content_hash(
            aspect=spec.aspect,
            fps=fps,
            theme=spec.theme,
            domain=spec.domain,
        )
        static_key = f"static:{b_hash}:{target_w}x{target_h}"
        self.layer_cache.get_or_bake(
            static_key,
            lambda: bake_static_shot_layer(
                beat,
                layout,
                domain=spec.domain,
                theme=spec.theme,
                width=target_w,
                height=target_h,
                font_cache=self.font_cache,
            ),
        )

        if wav_path is not None and wav_path.is_file():
            rms_env = extract_wav_rms_envelope(wav_path, fps, dur)
            word_timings = align_beat_karaoke(beat.narration, wav_path, dur)
        else:
            rms_env = [0.25 if (i % 6 < 3) else 0.05 for i in range(n_frames)]
            words = [w for w in (beat.narration or "").split() if w]
            if words:
                step = dur / len(words)
                word_timings = [
                    (w, round(i * step, 4), round((i + 1) * step, 4)) for i, w in enumerate(words)
                ]
            else:
                word_timings = []

        puppet_rig: PuppetRig | None = None
        if (
            beat.puppet.enabled
            and library_dir is not None
            and assets_dir is not None
            and is_puppet_ready(library_dir, assets_dir)
        ):
            puppet_rig = PuppetRig(
                library_dir=library_dir,
                assets_dir=assets_dir,
                target_height=max(120, int(round(layout.puppet_box.h))),
                pose=beat.puppet.pose,
                emotion=beat.puppet.emotion,
                narration=beat.narration,
                interaction=beat.puppet.interaction,
                facing=beat.puppet.facing,
                beat_id=beat.id,
                fps=fps,
                rms_env=rms_env,
            )

        out_path = Path(out_mp4)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp4 = out_path.with_name(f"{out_path.stem}.tmp.mp4")

        audio_inputs = (
            ["-i", str(wav_path)]
            if (wav_path is not None and wav_path.is_file())
            else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        )
        norm_flags = build_normalized_beat_flags(fps=fps, hw=self.hw)
        cmd = [
            ffmpeg_exe(),
            "-hide_banner",
            "-v",
            "error",
            "-y",
            *self.hw.ffmpeg_resource_clamp,
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{target_w}x{target_h}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            *audio_inputs,
            "-t",
            f"{dur:.4f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            *norm_flags,
            str(tmp_mp4),
        ]

        trans_frames = max(1, min(6, int(round(fps * 0.20))))
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        stderr_b = b""
        try:
            assert proc.stdin is not None
            for f_idx in range(n_frames):
                if cancel is not None and f_idx % 8 == 0:
                    cancel.check()
                t_sec = f_idx / fps
                mouth = rms_env[f_idx] if f_idx < len(rms_env) else 0.0
                frame = self.render_frame(
                    beat,
                    spec=spec,
                    layout=layout,
                    f_idx=f_idx,
                    t_sec=t_sec,
                    mouth_open=mouth,
                    word_timings=word_timings,
                    width=target_w,
                    height=target_h,
                    puppet_rig=puppet_rig,
                )
                try:
                    if (
                        prev_tail_frame is not None
                        and beat.transition_in != "editorial_cut"
                        and f_idx < trans_frames
                    ):
                        trans_frame = apply_transition(
                            prev_tail_frame,
                            frame,
                            (f_idx + 1) / float(trans_frames),
                            beat.transition_in,
                        )
                        try:
                            proc.stdin.write(trans_frame.tobytes())
                        finally:
                            trans_frame.close()
                    else:
                        proc.stdin.write(frame.tobytes())
                finally:
                    frame.close()

            proc.stdin.close()
            _, stderr_b = proc.communicate(timeout=180.0)
            if proc.returncode != 0:
                raise FFmpegError(
                    f"FFmpeg compositor lỗi beat {beat.id} (mã {proc.returncode}): "
                    f"{stderr_b.decode('utf-8', errors='replace')[-400:]}"
                )
            os.replace(tmp_mp4, out_path)
            return {
                "file_path": str(out_path),
                "frames": n_frames,
                "width": target_w,
                "height": target_h,
                "fps": fps,
                "layer_cache": self.layer_cache.stats(),
            }
        finally:
            if puppet_rig is not None:
                puppet_rig.close()
            for pipe in (proc.stdin, proc.stderr):
                if pipe is not None and not pipe.closed:
                    try:
                        pipe.close()
                    except OSError:
                        pass
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=2.0)
            except Exception:
                pass
            if tmp_mp4.exists():
                tmp_mp4.unlink(missing_ok=True)

    def render_timeline(
        self,
        spec: TimelineSpec,
        out_mp4: Path,
        *,
        cache_dir: Path,
        work_dir: Path,
        wav_paths: dict[str, Path] | None = None,
        library_dir: Path | None = None,
        assets_dir: Path | None = None,
        brand_dir: Path | None = None,
        watermark: WatermarkSettings | None = None,
        cancel: CancelToken | None = None,
    ) -> dict[str, Any]:
        """Dựng toàn bộ TimelineSpec qua Preflight + BeatCache + Concat -c copy + Watermark."""
        gate = PreflightQualityGate()
        report = gate.validate_and_reflow(spec, auto_fix=True)
        clean_spec = report.repaired_spec
        if not clean_spec.beats:
            raise ValueError("TimelineSpec chưa có beat nào để dựng")

        bcache = BeatCache(cache_dir)
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)

        beat_mp4s: list[Path] = []
        cache_hits = 0
        cache_misses = 0

        for beat in clean_spec.beats:
            if cancel is not None:
                cancel.check()
            key = beat.content_hash(
                aspect=clean_spec.aspect,
                fps=clean_spec.fps,
                theme=clean_spec.theme,
                domain=clean_spec.domain,
            )
            cached = bcache.lookup(key)
            if cached is not None:
                cache_hits += 1
                beat_mp4s.append(cached)
                continue

            cache_misses += 1
            raw_beat_mp4 = work / f"beat_{beat.id}.mp4"
            beat_wav = wav_paths.get(beat.id) if wav_paths else None
            self.render_beat_to_mp4(
                beat,
                clean_spec,
                raw_beat_mp4,
                wav_path=beat_wav,
                library_dir=library_dir,
                assets_dir=assets_dir,
                cancel=cancel,
            )
            stored = bcache.store_from_file(key, raw_beat_mp4)
            beat_mp4s.append(stored)

        out_path = Path(out_mp4)
        joined_mp4 = work / "joined_no_wm.mp4" if (watermark and watermark.enabled) else out_path
        bcache.concat_cached_beats(beat_mp4s, joined_mp4, work_dir=work, hw=self.hw)

        if watermark is not None and watermark.enabled:
            wm_png = work / "watermark.png"
            render_watermark_png(
                wm_png,
                watermark,
                width=clean_spec.width,
                height=clean_spec.height,
                brand_dir=brand_dir,
                assets_dir=assets_dir,
            )
            fc_txt = work / "wm_filtergraph.txt"
            fc_body = build_watermark_overlay_filter(
                input_video="0:v", input_wm="1:v", output_label="v_wm"
            )
            fc_tmp = fc_txt.with_name(f"{fc_txt.name}.tmp")
            try:
                fc_tmp.write_text(fc_body, encoding="utf-8")
                os.replace(fc_tmp, fc_txt)
            finally:
                if fc_tmp.exists():
                    fc_tmp.unlink(missing_ok=True)

            tmp_wm_out = out_path.with_name(f"{out_path.stem}.tmp.mp4")
            cmd = [
                ffmpeg_exe(),
                "-hide_banner",
                "-v",
                "error",
                "-y",
                *self.hw.ffmpeg_resource_clamp,
                "-i",
                str(joined_mp4),
                "-i",
                str(wm_png),
                "-filter_complex_script",
                str(fc_txt),
                "-map",
                "[v_wm]",
                "-map",
                "0:a",
                *build_normalized_beat_flags(fps=clean_spec.fps, hw=self.hw),
                str(tmp_wm_out),
            ]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                _, err_b = proc.communicate(timeout=180.0)
                if proc.returncode != 0:
                    raise FFmpegError(
                        f"FFmpeg watermark lỗi ({proc.returncode}): "
                        f"{err_b.decode('utf-8', errors='replace')[-300:]}"
                    )
                os.replace(tmp_wm_out, out_path)
            finally:
                if proc.stderr is not None:
                    try:
                        proc.stderr.close()
                    except OSError:
                        pass
                try:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
                if tmp_wm_out.exists():
                    tmp_wm_out.unlink(missing_ok=True)

        return {
            "file_path": str(out_path),
            "beats_total": len(clean_spec.beats),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "preflight_fixed": report.fixed_count,
            "hardware_mode": self.hw.mode,
            "layer_cache": self.layer_cache.stats(),
        }
