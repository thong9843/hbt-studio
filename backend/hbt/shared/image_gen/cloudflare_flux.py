"""Client Cloudflare Workers AI sinh ảnh 2D đồng nhất phong cách cho HBT Core.

- Sinh cỡ 768x1344 (4 bước) tiết kiệm ~45% neuron miễn phí, rồi phóng Pillow LANCZOS lên 1080x1920.
- Với `flux-2-klein-4b`: gửi `multipart/form-data`, khóa `seed` theo dự án và truyền ảnh Cảnh 1
  làm `input_image_0` để đồng bộ nét vẽ & bảng màu; tự fallback sang `flux-1-schnell` khi bật chế độ
  tiết kiệm hoặc gặp lỗi định dạng.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

FLUX_2_KLEIN = "@cf/black-forest-labs/flux-2-klein-4b"
FLUX_1_SCHNELL = "@cf/black-forest-labs/flux-1-schnell"

STYLE_ANCHOR = (
    "2D flat editorial storybook illustration, crisp dark ink outlines, "
    "subtle warm paper grain texture, cohesive muted color palette, "
    "clean visual storytelling composition, vertical 9:16, "
    "no text, no letters, no watermark."
)

STICKV_STYLE_ANCHOR = (
    "Clean 2D flat editorial infographic illustration, crisp dark ink outlines, "
    "vibrant modern educational colors, simple clear subject, "
    "no text, no letters, no watermark."
)

GEN_WIDTH = 768
GEN_HEIGHT = 1344
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
DEFAULT_STEPS = 4
REQUEST_TIMEOUT = 45.0


class CloudflareImageError(RuntimeError):
    """Lỗi gọi Cloudflare Workers AI hoặc thiếu cấu hình khóa."""

    def __init__(self, message: str, *, code: str = "cloudflare_error", status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def build_styled_prompt(prompt: str, fallback_context: str = "") -> str:
    """Gắn tiền tố Style Anchor tranh 2D editorial nếu prompt chưa có."""
    base = (prompt or "").strip() or (fallback_context or "").strip()
    if not base:
        return STYLE_ANCHOR
    if "2d flat editorial" in base.lower():
        return base
    return f"{STYLE_ANCHOR} {base}"


def derive_project_seed(slug: str) -> int:
    """Khóa seed cố định (1..2^31-1) theo slug dự án để giữ đồng nhất phong cách giữa các cảnh."""
    digest = hashlib.sha256((slug or "hbt").encode("utf-8")).digest()
    val = int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
    return val or 1


def _endpoint_url(account_id: str, model: str) -> str:
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id.strip()}/ai/run/{model}"


def _extract_error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            errors = data.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict) and first.get("message"):
                    return str(first["message"])
            if data.get("error"):
                return str(data["error"])
    except Exception:  # noqa: BLE001
        pass
    text = (resp.text or "").strip()
    return text[:240] if text else f"HTTP {resp.status_code}"


def _decode_image_bytes(resp: httpx.Response) -> bytes:
    """Hỗ trợ cả phản hồi nhị phân `image/*` lẫn JSON `{result: {image: base64}}` của Workers AI."""
    ctype = (resp.headers.get("content-type") or "").lower()
    if ctype.startswith("image/"):
        if not resp.content:
            raise CloudflareImageError("Cloudflare trả về ảnh rỗng.", status_code=502)
        return resp.content

    try:
        data: Any = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise CloudflareImageError(
            f"Phản hồi Cloudflare không phải ảnh hoặc JSON hợp lệ: {exc}", status_code=502
        ) from exc

    if isinstance(data, dict) and data.get("success") is False:
        raise CloudflareImageError(
            f"Cloudflare Workers AI báo lỗi: {_extract_error_detail(resp)}", status_code=502
        )

    result = data.get("result") if isinstance(data, dict) else None
    b64 = result.get("image") if isinstance(result, dict) else None
    if not isinstance(b64, str) or not b64.strip():
        raise CloudflareImageError(
            "Phản hồi Cloudflare không chứa dữ liệu ảnh (result.image).", status_code=502
        )
    try:
        return base64.b64decode(b64)
    except Exception as exc:  # noqa: BLE001
        raise CloudflareImageError(f"Không giải mã được ảnh base64 từ Cloudflare: {exc}") from exc


def _upscale_to_1080x1920(raw_bytes: bytes, dest_path: Path) -> Path:
    """Phóng nét bằng Pillow LANCZOS lên 1080x1920 và ghi nguyên tử ra PNG."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + ".tmp")
    try:
        with Image.open(io.BytesIO(raw_bytes)) as src:
            rgb = src.convert("RGB")
            try:
                if rgb.size != (TARGET_WIDTH, TARGET_HEIGHT):
                    resized = rgb.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
                else:
                    resized = rgb
                try:
                    resized.save(tmp_path, format="PNG")
                finally:
                    if resized is not rgb:
                        resized.close()
            finally:
                rgb.close()
        os.replace(tmp_path, dest_path)
    except CloudflareImageError:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise CloudflareImageError(f"Không xử lý được ảnh nhận từ Cloudflare: {exc}") from exc
    return dest_path


