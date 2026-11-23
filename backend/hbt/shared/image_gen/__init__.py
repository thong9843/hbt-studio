"""Client sinh ảnh AI (Cloudflare Workers AI Flux) dùng chung."""

from hbt.shared.image_gen.cloudflare_flux import (
    FLUX_1_SCHNELL,
    FLUX_2_KLEIN,
    STYLE_ANCHOR,
    CloudflareImageError,
    build_styled_prompt,
    derive_project_seed,
    generate_scene_image,
)

__all__ = [
    "FLUX_1_SCHNELL",
    "FLUX_2_KLEIN",
    "STYLE_ANCHOR",
    "CloudflareImageError",
    "build_styled_prompt",
    "derive_project_seed",
    "generate_scene_image",
]
