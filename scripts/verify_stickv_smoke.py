"""Công cụ đo kiểm thật (không mock FFmpeg) chống tái lỗi cho StickV.

Cách dùng:
  backend\\.venv\\Scripts\\python scripts/verify_stickv_smoke.py --project <slug>
  backend\\.venv\\Scripts\\python scripts/verify_stickv_smoke.py --synthetic --check-render
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _ffprobe_streams(media_path: Path) -> dict[str, Any]:
    """Đọc chính xác metadata từng stream từ MP4/WAV bằng ffprobe thật."""
    exe = shutil.which("ffprobe") or "ffprobe"
    proc = subprocess.run(
        [
            exe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,pix_fmt,r_frame_rate,avg_frame_rate,duration,nb_frames,sample_rate,channels",
            "-of",
            "json",
            str(media_path),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"error": (proc.stderr or "ffprobe failed").strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"invalid ffprobe json: {exc}"}


def _parse_rate(rate_str: str) -> float:
    raw = (rate_str or "").strip()
    if "/" in raw:
        num, den = raw.split("/", 1)
        try:
            d = float(den)
            return round(float(num) / d, 3) if d > 0 else 0.0
        except ValueError:
            return 0.0
    try:
        return round(float(raw), 3)
    except ValueError:
        return 0.0


def _wav_duration_s(wav_path: Path) -> float:
    if not wav_path.is_file() or wav_path.stat().st_size <= 44:
        return 0.0
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sr = wf.getframerate()
            return round(wf.getnframes() / float(sr), 4) if sr > 0 else 0.0
    except Exception:
        return 0.0


def _measure_render_motion(project_data: dict[str, Any]) -> tuple[float, float, float]:
    """Đo độ nhảy tọa độ nhân vật giữa các beat (px/frame @ 60fps) và góc gập gối IK (độ)."""
    from hbt.stickv.models import STICKV_ASPECT_SIZES, StickvBeat
    from hbt.stickv.puppet import solve_2bone_ik
    from hbt.stickv.stage import compute_beat_character_target

    aspect = str(project_data.get("aspect") or "9:16")
    w, h = STICKV_ASPECT_SIZES.get(aspect, (1080, 1920))  # type: ignore[arg-type]
    raw_beats = project_data.get("beats") or []
    prev_x: float | None = None
    max_jump_px = 0.0
    for rb in raw_beats:
        try:
            b = StickvBeat.model_validate(rb)
        except Exception:
            continue
        tx, _ty, _sc = compute_beat_character_target(
            w,
            h,
            260,
            int(h * 0.48),
            interaction=getattr(b, "interaction", "none") or "none",
            aspect=aspect,  # type: ignore[arg-type]
            camera_shot=getattr(b, "camera_shot", "wide_stage") or "wide_stage",
        )
        if prev_x is not None:
            # Trong tween 0.40s @ 60fps = 24 frame -> bước nhảy tối đa mỗi frame (ease-in-out peak ~1.5x)
            per_frame = abs(tx - prev_x) * (1.5 / 24.0)
            max_jump_px = max(max_jump_px, per_frame)
        prev_x = tx

    # Đo góc gập gối giải phẫu khi nhún 0% vs 3% chiều cao chân
    leg_h = 180.0
    l1, l2 = leg_h * 0.51, leg_h * 0.51
    hip_stand = (100.0, 100.0)
    ankle = (100.0, 100.0 + leg_h * 0.92)
    bends: list[float] = []
    for dip in (0.0, 4.0, 10.0, 18.0):
        hip = (hip_stand[0], hip_stand[1] + dip)
        knee, foot = solve_2bone_ik(hip, ankle, l1, l2, bend_dir=1)
        v1 = (hip[0] - knee[0], hip[1] - knee[1])
        v2 = (foot[0] - knee[0], foot[1] - knee[1])
        n1 = max(1e-6, math.hypot(*v1))
        n2 = max(1e-6, math.hypot(*v2))
        cos_t = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        bend_deg = 180.0 - math.degrees(math.acos(cos_t))
        bends.append(round(bend_deg, 2))
    return round(max_jump_px, 2), min(bends), max(bends)


def inspect_project(
    project_dir: Path,
    *,
    require_whisper: bool = False,
    check_render: bool = False,
) -> int:
    proj_file = project_dir / "project.json"
    if not proj_file.is_file():
        print(f"ERROR: Không tìm thấy {proj_file}")
        return 1

    proj = json.loads(proj_file.read_text(encoding="utf-8"))
    beats = proj.get("beats") or []
    outro_enabled = bool(proj.get("outro", True))

    renders_dir = project_dir / "renders"
    mp4_path = renders_dir / "final.mp4"
    if not mp4_path.is_file():
        mp4_path = renders_dir / "preview.mp4"

    voice_full = project_dir / "build" / "stickv_voice_full.wav"
    timing_file = project_dir / "build" / "stickv_timing.json"
    audio_dir = project_dir / "audio"

    video_dur = 0.0
    audio_dur = 0.0
    fps = 0.0
    pix_fmt = "missing"
    audio_sr = 0
    if mp4_path.is_file():
        probe = _ffprobe_streams(mp4_path)
        for st in probe.get("streams") or []:
            ctype = st.get("codec_type")
            if ctype == "video":
                video_dur = float(st.get("duration") or 0.0)
                fps = _parse_rate(str(st.get("avg_frame_rate") or st.get("r_frame_rate") or "0"))
                pix_fmt = str(st.get("pix_fmt") or "")
            elif ctype == "audio":
                audio_dur = float(st.get("duration") or 0.0)
                audio_sr = int(st.get("sample_rate") or 0)

    voice_full_dur = _wav_duration_s(voice_full)
    drift_ms = round(abs(video_dur - audio_dur) * 1000.0, 2) if (video_dur and audio_dur) else -1.0

    align_source = "missing"
    fallback_reason = ""
    timing_beats: dict[str, list[list[Any]]] = {}
    if timing_file.is_file():
        tdata = json.loads(timing_file.read_text(encoding="utf-8"))
        meta = tdata.get("meta") or {}
        align_source = str(meta.get("method") or "unknown")
        fallback_reason = str(meta.get("whisper_fallback_reason") or "")
        timing_beats = tdata.get("beats") or {}

    failures: list[str] = []
    if not mp4_path.is_file():
        failures.append(f"Thiếu file render ({renders_dir})")
    if drift_ms < 0 or drift_ms > 30.0:
        failures.append(f"INV-01 FAIL: drift_ms={drift_ms}ms > 30ms")
    if pix_fmt not in ("yuv420p", "missing"):
        failures.append(f"INV-07 FAIL: pix_fmt={pix_fmt} != yuv420p")
    if audio_sr and audio_sr != 48000:
        failures.append(f"INV-07 FAIL: audio_sr={audio_sr} != 48000")
    if require_whisper and align_source != "whisper":
        failures.append(f"INV-02 FAIL: alignment_source={align_source} != whisper")

    print(f"=== STICKV SMOKE VERIFIER: {project_dir.name} ===")
    print(f"MP4 file         : {mp4_path.name if mp4_path.is_file() else 'MISSING'}")
    print(f"video_stream_dur : {video_dur:.4f}s")
    print(f"audio_stream_dur : {audio_dur:.4f}s")
    print(f"drift_ms         : {drift_ms:.2f} ms (ngưỡng <= 30.0 ms)")
    print(f"voice_full_dur   : {voice_full_dur:.4f}s (outro={outro_enabled})")
    print(f"fps / pix_fmt    : {fps} fps / {pix_fmt} / audio {audio_sr}Hz")
    print(f"alignment_source : {align_source}")
    if fallback_reason:
        print(f"fallback_reason  : {fallback_reason}")

    if check_render:
        max_jump_px, min_bend, max_bend = _measure_render_motion(proj)
        print(f"max_char_jump_px : {max_jump_px} px/frame (ngưỡng <= 25.0)")
        print(f"knee_bend_deg    : min={min_bend}° / max={max_bend}° (ngưỡng max > 2.0°)")
        if max_jump_px > 25.0:
            failures.append(f"INV-03 FAIL: max_char_jump_px={max_jump_px} > 25")
        if max_bend <= 2.0:
            failures.append(f"INV-06 FAIL: max_knee_bend_deg={max_bend} <= 2.0")

    print("\n| Beat | proj_dur | wav_dur | delta_ms | beat_start | beat_end | first_w | last_w | words |")
    print("| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    acc_wav = 0.0
    acc_proj = 0.0
    for idx, beat in enumerate(beats):
        bid = str(beat.get("id") or f"b{idx + 1:03d}")
        p_dur = float(beat.get("duration_sec") or 0.0)
        w_dur = _wav_duration_s(audio_dir / f"{bid}.wav")
        d_ms = round((p_dur - w_dur) * 1000.0, 1) if w_dur > 0 else 0.0
        rows = timing_beats.get(str(idx)) or []
        first_w = float(rows[0][1]) if rows else -1.0
        last_w = float(rows[-1][2]) if rows else -1.0
        b_start = acc_wav if w_dur > 0 else acc_proj
        b_end = b_start + (w_dur if w_dur > 0 else p_dur)
        print(
            f"| {bid} | {p_dur:.3f}s | {w_dur:.3f}s | {d_ms:+.1f} | "
            f"{b_start:.3f}s | {b_end:.3f}s | {first_w:.3f}s | {last_w:.3f}s | {len(rows)} |"
        )
        acc_wav += w_dur
        acc_proj += p_dur

    total_delta_ms = round((acc_proj - acc_wav) * 1000.0, 1) if acc_wav > 0 else 0.0
    print(f"\nTổng proj_dur={acc_proj:.3f}s | Tổng wav_dur={acc_wav:.3f}s | Chênh={total_delta_ms:+.1f}ms")
    if acc_wav > 0 and voice_full_dur > 0:
        vf_delta_ms = round((voice_full_dur - acc_wav) * 1000.0, 1)
        print(f"Chênh voice_full - sum(wavs) = {vf_delta_ms:+.1f}ms")

    if failures:
        print("\nRESULT: FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nRESULT: PASS")
    return 0


def run_synthetic_smoke(*, check_render: bool = True) -> int:
    """Dựng thật clip ngắn 3 beat (~5s, không mock FFmpeg) rồi đo kiểm toàn bộ bất biến."""
    from hbt.stickv.models import StickvBeat, StickvProject
    from hbt.stickv.render import render_stickv

    with tempfile.TemporaryDirectory(prefix="stickv-smoke-") as tmp:
        pdir = Path(tmp) / "smoke-proj"
        pdir.mkdir(parents=True, exist_ok=True)
        proj = StickvProject(
            slug="smoke-proj",
            title="StickV Smoke Test",
            aspect="9:16",
            outro=False,
            beats=[
                StickvBeat(
                    id="b001",
                    narration="Tháp nghiêng Pisa nổi tiếng toàn cầu.",
                    pose="point_up",
                    board_type="bullets",
                    board_title="Tháp Pisa",
                    board_data={"items": ["Xây năm 1173", "Nghiêng 4 độ"]},
                    sfx_tag="none",
                ),
                StickvBeat(
                    id="b002",
                    narration="Nền đất sét mềm khiến móng lún lệch.",
                    pose="present_board",
                    board_type="myth_vs_fact",
                    board_title="Giải mã",
                    board_data={"myth": "Cố tình xây nghiêng", "fact": "Nền đất lún tự nhiên"},
                    sfx_tag="none",
                ),
                StickvBeat(
                    id="b003",
                    narration="Kỹ sư đã gia cố móng an toàn.",
                    pose="welcome_open",
                    board_type="recap_card",
                    board_title="TÓM TẮT 3 Ý CỐT LÕI",
                    board_data={"items": ["Đất yếu", "Gia cố móng", "An toàn 300 năm"]},
                    sfx_tag="none",
                ),
            ],
        )
        (pdir / "project.json").write_text(
            json.dumps(proj.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        render_stickv(
            proj,
            pdir,
            library_dir=REPO_ROOT / "library",
            assets_dir=REPO_ROOT / "assets",
            brand_dir=REPO_ROOT / "brand",
            voice_provider=None,
            preview=True,
        )
        (pdir / "project.json").write_text(
            json.dumps(proj.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return inspect_project(pdir, require_whisper=False, check_render=check_render)


def main() -> int:
    parser = argparse.ArgumentParser(description="StickV Real Smoke Verifier (chống xanh giả)")
    parser.add_argument("--project", default="", help="Slug dự án thật trong workspace/stickv/")
    parser.add_argument("--synthetic", action="store_true", help="Dựng thật clip 3 beat ngắn (~5s)")
    parser.add_argument("--check-render", action="store_true", help="Đo thêm jump nhân vật & góc gối IK")
    parser.add_argument("--require-whisper", action="store_true", help="Bắt buộc alignment_source == whisper")
    args = parser.parse_args()

    if args.synthetic:
        return run_synthetic_smoke(check_render=True if args.check_render else True)
    if args.project:
        pdir = REPO_ROOT / "workspace" / "stickv" / args.project
        return inspect_project(
            pdir,
            require_whisper=args.require_whisper,
            check_render=args.check_render,
        )
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
