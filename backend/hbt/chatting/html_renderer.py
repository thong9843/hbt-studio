"""Trình render khung chat iOS (HTML/CSS/SVG -> PNG RGBA) bằng 1 phiên Chromium/Playwright."""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
from pathlib import Path
from typing import Any

from hbt.config import REPO_ROOT

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
RENDER_SCRIPT = Path(__file__).resolve().parent / "html_render.mjs"


def file_to_data_uri(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "image/png"
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def is_html_renderer_available() -> bool:
    """Kiểm tra Node + playwright trong node_modules có sẵn sàng không."""
    pw_dir = REPO_ROOT / "node_modules" / "playwright"
    return RENDER_SCRIPT.is_file() and pw_dir.is_dir()


class HtmlChatSession:
    """Giữ 1 tiến trình Chromium duy nhất cho cả video để render các frame PNG trong suốt."""

    def __init__(self, platform: str = "messenger") -> None:
        tpl_name = "instagram_ios.html" if platform == "instagram" else "messenger_ios.html"
        self.template_path = TEMPLATES_DIR / tpl_name
        self._proc: subprocess.Popen[str] | None = None

    def __enter__(self) -> HtmlChatSession:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def start(self) -> bool:
        if not self.template_path.is_file() or not is_html_renderer_available():
            return False
        try:
            self._proc = subprocess.Popen(
                ["node", str(RENDER_SCRIPT), str(self.template_path)],
                cwd=str(REPO_ROOT),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            return True
        except Exception:
            self._proc = None
            return False

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def render_frame(self, state: dict[str, Any], out_png: Path) -> bool:
        if (
            not self.active
            or self._proc is None
            or self._proc.stdin is None
            or self._proc.stdout is None
        ):
            return False
        try:
            payload = json.dumps(
                {"cmd": "render", "state": state, "out": str(out_png)}, ensure_ascii=False
            )
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()
            resp_line = self._proc.stdout.readline()
            if not resp_line:
                return False
            resp = json.loads(resp_line)
            return bool(resp.get("ok")) and Path(out_png).is_file()
        except Exception:
            return False

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None and self._proc.stdin is not None:
                self._proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        finally:
            self._proc = None
