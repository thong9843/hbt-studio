"""Thư viện nền gameplay của PostV: `library/backgrounds/index.json` (IMPLEMENT-POSTV.md mục 4).

Mẫu theo `hbt.library.MusicLibrary`: mỗi clip bắt buộc có tiêu đề, nguồn và giấy phép. Chỉ nhận
video **dọc** (K-10) nên khi dựng không phải cắt hay lấp khung.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from hbt.library import ID_PATTERN, SAFE_SEGMENT, _unique_id
from hbt.pipeline.ffutil import FFmpegError, FFmpegNotFound, ffmpeg_exe, probe
from hbt.storage import BadRequest, NotFound, ServiceUnavailable, Unprocessable, slugify

BG_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
MIN_WIDTH, MIN_HEIGHT = 720, 1280  # nhỏ hơn thì từ chối; dưới 1080×1920 giao diện chỉ nhắc
FULL_WIDTH, FULL_HEIGHT = 1080, 1920
MIN_DURATION = 3.0  # giây
THUMB_WIDTH = 270


class BackgroundEntry(BaseModel):
    id: str  # slug từ tiêu đề, tạo một lần, không đổi
    file: str  # tên file trong library/backgrounds/
    title: str = Field(min_length=1)
    source: str = ""
    license: str = ""
    url: str = ""
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    duration: float = Field(gt=0)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not ID_PATTERN.match(v):
            raise ValueError("id chỉ gồm chữ thường, số và dấu '-'")
        return v

    @field_validator("file")
    @classmethod
    def _valid_file(cls, v: str) -> str:
        if not SAFE_SEGMENT.match(v) or Path(v).suffix.lower() not in BG_EXTENSIONS:
            raise ValueError("tên file không hợp lệ: " + ", ".join(sorted(BG_EXTENSIONS)))
        return v

    @property
    def low_resolution(self) -> bool:
        return self.width < FULL_WIDTH or self.height < FULL_HEIGHT


def _fps(rate: str) -> float:
    num, _, den = (rate or "0/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def inspect_video(path: Path) -> tuple[int, int, float, float]:
    """(rộng, cao, fps, giây) của luồng hình đầu tiên; BadRequest nếu không phải video đọc được."""
    try:
        info = probe(path)
    except FFmpegNotFound as e:
        raise ServiceUnavailable(str(e)) from e
    except FFmpegError as e:
        raise BadRequest("Không đọc được file video này") from e
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if stream is None:
        raise BadRequest("File không có luồng hình")
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    # video quay dọc bằng điện thoại có thể ghi rộng×cao kèm cờ xoay
    rotation = abs(int(float((stream.get("tags") or {}).get("rotate", 0) or 0)))
    for side in stream.get("side_data_list") or []:
        rotation = abs(int(float(side.get("rotation", rotation) or 0)))
    if rotation in (90, 270):
        width, height = height, width
    duration = float(info.get("format", {}).get("duration") or stream.get("duration") or 0)
    return width, height, _fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate")), duration


class BackgroundLibrary:
    def __init__(self, library_dir: Path):
        self.root = Path(library_dir) / "backgrounds"

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    @property
    def thumbs_dir(self) -> Path:
        return self.root / "thumbs"

    def _write(self, entries: list[BackgroundEntry]) -> None:
        tmp = self.index_path.with_name("index.json.tmp")
        data = [e.model_dump() for e in entries]
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.index_path)

    def list(self) -> list[BackgroundEntry]:
        if not self.index_path.is_file():
            return []
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("phải là một danh sách các clip")
            entries = [BackgroundEntry.model_validate(e) for e in raw]
            ids = [e.id for e in entries]
            if len(set(ids)) != len(ids):
                raise ValueError("có id bị trùng")
        except (json.JSONDecodeError, ValueError, ValidationError) as e:
            raise BadRequest(f"library/backgrounds/index.json không hợp lệ: {e}") from e
        return entries

    def find(self, clip_id: str) -> tuple[BackgroundEntry, Path]:
        """Clip theo id: id sai định dạng → 422, không có → 404."""
        if not ID_PATTERN.match(clip_id):
            raise Unprocessable("Id clip nền không hợp lệ")
        entry = next((e for e in self.list() if e.id == clip_id), None)
        if entry is None:
            raise NotFound(f"Không có clip '{clip_id}' trong thư viện nền")
        root = self.root.resolve()
        target = (root / entry.file).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise NotFound(f"Không có file video của clip '{clip_id}' trong thư viện")
        return entry, target

    def thumb_path(self, clip_id: str) -> Path:
        self.find(clip_id)
        path = self.thumbs_dir / f"{clip_id}.jpg"
        if not path.is_file():
            raise NotFound(f"Clip '{clip_id}' chưa có ảnh xem nhanh")
        return path

    def _make_thumb(self, video: Path, dest: Path, duration: float) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg_exe(), "-v", "error", "-y", "-ss", f"{min(1.0, duration / 2):.2f}",
            "-i", str(video), "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2",
            "-q:v", "4", str(dest),
        ]  # fmt: skip
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0 or not dest.is_file():
            raise BadRequest("Không tạo được ảnh xem nhanh từ clip này")

    def add(self, src: Path, filename: str, meta: dict) -> BackgroundEntry:
        """Thêm một clip: video dọc đủ lớn, tạo ảnh xem nhanh."""
        title = str(meta.get("title", "")).strip()
        if not title:
            raise BadRequest("Thiếu tiêu đề clip nền")
        ext = Path(filename).suffix.lower()
        if ext not in BG_EXTENSIONS:
            raise BadRequest("Đuôi file nền không hợp lệ: " + ", ".join(sorted(BG_EXTENSIONS)))
        width, height, fps, duration = inspect_video(src)
        if height <= width:
            raise BadRequest(f"Chỉ nhận video dọc (cao hơn rộng); file này là {width}×{height}")
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            raise BadRequest(
                f"Video nhỏ quá ({width}×{height}); cần tối thiểu {MIN_WIDTH}×{MIN_HEIGHT}"
            )
        if duration < MIN_DURATION:
            raise BadRequest(f"Clip ngắn quá ({duration:.1f} s); cần ít nhất {MIN_DURATION:g} s")
        entries = self.list()
        stem = slugify(title) or "clip-nen"
        clip_id = _unique_id(stem, {e.id for e in entries})
        name = f"{clip_id}{ext}"
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            entry = BackgroundEntry(
                id=clip_id, file=name, title=title,
                source=str(meta.get("source", "")).strip(),
                license=str(meta.get("license", "")).strip(),
                url=str(meta.get("url", "")).strip(), width=width, height=height,
                fps=round(fps, 3), duration=round(duration, 3),
                tags=[t.strip() for t in meta.get("tags", []) if str(t).strip()],
            )  # fmt: skip
        except ValidationError as e:
            detail = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            raise BadRequest(f"Thông tin clip không hợp lệ: {detail}") from e
        self._make_thumb(src, self.thumbs_dir / f"{clip_id}.jpg", duration)
        shutil.move(src, self.root / name)
        self._write([*entries, entry])
        return entry

    def remove(self, clip_id: str) -> None:
        """Xoá clip nền khỏi thư viện: xoá file video, file thumb và mục trong index.json."""
        _, video_path = self.find(clip_id)
        thumb_path = self.thumbs_dir / f"{clip_id}.jpg"
        entries = [e for e in self.list() if e.id != clip_id]
        try:
            if video_path.is_file():
                video_path.unlink()
        except OSError:
            pass
        try:
            if thumb_path.is_file():
                thumb_path.unlink()
        except OSError:
            pass
        self._write(entries)


def background_problems(clip_ids: list[str], library: BackgroundLibrary) -> list[str]:
    """Những gì còn thiếu ở phần nền để dựng được (rỗng nếu đủ). `clip_ids` rỗng = cả thư viện."""
    entries = library.list()
    if not entries:
        return ["Chưa có clip nền nào trong thư viện"]
    by_id = {e.id: e for e in entries}
    chosen = [by_id.get(c) for c in clip_ids] if clip_ids else list(entries)
    problems = []
    for cid, entry in zip(clip_ids or [e.id for e in entries], chosen, strict=True):
        if entry is None:
            problems.append(f"Clip nền '{cid}' không còn trong thư viện")
        elif not (library.root / entry.file).is_file():
            problems.append(f"Thiếu file video của clip nền '{entry.title}'")
    return problems
