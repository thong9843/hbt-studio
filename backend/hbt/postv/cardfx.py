"""Thẻ theo đoạn và hiệu ứng thẻ khi dựng (IMPLEMENT-POSTV.md mục 6, D20, D21).

Thẻ không vẽ từng khung: mỗi thẻ là một chuỗi vài PNG nhỏ (đã cắt sát) trong file `ffconcat`; số
like, bình luận, đăng lại, chia sẻ chạy từ 0 nên có vài chục trạng thái ở ~1 s đầu. Hiện dần, trượt,
nảy và mờ ra làm bằng filter của ffmpeg (`fade`, `scale`, `overlay`) trong **một** lệnh. Mọi thời
gian, cỡ nằm ở khối `anim` của `templates/story_cards.json` (N7).
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

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


def bounce_scale(t: float, cfg: dict) -> float:
    """Hệ số phóng của thẻ "nảy" sau `t` giây: from → peak (tại `peak_at`) → 1 trong `duration`."""
    d, f, p = cfg["duration"], cfg["from"], cfg["peak"]
    up = d * cfg["peak_at"]
    if t >= d:
        return 1.0
    if t < up:
        return f + (p - f) * t / up
    return p + (1 - p) * (t - up) / (d - up)


def _even(n: float) -> int:
    n = math.ceil(n)
    return n + (n % 2)


def build_asset(
    project: PostvProject,
    span: CardSpan,
    tpl: dict,
    censor: list[CensorMatcher] | None,
    censor_mode: str,
    count_up: bool,
    out_dir: Path,
    bounce: bool = False,
) -> CardAsset:
    """Vẽ (hoặc dùng lại) các trạng thái PNG của thẻ; cache theo nội dung, không theo thời gian.

    `bounce`: thẻ "nảy": các trạng thái ở `duration` đầu được phóng sẵn (from → peak → 1) và đặt
    giữa một khung trong suốt cỡ cố định, vì ffmpeg không đổi cỡ khung giữa dòng được qua `fade`
    và `overlay`; mọi trạng thái cùng cỡ nên ghép bằng vị trí cố định."""
    out_dir.mkdir(parents=True, exist_ok=True)
    source = _source(project, span)
    stats = [source.get(k) for k in ("likes", "replies", "reposts", "shares")]
    counting = count_up and span.kind != "hook" and any(stats)
    counts = count_schedule(tpl["anim"]["count"]) if counting else [(0.0, 1.0)]
    bcfg = tpl["anim"]["bounce"]
    times = {t for t, _ in counts}
    if bounce:
        steps = int(bcfg["steps"])
        times |= {bcfg["duration"] * i / steps for i in range(steps + 1)}
    schedule = sorted(times)
    key = cache.digest(
        "pv-card", span.kind, source, tpl, [m.word for m in censor or []], censor_mode, schedule,
        counting, bounce, CARD_CODE,
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
    x, y, right, bottom = box
    w, h = right - x, bottom - y
    canvas = (_even(w * bcfg["peak"] + 2), _even(h * bcfg["peak"] + 2)) if bounce else (w, h)
    by_scale: dict[float, Image.Image] = {}
    states: list[tuple[str, float]] = []
    previous = None
    for k, at in enumerate(schedule):
        k_count = next(sc for tt, sc in reversed(counts) if tt <= at + 1e-9)
        if k_count not in by_scale:
            image = final
            if k_count < 1.0:
                image = render_project_card(
                    project, span.kind, span.ref, tpl, censor, censor_mode, k_count
                )
            by_scale[k_count] = image.crop(box)
        crop = by_scale[k_count]
        if bounce:
            factor = bounce_scale(at, bcfg)
            if factor != 1.0:
                crop = crop.resize((round(w * factor), round(h * factor)), Image.LANCZOS)
            frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
            frame.alpha_composite(
                crop, ((canvas[0] - crop.width) // 2, (canvas[1] - crop.height) // 2)
            )
            crop = frame
        raw = crop.tobytes()
        if raw == previous:  # giống trạng thái trước: gộp vào, không thêm
            continue
        previous = raw
        name = f"{key[:10]}-{k:02d}.png"
        crop.save(out_dir / name)
        states.append((name, at))
    if bounce:  # đặt khung cố định sao cho tâm trùng tâm thẻ gốc
        x, y = x + w // 2 - canvas[0] // 2, y + h // 2 - canvas[1] // 2
    box_xywh = [x, y, *canvas]
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
    if timing["slide"]:
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
