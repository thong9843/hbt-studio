"""Kiểm thử Smart Asset Director: PacingGovernor & FreshnessMemory."""

from __future__ import annotations

from pathlib import Path

from hbt.shared.asset_director import (
    BeatCue,
    FreshnessMemory,
    PacingGovernor,
    PacingPolicy,
)


def test_pacing_governor_strips_15_msg_spam_and_keeps_climax() -> None:
    """15 tin nhắn bị LLM nhồi meme cả 15 -> siết còn <= 2 tin, cách >= 4 tin, bỏ setup đầu."""
    cues = [
        BeatCue(
            index=i,
            text=f"Tin nhắn {i}",
            beat_role="setup" if i == 0 else ("punchline" if i in (6, 13) else "build"),
            intensity=5 if i in (6, 13) else 4,
            meme_query=f"reaction {i}",
            est_time_s=i * 3.0,
        )
        for i in range(15)
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    kept = gov.select_visual_beats(cues)

    # floor(15 * 0.18) = 2
    assert 1 <= len(kept) <= 2
    assert 0 not in kept
    assert 6 in kept and 13 in kept
    for a, b in zip(kept, kept[1:], strict=False):
        assert b - a >= 4
        assert cues[b].est_time_s - cues[a].est_time_s >= 8.0


def test_pacing_governor_enforces_time_gap_and_no_consecutive() -> None:
    """Dù intensity=5 liên tiếp, không bao giờ chọn 2 tin sát nhau hoặc cách < 8.0s."""
    cues = [
        BeatCue(
            index=i,
            beat_role="punchline" if i > 0 else "setup",
            intensity=5,
            meme_query="cat shocked",
            est_time_s=i * 1.5,  # 15 tin * 1.5s = 22.5s
        )
        for i in range(18)
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    kept = gov.select_visual_beats(cues)

    assert 1 <= len(kept) <= 3
    assert 0 not in kept
    for a, b in zip(kept, kept[1:], strict=False):
        assert b - a >= 4
        assert cues[b].est_time_s - cues[a].est_time_s >= 8.0


def test_pacing_governor_fallback_to_single_intensity_3_punchline() -> None:
    """Khi không có tin nào intensity >= 4, hạ 1 bậc giữ đúng 1 punchline/twist intensity == 3."""
    cues = [
        BeatCue(index=0, beat_role="setup", intensity=3, meme_query="hi", est_time_s=0.0),
        BeatCue(index=3, beat_role="build", intensity=3, meme_query="ok", est_time_s=9.0),
        BeatCue(index=8, beat_role="twist", intensity=3, meme_query="side eye", est_time_s=24.0),
        BeatCue(
            index=11, beat_role="punchline", intensity=3, meme_query="facepalm", est_time_s=33.0
        ),
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    assert gov.select_visual_beats(cues) == [11]


def test_pacing_governor_sfx_and_duration_clamps() -> None:
    cues = [
        BeatCue(
            index=i,
            beat_role="twist" if i > 0 else "setup",
            intensity=4,
            sfx_query="vine boom",
            est_time_s=i * 2.5,
        )
        for i in range(12)
    ]
    gov = PacingGovernor(PacingPolicy.for_engine("chatting"))
    sfx_kept = gov.select_sfx_beats(cues)
    assert 1 <= len(sfx_kept) <= 4
    assert 0 not in sfx_kept
    for a, b in zip(sfx_kept, sfx_kept[1:], strict=False):
        assert cues[b].est_time_s - cues[a].est_time_s >= 6.5

    assert gov.clamp_video_meme_duration(0.4) == 1.2
    assert gov.clamp_video_meme_duration(9.5) == 3.8
    assert gov.clamp_video_meme_duration(2.4) == 2.4
    assert gov.static_sticker_duration(4) == 1.1
    assert gov.static_sticker_duration(5) == 1.5


def test_freshness_memory_cooldown_and_recovery(tmp_path: Path) -> None:
    """Tài nguyên dùng ở video N bị phạt trong 6 video tiếp theo và hồi về 0 từ video N+6."""
    mem = FreshnessMemory(tmp_path / "asset_usage.json", cooldown_videos=6)
    seq_n = mem.advance_video_seq()  # seq = 1
    assert seq_n == 1
    mem.record_usage("memes", "shocked-cat", source="giphy", source_id="g1", video_seq=seq_n)

    # Ngay ở video N (age=0): penalty = 0.65
    assert mem.is_in_cooldown("memes", "shocked-cat", video_seq=seq_n) is True
    assert mem.cooldown_penalty("memes", "shocked-cat", video_seq=seq_n) == 0.65
    assert mem.use_decay("memes", "shocked-cat") == 0.03

    # Video N+3 (age=3): penalty giảm một nửa
    p_mid = mem.cooldown_penalty("memes", "shocked-cat", video_seq=seq_n + 3)
    assert 0.30 < p_mid < 0.35

    # Video N+5 (age=5): vẫn trong cooldown
    assert mem.is_in_cooldown("memes", "shocked-cat", video_seq=seq_n + 5) is True

    # Video N+6 (age=6): hết cooldown, penalty == 0.0
    assert mem.is_in_cooldown("memes", "shocked-cat", video_seq=seq_n + 6) is False
    assert mem.cooldown_penalty("memes", "shocked-cat", video_seq=seq_n + 6) == 0.0


def _seed_local_library(lib: Path) -> None:
    import json

    memes_dir = lib / "memes"
    memes_dir.mkdir(parents=True, exist_ok=True)
    (memes_dir / "cat-shocked.mp4").write_bytes(b"fake-mp4-1")
    (memes_dir / "side-eye.mp4").write_bytes(b"fake-mp4-2")
    (memes_dir / "index.json").write_text(
        json.dumps(
            [
                {
                    "id": "cat-shocked",
                    "file": "cat-shocked.mp4",
                    "title": "Cat Shocked",
                    "tags": ["bat_ngo", "shock", "cat"],
                    "source": "local",
                },
                {
                    "id": "side-eye",
                    "file": "side-eye.mp4",
                    "title": "Side Eye Smug",
                    "tags": ["ca_khia", "side_eye", "smug"],
                    "source": "local",
                },
            ]
        ),
        encoding="utf-8",
    )

    sfx_dir = lib / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    (sfx_dir / "vine-boom.mp3").write_bytes(b"fake-mp3-1")
    (sfx_dir / "index.json").write_text(
        json.dumps(
            [
                {
                    "id": "vine-boom",
                    "file": "vine-boom.mp3",
                    "title": "Vine Boom",
                    "tags": ["vine", "boom", "dramatic"],
                    "source": "local",
                }
            ]
        ),
        encoding="utf-8",
    )


def test_resolver_prefers_local_when_fresh_and_matching(tmp_path: Path, monkeypatch) -> None:
    """Ưu tiên file local khi khớp tốt (>= 0.55) và không bị cooldown, không gọi mạng."""
    from hbt.shared.asset_director import (
        AssetResolver,
        DirectorConfig,
        FreshnessMemory,
        clear_search_cache,
    )

    clear_search_cache()
    lib = tmp_path / "library"
    ws = tmp_path / "workspace"
    _seed_local_library(lib)

    called_online = False

    async def _fail_if_called(*_a, **_kw):
        nonlocal called_online
        called_online = True
        return []

    monkeypatch.setattr("hbt.shared.asset_director.resolver.search_giphy_stickers", _fail_if_called)
    monkeypatch.setattr("hbt.shared.asset_director.resolver.search_greenmeme", _fail_if_called)

    mem = FreshnessMemory(ws / "asset_usage.json", cooldown_videos=6)
    res = AssetResolver(lib, ws, mem, config=DirectorConfig(auto_fetch_online=True))
    asset = res.resolve_visual("cat shocked", video_seq=1)

    assert asset is not None
    assert asset.asset_id == "cat-shocked"
    assert asset.origin == "local"
    assert called_online is False


def test_resolver_auto_fetches_online_when_local_in_cooldown_or_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """Khi kho thiếu hoặc bị cooldown, tự tải online (mock Giphy & Tuna), tôn trọng trần tải."""
    import json

    from hbt.shared.asset_director import (
        AssetDirector,
        AssetResolver,
        DirectorConfig,
        FetchBudget,
        FreshnessMemory,
        clear_search_cache,
    )

    clear_search_cache()
    lib = tmp_path / "library"
    ws = tmp_path / "workspace"
    _seed_local_library(lib)

    mem = FreshnessMemory(ws / "asset_usage.json", cooldown_videos=6)
    mem.record_usage("memes", "cat-shocked", video_seq=1)

    monkeypatch.setattr(
        "hbt.shared.asset_director.resolver.resolve_online_api_key",
        lambda name, _ws=None: (
            "test-key" if name in ("GIPHY_API_KEY", "VOICEMOD_TUNA_API_KEY") else ""
        ),
    )

    async def _mock_search_giphy(_q, **_kw):
        return [
            {
                "id": "g999",
                "title": "Mind Blown Cat",
                "download_url": "https://media.giphy.com/g999.webp",
            }
        ]

    async def _mock_import_giphy(*, sticker_id, title, download_url, library_dir, **_kw):
        stk_dir = Path(library_dir) / "stickers"
        stk_dir.mkdir(parents=True, exist_ok=True)
        fname = f"giphy-{sticker_id}.webp"
        out = stk_dir / fname
        out.write_bytes(b"webp-bytes")
        rec = {
            "id": f"giphy-{sticker_id}",
            "file": fname,
            "title": title,
            "tag": "soc",
            "source": "giphy",
        }
        (stk_dir / "index.json").write_text(json.dumps([rec]), encoding="utf-8")
        return {"ok": True, "item": rec, "path": str(out)}

    async def _mock_search_tuna(_q, **_kw):
        return [
            {
                "id": "t777",
                "title": "Bonk SFX",
                "preview_url": "https://tuna/bonk.mp3",
                "tags": ["bonk"],
            }
        ]

    async def _mock_import_tuna(*, item_id, title, preview_url, tags, library_dir, **_kw):
        sfx_dir = Path(library_dir) / "sfx"
        sfx_dir.mkdir(parents=True, exist_ok=True)
        fname = f"tuna-bonk-{item_id}.mp3"
        out = sfx_dir / fname
        out.write_bytes(b"mp3-bytes")
        rec = {
            "id": f"tuna-{item_id}",
            "file": fname,
            "title": title,
            "tags": tags or ["bonk"],
            "source": "tuna",
        }
        (sfx_dir / "index.json").write_text(json.dumps([rec]), encoding="utf-8")
        return {"ok": True, "item": rec, "file_path": str(out)}

    monkeypatch.setattr(
        "hbt.shared.asset_director.resolver.search_giphy_stickers", _mock_search_giphy
    )
    monkeypatch.setattr(
        "hbt.shared.asset_director.resolver.import_giphy_sticker", _mock_import_giphy
    )
    monkeypatch.setattr("hbt.shared.asset_director.resolver.search_tuna_sfx", _mock_search_tuna)
    monkeypatch.setattr("hbt.shared.asset_director.resolver.import_tuna_sfx", _mock_import_tuna)

    resolver = AssetResolver(lib, ws, mem, config=DirectorConfig(auto_fetch_online=True))
    budget = FetchBudget()

    # cat-shocked đang cooldown -> tự tải từ Giphy
    vis = resolver.resolve_visual("cat shocked", budget=budget, video_seq=2)
    assert vis is not None
    assert vis.origin == "online_fetched"
    assert vis.source == "giphy"
    assert vis.source_id == "g999"
    assert budget.visual == 1

    # Kiểm tra source_id đã được lưu vào stickers/index.json
    stk_idx = json.loads((lib / "stickers" / "index.json").read_text(encoding="utf-8"))
    assert stk_idx[0]["source_id"] == "g999"

    # SFX chưa có "bonk" -> tự tải từ Tuna
    sfx = resolver.resolve_sfx("bonk", budget=budget, video_seq=2)
    assert sfx is not None
    assert sfx.origin == "online_fetched"
    assert sfx.source == "tuna"
    assert budget.sfx == 1

    # Reroll loại trừ tài nguyên hiện tại
    director = AssetDirector(lib, ws)
    rerolled = director.reroll_asset(
        "sticker", "side eye", exclude_ids={"cat-shocked", "giphy-g999"}, auto_fetch_online=False
    )
    assert rerolled is not None
    assert rerolled.asset_id == "side-eye"


def test_resolver_falls_back_gracefully_on_network_timeout(tmp_path: Path, monkeypatch) -> None:
    """Khi API timeout / lỗi mạng, rơi êm về kho local, tuyệt đối không raise."""
    import httpx

    from hbt.shared.asset_director import (
        AssetResolver,
        DirectorConfig,
        FreshnessMemory,
        clear_search_cache,
    )

    clear_search_cache()
    lib = tmp_path / "library"
    ws = tmp_path / "workspace"
    _seed_local_library(lib)

    monkeypatch.setattr(
        "hbt.shared.asset_director.resolver.resolve_online_api_key", lambda *_a, **_kw: "k"
    )

    async def _timeout(*_a, **_kw):
        raise httpx.TimeoutException("timeout 4.5s")

    monkeypatch.setattr("hbt.shared.asset_director.resolver.search_giphy_stickers", _timeout)
    monkeypatch.setattr("hbt.shared.asset_director.resolver.search_greenmeme", _timeout)

    mem = FreshnessMemory(ws / "asset_usage.json")
    resolver = AssetResolver(lib, ws, mem, config=DirectorConfig(auto_fetch_online=True))
    asset = resolver.resolve_visual("something completely new", video_seq=1)
    assert asset is not None
    assert asset.origin == "local"
