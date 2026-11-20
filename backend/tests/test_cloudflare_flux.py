"""Unit tests cho Cloudflare Workers AI Flux client & API Tự vẽ ảnh HBT Core."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hbt.app_settings import (
    AppSettings,
    AppSettingsStore,
    resolve_cloudflare_config,
)
from hbt.config import Settings
from hbt.main import create_app
from hbt.shared.image_gen.cloudflare_flux import (
    FLUX_1_SCHNELL,
    FLUX_2_KLEIN,
    STYLE_ANCHOR,
    CloudflareImageError,
    build_styled_prompt,
    derive_project_seed,
    generate_scene_image,
)


def _png_bytes(
    size: tuple[int, int] = (768, 1344), color: tuple[int, int, int] = (40, 90, 120)
) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    try:
        img.save(buf, format="PNG")
    finally:
        img.close()
    return buf.getvalue()


def test_build_styled_prompt_and_seed():
    p = build_styled_prompt("ancient Easter Island statues")
    assert p.startswith(STYLE_ANCHOR)
    assert "ancient Easter Island statues" in p
    # Không gắn trùng lặp nếu đã có style anchor
    assert build_styled_prompt(p) == p
    assert derive_project_seed("dao-phuc-sinh") == derive_project_seed("dao-phuc-sinh")
    assert derive_project_seed("dao-phuc-sinh") != derive_project_seed("ai-cap-co-dai")


def test_missing_credentials_raises_clear_error(tmp_path: Path):
    with pytest.raises(CloudflareImageError) as exc_info:
        generate_scene_image(
            "test prompt",
            tmp_path / "scene-01.png",
            account_id="",
            api_token="tok",
        )
    assert exc_info.value.code == "missing_cloudflare_key"
    assert "Cloudflare" in str(exc_info.value)


def test_flux_2_klein_multipart_with_reference_and_upscale(tmp_path: Path):
    ref_path = tmp_path / "scene-01.png"
    ref_path.write_bytes(_png_bytes((64, 64), (10, 20, 30)))
    dest = tmp_path / "scene-02.png"

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["ctype"] = request.headers.get("content-type", "")
        captured["body"] = request.content
        raw = _png_bytes((768, 1344), (180, 120, 60))
        return httpx.Response(
            200,
            json={"success": True, "result": {"image": base64.b64encode(raw).decode("ascii")}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        out = generate_scene_image(
            "volcano eruption on island",
            dest,
            account_id="acc-123",
            api_token="secret-tok",
            model=FLUX_2_KLEIN,
            seed=4242,
            reference_image=ref_path,
            client=client,
        )
    finally:
        client.close()

    assert out == dest
    assert dest.is_file()
    assert str(captured["url"]).endswith(f"/accounts/acc-123/ai/run/{FLUX_2_KLEIN}")
    assert captured["auth"] == "Bearer secret-tok"
    assert "multipart/form-data" in str(captured["ctype"])
    body = captured["body"]
    assert isinstance(body, bytes)
    assert b'name="input_image_0"' in body
    assert b'name="seed"' in body and b"4242" in body
    assert b"2D flat editorial" in body

    with Image.open(dest) as img:
        assert img.size == (1080, 1920)


def test_flux_1_schnell_economy_and_fallback_plus_5xx_retry(tmp_path: Path):
    calls: list[str] = []

    def handler_fallback(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if FLUX_2_KLEIN in url:
            return httpx.Response(400, json={"success": False, "errors": [{"message": "bad form"}]})
        if len(calls) == 2:
            # Lần gọi schnell đầu tiên trả 502 -> phải retry 1 lần
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(
            200, content=_png_bytes((768, 1344)), headers={"content-type": "image/png"}
        )

    dest = tmp_path / "fallback.png"
    client = httpx.Client(transport=httpx.MockTransport(handler_fallback))
    try:
        generate_scene_image(
            "ancient library",
            dest,
            account_id="acc-1",
            api_token="tok-1",
            model=FLUX_2_KLEIN,
            client=client,
        )
    finally:
        client.close()

    assert len(calls) == 3
    assert FLUX_2_KLEIN in calls[0]
    assert FLUX_1_SCHNELL in calls[1]
    assert FLUX_1_SCHNELL in calls[2]
    with Image.open(dest) as img:
        assert img.size == (1080, 1920)

    # Chế độ tiết kiệm gọi thẳng flux-1-schnell
    eco_calls: list[str] = []

    def handler_eco(request: httpx.Request) -> httpx.Response:
        eco_calls.append(str(request.url))
        return httpx.Response(
            200, content=_png_bytes((768, 1344)), headers={"content-type": "image/png"}
        )

    client_eco = httpx.Client(transport=httpx.MockTransport(handler_eco))
    try:
        generate_scene_image(
            "simple desert",
            tmp_path / "eco.png",
            account_id="acc-1",
            api_token="tok-1",
            economy_mode=True,
            client=client_eco,
        )
    finally:
        client_eco.close()

    assert len(eco_calls) == 1
    assert FLUX_1_SCHNELL in eco_calls[0]


def test_resolve_cloudflare_config_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = AppSettingsStore(tmp_path)
    store.save(
        AppSettings(
            cloudflare_account_id="json-acc",
            cloudflare_api_token="json-tok",
            cloudflare_image_model=FLUX_1_SCHNELL,
        )
    )
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_IMAGE_MODEL", raising=False)
    monkeypatch.setattr("hbt.app_settings._read_env_file", lambda _p: {})

    acc, tok, model = resolve_cloudflare_config(tmp_path)
    assert (acc, tok, model) == ("json-acc", "json-tok", FLUX_1_SCHNELL)

    monkeypatch.setattr(
        "hbt.app_settings._read_env_file",
        lambda _p: {
            "CLOUDFLARE_ACCOUNT_ID": "env-acc",
            "CLOUDFLARE_API_TOKEN": "env-tok",
            "CLOUDFLARE_IMAGE_MODEL": FLUX_2_KLEIN,
        },
    )
    acc2, tok2, model2 = resolve_cloudflare_config(tmp_path)
    assert (acc2, tok2, model2) == ("env-acc", "env-tok", FLUX_2_KLEIN)


def test_hbt_core_generate_images_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ws = tmp_path / "workspace"
    lib = tmp_path / "library"
    ws.mkdir()
    lib.mkdir()
    settings = Settings(
        workspace_dir=ws,
        library_dir=lib,
        whisper_model="auto",
        whisper_device="cpu",
        default_fps=50,
    )
    app = create_app(settings)

    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setattr("hbt.app_settings._read_env_file", lambda _p: {})

    with TestClient(app) as client:
        # 1. Thiếu khóa -> 400 với mã missing_cloudflare_key
        resp_missing = client.post("/api/hbt-core/demo/generate-images", json={})
        assert resp_missing.status_code == 400
        assert resp_missing.json()["code"] == "missing_cloudflare_key"

        # 2. Lưu khóa vào app_settings và mock generate_scene_image
        AppSettingsStore(ws).save(
            AppSettings(cloudflare_account_id="acc-ok", cloudflare_api_token="tok-ok")
        )
        hbt_state = app.state.hbt
        proj = hbt_state.storage.create(title="Bí ẩn đảo Phục Sinh", series="Vì Sao", scene_count=3)

        gen_calls: list[tuple[str, Path | None]] = []

        def fake_generate(prompt, dest_path, **kwargs):
            gen_calls.append((dest_path.name, kwargs.get("reference_image")))
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(_png_bytes((1080, 1920)))
            return dest_path

        monkeypatch.setattr(
            "hbt.shared.image_gen.cloudflare_flux.generate_scene_image",
            fake_generate,
        )
        monkeypatch.setattr("hbt.api.core.generate_scene_image", fake_generate)

        # Sinh hàng loạt 3 cảnh
        resp = client.post(
            f"/api/hbt-core/{proj.slug}/generate-images",
            json={"overwrite": False},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        job = hbt_state.jobs.get(job_id)
        assert job.wait(timeout=5.0)
        assert job.status == "done"
        assert job.output["generated"] == 3
        assert len(gen_calls) == 3
        assert gen_calls[0][1] is None
        assert gen_calls[1][1] is not None and gen_calls[1][1].is_file()

        reloaded = hbt_state.storage.load(proj.slug)
        pdir = hbt_state.storage.project_dir(proj.slug)
        assert all(
            s.image.startswith("images/") and (pdir / s.image).is_file() for s in reloaded.scenes
        )

        # Vẽ lại riêng cảnh 1 (0-based index = 1 -> scene-02.png)
        resp_one = client.post(
            f"/api/hbt-core/{proj.slug}/scenes/1/generate-image",
            json={"image_prompt": "close up stone statue"},
        )
        assert resp_one.status_code == 200
        body_one = resp_one.json()
        assert body_one["ok"] is True
        assert body_one["image"].startswith("images/")
        assert (pdir / body_one["image"]).is_file()
        assert len(gen_calls) == 4
