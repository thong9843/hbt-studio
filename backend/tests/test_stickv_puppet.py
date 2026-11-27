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

    assert SEG_CACHE_VERSION == "v5_a_stance_legs"
    assert len(POSE_PRESETS) == 24
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
        "idea": lambda r, g, b, a: (a > 200) & (r > 220) & (g > 180) & (b < 60),  # #FACC15
        "sad": lambda r, g, b, a: (a > 200) & (b > 210) & (r < 100) & (g > 150),  # #38BDF8
        "shock": lambda r, g, b, a: (a > 200) & (r > 180) & (g < 60) & (b < 70),  # #D9232E
        "curious": lambda r, g, b, a: (
            (a > 200) & (r > 210) & (g > 120) & (g < 190) & (b < 40)
        ),  # #F59E0B
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


def test_gd4_expressive_guiding_poses_joint_lag_weight_shift_and_4level_lipsync(
    tmp_path: Path,
) -> None:
    from hbt.stickv.puppet import (
        POSE_PRESETS,
        VALID_FACE_MOODS,
        evaluate_pose_preset,
        resolve_stickv_emotion,
    )

    # 1. Đủ 6 cử chỉ hướng dẫn mới + 6 face_mood
    new_guiding = (
        "guide_sweep_board",
        "guide_two_sides",
        "guide_step_count",
        "guide_zoom_focus",
        "welcome_open",
        "lean_curious",
    )
    for p in new_guiding:
        assert p in POSE_PRESETS
        st = evaluate_pose_preset(p, 0.45, 0.7)
        assert st.torso_dy == 0.0  # Chân bám chặt mặt đất
        assert abs(st.torso_dx) <= 7.0
        assert abs(st.torso_angle) <= 3.51

    assert len(VALID_FACE_MOODS) == 6
    assert resolve_stickv_emotion("auto", "present_board", "", face_mood="warm_cta") == "happy"
    assert resolve_stickv_emotion("auto", "present_board", "", face_mood="shocked") == "shock"

    # 2. Lip-Sync 4 mức: closed (<0.12) -> narrow (0.12-0.32) -> medium (0.32-0.60) -> wide (>0.60)
    s0, _, y0 = compute_mouth_transform(0.05)
    s1, _, y1 = compute_mouth_transform(0.20)
    s2, _, y2 = compute_mouth_transform(0.46)
    s3, x3, y3 = compute_mouth_transform(0.82)
    assert s0 == "mouth_closed" and y0 == 1.0
    assert s1 == "mouth_open" and 0.50 <= y1 <= 0.68
    assert s2 == "mouth_open" and 0.72 <= y2 <= 0.98
    assert s3 == "mouth_open" and y3 > 1.05 and x3 < 1.0

    # 3. Prosody Micro-Brows (env > 0.65), Gaze Target (+5px -> 0px cuối câu) & chớp mắt 2.4-4.2s
    ec = EyeController(pose="guide_sweep_board", face_mood="explaining", beat_id="b007", fps=30)
    assert all(2.4 <= iv <= 4.2 for iv in ec.blink_intervals_s)
    assert len(set(ec.blink_intervals_s[:6])) > 1  # Không lặp đều máy móc
    _, sy_norm, ox_mid, oy_norm = ec.state_at(10, env_val=0.3, progress=0.4)
    _, sy_peak, _, oy_peak = ec.state_at(10, env_val=0.82, progress=0.4)
    _, _, ox_end, _ = ec.state_at(10, env_val=0.3, progress=0.98)
    assert ox_mid == 5.0
    assert ox_end == 0.0
    assert sy_peak > sy_norm
    assert oy_peak < oy_norm  # Nhướng lên trên (oy giảm 2.5px)

    # 4. Joint lag phân tầng: Torso dẫn -> Shoulder trễ (+2f) -> Elbow trễ (+4f)
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")
    rig = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        pose="guide_sweep_board",
        face_mood="explaining",
        fps=30,
        rms_env=[0.7] * 30,
        prev_pose_state=PuppetPoseState(),
    )
    try:
        states = []
        for idx in range(12):
            f = rig.render_frame(idx, idx / 30.0)
            states.append(rig.last_pose_state)
            f.close()
        # Ở các frame đầu, torso phản ứng nhanh hơn trong khi khuỷu tay trễ 4 frame rồi mới vung
        assert abs(states[1].torso_angle) > 0.0
        assert abs(states[8].elbow_r_angle) > abs(states[2].elbow_r_angle)
    finally:
        rig.close()


