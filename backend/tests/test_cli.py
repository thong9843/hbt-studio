import json
from pathlib import Path

import pytest

import cli
from hbt.pipeline.audio import TailTrimNeedsConfirmation
from hbt.pipeline.render import RenderError, RenderResult
from tests.helpers import needs_ffmpeg


def fake_result(tmp_path):
    return RenderResult(
        job_dir=tmp_path,
        video=tmp_path / "video.mp4",
        srt=tmp_path / "captions.srt",
        publish=tmp_path / "publish.txt",
        log=tmp_path / "log.txt",
        fps=50,
        width=1080,
        height=1920,
        duration=51.2,
        lufs=-14.1,
        aligner="silence",
        seconds=12.0,
        warnings=["Cảnh báo thử"],
    )


def test_parser_defaults_and_flags():
    args = cli.build_parser().parse_args(["render", "workspace/projects/x"])
    assert args.project_dir == Path("workspace/projects/x")
    assert not args.preview and args.fps is None and not args.no_outro
    args = cli.build_parser().parse_args(
        ["render", "p", "--preview", "--fps", "60", "--no-outro", "--allow-long-trim"]
    )
    assert args.preview and args.fps == 60 and args.no_outro and args.allow_long_trim


@pytest.mark.parametrize("fps", ["45", "24", "abc"])
def test_parser_rejects_odd_fps(fps, capsys):
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["render", "p", "--fps", fps])
    assert e.value.code == 2


def test_main_passes_options_and_prints_summary(monkeypatch, tmp_path, capsys):
    seen = {}

    def fake_render(project_dir, options, progress):
        seen.update(dir=project_dir, options=options)
        progress(0, "Kiểm tra", "")
        progress(25, "Clip từng cảnh", "Cảnh 1 xong")
        return fake_result(tmp_path)

    monkeypatch.setattr(cli, "render_project", fake_render)
    code = cli.main(["render", str(tmp_path), "--preview", "--fps", "30", "--no-outro"])
    out = capsys.readouterr().out
    assert code == 0
    opts = seen["options"]
    assert opts.preview and opts.fps == 30 and opts.outro is False and not opts.allow_long_trim
    assert "[  0.0%] Kiểm tra" in out and "Cảnh 1 xong" in out
    assert "1080x1920 @ 50 fps" in out and "aligner : silence" in out
    assert "CẢNH BÁO: Cảnh báo thử" in out


def test_main_keeps_project_outro_by_default(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        cli, "render_project", lambda d, o, progress: seen.update(o=o) or fake_result(tmp_path)
    )
    cli.main(["render", str(tmp_path)])
    assert seen["o"].outro is None


def test_main_reports_render_error(monkeypatch, tmp_path, capsys):
    def boom(*a, **k):
        raise RenderError("Thiếu file:\n  a.png")

    monkeypatch.setattr(cli, "render_project", boom)
    assert cli.main(["render", str(tmp_path)]) == 1
    assert "LỖI: Thiếu file" in capsys.readouterr().err


def test_main_asks_for_confirmation_on_long_trim(monkeypatch, tmp_path, capsys):
    def stop(*a, **k):
        raise TailTrimNeedsConfirmation("Đuôi thừa dài 9.50 giây")

    monkeypatch.setattr(cli, "render_project", stop)
    assert cli.main(["render", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "DỪNG" in err and "--allow-long-trim" in err


def test_main_describes_invalid_project(tmp_path, capsys):
    (tmp_path / "project.json").write_text(
        json.dumps({"slug": "Bad Slug", "title": "T", "voice": "v.mp3", "scenes": []}),
        encoding="utf-8",
    )
    assert cli.main(["render", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "project.json không hợp lệ" in err and "slug" in err and "scenes" in err


def test_main_missing_project(tmp_path, capsys):
    assert cli.main(["render", str(tmp_path / "nope")]) == 1
    assert "project.json" in capsys.readouterr().err
    assert not (tmp_path / "nope").exists()  # không để lại thư mục renders/ rác


# ---------------------------------------------------------------- từ nhạy cảm
def project_folder(tmp_path):
    folder = tmp_path / "workspace" / "projects" / "demo"
    folder.mkdir(parents=True)
    return folder


def test_main_loads_the_default_word_list_and_passes_it(monkeypatch, tmp_path):
    seen = {}

    def fake_render(project_dir, options, progress):
        seen["words"] = options.sensitive_words
        return fake_result(tmp_path)

    monkeypatch.setattr(cli, "render_project", fake_render)
    folder = project_folder(tmp_path)
    assert cli.main(["render", str(folder)]) == 0
    ids = [c.id for c in seen["words"].categories]
    assert "drugs" in ids and "alcohol" in ids


def test_main_prefers_the_users_own_word_list(monkeypatch, tmp_path):
    seen = {}

    def fake_render(project_dir, options, progress):
        seen["words"] = options.sensitive_words
        return fake_result(tmp_path)

    monkeypatch.setattr(cli, "render_project", fake_render)
    folder = project_folder(tmp_path)
    mine = tmp_path / "workspace" / "settings"
    mine.mkdir()
    (mine / "sensitive_words.json").write_text(
        json.dumps({"categories": [{"id": "rieng", "level": "block", "words": ["muỗi"]}]}),
        encoding="utf-8",
    )
    assert cli.main(["render", str(folder)]) == 0
    assert [c.id for c in seen["words"].categories] == ["rieng"]


def edit_voices(pdir, voices):
    path = pdir / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for i, text in voices.items():
        data["scenes"][i]["voice"] = text
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@needs_ffmpeg
def test_cli_stops_on_a_blocked_word_before_rendering(tmp_path, capsys):
    from tests.test_render import make_project

    pdir, _ = make_project(tmp_path, outro=False)
    edit_voices(pdir, {1: "Chuyện ma túy."})
    code = cli.main(["render", str(pdir), "--preview", "--no-outro"])
    err = capsys.readouterr().err
    assert code == 1 and "Chặn xuất" in err and "Cảnh 2" in err and "ma tuý" in err
    assert not list(pdir.rglob("video.mp4"))  # dừng ở bước 1, chưa dựng gì


@needs_ffmpeg
def test_cli_still_renders_with_warn_and_info_words(tmp_path, capsys):
    from tests.test_render import make_project

    pdir, _ = make_project(tmp_path, outro=False)
    edit_voices(pdir, {0: "Quán bia có 3 người."})  # warn (bia) + info (số 3)
    code = cli.main(["render", str(pdir), "--preview", "--no-outro"])
    out = capsys.readouterr().out
    assert code == 0 and "CẢNH BÁO" in out
    assert len(list(pdir.rglob("video.mp4"))) == 1


def test_seconds_flag_is_passed_as_preview_seconds(monkeypatch, tmp_path):
    seen = {}

    def fake_render(project_dir, options, progress):
        seen["seconds"] = options.preview_seconds
        return fake_result(tmp_path)

    monkeypatch.setattr(cli, "render_project", fake_render)
    folder = project_folder(tmp_path)
    assert cli.build_parser().parse_args(["render", "p"]).seconds is None
    assert cli.main(["render", str(folder), "--preview", "--seconds", "10"]) == 0
    assert seen["seconds"] == 10.0


def test_summary_without_lufs_for_the_head_preview(monkeypatch, tmp_path, capsys):
    result = fake_result(tmp_path)
    result.lufs = None
    monkeypatch.setattr(cli, "render_project", lambda *a, **k: result)
    assert cli.main(["render", str(project_folder(tmp_path))]) == 0
    assert "(không đo)" in capsys.readouterr().out
