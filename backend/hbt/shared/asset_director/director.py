"""Facade điều phối tổng cho Smart Asset Director (`direct_chat_doc` + `reroll_asset`)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from hbt.shared.asset_director.freshness import FreshnessMemory
from hbt.shared.asset_director.models import (
    AssetCategory,
    BeatCue,
    DirectorConfig,
    DirectorReport,
    PacingPolicy,
    ResolvedAsset,
)
from hbt.shared.asset_director.pacing import PacingGovernor
from hbt.shared.asset_director.resolver import AssetResolver, FetchBudget
from hbt.shared.online_sources.meme_tagging import auto_tag_meme

_VALID_CHAT_STICKERS = {
    "soc",
    "cuoi",
    "khoc",
    "gian",
    "ngai",
    "yeu",
    "nghi",
    "can",
    "bat_luc",
    "ok",
}

_TAG_TO_STICKER: dict[str, str] = {
    "bat_ngo": "soc",
    "hai_huoc": "cuoi",
    "that_vong": "khoc",
    "tuc_gian": "gian",
    "ngai_ngung": "ngai",
    "vo_tay": "ok",
    "ca_khia": "cuoi",
    "drama": "soc",
}


def _infer_sticker_tag(query: str, existing: str | None = None) -> str:
    if existing and existing in _VALID_CHAT_STICKERS:
        return existing
    tags, _ = auto_tag_meme(query or "")
    for t in tags:
        if t in _TAG_TO_STICKER:
            return _TAG_TO_STICKER[t]
    return "soc"


class AssetDirector:
    """Điều phối 3 lớp: Prompt Signals -> PacingGovernor -> Freshness + Local/Online Resolver."""

    def __init__(
        self,
        library_dir: Path,
        workspace_dir: Path,
        *,
        engine: str = "chatting",
        policy: PacingPolicy | None = None,
        config: DirectorConfig | None = None,
    ) -> None:
        self.library_dir = Path(library_dir)
        self.workspace_dir = Path(workspace_dir)
        self.policy = policy or PacingPolicy.for_engine(engine)
        self.config = config or DirectorConfig()
        self.governor = PacingGovernor(self.policy)
        self.memory = FreshnessMemory(
            self.workspace_dir / "asset_usage.json",
            cooldown_videos=self.config.cooldown_videos,
        )
        self.resolver = AssetResolver(
            self.library_dir, self.workspace_dir, self.memory, config=self.config
        )

    def direct_chat_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        auto_fetch_online: bool | None = None,
    ) -> tuple[list[dict[str, Any]], DirectorReport]:
        """Hậu kiểm nhịp + chọn/tải meme & SFX cho danh sách tin nhắn Chatting."""
        allow_online = (
            self.config.auto_fetch_online if auto_fetch_online is None else auto_fetch_online
        )
        est_t = 0.4
        cues: list[BeatCue] = []
        raw_visual_count = 0
        raw_sfx_count = 0

        for idx, m in enumerate(messages):
            text = str(m.get("text") or "")
            meme_q = str(m.get("meme_query") or "").strip() or None
            sticker = str(m.get("sticker") or "").strip() or None
            sfx_q = str(m.get("sfx_query") or "").strip() or None
            raw_int = m.get("intensity")
            if raw_int is None:
                # Tương thích ngược: tin nhắn legacy chỉ có `sticker` (chưa chấm điểm) -> xem như mức 4
                intensity = 4 if (meme_q or sticker or sfx_q) else 2
            else:
                try:
                    intensity = max(1, min(5, int(raw_int)))
                except (TypeError, ValueError):
                    intensity = 2
            beat_role = m.get("beat_role")
            if not beat_role:
                beat_role = "setup" if idx == 0 else ("reaction" if (meme_q or sticker) else "build")

            if meme_q or sticker:
                raw_visual_count += 1
            if sfx_q:
                raw_sfx_count += 1

            cues.append(
                BeatCue(
                    index=idx,
                    text=text,
                    beat_role=str(beat_role),
                    intensity=intensity,
                    meme_query=meme_q,
                    sticker_tag=sticker,
                    sfx_query=sfx_q,
                    est_time_s=round(est_t, 2),
                )
            )
            # Ước lượng thời lượng đọc + pop + nghỉ để kiểm khoảng cách thời gian trước TTS
            est_t += max(1.3, min(5.5, len(text) / 14.0)) + 0.85

        kept_visual = set(self.governor.select_visual_beats(cues))
        kept_sfx = set(self.governor.select_sfx_beats(cues))

        video_seq = self.memory.advance_video_seq() if (kept_visual or kept_sfx) else self.memory.current_video_seq()
        budget = FetchBudget()
        used_visual_ids: set[str] = set()
        used_sfx_ids: set[str] = set()
        fetched_online = 0
        resolved_visual_count = 0
        resolved_sfx_count = 0

        for idx, m in enumerate(messages):
            cue = cues[idx]
            m["beat_role"] = cue.beat_role
            m["intensity"] = cue.intensity

            if idx in kept_visual:
                q = cue.meme_query or cue.sticker_tag or cue.text
                prefer_gm = (cue.beat_role == "punchline") or (cue.intensity >= 5)
                resolved = self.resolver.resolve_visual(
                    q,
                    exclude_ids=used_visual_ids,
                    auto_fetch_online=allow_online,
                    prefer_greenmeme=prefer_gm,
                    budget=budget,
                    video_seq=video_seq,
                )
                if resolved is not None:
                    used_visual_ids.add(resolved.asset_id)
                    used_visual_ids.add(resolved.file)
                    m["meme_id"] = resolved.asset_id
                    m["sticker"] = _infer_sticker_tag(q, cue.sticker_tag)
                    m["meme_query"] = cue.meme_query or cue.sticker_tag
                    m["asset_origin"] = resolved.origin
                    self.memory.record_usage(
                        resolved.category,
                        resolved.asset_id,
                        source=resolved.source,
                        source_id=resolved.source_id,
                        video_seq=video_seq,
                    )
                    resolved_visual_count += 1
                    if resolved.origin == "online_fetched":
                        fetched_online += 1
                else:
                    # Vẫn giữ tag sticker hợp lệ nếu kho hoàn toàn trống & offline
                    m["sticker"] = _infer_sticker_tag(q, cue.sticker_tag)
                    m["meme_id"] = None
                    m["asset_origin"] = None
                    resolved_visual_count += 1
            else:
                m["sticker"] = None
                m["meme_id"] = None
                m["meme_query"] = None
                m["asset_origin"] = None

            if idx in kept_sfx and cue.sfx_query:
                resolved_sfx = self.resolver.resolve_sfx(
                    cue.sfx_query,
                    exclude_ids=used_sfx_ids,
                    auto_fetch_online=allow_online,
                    budget=budget,
                    video_seq=video_seq,
                )
                if resolved_sfx is not None:
                    used_sfx_ids.add(resolved_sfx.asset_id)
                    used_sfx_ids.add(resolved_sfx.file)
                    m["sfx_id"] = resolved_sfx.asset_id
                    m["sfx_query"] = cue.sfx_query
                    if not m.get("asset_origin"):
                        m["asset_origin"] = resolved_sfx.origin
                    self.memory.record_usage(
                        "sfx",
                        resolved_sfx.asset_id,
                        source=resolved_sfx.source,
                        source_id=resolved_sfx.source_id,
                        video_seq=video_seq,
                    )
                    resolved_sfx_count += 1
                    if resolved_sfx.origin == "online_fetched":
                        fetched_online += 1
                else:
                    m["sfx_id"] = None
                    m["sfx_query"] = None
            else:
                m["sfx_id"] = None
                m["sfx_query"] = None

        memes_stripped = max(0, raw_visual_count - resolved_visual_count)
        sfx_stripped = max(0, raw_sfx_count - resolved_sfx_count)
        warnings: list[str] = []
        if memes_stripped > 0:
            warnings.append(
                f"Smart Asset Director đã lược bỏ {memes_stripped} meme/sticker thừa, "
                f"giữ {resolved_visual_count} điểm cao trào."
            )

        report = DirectorReport(
            memes_kept=resolved_visual_count,
            memes_stripped=memes_stripped,
            sfx_kept=resolved_sfx_count,
            sfx_stripped=sfx_stripped,
            fetched_online_count=fetched_online,
            kept_visual_indices=sorted(kept_visual),
            kept_sfx_indices=sorted(kept_sfx),
            warnings=warnings,
        )
        return messages, report

    def direct_chat_doc(
        self,
        doc: Any,
        *,
        auto_fetch_online: bool | None = None,
    ) -> tuple[Any, DirectorReport]:
        """Điều phối trực tiếp trên một đối tượng `ChatDoc` (Pydantic)."""
        raw_msgs = [m.model_dump(by_alias=True) for m in doc.messages]
        directed_msgs, report = self.direct_chat_messages(
            raw_msgs, auto_fetch_online=auto_fetch_online
        )
        msg_cls = type(doc.messages[0]) if doc.messages else None
        if msg_cls is not None:
            doc.messages = [msg_cls.model_validate(m) for m in directed_msgs]
        if report.warnings:
            existing = list(getattr(doc, "warnings", []) or [])
            for w in report.warnings:
                if w not in existing:
                    existing.append(w)
            doc.warnings = existing
        return doc, report

    def reroll_asset(
        self,
        category: AssetCategory | str,
        query: str,
        *,
        exclude_ids: Iterable[str] | None = None,
        auto_fetch_online: bool | None = None,
        prefer_greenmeme: bool = False,
    ) -> ResolvedAsset | None:
        """Đổi nhanh 1 chạm sang tài nguyên khác không trùng `exclude_ids`."""
        excluded = {str(x).strip() for x in (exclude_ids or ()) if str(x).strip()}
        cat = str(category).strip().lower()
        seq = self.memory.current_video_seq()
        budget = FetchBudget()

        if cat in ("meme", "memes", "sticker", "stickers"):
            resolved = self.resolver.resolve_visual(
                query,
                exclude_ids=excluded,
                auto_fetch_online=auto_fetch_online,
                prefer_greenmeme=prefer_greenmeme or (cat in ("meme", "memes")),
                budget=budget,
                video_seq=seq,
            )
        elif cat == "sfx":
            resolved = self.resolver.resolve_sfx(
                query,
                exclude_ids=excluded,
                auto_fetch_online=auto_fetch_online,
                budget=budget,
                video_seq=seq,
            )
        elif cat in ("music", "bgm"):
            resolved = self.resolver.resolve_bgm(
                query,
                exclude_ids=excluded,
                auto_fetch_online=auto_fetch_online,
                budget=budget,
                video_seq=seq,
            )
        else:
            return None

        if resolved is not None:
            self.memory.record_usage(
                resolved.category,
                resolved.asset_id,
                source=resolved.source,
                source_id=resolved.source_id,
                video_seq=seq,
            )
        return resolved


def direct_chat_assets(
    doc: Any,
    library_dir: Path,
    workspace_dir: Path,
    *,
    auto_fetch_online: bool = True,
) -> tuple[Any, DirectorReport]:
    """Hàm tiện ích 1 dòng cho Chatting."""
    director = AssetDirector(library_dir, workspace_dir, engine="chatting")
    return director.direct_chat_doc(doc, auto_fetch_online=auto_fetch_online)