def test_stickv_60fps_matches_30fps_realtime_motion_and_blink(tmp_path: Path) -> None:
    """Chuyển động 60fps phải khớp tốc độ thời gian thực 30fps (không chạy nhanh gấp đôi)."""
    ec30 = EyeController(pose="present_board", beat_id="b010", fps=30)
    ec60 = EyeController(pose="present_board", beat_id="b010", fps=60)
    assert [ec30.state_at(i)[1] for i in range(4)] == [0.45, 0.12, 0.50, 1.0]
    assert [ec60.state_at(i)[1] for i in range(7)] == [0.45, 0.45, 0.12, 0.12, 0.50, 0.50, 1.0]

    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")
    rig30 = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        pose="guide_sweep_board",
        fps=30,
        rms_env=[0.7] * 30,
        prev_pose_state=PuppetPoseState(),
    )
    rig60 = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        pose="guide_sweep_board",
        fps=60,
        rms_env=[0.7] * 60,
        prev_pose_state=PuppetPoseState(),
    )
    try:
        for i in range(16):  # t = 0.00s .. 0.50s
            rig30._pose_state_at(i / 30.0, 0.7)
        for i in range(31):  # t = 0.00s .. 0.50s
            rig60._pose_state_at(i / 60.0, 0.7)
        st30 = rig30.last_pose_state
        st60 = rig60.last_pose_state
        assert abs(st60.torso_angle - st30.torso_angle) < 1.5
        assert abs(st60.torso_dx - st30.torso_dx) < 1.5
        assert abs(st60.arm_r_angle - st30.arm_r_angle) < 4.5
        assert abs(st60.elbow_r_angle - st30.elbow_r_angle) < 4.5
        assert abs(st60.head_angle - st30.head_angle) < 1.5
    finally:
        rig30.close()
        rig60.close()


