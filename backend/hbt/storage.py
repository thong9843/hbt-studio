"""Lưu trữ project trên đĩa (IMPLEMENT.md mục 3): `workspace/projects/<slug>/...`."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
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
from hbt.pipeline.cache import sha256_file
from hbt.pipeline.ffutil import FFmpegError, FFmpegNotFound, probe

log = logging.getLogger(__name__)
IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
COVER_MIN_SIDE = 540  # px; ảnh bìa tải lên có cạnh ngắn hơn thì từ chối
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac"}
DELETE_ATTEMPTS = 5  # xoá project: số lần thử khi Windows còn giữ file
DELETE_RETRY_SECONDS = 0.1
KEEP_IN_BUILD = ("timing.json", "timing.json.key")  # dọn build/ vẫn giữ căn chữ
RENDER_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)  # job_id app + tên CLI (20261026-…-preview)
TRASH_PREFIX = ".deleting-"  # thư mục lần xuất đang xoá: bị bỏ qua khi liệt kê
COPY_EXCLUDE = ("build", "renders", "backups")  # nhân bản không chép file tạm, lần xuất, sao lưu


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


# Chỉ những tên do app tự đặt mới được dọn: dạng hash, hoặc dạng cũ scene-NN.<đuôi>
_OURS = re.compile(r"^([0-9a-f]{16}|scene-[0-9]{2,})\.(png|jpg|webp)$")


def _cleanup_unused_images(folder: Path, project: Project) -> None:
    """Xoá file ảnh do app đặt tên mà không còn cảnh nào tham chiếu.

    File khác trong images/ được giữ nguyên (chỉ ghi log cảnh báo)."""
    images_dir = folder / "images"
    if not images_dir.is_dir():
        return
    referenced = {Path(s.image).name for s in project.scenes if s.image}
    for f in images_dir.iterdir():
        if not f.is_file() or f.name.startswith(".") or f.name in referenced:
            continue
        if not _OURS.match(f.name):
            log.warning("Giữ nguyên file lạ trong %s: %s", images_dir, f.name)
            continue
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

    def clean_build(self, slug: str) -> dict:
        """Xoá file trung gian trong `build/`, luôn giữ `timing.json` và `timing.json.key`
        (căn chữ là bước đắt nhất), và xoá nốt `renders/.deleting-*` (lần xuất xoá dở).
        Không động tới lần xuất thật, ảnh, giọng, nhạc, project.json."""
        folder = self.project_dir(slug)
        build = folder / "build"
        renders = folder / "renders"
        keep = set(KEEP_IN_BUILD)
        leftovers = _deleting_leftovers(renders)
        before = _tree_size(build) + sum(_tree_size(d) for d in leftovers)
        failed = 0
        if build.is_dir() and not build.is_symlink():
            for entry in build.iterdir():
                if entry.name in keep:
                    continue
                failed += _remove(entry)
        for d in leftovers:
            failed += _remove(d)
        after = _tree_size(build) + sum(_tree_size(d) for d in _deleting_leftovers(renders))
        kept = sorted(n for n in keep if (build / n).is_file())
        return {
            "before_bytes": before,
            "after_bytes": after,
            "freed_bytes": before - after,
            "kept": kept,
            "failed": failed,
        }

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
        # Windows: file vừa ghi/đang đọc (vd ảnh xem trước) làm rmtree lỗi trong chốc lát.
        for attempt in range(DELETE_ATTEMPTS):
            try:
                shutil.rmtree(folder)
                return
            except FileNotFoundError:
                if not folder.exists():
                    return
            except OSError as e:
                if attempt == DELETE_ATTEMPTS - 1:
                    raise Conflict(
                        "Không xoá được vì file đang mở (đóng chương trình đang dùng "
                        "dự án này rồi thử lại)"
                    ) from e
            time.sleep(DELETE_RETRY_SECONDS)

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
        current_music = self._music_sha256(slug)
        for d in renders.iterdir():
            video = d / "video.mp4"
            if d.name.startswith(TRASH_PREFIX) or not video.is_file():
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
                "aligner_info": meta.get("aligner_info"),
                "preview_seconds": meta.get("preview_seconds"),
                "music_start": meta.get("music_start"),
                "music_start_source": meta.get("music_start_source"),
                "render_seconds": meta.get("render_seconds"),  # bản dựng cũ không có → None
                "align_cached": meta.get("align_cached"),
                "trimmed_tail_seconds": meta.get("trimmed_tail_seconds"),
                # nhạc hiện tại của project có đúng là nhạc đã dùng cho lần xuất này không
                "music_matches_current": current_music is not None
                and meta.get("music_sha256") == current_music,
                "created_at": meta.get("created_at") or _now_iso(video.stat().st_mtime),
                "size": video.stat().st_size,
                "video": self.rel(video),
            }
            for key, name in (
                ("srt", "captions.srt"),
                ("publish", "publish.txt"),
                ("log", "log.txt"),
                ("cover", "cover_9x16.jpg"),
                ("youtube_cover", "youtube_3x2.jpg"),
                ("trimmed_tail", "trimmed_tail.wav"),
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
    def _music_sha256(self, slug: str) -> str | None:
        """SHA-256 của file nhạc hiện tại trong project; None nếu không có nhạc."""
        music = self.load(slug).music
        path = self.project_dir(slug) / music.file if music and music.file else None
        return sha256_file(path) if path is not None and path.is_file() else None

    def delete_render(self, slug: str, job_id: str) -> None:
        """Xoá cả thư mục `renders/<job_id>/` (video, bìa, publish.txt, meta). Không đụng `build/`,
        `timing.json`, `backups/`. Đổi tên thư mục trước: Windows từ chối nếu có file đang mở
        (trình phát…) nên không bao giờ xoá dở dang → Conflict."""
        if not RENDER_ID_RE.fullmatch(job_id):
            raise Unprocessable("Mã lần xuất không hợp lệ")
        renders = (self.project_dir(slug) / "renders").resolve()
        target = (renders / job_id).resolve()
        if target.parent != renders:
            raise Unprocessable("Mã lần xuất không hợp lệ")
        if not self.project_dir(slug).joinpath("project.json").is_file():
            raise NotFound(f"Không có project '{slug}'")
        if not target.is_dir():
            raise NotFound(f"Không có lần xuất '{job_id}'")
        trash = renders / f"{TRASH_PREFIX}{job_id}"
        shutil.rmtree(trash, ignore_errors=True)  # dư của lần xoá trước (nếu có)
        try:
            target.rename(trash)
        except OSError as e:
            raise Conflict(
                "Không xoá được vì file đang mở (đóng trình phát hoặc chương trình đang dùng "
                "video này rồi thử lại)"
            ) from e
        shutil.rmtree(trash, ignore_errors=True)

    def _renders_newest_first(self, slug: str) -> list[tuple[str, Path, dict]]:
        """(created_at, thư mục, meta) của các lần xuất có video, mới nhất trước."""
        renders = self.project_dir(slug) / "renders"
        if not renders.is_dir():
            return []
        found = []
        for d in renders.iterdir():
            video = d / "video.mp4"
            if d.name.startswith(TRASH_PREFIX) or not video.is_file():
                continue
            meta = {}
            if (d / "meta.json").is_file():
                try:
                    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            found.append((meta.get("created_at") or _now_iso(video.stat().st_mtime), d, meta))
        return sorted(found, key=lambda r: r[0], reverse=True)

    def _render_brief(self, created: str, d: Path, meta: dict) -> dict:
        return {
            "job_id": d.name,
            "preview": bool(meta.get("preview", False)),
            "fps": meta.get("fps"),
            "duration": meta.get("duration"),
            "render_seconds": meta.get("render_seconds"),
            "align_cached": meta.get("align_cached"),
            "trimmed_tail_seconds": meta.get("trimmed_tail_seconds"),  # bản cũ / không cắt → None
            "created_at": created,
            "video": self.rel(d / "video.mp4"),
        }

    def render_summary(self, slug: str) -> dict:
        """`last_render` (lần xuất mới nhất), `last_final` (bản đẹp mới nhất, không phải Xem nhanh)
        và `cover` (cover_9x16.jpg của lần xuất gần nhất CÓ bìa); thiếu thì None."""
        last_render = last_final = cover = None
        for created, d, meta in self._renders_newest_first(slug):
            if last_render is None:
                last_render = self._render_brief(created, d, meta)
            if last_final is None and not meta.get("preview", False):
                last_final = self._render_brief(created, d, meta)
            if cover is None and (d / "cover_9x16.jpg").is_file():
                cover = self.rel(d / "cover_9x16.jpg")
            if last_render and last_final and cover:
                break
        return {"last_render": last_render, "last_final": last_final, "cover": cover}

    def last_render(self, slug: str) -> dict | None:
        return self.render_summary(slug)["last_render"]

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
                **self.render_summary(d.name),
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
        elif kind == "cover":
            if project.thumbnail is None:
                raise Unprocessable("Hãy bật ảnh bìa (thêm khối thumbnail) trước khi tải ảnh bìa")
            ext = _image_extension(src)
            _check_cover_size(src)
            rel = f"images/cover.{ext}"
            (folder / "images").mkdir(exist_ok=True)
            os.replace(src, folder / rel)  # ghi đè bản cũ cùng đuôi
            for old in (folder / "images").glob("cover.*"):  # bản cũ khác đuôi
                if old.name != f"cover.{ext}" and old.is_file():
                    old.unlink()
            project.thumbnail.image = rel
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
            raise BadRequest("`kind` phải là image, cover, voice hoặc music")
        self.save(slug, project)
        return rel, project


def _deleting_leftovers(renders: Path) -> list[Path]:
    """Thư mục `renders/.deleting-*` còn sót (xoá lần xuất dở); không theo liên kết."""
    if not renders.is_dir() or renders.is_symlink():
        return []
    return [
        d
        for d in renders.iterdir()
        if d.name.startswith(TRASH_PREFIX) and d.is_dir() and not d.is_symlink()
    ]


def _remove(entry: Path) -> int:
    """Xoá file hoặc thư mục; trả 1 nếu không xoá được (file đang bị khoá)."""
    try:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    except OSError:
        return 1
    return 0


def _tree_size(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file() and not p.is_symlink())


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


def _check_cover_size(path: Path) -> None:
    try:
        with Image.open(path) as im:
            w, h = im.size
    except (Image.DecompressionBombError, OSError) as e:
        raise BadRequest("File không phải ảnh hợp lệ") from e
    if min(w, h) < COVER_MIN_SIDE:
        raise BadRequest(f"Ảnh bìa quá nhỏ ({w}×{h}); cạnh ngắn cần từ {COVER_MIN_SIDE} px trở lên")


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