def _post_with_retry(
    http_client: httpx.Client,
    url: str,
    headers: dict[str, str],
    **kwargs: Any,
) -> httpx.Response:
    """Gọi POST với 1 lần retry nhẹ khi Cloudflare trả 5xx hoặc lỗi mạng tạm thời."""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = http_client.post(url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise CloudflareImageError(
                f"Lỗi kết nối Cloudflare Workers AI: {exc}", status_code=502
            ) from exc
        if resp.status_code >= 500 and attempt == 0:
            continue
        return resp
    raise CloudflareImageError(f"Lỗi kết nối Cloudflare Workers AI: {last_exc}", status_code=502)


def _call_klein(
    http_client: httpx.Client,
    account_id: str,
    headers: dict[str, str],
    styled_prompt: str,
    *,
    seed: int | None,
    steps: int,
    reference_image: Path | None,
) -> httpx.Response:
    fields: list[tuple[str, Any]] = [
        ("prompt", (None, styled_prompt)),
        ("width", (None, str(GEN_WIDTH))),
        ("height", (None, str(GEN_HEIGHT))),
        ("steps", (None, str(steps))),
    ]
    if seed is not None:
        fields.append(("seed", (None, str(seed))))
    if reference_image is not None and reference_image.is_file():
        fields.append(
            ("input_image_0", (reference_image.name, reference_image.read_bytes(), "image/png"))
        )
    return _post_with_retry(
        http_client,
        _endpoint_url(account_id, FLUX_2_KLEIN),
        headers,
        files=fields,
    )


def _call_schnell(
    http_client: httpx.Client,
    account_id: str,
    headers: dict[str, str],
    styled_prompt: str,
    *,
    seed: int | None,
    steps: int,
) -> httpx.Response:
    payload: dict[str, Any] = {
        "prompt": styled_prompt,
        "width": GEN_WIDTH,
        "height": GEN_HEIGHT,
        "steps": steps,
    }
    if seed is not None:
        payload["seed"] = seed
    return _post_with_retry(
        http_client,
        _endpoint_url(account_id, FLUX_1_SCHNELL),
        headers,
        json=payload,
    )


def generate_scene_image(
    prompt: str,
    dest_path: Path,
    *,
    account_id: str,
    api_token: str,
    model: str = FLUX_2_KLEIN,
    seed: int | None = None,
    reference_image: Path | None = None,
    use_style_ref: bool = False,
    economy_mode: bool = False,
    steps: int = DEFAULT_STEPS,
    timeout: float = REQUEST_TIMEOUT,
    fallback_context: str = "",
    client: httpx.Client | None = None,
) -> Path:
    """Sinh 1 ảnh 2D 9:16 qua Cloudflare Workers AI, phóng nét 1080x1920 và lưu vào `dest_path`.

    Mặc định `use_style_ref=False` (chỉ giữ `STYLE_ANCHOR` + `seed` theo dự án) để đồng nhất nét vẽ
    nhưng không ép lặp cùng một vật thể từ Cảnh 1 sang các cảnh khác bối cảnh.
    """
    clean_account = (account_id or "").strip()
    clean_token = (api_token or "").strip()
    if not clean_account or not clean_token:
        raise CloudflareImageError(
            "Chưa cấu hình Cloudflare Account ID hoặc API Token. Vào Cài đặt để nhập khóa.",
            code="missing_cloudflare_key",
            status_code=400,
        )

    styled_prompt = build_styled_prompt(prompt, fallback_context=fallback_context)
    effective_model = FLUX_1_SCHNELL if economy_mode else (model or FLUX_2_KLEIN)
    effective_ref = reference_image if use_style_ref else None
    headers = {"Authorization": f"Bearer {clean_token}"}

    own_client = client is None
    http_client = client if client is not None else httpx.Client(timeout=timeout)
    try:
        if effective_model == FLUX_2_KLEIN:
            resp = _call_klein(
                http_client,
                clean_account,
                headers,
                styled_prompt,
                seed=seed,
                steps=steps,
                reference_image=effective_ref,
            )
            if resp.status_code in (400, 422):
                logger.warning(
                    "flux-2-klein-4b trả HTTP %s (%s) -> fallback sang flux-1-schnell",
                    resp.status_code,
                    _extract_error_detail(resp),
                )
                resp = _call_schnell(
                    http_client,
                    clean_account,
                    headers,
                    styled_prompt,
                    seed=seed,
                    steps=steps,
                )
        else:
            resp = _call_schnell(
                http_client,
                clean_account,
                headers,
                styled_prompt,
                seed=seed,
                steps=steps,
            )

        if resp.status_code >= 400:
            raw_snippet = (resp.text or "").strip()[:400]
            logger.error(
                "Cloudflare Workers AI lỗi HTTP %s (%s): %s",
                resp.status_code,
                effective_model,
                raw_snippet,
            )
            detail = _extract_error_detail(resp)
            if resp.status_code in (401, 403):
                msg = (
                    f"Cloudflare từ chối xác thực (HTTP {resp.status_code}): "
                    f"Kiểm tra lại Account ID, API Token và quyền Workers AI. ({detail})"
                )
            elif resp.status_code == 404:
                msg = (
                    f"Không tìm thấy Account ID hoặc model Cloudflare (HTTP 404). "
                    f"Kiểm tra lại Account ID. ({detail})"
                )
            elif resp.status_code == 429:
                msg = f"Cloudflare Workers AI đã hết hạn mức (HTTP 429 / hết neurons). ({detail})"
            else:
                msg = f"Cloudflare Workers AI lỗi HTTP {resp.status_code}: {detail}"
            raise CloudflareImageError(
                msg,
                status_code=502 if resp.status_code >= 500 else resp.status_code,
            )

        raw_bytes = _decode_image_bytes(resp)
        return _upscale_to_1080x1920(raw_bytes, dest_path)
    finally:
        if own_client:
            http_client.close()


def generate_illustration_image(
    prompt: str,
    dest_path: Path,
    *,
    account_id: str,
    api_token: str,
    width: int = 768,
    height: int = 512,
    steps: int = DEFAULT_STEPS,
    seed: int | None = None,
    style_anchor: str = STICKV_STYLE_ANCHOR,
    timeout: float = REQUEST_TIMEOUT,
    client: httpx.Client | None = None,
) -> Path:
    """Sinh 1 ảnh minh họa 2D ngang (768x512, flux-1-schnell) cho StickV Polaroid, không phóng 9:16."""
    clean_account = (account_id or "").strip()
    clean_token = (api_token or "").strip()
    if not clean_account or not clean_token:
        raise CloudflareImageError(
            "Chưa cấu hình Cloudflare Account ID hoặc API Token. Vào Cài đặt để nhập khóa.",
            code="missing_cloudflare_key",
            status_code=400,
        )

    base = (prompt or "").strip()
    styled = (
        base
        if (base and "editorial infographic" in base.lower())
        else (f"{style_anchor} {base}".strip() if base else style_anchor)
    )
    payload: dict[str, Any] = {
        "prompt": styled,
        "width": int(width),
        "height": int(height),
        "steps": int(steps),
    }
    if seed is not None:
        payload["seed"] = int(seed)

    headers = {"Authorization": f"Bearer {clean_token}"}
    own_client = client is None
    http_client = client if client is not None else httpx.Client(timeout=timeout)
    try:
        resp = _post_with_retry(
            http_client,
            _endpoint_url(clean_account, FLUX_1_SCHNELL),
            headers,
            json=payload,
        )
        if resp.status_code >= 400:
            detail = _extract_error_detail(resp)
            raise CloudflareImageError(
                f"Cloudflare Workers AI lỗi HTTP {resp.status_code}: {detail}",
                status_code=502 if resp.status_code >= 500 else resp.status_code,
            )
        raw_bytes = _decode_image_bytes(resp)
    finally:
        if own_client:
            http_client.close()

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + ".tmp")
    fmt = "JPEG" if dest_path.suffix.lower() in {".jpg", ".jpeg"} else "PNG"
    try:
        with Image.open(io.BytesIO(raw_bytes)) as src:
            rgb = src.convert("RGB")
            try:
                if fmt == "JPEG":
                    rgb.save(tmp_path, format="JPEG", quality=90)
                else:
                    rgb.save(tmp_path, format="PNG")
            finally:
                rgb.close()
        os.replace(tmp_path, dest_path)
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise CloudflareImageError(f"Không lưu được ảnh minh họa Cloudflare: {exc}") from exc
    return dest_path
