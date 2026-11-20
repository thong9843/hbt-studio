"""Bộ điều phối Animation Stickman hỗn hợp (.webm alpha / chuỗi PNG / fallback 27+ PNG)."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from hbt.pipeline.ffutil import ffmpeg_exe
from hbt.shared.ffmpeg_utils import FFMPEG_RESOURCE_CLAMP
from hbt.stickv.puppet import PuppetPoseState, PuppetRig, compute_smoothed_rms, is_puppet_ready
from hbt.stickv.stage import resolve_pose_png

ANIM_VIDEO_EXTS = {".webm", ".mov"}

# Ánh xạ tên animation chuẩn sang tên pose PNG dự phòng
ANIM_TO_POSE_FALLBACK: dict[str, str] = {
    "shock_jump": "shock",
    "idea_bulb": "idea",
    "point_board": "point_right",
    "facepalm": "facepalm",
    "nod_agree": "happy",
    "shake_head": "confused",
    "celebrate": "celebrate",
    "stop_hand": "stop",
    "idle_breathe": "explain",
    "talk_explain": "explain",
    "talk_excited": "excited",
    "think_loop": "think",
    "walk_loop": "walk",
    "run_loop": "run",
    "cry_loop": "cry",
    "laugh_loop": "laugh",
}


def _anim_roots(library_dir: Path, assets_dir: Path) -> list[Path]:
    return [
        Path(assets_dir) / "stickman" / "animations",
        Path(library_dir) / "stickman" / "animations",
    ]


def list_available_animations(library_dir: Path, assets_dir: Path) -> dict[str, list[str]]:
    """Quét danh sách animation hiện có trong `oneshot/` và `loop/` (không lỗi nếu rỗng)."""
    result: dict[str, list[str]] = {"oneshot": [], "loop": []}
    for group in ("oneshot", "loop"):
        seen: set[str] = set()
        names: list[str] = []
        for root in _anim_roots(library_dir, assets_dir):
            folder = root / group
            if not folder.is_dir():
                continue
            for item in sorted(folder.iterdir()):
                if item.name.startswith("."):
                    continue
                if item.is_file() and item.suffix.lower() in ANIM_VIDEO_EXTS:
                    if item.stem not in seen:
                        seen.add(item.stem)
                        names.append(item.stem)
                elif item.is_dir() and any(
                    p.is_file() and p.suffix.lower() == ".png" for p in item.iterdir()
                ):
                    if item.name not in seen:
                        seen.add(item.name)
                        names.append(item.name)
        result[group] = names
    return result


def resolve_animation_source(
    name: str | None,
    group: str,
    library_dir: Path,
    assets_dir: Path,
) -> Path | None:
    """Tìm file `.webm`/`.mov` hoặc thư mục chuỗi `.png` theo tên animation."""
    clean = (name or "").strip()
    if not clean:
        return None
    stem = Path(clean).stem
    for root in _anim_roots(library_dir, assets_dir):
        folder = root / group
        if not folder.is_dir():
            continue
        for ext in (".webm", ".mov"):
            cand = folder / f"{stem}{ext}"
            if cand.is_file():
                return cand
        seq_dir = folder / stem
        if seq_dir.is_dir() and any(
            p.is_file() and p.suffix.lower() == ".png" for p in seq_dir.iterdir()
        ):
            return seq_dir
    return None


def _probe_video_dimensions(path: Path) -> tuple[int, int]:
    try:
        proc = subprocess.run(
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            streams = data.get("streams") or []
            if streams:
                w = int(streams[0].get("width") or 0)
                h = int(streams[0].get("height") or 0)
                if w > 0 and h > 0:
                    return w, h
    except Exception:
        pass
    return 0, 0


def _decode_video_rgba_frames(
    path: Path,
    *,
    fps: int,
    target_height: int,
    max_frames: int = 300,
) -> list[Image.Image]:
    """Giải mã clip `.webm` (VP9 alpha) hoặc `.mov` sang danh sách frame RGBA đã scale."""
    src_w, src_h = _probe_video_dimensions(path)
    if src_w <= 0 or src_h <= 0:
        return []
    out_h = max(64, int(target_height))
    out_w = max(64, int(round(src_w * (out_h / src_h))))

    decoder_args: list[str] = []
    if path.suffix.lower() == ".webm":
        decoder_args = ["-c:v", "libvpx-vp9"]

    cmd = [
        ffmpeg_exe(),
        "-v",
        "error",
        *FFMPEG_RESOURCE_CLAMP,
        *decoder_args,
        "-i",
        str(path),
        "-vf",
        f"fps={fps},scale={out_w}:{out_h}:flags=lanczos,format=rgba",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
    except Exception:
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []

    frame_bytes = out_w * out_h * 4
    total = min(max_frames, len(proc.stdout) // frame_bytes)
    frames: list[Image.Image] = []
    for idx in range(total):
        chunk = proc.stdout[idx * frame_bytes : (idx + 1) * frame_bytes]
        frames.append(Image.frombytes("RGBA", (out_w, out_h), chunk))
    return frames


def _load_png_sequence_frames(
    folder: Path,
    *,
    target_height: int,
    max_frames: int = 300,
) -> list[Image.Image]:
    pngs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".png")
    frames: list[Image.Image] = []
    for p in pngs[:max_frames]:
        try:
            with Image.open(p) as raw:
                rgba = raw.convert("RGBA")
                scale = max(64, target_height) / max(1, rgba.height)
                new_w = max(32, int(round(rgba.width * scale)))
                resized = rgba.resize((new_w, max(64, target_height)), Image.Resampling.LANCZOS)
                frames.append(resized)
        except Exception:
            continue
    return frames


def load_animation_frames(
    source: Path | None,
    *,
    fps: int,
    target_height: int,
) -> list[Image.Image]:
    if source is None:
        return []
    if source.is_dir():
        return _load_png_sequence_frames(source, target_height=target_height)
    if source.is_file() and source.suffix.lower() in ANIM_VIDEO_EXTS:
        return _decode_video_rgba_frames(source, fps=fps, target_height=target_height)
    return []


@dataclass(frozen=True)
class AnimatorMotion:
    dy: float = 0.0
    tilt_deg: float = 0.0
    scale_y: float = 1.0
    phase: str = "loop"
    used_fallback: bool = True


def _apply_25d_transform(
    img: Image.Image,
    *,
    facing: str,
    tilt_deg: float,
    scale_y: float,
) -> Image.Image:
    out = img
    flipped = False
    if facing == "left":
        out = out.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        flipped = True
    if abs(scale_y - 1.0) > 0.002:
        new_h = max(16, int(round(out.height * scale_y)))
        scaled = out.resize((out.width, new_h), Image.Resampling.BILINEAR)
        if flipped:
            out.close()
        out = scaled
        flipped = True
    if abs(tilt_deg) > 0.15:
        rotated = out.rotate(
            tilt_deg,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=(0, 0, 0, 0),
        )
        if flipped:
            out.close()
        out = rotated
    return out if flipped else out.copy()


class StickmanAnimator:
    """Điều phối 3 pha chuyển động cho 1 beat: oneshot -> loop -> idle (có PNG fallback)."""

    def __init__(
        self,
        *,
        pose: str,
        anim_oneshot: str | None,
        anim_loop: str | None,
        facing: str,
        duration_sec: float,
        speech_start: float,
        speech_end: float,
        fps: int,
        rms_env: list[float],
        library_dir: Path,
        assets_dir: Path,
        target_height: int,
        char_img_fallback: Image.Image | None = None,
        interaction: str = "none",
        emotion: str = "auto",
        face_mood: str | None = None,
        narration: str = "",
        beat_id: str = "b001",
        animation_mode: str = "auto",
        wav_path: Path | None = None,
        prev_pose_state: PuppetPoseState | None = None,
        global_t_offset: float = 0.0,
    ) -> None:
        self.facing = facing
        self.duration_sec = max(0.5, float(duration_sec))
        self.speech_start = max(0.0, float(speech_start))
        self.speech_end = max(self.speech_start, min(self.duration_sec, float(speech_end)))
        self.fps = max(15, int(fps))
        self.rms_env = rms_env
        self.target_height = max(64, int(target_height))
        self.animation_mode = (animation_mode or "auto").strip().lower()

        # Mức 1: 2D Procedural Puppet (khi đủ bộ linh kiện & animation_mode != "static")
        self.puppet_rig: PuppetRig | None = None
        if self.animation_mode != "static" and is_puppet_ready(library_dir, assets_dir):
            try:
                puppet_env = (
                    compute_smoothed_rms(wav_path, self.fps, self.duration_sec)
                    if wav_path is not None and wav_path.is_file()
                    else rms_env
                )
                self.puppet_rig = PuppetRig(
                    library_dir=library_dir,
                    assets_dir=assets_dir,
                    target_height=self.target_height,
                    pose=pose,
                    emotion=emotion,
                    face_mood=face_mood,
                    narration=narration,
                    anim_oneshot=anim_oneshot,
                    anim_loop=anim_loop or "talk_explain",
                    interaction=interaction,
                    facing=facing,
                    beat_id=beat_id,
                    fps=self.fps,
                    speech_start=self.speech_start,
                    speech_end=self.speech_end,
                    rms_env=puppet_env,
                    prev_pose_state=prev_pose_state,
                    global_t_offset=global_t_offset,
                )
            except Exception:
                self.puppet_rig = None

        # Mức 2: Clip .webm/.mov alpha hoặc chuỗi PNG (khi chưa có Puppet)
        if self.puppet_rig is None and self.animation_mode != "static":
            oneshot_src = resolve_animation_source(anim_oneshot, "oneshot", library_dir, assets_dir)
            loop_src = resolve_animation_source(anim_loop, "loop", library_dir, assets_dir)
            idle_src = resolve_animation_source("idle_breathe", "loop", library_dir, assets_dir)

            self.oneshot_frames = load_animation_frames(
                oneshot_src, fps=self.fps, target_height=self.target_height
            )
            self.loop_frames = load_animation_frames(
                loop_src, fps=self.fps, target_height=self.target_height
            )
            self.idle_frames = load_animation_frames(
                idle_src, fps=self.fps, target_height=self.target_height
            )
        else:
            self.oneshot_frames = []
            self.loop_frames = []
            self.idle_frames = []

        self.oneshot_dur = (
            min(len(self.oneshot_frames) / self.fps, max(0.6, self.speech_end))
            if self.oneshot_frames
            else 0.0
        )

        self._owns_fallback = False
        self.fallback_img: Image.Image | None = char_img_fallback
        if self.fallback_img is None:
            fb_pose = (
                ANIM_TO_POSE_FALLBACK.get(anim_loop or "", "")
                or ANIM_TO_POSE_FALLBACK.get(anim_oneshot or "", "")
                or pose
            )
            png_path = resolve_pose_png(fb_pose, library_dir, assets_dir)
            if png_path.is_file():
                with Image.open(png_path) as raw:
                    rgba = raw.convert("RGBA")
                    scale = self.target_height / max(1, rgba.height)
                    nw = max(32, int(round(rgba.width * scale)))
                    self.fallback_img = rgba.resize(
                        (nw, self.target_height), Image.Resampling.LANCZOS
                    )
                    self._owns_fallback = True

    def frame_at(self, frame_idx: int, t_sec: float) -> tuple[Image.Image | None, AnimatorMotion]:
        if self.puppet_rig is not None:
            self.puppet_rig.facing = self.facing
            img = self.puppet_rig.render_frame(frame_idx, t_sec)
            return img, AnimatorMotion(phase="puppet", used_fallback=False)

        rms = self.rms_env[frame_idx] if 0 <= frame_idx < len(self.rms_env) else 0.0
        rms_norm = max(0.0, min(1.0, rms))
        is_speaking = (self.speech_start <= t_sec <= self.speech_end) and rms_norm > 0.08

        # Pha 1: One-shot đầu câu
        if self.oneshot_frames and t_sec < self.oneshot_dur:
            idx = min(len(self.oneshot_frames) - 1, max(0, int(round(t_sec * self.fps))))
            img = _apply_25d_transform(
                self.oneshot_frames[idx], facing=self.facing, tilt_deg=0.0, scale_y=1.0
            )
            return img, AnimatorMotion(phase="oneshot", used_fallback=False)

        # Pha 3: Khoảng nghỉ cuối beat
        if t_sec > self.speech_end:
            if self.idle_frames:
                local_idx = max(0, int(round((t_sec - self.speech_end) * self.fps)))
                img = _apply_25d_transform(
                    self.idle_frames[local_idx % len(self.idle_frames)],
                    facing=self.facing,
                    tilt_deg=0.0,
                    scale_y=1.0,
                )
                return img, AnimatorMotion(phase="idle", used_fallback=False)
            if self.loop_frames:
                base = self.loop_frames[0]
                dy = math.sin(t_sec * 2.5) * 1.2
                img = _apply_25d_transform(base, facing=self.facing, tilt_deg=0.0, scale_y=1.005)
                return img, AnimatorMotion(dy=dy, phase="idle", used_fallback=False)

        # Pha 2: Loop diễn giải chính
        if self.loop_frames and t_sec <= self.speech_end:
            local_t = max(0.0, t_sec - self.oneshot_dur)
            local_idx = int(round(local_t * self.fps)) % len(self.loop_frames)
            img = _apply_25d_transform(
                self.loop_frames[local_idx], facing=self.facing, tilt_deg=0.0, scale_y=1.0
            )
            return img, AnimatorMotion(phase="loop", used_fallback=False)

        # Fallback PNG 2.5D theo RMS Audio Envelope
        if self.fallback_img is None:
            return None, AnimatorMotion(phase="idle", used_fallback=True)

        if is_speaking:
            dy = -4.0 * rms_norm
            tilt = math.sin(t_sec * 6.0) * 1.5 * rms_norm
            scale_y = 1.0 + 0.03 * rms_norm
            phase = "oneshot" if t_sec < 0.8 else "loop"
        else:
            # Khoảng lặng: thở nhẹ (biên độ giảm 70%)
            dy = math.sin(t_sec * 2.5) * 1.2
            tilt = 0.0
            scale_y = 1.0 + 0.008 * math.sin(t_sec * 2.5)
            phase = "idle"

        img = _apply_25d_transform(
            self.fallback_img, facing=self.facing, tilt_deg=tilt, scale_y=scale_y
        )
        return img, AnimatorMotion(
            dy=dy, tilt_deg=tilt, scale_y=scale_y, phase=phase, used_fallback=True
        )

    @property
    def last_pose_state(self) -> PuppetPoseState | None:
        return self.puppet_rig.last_pose_state if self.puppet_rig is not None else None

    def close(self) -> None:
        if self.puppet_rig is not None:
            self.puppet_rig.close()
            self.puppet_rig = None
        for group in (self.oneshot_frames, self.loop_frames, self.idle_frames):
            for im in group:
                im.close()
            group.clear()
        if self._owns_fallback and self.fallback_img is not None:
            self.fallback_img.close()
            self.fallback_img = None
