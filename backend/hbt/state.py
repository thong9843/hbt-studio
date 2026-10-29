"""Trạng thái dùng chung của app, gắn vào `app.state.hbt`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hbt.app_settings import AppSettingsStore
from hbt.config import Settings
from hbt.jobs import JobManager
from hbt.library import MusicLibrary
from hbt.postv.backgrounds import BackgroundLibrary
from hbt.postv.censor import CensorStore
from hbt.postv.voice import VoiceProvider
from hbt.sensitive import SensitiveStore
from hbt.storage import Storage


@dataclass
class AppState:
    settings: Settings
    storage: Storage
    jobs: JobManager
    library: MusicLibrary
    sensitive: SensitiveStore
    app_settings: AppSettingsStore
    brand_dir: Path
    postv_words: CensorStore
    backgrounds: BackgroundLibrary
    voice: VoiceProvider
