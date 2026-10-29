"""Thẻ theo đoạn và hiệu ứng thẻ khi dựng (IMPLEMENT-POSTV.md mục 6, D20, D21).

Thẻ không vẽ từng khung: mỗi thẻ là một chuỗi vài PNG nhỏ (đã cắt sát) trong file `ffconcat`; số
like, bình luận, đăng lại, chia sẻ chạy từ 0 nên có vài chục trạng thái ở ~1 s đầu. Hiện dần, trượt,
nảy và mờ ra làm bằng filter của ffmpeg (`fade`, `scale`, `overlay`) trong **một** lệnh. Mọi thời
gian, cỡ nằm ở khối `anim` của `templates/story_cards.json` (N7).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hbt.pipeline import cache
from hbt.postv import card as _card
from hbt.postv.card import render_project_card
from hbt.postv.censor import CensorMatcher
from hbt.postv.models import PostvProject, PostvSegment

# Đổi mã thẻ hoặc hiệu ứng thì tạo lại ảnh thẻ (nhưng không động tới nền).
CARD_CODE = cache.code_digest(_card, sys.modules[__name__])
DEFAULT_CARD = {"hook": "hook", "post": "post", "comment": "comment", "commentary": "none"}
ADJACENT = 1e-6


@dataclass(frozen=True)
class CardSpan:
    kind: str  # "hook" | "post" | "comment"
    ref: str | None
    start: float
    end: float  # lúc thẻ kế tiếp (hoặc hết video) bắt đầu; chưa tính phần mờ ra
    fresh: bool = True  # true: thẻ hiện ra từ khung trống; false: hoà từ thẻ liền trước
    handoff: bool = False  # true: thẻ liền sau tiếp nối (thẻ này mờ ra cùng lúc)


def card_of(seg: PostvSegment) -> tuple[str, str | None]:
    """(loại thẻ, ref) của một đoạn: `card` đặt tay, không thì theo `role`."""
    kind = seg.card or DEFAULT_CARD[seg.role]
    return kind, (seg.ref if kind == "comment" else None)


def plan_cards(
    items: Sequence[tuple[str, str | None]], starts: Sequence[float], total: float
) -> list[CardSpan]:
    """Gộp các đoạn liền nhau có cùng thẻ; thẻ giữ tới đoạn có thẻ khác hoặc `none`."""
    runs: list[list] = []  # [kind, ref, start, end]
    for i, (kind, ref) in enumerate(items):
        end = starts[i + 1] if i + 1 < len(items) else total
        if kind == "none":
            continue
        if runs and runs[-1][:2] == [kind, ref] and abs(runs[-1][3] - starts[i]) < ADJACENT:
            runs[-1][3] = end
        else:
            runs.append([kind, ref, starts[i], end])
    spans = []
    for k, (kind, ref, start, end) in enumerate(runs):
        fresh = k == 0 or abs(runs[k - 1][3] - start) >= ADJACENT
        handoff = k + 1 < len(runs) and abs(runs[k + 1][2] - end) < ADJACENT
        spans.append(CardSpan(kind, ref, start, end, fresh, handoff))
    return spans


def segment_starts(offsets: Sequence[float], n: int, x: float) -> list[float]:
    """Lúc đổi thẻ của từng đoạn: giữa khoảng nghỉ giữa hai đoạn lời (= mốc trượt + X/2)."""
    return [0.0, *(o + x / 2 for o in offsets)][:n]


def ease_out_cubic(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


@dataclass(frozen=True)
class CardAsset:
    states: list[tuple[Path, float]]  # (png đã cắt, giây từ lúc thẻ hiện), giây = lúc bắt đầu
    x: int
    y: int
    w: int
    h: int


def count_schedule(cfg: dict) -> list[tuple[float, float]]:
    """[(lúc bắt đầu, hệ số 0..1)] của các trạng thái số chạy tăng; trạng thái đầu = 0."""
    steps = int(cfg["steps"])
    out = [(0.0, 0.0)]
    for i in range(1, steps + 1):
        out.append((cfg["delay"] + cfg["seconds"] * i / steps, ease_out_cubic(i / steps)))
    return out


def _source(project: PostvProject, span: CardSpan) -> dict:
    """Dữ liệu của project mà ảnh thẻ này phụ thuộc vào (để băm khoá cache)."""
    if span.kind == "post":
        return project.post.model_dump()
    if span.kind == "comment":
        return next(c.model_dump() for c in project.comments if c.id == span.ref)
    return {"hook": project.hook.model_dump(), "post": project.post.text}


def build_asset(
    project: PostvProject,
    span: CardSpan,
    tpl: dict,
    censor: list[CensorMatcher] | None,
    censor_mode: str,
    count_up: bool,
    out_dir: Path,
) -> CardAsset:
    """Vẽ (hoặc dùng lại) các trạng thái PNG của thẻ; cache theo nội dung, không theo thời gian."""
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _source(project, span)
    stats = [source.get(k) for k in ("likes", "replies", "reposts", "shares")]
    counting = count_up and span.kind != "hook" and any(stats)
    schedule = count_schedule(tpl["anim"]["count"]) if counting else [(0.0, 1.0)]
    key = cache.digest(
        "pv-card", span.kind, source, tpl, [m.word for m in censor or []], censor_mode, schedule,
        CARD_CODE,
    )  # fmt: skip
    meta_path = out_dir / f"{key}.json"
    if meta_path.is_file():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if all((out_dir / n).is_file() for n, _ in data["states"]):
            return CardAsset([(out_dir / n, t) for n, t in data["states"]], *data["box"])
    final = render_project_card(project, span.kind, span.ref, tpl, censor, censor_mode, 1.0)
    box = final.getchannel("A").getbbox()
    if box is None:
        raise ValueError("Thẻ trống")
    states: list[tuple[str, float]] = []
    previous = None
    for k, (at, scale) in enumerate(schedule):
        image = final
        if scale < 1.0:
            image = render_project_card(
                project, span.kind, span.ref, tpl, censor, censor_mode, scale
            )
        crop = image.crop(box)
        raw = crop.tobytes()
        if raw == previous:  # giống trạng thái trước: gộp vào, không thêm
            continue
        previous = raw
        name = f"{key[:10]}-{k:02d}.png"
        crop.save(out_dir / name)
        states.append((name, at))
    x, y, right, bottom = box
    box_xywh = [x, y, right - x, bottom - y]
    meta_path.write_text(json.dumps({"states": states, "box": box_xywh}), encoding="utf-8")
    return CardAsset([(out_dir / n, t) for n, t in states], *box_xywh)


def write_card_concat(asset: CardAsset, seconds: float, path: Path) -> None:
    """File ffconcat của một thẻ dài đúng `seconds` (trạng thái cuối giữ tới hết)."""
    lines = ["ffconcat version 1.0"]
    states = [(p, t) for p, t in asset.states if t < seconds - 1e-3]
    for i, (png, at) in enumerate(states):
        nxt = states[i + 1][1] if i + 1 < len(states) else seconds
        lines += [f"file '{png.resolve().as_posix()}'", f"duration {nxt - at:.6f}"]
    lines.append(f"file '{states[-1][0].resolve().as_posix()}'")  # demuxer bỏ duration mục cuối
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def bounce_scale_expr(cfg: dict) -> str:
    """Hệ số phóng theo `t` (giây từ lúc thẻ hiện): from → peak → 1 trong `duration`."""
    d, f, p = cfg["duration"], cfg["from"], cfg["peak"]
    up = d * cfg["peak_at"]
    return (
        f"if(lt(t,{_num(up)}),{_num(f)}+({_num(p - f)})*t/{_num(up)},"
        f"if(lt(t,{_num(d)}),{_num(p)}+({_num(1 - p)})*(t-{_num(up)})/{_num(d - up)},1))"
    )


def card_timing(span: CardSpan, tpl: dict, mode: str, total: float) -> dict:
    """Thời gian hiện/mờ và kiểu vào của một thẻ (giây, tương đối so với lúc thẻ hiện)."""
    anim = tpl["anim"]
    smooth, bounce = anim["smooth"], anim["bounce"]
    bounced = span.fresh and (mode == "bounce" or span.kind == "hook")
    if not span.fresh:
        in_d, slide = smooth["change"], 0.0
    elif bounced:
        in_d, slide = bounce["duration"], 0.0
    else:
        in_d, slide = smooth["in"], float(smooth["slide"])
    out_d = smooth["change"] if span.handoff else smooth["out"]
    visible = span.end - span.start
    if span.end >= total - 1e-6:  # thẻ cuối chạy tới hết thân video: mờ xong đúng lúc hết
        visible = max(total - span.start - out_d, 0.0)
    in_d = min(in_d, max(visible, 0.05))
    return {
        "in": in_d, "slide": slide, "bounce": bounced, "out": out_d, "visible": visible,
        "seconds": visible + out_d,
    }  # fmt: skip


def card_chain(
    index: int,
    label: str,
    asset: CardAsset,
    span: CardSpan,
    timing: dict,
    tpl: dict,
    fps: int,
    scale: float,
    prev: str,
    out: str,
) -> list[str]:
    """Các đoạn filtergraph đưa thẻ (input số `index`) lên `prev` → `out`."""
    t_in, s = timing["in"], span.start
    chain = [f"[{index}:v]fps={fps},format=rgba"]
    if scale != 1.0:
        chain.append(f"scale=w='round(iw*{_num(scale)})':h='round(ih*{_num(scale)})':flags=lanczos")
    x0, y0 = asset.x * scale, asset.y * scale
    if timing["bounce"]:
        f = bounce_scale_expr(tpl["anim"]["bounce"])
        chain.append(f"scale=w='round(iw*({f}))':h='round(ih*({f}))':eval=frame,format=rgba")
        cx, cy = x0 + asset.w * scale / 2, y0 + asset.h * scale / 2
        pos = f"x='{_num(cx)}-w/2':y='{_num(cy)}-h/2'"
    elif timing["slide"]:
        slide = timing["slide"] * scale
        pos = (
            f"x={_num(x0)}:y='{_num(y0)}-{_num(slide)}*pow(max(1-(t-{_num(s)})/{_num(t_in)},0),3)'"
        )
    else:
        pos = f"x={_num(x0)}:y={_num(y0)}"
    chain.append(f"fade=t=in:st=0:d={_num(t_in)}:alpha=1")
    chain.append(f"fade=t=out:st={_num(timing['visible'])}:d={_num(timing['out'])}:alpha=1")
    chain.append(f"setpts=PTS+{_num(s)}/TB[{label}]")
    return [
        ",".join(chain),
        f"[{prev}][{label}]overlay={pos}:eval=frame:eof_action=pass:repeatlast=0[{out}]",
    ]
