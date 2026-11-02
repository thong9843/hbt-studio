"""Mẫu JSON nháp `hbt_draft: 1` dùng chung cho test GĐ2 (khớp docs/gd2/IMPLEMENT-GD2.md mục 2.2)."""

from __future__ import annotations

import copy

SAMPLE = {
    "hbt_draft": 1,
    "topic": "Vì sao muỗi thích đốt một số người hơn?",
    "series_hint": "Vì sao…",
    "music_mood": "tò mò",
    "sources": [
        {
            "id": "s1",
            "claim": "Muỗi phát hiện CO2 từ xa khoảng 10 m",
            "url": "https://www.cdc.gov/mosquitoes/",
        }
    ],
    "scenes": [
        {
            "voice": "Có người ngồi cả buổi không sao, | có người bị đốt sưng cả chân.",
            "card": {
                "y": "top",
                "lines": [
                    {"text": "VÌ SAO MUỖI", "size": "l", "color": "ink"},
                    {"text": "CHỌN BẠN?", "size": "xl", "color": "accent"},
                ],
            },
            "labels": [],
            "punch": True,
            "caption_y": None,
            "image_prompt": "close-up of a mosquito on human skin, macro photo, vertical 9:16",
        },
        {
            "voice": "Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét.",
            "card": {"y": "top", "lines": [{"text": "CO2 TỪ 10 MÉT", "size": "l", "color": "ink"}]},
            "labels": [],
            "punch": False,
            "caption_y": None,
            "image_prompt": "person breathing out in warm evening air, vertical 9:16",
        },
        {
            "voice": "Thở nhiều, đổ mồ hôi nhiều | thì muỗi tìm bạn dễ hơn.",
            "card": {
                "y": "top",
                "lines": [{"text": "THỞ NHIỀU = DỄ BỊ ĐỐT", "size": "m", "color": "ink"}],
            },
            "labels": [],
            "punch": False,
            "caption_y": None,
            "image_prompt": "person jogging at dusk near a pond, vertical 9:16",
        },
    ],
    "publish": {
        "hook": 'Bạn có phải "nam châm hút muỗi"?',
        "hashtags": ["haybiettuot", "muoi", "visao"],
    },
    "thumbnail": {
        "scene": 1,
        "lines": ["VÌ SAO MUỖI", "CHỌN BẠN?"],
        "series": "",
        "accent": "#FFD43B",
    },
}


def sample(**changes):
    """Bản sao của mẫu; `changes` ghi đè khoá gốc."""
    d = copy.deepcopy(SAMPLE)
    d.update(changes)
    return d


def codes(items):
    return [i["code"] for i in items]
