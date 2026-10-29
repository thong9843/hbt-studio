"""VieNeu thật (chậm; cần backend/.venv-tts + trọng số): không chạy trong CI, thiếu thì bỏ qua."""

import os

import pytest

from hbt.config import REPO_ROOT
from hbt.postv.voice import (
    DEFAULT_NARRATOR,
    VieNeuProvider,
    VoicePlanItem,
    synthesize_plan,
    wav_seconds,
)

provider = VieNeuProvider(REPO_ROOT / "models")
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("CI") == "true", reason="VieNeu thật không chạy trong CI"),
    pytest.mark.skipif(not provider.status().ok, reason=provider.status().note[:80]),
]


def test_real_voices_and_two_voice_synthesis(tmp_path):
    voices = VieNeuProvider(REPO_ROOT / "models", cache_file=None).list_voices()
    ids = {v.id for v in voices}
    assert len(voices) >= 20 and DEFAULT_NARRATOR in ids
    assert {v.gender for v in voices} >= {"Nam", "Nữ"}
    plan = [
        VoicePlanItem(0, "narrator", DEFAULT_NARRATOR, "Xin chào các bạn."),
        VoicePlanItem(1, "post", "Trúc Ly", "Hôm nay trời đẹp, giá 150.000 đồng."),
    ]
    result = synthesize_plan(
        plan, tmp_path, provider, {"narrator": DEFAULT_NARRATOR, "post": "Trúc Ly"}
    )
    assert result.generated == 2
    assert 2.0 < wav_seconds(result.file) < 15.0
    again = synthesize_plan(plan, tmp_path, provider, {})
    assert again.cached == 2 and again.generated == 0
