"""Mặc định test không chạy Whisper thật (không model, không GPU, không chờ).

Test nào cần Whisper giả thì tự patch `hbt.pipeline.render.run_whisper`."""

import pytest

from hbt.pipeline import render
from hbt.pipeline.whisper import WhisperFailed


@pytest.fixture(autouse=True)
def whisper_off(monkeypatch):
    def unavailable(*args, **kwargs):
        raise WhisperFailed("Whisper tắt trong test")

    monkeypatch.setattr(render, "run_whisper", unavailable)
