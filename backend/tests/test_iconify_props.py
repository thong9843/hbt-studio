"""Unit test cho Iconify auto-props (mock API, cache cục bộ & fallback offline)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from hbt.shared.online_sources.iconify_props import (
    clear_iconify_cache,
    resolve_prop_png,
    search_iconify_icons,
)


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (64, 64), (56, 189, 248, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_iconify_search_and_cache_download(tmp_path: Path) -> None:
    clear_iconify_cache()
    search_resp = MagicMock()
    search_resp.json.return_value = {"icons": ["mdi:brain", "lucide:brain"]}
    search_resp.raise_for_status.return_value = None

    png_resp = MagicMock()
    png_resp.content = _png_bytes()
    png_resp.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.side_effect = [search_resp, png_resp]

    with patch("hbt.shared.online_sources.iconify_props.httpx.Client", return_value=mock_client):
        icons = search_iconify_icons("brain", limit=6)
        assert len(icons) == 2
        assert icons[0]["id"] == "mdi:brain"

        p = resolve_prop_png("brain", tmp_path)
        assert p.is_file()
        assert p.name == "brain.png"
        assert (tmp_path / "props" / "brain.png").is_file()

    # Lần 2 đọc từ cache cục bộ không gọi mạng
    with patch(
        "hbt.shared.online_sources.iconify_props.httpx.Client",
        side_effect=AssertionError("should use cache"),
    ):
        p2 = resolve_prop_png("brain", tmp_path)
        assert p2 == p


def test_iconify_offline_fallback_badge(tmp_path: Path) -> None:
    clear_iconify_cache()
    with patch(
        "hbt.shared.online_sources.iconify_props.httpx.Client", side_effect=OSError("offline")
    ):
        p = resolve_prop_png("black hole", tmp_path)
        assert p.is_file()
        assert p.name == "black-hole_fallback.png"
        with Image.open(p) as im:
            assert im.mode == "RGBA"
            assert im.size == (320, 320)