def test_v5_a_stance_legs_and_arm_ik_choreography(tmp_path: Path) -> None:
    """Giữ nguyên 2 chân chữ A gốc trong body_torso (v5_a_stance_legs), 2 tay IK + 4 hand_shape."""
    import math

    from hbt.stickv.puppet import (
        ALL_SEGMENT_NAMES,
        SEG_CACHE_VERSION,
        VALID_HAND_SHAPES,
        clamp_arm_target,
        clean_puppet_sprite,
        detect_rms_peaks,
        resolve_hand_shape,
        solve_2bone_ik,
    )

    assert SEG_CACHE_VERSION == "v5_a_stance_legs"
    assert "shoe_left" not in ALL_SEGMENT_NAMES
    assert "shoe_right" not in ALL_SEGMENT_NAMES

    # 1. solve_2bone_ik cho 2 cánh tay bảo toàn độ dài L1, L2 và kẹp tầm với [0.25, 0.98]*(L1+L2)
    root = (100.0, 100.0)
    l1, l2 = 60.0, 55.0
    elbow, wrist = solve_2bone_ik(root, (170.0, 150.0), l1, l2, bend_dir=1)
    assert abs(math.hypot(elbow[0] - root[0], elbow[1] - root[1]) - l1) < 0.5
    assert abs(math.hypot(wrist[0] - elbow[0], wrist[1] - elbow[1]) - l2) < 0.5

    _, wrist_far = solve_2bone_ik(root, (900.0, 900.0), l1, l2, bend_dir=1)
    assert math.hypot(wrist_far[0] - root[0], wrist_far[1] - root[1]) <= 0.98 * (l1 + l2) + 0.5

    # 2. Khóa Silhouette Lock: cấm CẢ 2 tay vắt chéo qua trục cà vạt đỏ (kể cả arms_crossed)
    clamped_l = clamp_arm_target(
        "left", (80.0, 100.0), (220.0, 130.0), 100.0, 60.0, l1, l2, pose="present_board"
    )
    assert clamped_l[0] <= 100.0 - 60.0 * 0.14 + 0.5
    crossed_l = clamp_arm_target(
        "left", (80.0, 100.0), (145.0, 130.0), 100.0, 60.0, l1, l2, pose="arms_crossed"
    )
    assert crossed_l[0] <= 100.0 - 60.0 * 0.14 + 0.5
    clamped_r = clamp_arm_target(
        "right", (120.0, 100.0), (40.0, 130.0), 100.0, 60.0, l1, l2, pose="think_chin"
    )
    assert clamped_r[0] >= 100.0 + 60.0 * 0.14 - 0.5

    # 3. Đủ 4 dáng găng tay bo tròn liền khối (thay thế count_fingers bằng thumb_up)
    assert set(VALID_HAND_SHAPES) == {"open_palm", "point_index", "fist_punch", "thumb_up"}
    assert resolve_hand_shape("point_up", "right") == "point_index"
    assert resolve_hand_shape("emphatic_chop", "right") == "fist_punch"
    assert resolve_hand_shape("count_points", "right") == "thumb_up"
    assert resolve_hand_shape("present_board", "left") == "open_palm"
    assert resolve_hand_shape("welcome_open", "right", board_type="recap_card") == "thumb_up"

    # 4. body_torso giữ nguyên chiều dài 2 chân chữ A xuống tận đáy ảnh gốc (không cắt ngang hông)
    fps = 30
    env = [0.25] * (4 * fps)
    env[30] = 0.85
    env[65] = 0.90
    peaks = detect_rms_peaks(env, fps)
    assert len(peaks) >= 2

    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")
    base_img_p = lib / "stickman" / "puppet" / "base_character.png"
    seg_res = auto_segment_puppet(base_img_p, tmp_path / ".seg_check")
    assert seg_res["rig_config"].get("torso_full_legs") is True
    with Image.open(base_img_p) as raw_b:
        cleaned_b = clean_puppet_sprite(raw_b, padding=4)
        cleaned_h = cleaned_b.height
        cleaned_b.close()
    with Image.open(seg_res["segments"]["body_torso"]) as bt_im:
        assert bt_im.height >= int(cleaned_h * 0.58)

    rig = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        pose="point_up",
        board_type="bullets",
        duration_sec=4.0,
        fps=fps,
        rms_env=env,
    )
    try:
        f_p1 = rig.render_frame(8, 8 / fps)
        f_p2a = rig.render_frame(32, 32 / fps)
        f_p2b = rig.render_frame(80, 80 / fps)
        f_p3 = rig.render_frame(112, 112 / fps)
        assert not np.array_equal(np.array(f_p1), np.array(f_p2a))
        assert not np.array_equal(np.array(f_p2a), np.array(f_p2b))
        assert not np.array_equal(np.array(f_p2b), np.array(f_p3))
        for im in (f_p1, f_p2a, f_p2b, f_p3):
            im.close()
    finally:
        rig.close()


def test_smooth_60fps_wrist_kinematics_across_beat_boundaries(tmp_path: Path) -> None:
    """INV-09: Lò xo giảm chấn tới hạn xuyên beat (kể cả đổi facing), 0 nhảy cổ tay > 10px/f."""
    import math

    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")
    fps = 60
    beats_spec = [
        ("b001", "point_up", "right", "pinned_photo", 2.0),
        ("b002", "shock_hands_up", "left", "myth_vs_fact", 2.0),
        ("b003", "welcome_open", "right", "recap_card", 2.0),
    ]
    prev_state: PuppetPoseState | None = None
    global_t = 0.0
    traj_l: list[tuple[float, float]] = []
    traj_r: list[tuple[float, float]] = []

    for bid, pose, facing, btype, dur in beats_spec:
        n_frames = int(dur * fps)
        # Sóng RMS 4.5Hz dày đặc để xác nhận kênh tay đã tách khỏi RMS nhanh
        env = [0.5 + 0.48 * math.sin(2.0 * math.pi * 4.5 * (i / fps)) for i in range(n_frames)]
        rig = PuppetRig(
            library_dir=lib,
            assets_dir=assets,
            target_height=420,
            pose=pose,
            facing=facing,
            beat_id=bid,
            fps=fps,
            duration_sec=dur,
            speech_end=dur - 0.25,
            rms_env=env,
            prev_pose_state=prev_state,
            global_t_offset=global_t,
            board_type=btype,
        )
        try:
            for fi in range(n_frames):
                fr = rig.render_frame(fi, fi / float(fps))
                fr.close()
                traj_l.append(rig.last_wrists[0])
                traj_r.append(rig.last_wrists[1])
            prev_state = rig.last_pose_state
        finally:
            rig.close()
        global_t += dur

    steps = [
        math.hypot(t[i][0] - t[i - 1][0], t[i][1] - t[i - 1][1])
        for t in (traj_l, traj_r)
        for i in range(1, len(t))
    ]
    assert max(steps) <= 10.0
    assert float(np.percentile(steps, 95)) <= 3.5


