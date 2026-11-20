"""Nội dung đăng `publish.txt` của PostV: như HBT, thêm dòng nguồn và ghi công nền (mục 6)."""

from __future__ import annotations

from collections.abc import Sequence

from hbt.postv.backgrounds import BackgroundEntry
from hbt.postv.models import PostvProject


def source_line(project: PostvProject) -> str:
    """`Nguồn: …` từ liên kết (ưu tiên) hoặc ghi chú nguồn; rỗng nếu chưa ghi gì."""
    src = project.source
    value = (src.url or src.note).strip()
    return f"Nguồn: {value}" if value else ""


def build_publish_text(project: PostvProject, backgrounds: Sequence[BackgroundEntry] = ()) -> str:
    pub = project.publish
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in pub.hashtags)
    source = source_line(project)
    music = f"Nhạc: {project.music.credit}" if project.music and project.music.credit else ""

    tiktok = ["[TikTok]", pub.hook, source, tags]

    desc = [pub.hook]
    if project.series:
        desc.append(f'Series "{project.series}".')
    desc += [source, music]
    youtube = [
        "[YouTube Shorts]",
        f"Title: {project.title} #shorts",
        "Description: " + " ".join(p for p in desc if p),
    ]

    blocks = ["\n".join(p for p in tiktok if p), "\n".join(youtube)]
    credits = [f"Nền: {b.title}" for b in backgrounds]
    if credits or music:
        blocks.append("\n".join(["[Ghi công]", *credits, music]).strip())
    if project.thumbnail:
        blocks.append(
            "\n".join(
                [
                    "[Thumbnail]",
                    "Dòng chữ bìa: " + " / ".join(project.thumbnail.lines),
                    "TikTok: cover_9x16.jpg",
                    "YouTube Shorts: youtube_3x2.jpg",
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"
