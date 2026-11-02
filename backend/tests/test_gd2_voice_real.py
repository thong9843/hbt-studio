"""Giọng VieNeu thật cho HBT (chậm; cần backend/.venv-tts + trọng số): không chạy trong CI,
thiếu VieNeu thì bỏ qua."""

import os

import pytest

from hbt.config import REPO_ROOT
from hbt.gd2.voice import build_hbt_plan, spoken_chunks, synthesize_hbt
from hbt.models import Project, Scene
from hbt.postv.voice import DEFAULT_NARRATOR, VieNeuProvider, wav_seconds

provider = VieNeuProvider(REPO_ROOT / "models")
pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(os.environ.get("CI") == "true", reason="VieNeu thật không chạy trong CI"),
    pytest.mark.skipif(not provider.status().ok, reason=provider.status().note[:80]),
]


def test_real_hbt_voice_reads_spoken_text_and_pauses(tmp_path):
    project = Project(
        slug="muoi",
        title="Muỗi",
        scenes=[
            Scene(voice="Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét."),
            Scene(voice="Thở nhiều, | thì muỗi tìm bạn dễ hơn."),
            Scene(voice="Chỉ vậy thôi."),
        ],
    )
    assert spoken_chunks(project.scenes[0].voice) == [
        "Muỗi đánh hơi khí CO2 từ xa khoảng mười mét."
    ]
    plan = build_hbt_plan(project, DEFAULT_NARRATOR)
    assert len(plan) == 4  # cảnh 2 tách đôi ở `|`
    result = synthesize_hbt(plan, tmp_path, provider)
    assert result.generated == 4 and result.file == tmp_path / "voice.wav"
    assert 4.0 < wav_seconds(result.file) < 30.0
    assert [s["scene"] for s in result.scenes] == [0, 1, 2]
    again = synthesize_hbt(plan, tmp_path, provider)  # cache theo lời + giọng
    assert again.cached == 4 and again.generated == 0
