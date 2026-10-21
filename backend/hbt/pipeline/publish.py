"""Nội dung đăng `publish.txt` (IMPLEMENT.md mục 8)."""

from __future__ import annotations

from hbt.models import Project


def build_publish_text(project: Project) -> str:
    pub = project.publish
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in pub.hashtags)

    tiktok = ["[TikTok]", pub.hook, tags]

    desc = [pub.hook]
    if project.series:
        desc.append(f'Series "{project.series}".')
    if project.music and project.music.credit:
        desc.append(f"Nhạc: {project.music.credit}")
    youtube = [
        "[YouTube Shorts]",
        f"Title: {project.title} #shorts",
        "Description: " + " ".join(p for p in desc if p),
    ]

    blocks = ["\n".join(tiktok), "\n".join(youtube)]
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
