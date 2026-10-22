"""Lưu trữ project trên đĩa (IMPLEMENT.md mục 3): `workspace/projects/<slug>/...`."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from hbt.app_settings import AppSettingsStore
from hbt.config import DEFAULT_FPS
from hbt.models import (
    MAX_SCENES,
    MIN_SCENES,
    SLUG_MAX,
    WINDOWS_RESERVED,
    Music,
    Project,
    Scene,
    Settings,
    Theme,
    Voice,
    check_slug,
    is_valid_slug,
)
from hbt.pipeline.ffutil import FFmpegError, FFmpegNotFound, probe

IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac"}
COPY_EXCLUDE = ("build", "renders")  # nhân bản không chép file trung gian và các lần xuất


class StorageError(Exception):
    """Lỗi lưu trữ; `message` hiển thị cho người dùng."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(StorageError):
    pass


class Conflict(StorageError):
    pass


class BadRequest(StorageError):
    pass


class ServiceUnavailable(StorageError):
    """Thiếu công cụ bên ngoài (ví dụ FFmpeg) nên chưa làm được việc này."""


class Unprocessable(StorageError):
    """Yêu cầu hợp lệ về cú pháp nhưng project chưa đủ điều kiện (ví dụ thiếu ảnh để dựng)."""


# Tên ảnh đã đúng dạng images/<16 ký tự hex>.<đuôi hợp lệ>: không đọc lại file khi mở project
HASHED_IMAGE = re.compile(r"^images/[0-9a-f]{16}\.(png|jpg|webp)$")
CANONICAL_IMAGE = re.compile(r"^images/scene-[0-9]{2,}(\.[a-z0-9]+)$")


def content_hash_16(data: bytes) -> str:
    """16 ký tự đầu của SHA-256 nội dung file ảnh."""
    return hashlib.sha256(data).hexdigest()[:16]


def _cleanup_unused_images(folder: Path, project: Project) -> None:
    """Xoá file trong images/ không còn cảnh nào tham chiếu."""
    images_dir = folder / "images"
    if not images_dir.is_dir():
        return
    referenced = {Path(s.image).name for s in project.scenes if s.image}
    for f in images_dir.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.name not in referenced:
            try:
                f.unlink()
            except OSError:
                pass


def scene_image_stem(scene_index: int) -> str:
    """Chỉ số cảnh của API (từ 0) → tên file ảnh đánh số từ 1: 0 → 'scene-01'."""
    return f"scene-{scene_index + 1:02d}"


def scene_index_from_stem(stem: str) -> int:
    """Chiều ngược lại của `scene_image_stem`: 'scene-03' → 2."""
    m = re.fullmatch(r"scene-(\d{2,})", stem)
    if not m or int(m.group(1)) < 1:
        raise ValueError(f"Không phải tên ảnh cảnh: {stem!r}")
    return int(m.group(1)) - 1


def slugify(title: str) -> str:
    """Tiêu đề tiếng Việt → slug ASCII: 'Vì sao muỗi đốt?' → 'vi-sao-muoi-dot'."""
    s = title.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > SLUG_MAX:
        s = s[:SLUG_MAX].rsplit("-", 1)[0] or s[:SLUG_MAX]
    if s in WINDOWS_RESERVED:  # "Con", "NUL"... không tạo được thư mục tên này trên Windows
        s += "-video"
    return s or "video"


def _now_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat().replace("+00:00", "Z")


