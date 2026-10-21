"""Chẩn đoán tạm: in ra (dạng chú thích GitHub) đầu ra thật của `ffmpeg -filters` / `-encoders`."""

from __future__ import annotations

import subprocess

from hbt.api import health


def notice(title: str, text: str) -> None:
    safe = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"::notice title={title}::{safe}")


for flag in ("-filters", "-encoders"):
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", flag], capture_output=True, text=True, encoding="utf-8"
    )
    names = health.parse_names(r.stdout)
    head = "\n".join(r.stdout.splitlines()[:14])
    notice(
        f"ffmpeg {flag}",
        f"rc={r.returncode} stdout_lines={len(r.stdout.splitlines())} "
        f"stderr_lines={len(r.stderr.splitlines())} parsed_names={len(names)}\n{head}",
    )
notice("health.check_ffmpeg()", repr(health.check_ffmpeg()))
