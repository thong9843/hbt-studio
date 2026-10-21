import pytest

from hbt import config


def test_defaults(tmp_path, monkeypatch):
    for key in config._KEYS:
        monkeypatch.delenv(key, raising=False)
    s = config.load_settings(tmp_path / "missing.env")
    assert s.default_fps == 50
    assert s.whisper_model == "large-v3"
    assert s.whisper_device == "auto"
    assert s.workspace_dir == (config.REPO_ROOT / "workspace").resolve()


def test_env_file_with_comments(tmp_path, monkeypatch):
    for key in config._KEYS:
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("DEFAULT_FPS=30\nWHISPER_DEVICE=cpu        # auto | cuda | cpu\n", "utf-8")
    s = config.load_settings(env)
    assert s.default_fps == 30
    assert s.whisper_device == "cpu"


@pytest.mark.parametrize("fps", [30, 50, 60])
def test_allowed_fps(tmp_path, monkeypatch, fps):
    monkeypatch.setenv("DEFAULT_FPS", str(fps))
    assert config.load_settings(tmp_path / "missing.env").default_fps == fps


def test_rejects_odd_fps(tmp_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_FPS", "45")
    with pytest.raises(ValueError):
        config.load_settings(tmp_path / "missing.env")