def test_arms_and_gloves_render_in_front_of_torso_and_behind_head(tmp_path: Path) -> None:
    """INV-06: Cả 2 cánh tay & găng tay nằm TRƯỚC body_torso, và head nằm TRÊN CÙNG."""
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")

    rig = PuppetRig(
        library_dir=lib,
        assets_dir=assets,
        target_height=360,
        pose="arms_crossed",
        facing="right",
        duration_sec=1.0,
        fps=60,
        rms_env=[0.3] * 60,
    )
    try:
        t_size = rig.parts["body_torso"].size
        h_size = rig.parts["head_blank"].size
        rig.parts["body_torso"].close()
        rig.parts["head_blank"].close()
        rig.parts["body_torso"] = Image.new("RGBA", t_size, (220, 40, 120, 255))
        rig.parts["head_blank"] = Image.new("RGBA", h_size, (30, 110, 240, 255))
        if rig._torso_2x is not None:
            rig._torso_2x.close()
            rig._torso_2x = None
        rig._torso_rot_cache.clear()

        fr = rig.render_frame(0, 0.0)
        try:
            arr = np.asarray(fr)
            cw, ch = rig.canvas_size
            ground_y = float(ch - 8)
            t_w, t_h = t_size
            foot_x = cw * 0.5
            sx_l = int(
                round(foot_x - t_w * 0.5 + float(rig.rig_cfg["shoulder_left_torso"][0]) * t_w)
            )
            sy_l = int(round(ground_y - t_h + float(rig.rig_cfg["shoulder_left_torso"][1]) * t_h))
            sx_r = int(
                round(foot_x - t_w * 0.5 + float(rig.rig_cfg["shoulder_right_torso"][0]) * t_w)
            )
            sy_r = int(round(ground_y - t_h + float(rig.rig_cfg["shoulder_right_torso"][1]) * t_h))
            # Cả khớp vai/tay trái lẫn phải phải đè lên thân áo hồng cánh sen (220, 40, 120)
            for sx, sy in ((sx_l, sy_l), (sx_r, sy_r)):
                patch = arr[max(0, sy - 2) : sy + 3, max(0, sx - 2) : sx + 3]
                assert np.any((patch[..., 0] < 60) & (patch[..., 1] < 60) & (patch[..., 2] < 60))
        finally:
            fr.close()

        # Hạ nhẹ cổ để head chồng trực tiếp lên vùng khớp vai/tay -> đầu vẫn phải đè lên tay
        rig.rig_cfg["neck_anchor_torso"] = [0.50, 0.24]
        fr_head = rig.render_frame(0, 0.0)
        try:
            arr_h = np.asarray(fr_head)
            sh_mid_y = int(
                round(ground_y - t_h + float(rig.rig_cfg["shoulder_left_torso"][1]) * t_h)
            )
            patch_l = arr_h[max(0, sh_mid_y - 2) : sh_mid_y + 3, max(0, sx_l - 2) : sx_l + 3]
            patch_r = arr_h[max(0, sh_mid_y - 2) : sh_mid_y + 3, max(0, sx_r - 2) : sx_r + 3]
            assert np.any((patch_l[..., 2] > 180) & (patch_l[..., 0] < 80))
            assert np.any((patch_r[..., 2] > 180) & (patch_r[..., 0] < 80))
        finally:
            fr_head.close()
    finally:
        rig.close()


