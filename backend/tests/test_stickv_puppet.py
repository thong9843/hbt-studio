"""Unit test cho Bộ diễn hoạt 2D Puppet phân cấp, tách khớp, EMA lip-sync & fallback 3 tầng."""

from __future__ import annotations

import wave
from io import BytesIO
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from hbt.config import Settings
from hbt.main import create_app
from hbt.stickv.animator import StickmanAnimator
from hbt.stickv.puppet import (
    EyeController,
    PuppetPoseState,
    PuppetRig,
    auto_segment_puppet,
    compute_mouth_transform,
    compute_smoothed_rms,
    find_puppet_slot_paths,
    get_puppet_status,
    is_puppet_ready,
    lerp_pose_state,
    rotate_around_pivot,
)


def _draw_synthetic_a_pose(dest: Path, *, w: int = 320, h: int = 420) -> Path:
    """Vẽ Stickman A-pose trắng đen tối giản trên nền trắng để test auto_segment_puppet."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    cx = w // 2
    # Đầu tròn trắng viền đen (y: 20..120)
    d.ellipse((cx - 50, 20, cx + 50, 120), fill=(255, 255, 255), outline=(11, 14, 20), width=6)
    # Thân + cà vạt đỏ + 2 chân
    d.line([(cx, 122), (cx, 270)], fill=(11, 14, 20), width=10)
    d.polygon([(cx, 128), (cx - 8, 175), (cx, 195), (cx + 8, 175)], fill=(217, 35, 46))
    d.line([(cx, 270), (cx - 22, 390)], fill=(11, 14, 20), width=9)
    d.line([(cx, 270), (cx + 22, 390)], fill=(11, 14, 20), width=9)
    # Tay trái & tay phải dạng A-pose tách khỏi thân
    d.line([(cx - 10, 138), (cx - 95, 245)], fill=(11, 14, 20), width=8)
    d.ellipse((cx - 110, 238, cx - 82, 266), fill=(255, 255, 255), outline=(11, 14, 20), width=4)
    d.line([(cx + 10, 138), (cx + 95, 245)], fill=(11, 14, 20), width=8)
    d.ellipse((cx + 82, 238, cx + 110, 266), fill=(255, 255, 255), outline=(11, 14, 20), width=4)
    img.save(dest)
    img.close()
    return dest


def _draw_eyes(dest: Path, color: tuple[int, int, int] = (11, 14, 20)) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (140, 60), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((20, 15, 50, 48), fill=color)
    d.ellipse((90, 15, 120, 48), fill=color)
    img.save(dest)
    img.close()
    return dest


def _draw_mouth(dest: Path, *, open_style: bool) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 60), (255, 255, 255))
    d = ImageDraw.Draw(img)
    if open_style:
        d.chord(
            (15, 10, 85, 52), start=0, end=180, fill=(240, 60, 180), outline=(11, 14, 20), width=4
        )
    else:
        d.arc((20, 18, 80, 44), start=15, end=165, fill=(11, 14, 20), width=5)
    img.save(dest)
    img.close()
    return dest


def _make_full_puppet_dir(base_dir: Path, *, prefix_jpg_mode: bool = False) -> None:
    if prefix_jpg_mode:
        _draw_synthetic_a_pose(base_dir / "base_character.png_Thân_gốc_demo.jpg")
        _draw_eyes(base_dir / "eyes_neutral.png_Mắt_thường.jpg")
        _draw_eyes(base_dir / "eyes_happy.png_Mắt_cười.jpg", color=(20, 120, 40))
        _draw_eyes(base_dir / "eyes_shock.png_Mắt_sốc.jpg", color=(20, 60, 200))
        _draw_eyes(base_dir / "eyes_angry.png_Mắt_giận.jpg", color=(200, 20, 20))
        _draw_mouth(base_dir / "mouth_closed.png_Khép.jpg", open_style=False)
        _draw_mouth(base_dir / "mouth_open.png_Mở.jpg", open_style=True)
    else:
        _draw_synthetic_a_pose(base_dir / "base_character.png")
        _draw_eyes(base_dir / "eyes_neutral.png")
        _draw_eyes(base_dir / "eyes_happy.png", color=(20, 120, 40))
        _draw_eyes(base_dir / "eyes_shock.png", color=(20, 60, 200))
        _draw_eyes(base_dir / "eyes_angry.png", color=(200, 20, 20))
        _draw_mouth(base_dir / "mouth_closed.png", open_style=False)
        _draw_mouth(base_dir / "mouth_open.png", open_style=True)


def test_auto_segment_puppet_and_sha256_cache(tmp_path: Path) -> None:
    base_p = _draw_synthetic_a_pose(tmp_path / "base_character.png")
    cache_dir = tmp_path / ".segments"

    res1 = auto_segment_puppet(base_p, cache_dir)
    assert res1["cached"] is False
    for name in ("body_torso", "head_blank", "arm_left", "arm_right"):
        p = res1["segments"][name]
        assert p.is_file()
        with Image.open(p) as im:
            assert im.mode == "RGBA"
            assert im.getbbox() is not None

    # Kiểm tra vá khớp tròn màu tối #0B0E14 tại tâm xoay vai trên thân
    with Image.open(res1["segments"]["body_torso"]) as torso:
        cfg = res1["rig_config"]
        sx = int(round(cfg["shoulder_left_torso"][0] * torso.width))
        sy = int(round(cfg["shoulder_left_torso"][1] * torso.height))
        px = torso.getpixel((min(torso.width - 1, sx), min(torso.height - 1, sy)))
        assert px[3] > 200 and px[0] < 35

    res2 = auto_segment_puppet(base_p, cache_dir)
    assert res2["cached"] is True


def test_rotate_around_pivot_and_head_child_lock(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")

    # Kiểm tra rotate_around_pivot giữ chính xác điểm pivot
    sq = Image.new("RGBA", (80, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(sq)
    d.ellipse((10, 10, 70, 90), fill=(255, 255, 255, 255), outline=(11, 14, 20, 255), width=4)
    rot, npiv = rotate_around_pivot(sq, 25.0, (40.0, 90.0))
    assert rot.width >= 80 and rot.height >= 100
    assert 0.0 <= npiv[0] <= rot.width and 0.0 <= npiv[1] <= rot.height
    sq.close()
    rot.close()

    # Dựng PuppetRig và kiểm tra mắt/miệng xoay cùng đầu (không lệch ra ngoài đầu)
    rig = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=420,
        pose="think",
        anim_oneshot="nod_agree",
        anim_loop="think_loop",
        fps=30,
        rms_env=[0.75] * 45,
    )
    try:
        frame = rig.render_frame(4, 0.15)
        assert frame.mode == "RGBA"
        assert frame.height == 420
        # Đảm bảo miệng từ mouth_open chỉ nằm trong vùng đầu phía trên (y < 45% height)
        arr = np.array(frame)
        mouth_px = (
            (arr[:, :, 0] > 180)
            & (arr[:, :, 1] < 100)
            & (arr[:, :, 2] > 140)
            & (arr[:, :, 3] > 200)
        )
        assert np.any(mouth_px)
        ys, _ = np.nonzero(mouth_px)
        assert int(ys.max()) < int(frame.height * 0.45)
        frame.close()
    finally:
        rig.close()


def test_compute_smoothed_rms_ema_and_mouth_squash_stretch(tmp_path: Path) -> None:
    wav_p = tmp_path / "speech.wav"
    sr = 16000
    # 0.5s im lặng -> 0.5s sóng sin lớn -> 0.5s im lặng
    t_mid = np.linspace(0.0, 0.5, int(sr * 0.5), endpoint=False)
    sil = np.zeros(int(sr * 0.5), dtype=np.int16)
    loud = (np.sin(2 * np.pi * 220 * t_mid) * 20000).astype(np.int16)
    samples = np.concatenate([sil, loud, sil])
    with wave.open(str(wav_p), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())

    env = compute_smoothed_rms(wav_p, fps=30, duration_sec=1.5)
    assert len(env) == 45
    assert max(env[:10]) < 0.14  # đoạn im lặng đầu
    assert max(env[16:29]) >= 0.70  # đoạn nói ở giữa

    slot_sil, sx_s, sy_s = compute_mouth_transform(0.08)
    assert slot_sil == "mouth_closed"
    assert (sx_s, sy_s) == (1.0, 1.0)

    slot_loud, sx_l, sy_l = compute_mouth_transform(0.84)
    assert slot_loud == "mouth_open"
    assert sy_l > 1.2
    assert sx_l < 1.0  # Squash & Stretch


def test_eye_controller_blinking_and_happy_skip() -> None:
    ec = EyeController(pose="explain", interaction="hold_prop", beat_id="b001", fps=30)
    assert ec.eye_slot == "eyes_neutral"
    _, sy0, ox, oy = ec.state_at(0)
    _, sy1, _, _ = ec.state_at(1)
    _, sy2, _, _ = ec.state_at(2)
    _, sy3, _, _ = ec.state_at(3)
    assert (sy0, sy1, sy2, sy3) == (0.45, 0.12, 0.50, 1.0)
    assert (ox, oy) == (4.0, -2.0)

    ec_happy = EyeController(pose="happy", beat_id="b002", fps=30)
    assert ec_happy.eye_slot == "eyes_happy"
    assert ec_happy.state_at(1)[1] == 1.0


def test_lerp_pose_state_and_prefix_discovery_and_three_tier_fallback(tmp_path: Path) -> None:
    # Lerp 0.15s mượt
    a = PuppetPoseState(head_angle=-8.0, arm_l_angle=-48.0)
    b = PuppetPoseState(head_angle=0.0, arm_l_angle=8.0)
    mid = lerp_pose_state(a, b, 0.5)
    assert mid.head_angle == -4.0
    assert mid.arm_l_angle == -20.0

    # Phát hiện file tiền tố .jpg trong library/stickman/
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman", prefix_jpg_mode=True)
    paths = find_puppet_slot_paths(lib, assets)
    assert paths["base_character"][0] is not None
    assert is_puppet_ready(lib, assets) is True
    st = get_puppet_status(lib, assets)
    assert st["ready"] is True
    assert st["present_count"] == 7

    # Mức 1: Puppet 2D
    anim1 = StickmanAnimator(
        pose="explain",
        anim_oneshot="shock_jump",
        anim_loop="talk_explain",
        facing="right",
        duration_sec=2.0,
        speech_start=0.0,
        speech_end=1.6,
        fps=30,
        rms_env=[0.5] * 60,
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
    )
    try:
        f1, m1 = anim1.frame_at(5, 0.16)
        assert f1 is not None and m1.phase == "puppet" and not m1.used_fallback
        f1.close()
    finally:
        anim1.close()

    # Mức 3 khi ép static
    _draw_synthetic_a_pose(assets / "stickman" / "explain.png")
    anim3 = StickmanAnimator(
        pose="explain",
        anim_oneshot="shock_jump",
        anim_loop="talk_explain",
        facing="right",
        duration_sec=2.0,
        speech_start=0.0,
        speech_end=1.6,
        fps=30,
        rms_env=[0.5] * 60,
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        animation_mode="static",
    )
    try:
        f3, m3 = anim3.frame_at(5, 0.16)
        assert f3 is not None and m3.used_fallback is True
        f3.close()
    finally:
        anim3.close()


def test_puppet_api_upload_slots_and_preview(tmp_path: Path) -> None:
    settings = Settings(
        workspace_dir=tmp_path / "ws",
        assets_dir=tmp_path / "assets",
        library_dir=tmp_path / "lib",
        whisper_model="small",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings)
    client = TestClient(app)

    r0 = client.get("/api/asset-hub/stickman/puppet")
    assert r0.status_code == 200
    assert r0.json()["ready"] is False
    assert r0.json()["present_count"] == 0

    def _to_bytes(src_path: Path) -> bytes:
        return src_path.read_bytes()

    base_p = _draw_synthetic_a_pose(tmp_path / "raw_base.png")
    eye_p = _draw_eyes(tmp_path / "raw_eye.png")
    mouth_p = _draw_mouth(tmp_path / "raw_mouth.png", open_style=False)

    r_base = client.post(
        "/api/asset-hub/stickman/puppet/base_character",
        files={"file": ("base.png", _to_bytes(base_p), "image/png")},
    )
    assert r_base.status_code == 201
    assert r_base.json()["segmented"] is True

    client.post(
        "/api/asset-hub/stickman/puppet/eyes_neutral",
        files={"file": ("eyes.png", _to_bytes(eye_p), "image/png")},
    )
    r_mouth = client.post(
        "/api/asset-hub/stickman/puppet/mouth_closed",
        files={"file": ("mouth.png", _to_bytes(mouth_p), "image/png")},
    )
    assert r_mouth.status_code == 201
    assert r_mouth.json()["status"]["ready"] is True
    assert r_mouth.json()["status"]["present_count"] == 3

    r_prev = client.get("/api/stickv/puppet/preview?pose=explain&facing=right")
    assert r_prev.status_code == 200
    assert r_prev.headers["content-type"] == "image/png"
    with Image.open(BytesIO(r_prev.content)) as im:
        assert im.mode == "RGBA"
        assert im.height == 480


def test_continuous_cross_beat_pose_tweening_and_3level_mouth(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")

    # Kiểm tra 3 mức khẩu hình: closed -> half_open -> open
    s_closed, _, sy_c = compute_mouth_transform(0.08)
    s_half, _, sy_h = compute_mouth_transform(0.25)
    s_open, _, sy_o = compute_mouth_transform(0.80)
    assert s_closed == "mouth_closed" and sy_c == 1.0
    assert s_half == "mouth_open" and 0.55 <= sy_h <= 0.78
    assert s_open == "mouth_open" and sy_o > 1.0

    # Beat 1 kết thúc ở trạng thái vung tay lớn; Beat 2 nhận prev_pose_state không reset về 0
    prev_state = PuppetPoseState(head_angle=-10.0, arm_l_angle=-42.0, arm_r_angle=38.0)
    rig2 = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        pose="explain",
        anim_loop="talk_explain",
        fps=30,
        rms_env=[0.5] * 30,
        prev_pose_state=prev_state,
        global_t_offset=2.5,
    )
    try:
        f0 = rig2.render_frame(0, 0.0)
        f0.close()
        # Frame đầu tiên của Beat 2 vẫn giữ quán tính gần prev_state (không nhảy về 0 ngay)
        assert rig2.last_pose_state.arm_l_angle < -20.0
        assert rig2.last_pose_state.head_angle < -5.0
    finally:
        rig2.close()


def test_v3_expressive_18_poses_and_10_emotions(tmp_path: Path) -> None:
    from hbt.stickv.puppet import (
        ARM_2SEG_NAMES,
        POSE_PRESETS,
        SEG_CACHE_VERSION,
        VALID_EMOTIONS,
        normalize_stickv_pose,
        resolve_stickv_emotion,
    )

    assert SEG_CACHE_VERSION == "v3_expressive"
    assert len(POSE_PRESETS) == 18
    assert len(VALID_EMOTIONS) == 10
    assert normalize_stickv_pose("explain") == "present_board"
    assert normalize_stickv_pose("wave") == "wave_hello"
    assert normalize_stickv_pose("facepalm") == "facepalm_light"
    assert normalize_stickv_pose("confused") == "scratch_head"
    assert normalize_stickv_pose("nod") == "nod_yes"
    assert normalize_stickv_pose("stop") == "shake_no"
    assert normalize_stickv_pose("point_high") == "point_board_high"
    assert resolve_stickv_emotion("auto", "think_chin", "Tại sao?") == "curious"
    assert resolve_stickv_emotion("idea", "explain", "") == "idea"

    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")
    res = auto_segment_puppet(
        lib / "stickman" / "puppet" / "base_character.png",
        lib / "stickman" / "puppet" / ".segments",
    )
    for seg_name in ARM_2SEG_NAMES:
        p = res["segments"][seg_name]
        assert p.is_file()
        assert SEG_CACHE_VERSION in p.name
    # Kiểm tra vá khớp khuỷu #0B0E14 trên forearm_right
    with Image.open(res["segments"]["forearm_right"]) as fr:
        el_piv = res["rig_config"]["elbow_right_pivot"]
        px = fr.getpixel(
            (
                min(fr.width - 1, int(round(el_piv[0] * fr.width))),
                min(fr.height - 1, int(round(el_piv[1] * fr.height))),
            )
        )
        assert px[3] > 200 and px[0] < 35

    # Render thử đủ 18 hành động bằng xương tay 2 đoạn
    for pose_name in POSE_PRESETS:
        rig = PuppetRig(
            library_dir=lib,
            assets_dir=assets,
            target_height=360,
            pose=pose_name,
            fps=30,
            rms_env=[0.6] * 25,
        )
        try:
            f = rig.render_frame(12, 0.4)
            assert f.mode == "RGBA" and f.height == 360 and f.getbbox() is not None
            f.close()
        finally:
            rig.close()

    # Render thử đủ 10 biểu cảm khuôn mặt & kiểm tra các ký hiệu màu cảm xúc
    expected_colors = {
        "idea": lambda r, g, b, a: a > 200 and r > 220 and g > 180 and b < 60,  # #FACC15
        "sad": lambda r, g, b, a: a > 200 and b > 210 and r < 100 and g > 150,  # #38BDF8
        "shock": lambda r, g, b, a: a > 200 and r > 180 and g < 60 and b < 70,  # #D9232E
        "curious": lambda r, g, b, a: a > 200 and r > 210 and 120 < g < 190 and b < 40,  # #F59E0B
    }
    for emo in VALID_EMOTIONS:
        rig = PuppetRig(
            library_dir=lib,
            assets_dir=assets,
            target_height=420,
            pose="present_board",
            emotion=emo,
            fps=30,
            rms_env=[0.5] * 20,
        )
        try:
            f = rig.render_frame(8, 0.3)
            assert f.mode == "RGBA" and f.height == 420
            if emo in expected_colors:
                arr = np.array(f)
                pred = expected_colors[emo]
                matched = np.any(pred(arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]))
                assert matched, f"Thiếu ký hiệu màu đặc trưng cho emotion={emo}"
            f.close()
        finally:
            rig.close()