def _write_json_atomic(path: Path, data: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class Storage:
    def __init__(
        self,
        workspace_dir: Path,
        default_fps: int = DEFAULT_FPS,
        app_settings: AppSettingsStore | None = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.default_fps = default_fps
        self.app_settings = app_settings

    @property
    def projects_dir(self) -> Path:
        return self.workspace_dir / "projects"

    # ---------------------------------------------------------------- đường dẫn
    def project_dir(self, slug: str) -> Path:
        try:  # chặn `..`, dấu `/`, tên Windows dành riêng... trước khi chạm vào đĩa
            check_slug(slug)
        except ValueError as e:
            raise Unprocessable(f"Slug không hợp lệ: {e}") from e
        return self.projects_dir / slug

    def project_file(self, slug: str, rel: str) -> Path:
        """Đường dẫn tuyệt đối của `rel` trong thư mục project; Unprocessable nếu thoát ra ngoài."""
        folder = self.project_dir(slug).resolve()
        target = (folder / rel).resolve()
        if not rel or not target.is_relative_to(folder):
            raise Unprocessable("Đường dẫn file không hợp lệ")
        return target

    def exists(self, slug: str) -> bool:
        try:
            return (self.project_dir(slug) / "project.json").is_file()
        except Unprocessable:
            return False

    def rel(self, path: Path) -> str:
        """Đường dẫn tương đối so với workspace, dùng dấu `/` (để ghép vào URL /files/...)."""
        return path.resolve().relative_to(self.workspace_dir.resolve()).as_posix()

    def unique_slug(self, base: str) -> str:
        slug, n = base, 2
        while (self.projects_dir / slug).exists():
            suffix = f"-{n}"
            slug = base[: SLUG_MAX - len(suffix)].rstrip("-") + suffix  # luôn ≤ SLUG_MAX
            n += 1
        return slug

    # ---------------------------------------------------------------- CRUD
    def create(self, title: str, series: str = "", scene_count: int = 8) -> Project:
        if not title.strip():
            raise BadRequest("Tiêu đề không được để trống")
        if not MIN_SCENES <= scene_count <= MAX_SCENES:
            raise BadRequest(f"Số cảnh phải từ {MIN_SCENES} đến {MAX_SCENES}")
        slug = self.unique_slug(slugify(title))
        defaults = self.app_settings.load() if self.app_settings else None  # màn Cài đặt
        project = Project(
            slug=slug,
            title=title.strip(),
            series=series.strip(),
            scenes=[Scene() for _ in range(scene_count)],
            settings=Settings(fps=defaults.default_fps if defaults else self.default_fps),
            theme=Theme(**defaults.theme.model_dump()) if defaults else Theme(),
        )
        (self.projects_dir / slug / "images").mkdir(parents=True)
        return self.save(slug, project)

    def load(self, slug: str) -> Project:
        path = self.project_dir(slug) / "project.json"
        if not path.is_file():
            raise NotFound(f"Không có project '{slug}'")
        try:
            project = Project.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as e:
            raise BadRequest(f"project.json của '{slug}' không hợp lệ: {e}") from e

        # Tự chuyển project cũ dạng scene-01.png hoặc ảnh chưa chuẩn hash sang
        # định dạng images/<sha256 16 ký tự>.<ext>
        folder = self.project_dir(slug)
        images_dir = folder / "images"
        changed = False
        if images_dir.is_dir():
            for scene in project.scenes:
                if not scene.image or HASHED_IMAGE.match(scene.image):
                    continue
                img_path = folder / scene.image
                if not img_path.is_file():
                    continue
                data = img_path.read_bytes()
                h = content_hash_16(data)
                ext = img_path.suffix.lower().lstrip(".")
                expected_rel = f"images/{h}.{ext}"
                if scene.image != expected_rel:
                    dest = folder / expected_rel
                    if not dest.is_file():
                        shutil.copy2(img_path, dest)
                    scene.image = expected_rel
                    changed = True
        if changed:
            self.save(slug, project)
        return project

    def save(self, slug: str, project: Project) -> Project:
        if project.slug != slug:
            raise BadRequest(f"slug trong nội dung ('{project.slug}') khác đường dẫn ('{slug}')")
        folder = self.project_dir(slug)
        folder.mkdir(parents=True, exist_ok=True)
        _cleanup_unused_images(folder, project)
        _write_json_atomic(folder / "project.json", project.model_dump(mode="json"))
        return project

    def delete(self, slug: str) -> None:
        folder = self.project_dir(slug)
        if not (folder / "project.json").is_file():
            raise NotFound(f"Không có project '{slug}'")
        shutil.rmtree(folder)

    def delete_scene(self, slug: str, scene_index: int) -> Project:
        """Xoá một cảnh trong project (giữ ràng buộc MIN_SCENES..MAX_SCENES)."""
        project = self.load(slug)
        if not 0 <= scene_index < len(project.scenes):
            raise NotFound(
                f"Project '{slug}' không có cảnh {scene_index} (0..{len(project.scenes) - 1})"
            )
        if len(project.scenes) <= MIN_SCENES:
            raise BadRequest(f"Project phải có ít nhất {MIN_SCENES} cảnh")
        del project.scenes[scene_index]
        if project.thumbnail and isinstance(project.thumbnail.scene, int):
            deleted_1 = scene_index + 1
            if deleted_1 < project.thumbnail.scene:
                project.thumbnail.scene -= 1
            project.thumbnail.scene = max(1, min(project.thumbnail.scene, len(project.scenes)))
        return self.save(slug, project)

    def duplicate(self, slug: str, title: str | None = None) -> Project:
        source = self.load(slug)
        new_title = (title or f"{source.title} (bản sao)").strip()
        new_slug = self.unique_slug(slugify(new_title))
        shutil.copytree(
            self.project_dir(slug),
            self.projects_dir / new_slug,
            ignore=shutil.ignore_patterns(*COPY_EXCLUDE),
        )
        copy = source.model_copy(update={"slug": new_slug, "title": new_title})
        return self.save(new_slug, copy)

    # ---------------------------------------------------------------- thứ tự cảnh
    def reorder_scenes(self, slug: str, order: list[int]) -> Project:
        """Đổi thứ tự cảnh: cảnh mới thứ i là cảnh cũ `order[i]`. Tên file ảnh không đổi."""
        project = self.load(slug)
        n = len(project.scenes)
        if sorted(order) != list(range(n)):
            raise BadRequest(f"`order` phải là một hoán vị của 0..{n - 1}")
        project.scenes = [project.scenes[k] for k in order]
        return self.save(slug, project)

    # ---------------------------------------------------------------- lịch sử xuất, nhạc thư viện
    def list_renders(self, slug: str) -> list[dict]:
        """Các lần xuất của project (mới nhất trước); đường dẫn tương đối so với workspace."""
        renders = self.project_dir(slug) / "renders"
        out: list[dict] = []
        if not renders.is_dir():
            return out
        for d in renders.iterdir():
            video = d / "video.mp4"
            if not video.is_file():
                continue
            meta: dict = {}
            if (d / "meta.json").is_file():
                try:
                    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            item = {
                "job_id": d.name,
                "preview": bool(meta.get("preview", False)),
                "fps": meta.get("fps"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "duration": meta.get("duration"),
                "lufs": meta.get("lufs"),
                "aligner": meta.get("aligner"),
                "created_at": meta.get("created_at") or _now_iso(video.stat().st_mtime),
                "size": video.stat().st_size,
                "video": self.rel(video),
            }
            for key, name in (
                ("srt", "captions.srt"),
                ("publish", "publish.txt"),
                ("log", "log.txt"),
            ):
                item[key] = self.rel(d / name) if (d / name).is_file() else None
            out.append(item)
        return sorted(out, key=lambda r: r["created_at"], reverse=True)

    def attach_music(self, slug: str, src: Path, credit: str) -> tuple[str, Project]:
        """Chép một file nhạc có sẵn (từ thư viện) vào project và đặt ghi công."""
        project = self.load(slug)
        folder = self.project_dir(slug)
        rel = f"music{src.suffix.lower()}"
        _remove_siblings(folder, "music")
        shutil.copyfile(src, folder / rel)
        project.music = Music(file=rel, credit=credit)
        self.save(slug, project)
        return rel, project

    # ---------------------------------------------------------------- danh sách
    def last_render(self, slug: str) -> dict | None:
        best = None
        renders = self.project_dir(slug) / "renders"
        if not renders.is_dir():
            return None
        for d in renders.iterdir():
            video = d / "video.mp4"
            if not video.is_file():
                continue
            meta = {}
            if (d / "meta.json").is_file():
                try:
                    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            created = meta.get("created_at") or _now_iso(video.stat().st_mtime)
            if best is None or created > best["created_at"]:
                best = {
                    "job_id": d.name,
                    "preview": bool(meta.get("preview", False)),
                    "fps": meta.get("fps"),
                    "duration": meta.get("duration"),
                    "created_at": created,
                    "video": self.rel(video),
                }
        return best

    def list_projects(self) -> list[dict]:
        out = []
        if not self.projects_dir.is_dir():
            return out
        for d in self.projects_dir.iterdir():
            pj = d / "project.json"
            if not pj.is_file() or not is_valid_slug(d.name):
                continue
            item = {
                "slug": d.name,
                "title": d.name,
                "updated_at": _now_iso(pj.stat().st_mtime),
                "thumb": None,
                "last_render": self.last_render(d.name),
            }
            try:
                project = self.load(d.name)
                item["title"] = project.title
                first = project.scenes[0].image
                if first and (d / first).is_file():
                    item["thumb"] = self.rel(d / first)
            except StorageError as e:
                item["error"] = e.message
            out.append(item)
        return sorted(out, key=lambda i: i["updated_at"], reverse=True)

    # ---------------------------------------------------------------- tài sản
    def save_asset(
        self, slug: str, kind: str, src: Path, filename: str, scene_index: int | None = None
    ) -> tuple[str, Project]:
        """Nhận file tải lên (`src` là file tạm), kiểm tra, đặt vào project và lưu project.json."""
        project = self.load(slug)
        folder = self.project_dir(slug)
        if kind == "image":
            if scene_index is None or not 0 <= scene_index < len(project.scenes):
                raise BadRequest(f"Cần `scene_index` từ 0 đến {len(project.scenes) - 1} cho ảnh")
            ext = _image_extension(src)
            data = src.read_bytes()
            h = content_hash_16(data)
            rel = f"images/{h}.{ext}"
            (folder / "images").mkdir(exist_ok=True)
            dest = folder / rel
            if not dest.is_file():
                shutil.move(src, dest)
            else:
                src.unlink(missing_ok=True)
            project.scenes[scene_index].image = rel
        elif kind in ("voice", "music"):
            ext = _audio_extension(src, filename)
            rel = f"{kind}.{ext}"
            _remove_siblings(folder, kind)
            shutil.move(src, folder / rel)
            if kind == "voice":
                project.voice = Voice(file=rel)  # điểm cắt cũ không còn đúng với file mới
            else:
                project.music = Music(file=rel)
        else:
            raise BadRequest("`kind` phải là image, voice hoặc music")
        self.save(slug, project)
        return rel, project


def _remove_siblings(folder: Path, stem: str) -> None:
    for old in folder.glob(f"{stem}.*"):
        if old.is_file():
            old.unlink()


def _image_extension(path: Path) -> str:
    try:
        with Image.open(path) as im:
            fmt = im.format
            im.verify()
    except (UnidentifiedImageError, OSError) as e:
        raise BadRequest("File không phải ảnh hợp lệ") from e
    if fmt not in IMAGE_FORMATS:
        raise BadRequest("Ảnh phải là PNG, JPG hoặc WEBP")
    return IMAGE_FORMATS[fmt]


def _audio_extension(path: Path, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        raise BadRequest("Âm thanh phải là " + ", ".join(sorted(AUDIO_EXTENSIONS)))
    try:
        streams = probe(path)["streams"]
    except FFmpegNotFound as e:
        raise ServiceUnavailable(str(e)) from e
    except FFmpegError as e:
        raise BadRequest("File không phải âm thanh hợp lệ") from e
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise BadRequest("File không có luồng âm thanh")
    return ext.lstrip(".")