def test_outward_elbows_and_clear_red_tie_across_six_poses(tmp_path: Path) -> None:
    """Packet A1.1: Khuỷu tay luôn hướng ra ngoài và 6 tư thế không cắt chéo qua cà vạt đỏ."""
    from hbt.stickv.puppet import solve_arm_ik_natural

    # 1. Kiểm tra bất biến khuỷu hướng ngoài trực tiếp qua các vùng mục tiêu (hông, ngực, trên cao)
    sh_l_t = (100.0, 120.0)
    sh_r_t = (160.0, 120.0)
    for tgt_l, tgt_r in (
        ((95.0, 210.0), (165.0, 210.0)),  # tay đặt cạnh hông
        ((105.0, 140.0), (155.0, 140.0)),  # gần thân
        ((60.0, 50.0), (220.0, 50.0)),  # giơ cao chỉ bảng
    ):
        el_l, _ = solve_arm_ik_natural("left", sh_l_t, tgt_l, 52.0, 48.0)
        el_r, _ = solve_arm_ik_natural("right", sh_r_t, tgt_r, 52.0, 48.0)
        assert el_l[0] < sh_l_t[0]
        assert el_r[0] > sh_r_t[0]

    # 2. Render 6 tư thế chính với PuppetRig: khuỷu ngoài + 0 pixel tay tối cắt ngang tie_bbox
    lib = tmp_path / "lib"
    assets = tmp_path / "assets"
    _make_full_puppet_dir(lib / "stickman" / "puppet")
    six_poses = (
        "arms_crossed",
        "hands_on_hips",
        "think_chin",
        "lean_secret",
        "point_up",
        "present_board",
    )

    for pose_name in six_poses:
        rig = PuppetRig(
            library_dir=lib,
            assets_dir=assets,
            target_height=360,
            pose=pose_name,
            facing="right",
            duration_sec=1.0,
            fps=60,
            rms_env=[0.25] * 60,
        )
        try:
            t_size = rig.parts["body_torso"].size
            rig.parts["body_torso"].close()
            torso_img = Image.new("RGBA", t_size, (245, 245, 245, 255))
            td = ImageDraw.Draw(torso_img)
            cx = t_size[0] // 2
            tie_top = int(round(t_size[1] * 0.08))
            tie_bot = int(round(t_size[1] * 0.36))
            td.rectangle((cx - 4, tie_top, cx + 4, tie_bot), fill=(217, 35, 46, 255))
            rig.parts["body_torso"] = torso_img
            if rig._torso_2x is not None:
                rig._torso_2x.close()
                rig._torso_2x = None
            rig._torso_rot_cache.clear()

            # Chờ lò xo ổn định ở 60fps rồi lấy frame cuối cùng
            last_fr = None
            for fi in range(60):
                if last_fr is not None:
                    last_fr.close()
                last_fr = rig.render_frame(fi, fi / 60.0)

            assert rig._elbow_springs is not None
            cw, ch = rig.canvas_size
            ground_y = float(ch - 8)
            t_w, t_h = t_size
            foot_x = cw * 0.5
            sh_l_x = foot_x - t_w * 0.5 + float(rig.rig_cfg["shoulder_left_torso"][0]) * t_w
            sh_r_x = foot_x - t_w * 0.5 + float(rig.rig_cfg["shoulder_right_torso"][0]) * t_w
            assert rig._elbow_springs["el_lx"].pos < sh_l_x, pose_name
            assert rig._elbow_springs["el_rx"].pos > sh_r_x, pose_name

            assert last_fr is not None
            try:
                arr = np.asarray(last_fr)
                y0 = max(0, int(round(ground_y - t_h + tie_top + 4)))
                y1 = min(ch, int(round(ground_y - t_h + tie_bot - 4)))
                x0 = max(0, int(round(foot_x - 18)))
                x1 = min(cw, int(round(foot_x + 19)))
                strip = arr[y0:y1, x0:x1]
                red_mask = (
                    (strip[..., 0] > 180)
                    & (strip[..., 1] < 70)
                    & (strip[..., 2] < 70)
                    & (strip[..., 3] > 200)
                )
                ys, xs = np.where(red_mask)
                assert len(xs) >= 40, f"{pose_name}: red tie missing or occluded"
                tie_bbox = arr[
                    y0 + int(ys.min()) : y0 + int(ys.max()) + 1,
                    x0 + int(xs.min()) : x0 + int(xs.max()) + 1,
                ]
                dark_on_tie = (
                    (tie_bbox[..., 0] < 60)
                    & (tie_bbox[..., 1] < 60)
                    & (tie_bbox[..., 2] < 60)
                    & (tie_bbox[..., 3] > 120)
                )
                assert int(np.sum(dark_on_tie)) == 0, (
                    f"{pose_name}: dark arm pixels crossed red tie"
                )
            finally:
                last_fr.close()
        finally:
            rig.close()
