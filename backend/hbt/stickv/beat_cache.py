"""Cache render từng beat StickV theo chuỗi trạng thái (State-Chained Beat Cache)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PIL import Image

from hbt.shared.pipeline.watermark import WatermarkSettings
from hbt.stickv.backdrops import LOOP_DURATION_S
from hbt.stickv.models import StickvBeat
from hbt.stickv.puppet import SEG_CACHE_VERSION, PuppetPoseState
from hbt.stickv.stage import BeatStageState

BEAT_CACHE_SCHEMA_VERSION = "v1_state_chained_60fps"
DEFAULT_BEAT_CACHE_MAX_MB = 200.0


def serialize_pose_state(pose_state: PuppetPoseState | None) -> dict[str, Any] | None:
    """Chuyển toàn bộ 20 trường `PuppetPoseState` (gồm cả 6 vận tốc lò xo) thành dict JSON."""
    if pose_state is None:
        return None
    if isinstance(pose_state, PuppetPoseState):
        return {k: v for k, v in asdict(pose_state).items()}
    if isinstance(pose_state, dict):
        return dict(pose_state)
    return None


def deserialize_pose_state(data: dict[str, Any] | None) -> PuppetPoseState | None:
    """Khôi phục nguyên vẹn `PuppetPoseState` từ JSON (giữ đủ 6 vận tốc lò xo)."""
    if not isinstance(data, dict):
        return None
    return PuppetPoseState(
        head_angle=float(data.get("head_angle", 0.0)),
        head_dx=float(data.get("head_dx", 0.0)),
        arm_l_angle=float(data.get("arm_l_angle", 0.0)),
        elbow_l_angle=float(data.get("elbow_l_angle", 0.0)),
        arm_r_angle=float(data.get("arm_r_angle", 0.0)),
        elbow_r_angle=float(data.get("elbow_r_angle", 0.0)),
        torso_angle=float(data.get("torso_angle", 0.0)),
        torso_dx=float(data.get("torso_dx", 0.0)),
        torso_dy=float(data.get("torso_dy", 0.0)),
        torso_scale_y=float(data.get("torso_scale_y", 1.0)),
        lw_x=float(data["lw_x"]) if data.get("lw_x") is not None else None,
        lw_y=float(data["lw_y"]) if data.get("lw_y") is not None else None,
        rw_x=float(data["rw_x"]) if data.get("rw_x") is not None else None,
        rw_y=float(data["rw_y"]) if data.get("rw_y") is not None else None,
        lw_vx=float(data.get("lw_vx", 0.0)),
        lw_vy=float(data.get("lw_vy", 0.0)),
        rw_vx=float(data.get("rw_vx", 0.0)),
        rw_vy=float(data.get("rw_vy", 0.0)),
        head_vel=float(data.get("head_vel", 0.0)),
        torso_vel=float(data.get("torso_vel", 0.0)),
    )


def serialize_stage_state(state: BeatStageState | None) -> dict[str, Any] | None:
    """Tuần tự hóa `BeatStageState` + `PuppetPoseState` lồng bên trong."""
    if state is None:
        return None
    return {
        "x": float(state.x),
        "y": float(state.y),
        "scale": float(state.scale),
        "pose_state": serialize_pose_state(state.pose_state),
        "camera_zoom": float(state.camera_zoom),
        "camera_pan_x": float(state.camera_pan_x),
        "camera_pan_y": float(state.camera_pan_y),
        "board_alpha": float(state.board_alpha),
        "camera_shot": str(state.camera_shot),
        "last_board_title": str(state.last_board_title),
        "last_board_type": str(state.last_board_type),
        "last_chapter": int(state.last_chapter),
    }


def deserialize_stage_state(data: dict[str, Any] | None) -> BeatStageState | None:
    """Khôi phục `BeatStageState` từ JSON kèm toàn bộ `pose_state`."""
    if not isinstance(data, dict):
        return None
    return BeatStageState(
        x=float(data.get("x", 0.0)),
        y=float(data.get("y", 0.0)),
        scale=float(data.get("scale", 1.0)),
        pose_state=deserialize_pose_state(data.get("pose_state")),
        camera_zoom=float(data.get("camera_zoom", 1.0)),
        camera_pan_x=float(data.get("camera_pan_x", 0.5)),
        camera_pan_y=float(data.get("camera_pan_y", 0.5)),
        board_alpha=float(data.get("board_alpha", 1.0)),
        camera_shot=str(data.get("camera_shot", "wide_stage")),
        last_board_title=str(data.get("last_board_title", "")),
        last_board_type=str(data.get("last_board_type", "")),
        last_chapter=int(data.get("last_chapter", 1)),
    )


def hash_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def hash_board_image(board_img: Image.Image | None) -> str:
    if board_img is None:
        return "none"
    h = hashlib.sha256()
    h.update(f"{board_img.mode}:{board_img.width}x{board_img.height}:".encode())
    h.update(board_img.tobytes())
    return h.hexdigest()[:24]


def compute_beat_cache_key(
    *,
    beat: StickvBeat,
    aspect: str,
    w: int,
    h: int,
    fps: int,
    domain: str,
    theme: str,
    animation_mode: str,
    pause_scale: float,
    primary_entity_en: str,
    total_chapters: int,
    has_next_diff_title: bool,
    show_chapter_banner: bool,
    watermark: WatermarkSettings | None,
    n_frames_beat: int,
    eff_dur_b: float,
    speech_start: float,
    speech_end: float,
    word_timings: list[tuple[str, float, float]],
    spoken_segs: list[tuple[float, float, str]],
    wav_sha256: str,
    global_frame_offset: int,
    prev_stage_state: BeatStageState | None,
    prev_board_img: Image.Image | None,
) -> str:
    """Sinh khóa SHA256 nối trạng thái (`prev_stage_state`, `prev_board_sha256`, pha nền)."""
    loop_frames = max(1, int(round(LOOP_DURATION_S * max(1, int(fps)))))
    wm_payload = (
        watermark.model_dump(mode="json")
        if (watermark and watermark.enabled)
        else {"enabled": False}
    )
    payload = {
        "schema": BEAT_CACHE_SCHEMA_VERSION,
        "seg_cache_version": SEG_CACHE_VERSION,
        "beat": beat.model_dump(mode="json"),
        "render": {
            "aspect": aspect,
            "w": int(w),
            "h": int(h),
            "fps": int(fps),
            "domain": domain,
            "theme": theme,
            "animation_mode": animation_mode,
            "pause_scale": round(float(pause_scale), 4),
            "primary_entity_en": primary_entity_en,
            "total_chapters": int(total_chapters),
            "has_next_diff_title": bool(has_next_diff_title),
            "show_chapter_banner": bool(show_chapter_banner),
        },
        "watermark": wm_payload,
        "timing": {
            "n_frames_beat": int(n_frames_beat),
            "eff_dur_b": round(float(eff_dur_b), 4),
            "speech_start": round(float(speech_start), 4),
            "speech_end": round(float(speech_end), 4),
            "word_timings": [
                [str(w_s), round(float(a), 4), round(float(b), 4)] for w_s, a, b in word_timings
            ],
            "spoken_segs": [
                [round(float(a), 4), round(float(b), 4), str(t)] for a, b, t in spoken_segs
            ],
            "wav_sha256": wav_sha256,
        },
        "loop_frame_mod": int(global_frame_offset) % loop_frames,
        "prev_stage_state": serialize_stage_state(prev_stage_state),
        "prev_board_sha256": hash_board_image(prev_board_img),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]


class StickvBeatCache:
    """Bộ nhớ đệm kết quả dựng theo beat (`mp4 + state.json + board.png`), giới hạn 200MB LRU."""

    def __init__(self, cache_dir: Path, *, max_mb: float = DEFAULT_BEAT_CACHE_MAX_MB) -> None:
        self.cache_dir = Path(cache_dir)
        self.max_bytes = max(8 * 1024 * 1024, int(float(max_mb) * 1024 * 1024))

    @property
    def enabled(self) -> bool:
        return os.environ.get("STICKV_DISABLE_BEAT_CACHE") != "1"

    def _paths(self, key: str) -> tuple[Path, Path, Path]:
        return (
            self.cache_dir / f"{key}.mp4",
            self.cache_dir / f"{key}.state.json",
            self.cache_dir / f"{key}.board.png",
        )

    def lookup(self, key: str) -> tuple[Path, BeatStageState | None, Image.Image | None] | None:
        if not self.enabled:
            return None
        mp4_p, state_p, board_p = self._paths(key)
        if not (mp4_p.is_file() and mp4_p.stat().st_size > 128 and state_p.is_file()):
            return None
        try:
            raw_state = json.loads(state_p.read_text(encoding="utf-8"))
            state = deserialize_stage_state(raw_state.get("stage_state"))
            board_img: Image.Image | None = None
            if board_p.is_file() and board_p.stat().st_size > 32:
                with Image.open(board_p) as raw_b:
                    board_img = raw_b.convert("RGBA")
            now = time.time()
            for p in (mp4_p, state_p, board_p):
                if p.exists():
                    os.utime(p, (now, now))
            return mp4_p, state, board_img
        except Exception:
            return None

    def store(
        self,
        key: str,
        mp4_path: Path,
        stage_state: BeatStageState | None,
        board_img: Image.Image | None,
    ) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        dst_mp4, dst_state, dst_board = self._paths(key)

        state_tmp = dst_state.with_name(f"{key}.state.tmp.json")
        mp4_tmp = dst_mp4.with_name(f"{key}.tmp.mp4")
        board_tmp = dst_board.with_name(f"{key}.board.tmp.png")
        try:
            state_payload = {
                "schema": BEAT_CACHE_SCHEMA_VERSION,
                "stage_state": serialize_stage_state(stage_state),
            }
            state_tmp.write_text(
                json.dumps(state_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            shutil.copy2(mp4_path, mp4_tmp)
            if board_img is not None:
                board_img.save(board_tmp, format="PNG")
                os.replace(board_tmp, dst_board)
            elif dst_board.exists():
                dst_board.unlink(missing_ok=True)
            os.replace(mp4_tmp, dst_mp4)
            os.replace(state_tmp, dst_state)
        finally:
            for tmp in (state_tmp, mp4_tmp, board_tmp):
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
        self._prune_lru()
        return dst_mp4

    def _prune_lru(self) -> None:
        if not self.cache_dir.is_dir():
            return
        groups: dict[str, tuple[float, int, list[Path]]] = {}
        total_bytes = 0
        for p in self.cache_dir.iterdir():
            if not p.is_file() or ".tmp." in p.name:
                continue
            stem = p.name.split(".", 1)[0]
            try:
                st = p.stat()
            except OSError:
                continue
            total_bytes += st.st_size
            prev = groups.get(stem)
            if prev is None:
                groups[stem] = (st.st_mtime, st.st_size, [p])
            else:
                groups[stem] = (max(prev[0], st.st_mtime), prev[1] + st.st_size, [*prev[2], p])
        if total_bytes <= self.max_bytes:
            return
        for _stem, (_mtime, size_b, files) in sorted(groups.items(), key=lambda kv: kv[1][0]):
            if total_bytes <= self.max_bytes:
                break
            for fp in files:
                fp.unlink(missing_ok=True)
            total_bytes -= size_b
