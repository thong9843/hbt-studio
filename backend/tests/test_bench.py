"""bench-align: thời gian, tỉ lệ khớp, độ lệch mốc cắt cảnh so với khoảng lặng (Whisper giả)."""

import pytest

import cli
from hbt.pipeline import bench
from hbt.pipeline.bench import BenchRow, format_rows
from hbt.pipeline.whisper import Step, WhisperFailed, WhisperRun
from tests.helpers import needs_ffmpeg
from tests.test_render import make_project
from tests.test_whisper_align import FakeWhisper


def test_scene_offsets_come_from_the_gap_between_scenes():
    # 2 cảnh, mỗi cảnh 2 token; cảnh 1 kết thúc ở 2,0, cảnh 2 bắt đầu ở 3,0
    times = [(0.0, 1.0), (1.0, 2.0), (3.0, 4.0), (4.0, 5.0)]
    (offset,) = bench.scene_offsets(times, [0, 0, 1, 1], 2)
    assert 2.0 < offset < 3.0


def test_format_rows_shows_numbers_and_errors():
    text = format_rows(
        [
            BenchRow(
                "small",
                used="small (cpu, int8)",
                seconds=23.4,
                match_ratio=0.97,
                mean_offset_ms=12.0,
                max_offset_ms=40.0,
            ),
            BenchRow("medium", seconds=1.0, error="hết giờ"),
            BenchRow("large-v3", used="large-v3 (cpu, int8)", seconds=90.0, match_ratio=0.99),
        ]
    )
    assert "23,4 s" in text and "97,0%" in text and "12 ms" in text and "40 ms" in text
    assert "LỖI sau 1,0 s: hết giờ" in text
    assert text.splitlines()[-1].rstrip().endswith("—")  # không có mốc để so → gạch ngang


@pytest.fixture
def bench_project(tmp_path, monkeypatch):
    pdir, _ = make_project(tmp_path)
    return pdir


@needs_ffmpeg
def test_bench_reports_each_model(bench_project, monkeypatch):
    seen = []

    def fake(wav, prompt, cfg, log=print, *, steps=None, on_progress=None):
        seen.append((cfg.model, [s.model for s in steps]))
        if cfg.model == "medium":
            raise WhisperFailed("hết giờ")
        run = FakeWhisper()(wav, prompt, cfg, log)
        return WhisperRun(run.syllables, Step("cpu", "int8", cfg.model), 5.0)

    monkeypatch.setattr(bench, "run_whisper", fake)
    monkeypatch.setattr(bench, "_detect_cuda", lambda: False)
    rows = bench.bench_align(bench_project, ["small", "medium"], bench.WhisperConfig(device="cpu"))
    small, medium = rows
    assert seen == [("small", ["small"]), ("medium", ["medium"])]
    assert small.used == "small (cpu, int8)" and small.seconds == 5.0
    assert small.match_ratio == 1.0
    # giọng giả rõ từng câu: Whisper và khoảng lặng cho cùng mốc cắt (lệch dưới 0,15 s)
    assert small.max_offset_ms is not None and small.max_offset_ms < 150
    assert medium.error == "hết giờ" and medium.match_ratio is None


@needs_ffmpeg
def test_bench_reuses_build_voice(bench_project, monkeypatch):
    monkeypatch.setattr(bench, "run_whisper", FakeWhisperRunner())
    bench.bench_align(bench_project, ["small"], bench.WhisperConfig(device="cpu"))
    first = (bench_project / "build" / "voice.wav").stat().st_mtime_ns
    bench.bench_align(bench_project, ["small"], bench.WhisperConfig(device="cpu"))
    assert (bench_project / "build" / "voice.wav").stat().st_mtime_ns == first


class FakeWhisperRunner:
    def __call__(self, wav, prompt, cfg, log=print, *, steps=None, on_progress=None):
        run = FakeWhisper()(wav, prompt, cfg, log)
        return WhisperRun(run.syllables, steps[0], 1.0)


@needs_ffmpeg
def test_cli_bench_align_prints_a_table(bench_project, monkeypatch, capsys):
    monkeypatch.setattr(bench, "run_whisper", FakeWhisperRunner())
    monkeypatch.setattr(bench, "_detect_cuda", lambda: False)
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    code = cli.main(["bench-align", str(bench_project), "--models", "small,medium"])
    out = capsys.readouterr().out
    assert code == 0
    assert "small" in out and "medium" in out and "khớp" in out and "100,0%" in out


def test_cli_bench_align_rejects_unknown_model(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["bench-align", str(tmp_path), "--models", "huge"])
    assert "huge" in capsys.readouterr().err


def test_cli_bench_align_missing_project(tmp_path, capsys):
    assert cli.main(["bench-align", str(tmp_path / "khong-co")]) == 1
    assert "LỖI" in capsys.readouterr().err


@needs_ffmpeg
def test_bench_can_measure_with_and_without_the_initial_prompt(bench_project, monkeypatch):
    prompts = []

    def fake(wav, prompt, cfg, log=print, *, steps=None, on_progress=None):
        prompts.append((cfg.model, bool(prompt)))
        run = FakeWhisper()(wav, prompt, cfg, log)
        return WhisperRun(run.syllables, steps[0], 2.0)

    monkeypatch.setattr(bench, "run_whisper", fake)
    monkeypatch.setattr(bench, "_detect_cuda", lambda: False)
    cfg = bench.WhisperConfig(device="cpu")
    rows = bench.bench_align(bench_project, ["small", "medium"], cfg, prompts=(True, False))
    assert prompts == [("small", True), ("small", False), ("medium", True), ("medium", False)]
    assert [(r.model, r.prompt) for r in rows] == prompts
    assert all(len(r.offsets_ms) == 2 for r in rows)  # 3 cảnh → 2 mốc cắt, báo từng mốc


@needs_ffmpeg
def test_bench_default_is_prompt_on_like_the_render_path(bench_project, monkeypatch):
    seen = []

    def fake(wav, prompt, cfg, log=print, *, steps=None, on_progress=None):
        seen.append(bool(prompt))
        run = FakeWhisper()(wav, prompt, cfg, log)
        return WhisperRun(run.syllables, steps[0], 1.0)

    monkeypatch.setattr(bench, "run_whisper", fake)
    bench.bench_align(bench_project, ["small"], bench.WhisperConfig(device="cpu"))
    assert seen == [True]


def test_format_rows_lists_prompt_per_mark_offsets_and_timeouts():
    text = format_rows(
        [
            BenchRow(
                "small", True, "small (cpu, int8)", 20.0, 0.629, 3684.0, 12374.0, [100.0, 12374.0]
            ),
            BenchRow("small", False, "small (cpu, int8)", 17.0, 0.894, 126.0, 350.0, [50.0, 350.0]),
            BenchRow(
                "large-v3", True, seconds=900.2, error="quá giới hạn 900 giây", timed_out=True
            ),
        ]
    )
    lines = text.splitlines()
    assert "prompt" in lines[0]
    assert " có " in lines[2] and " không " in lines[4]
    assert "từng mốc (ms): 100 12374" in text and "từng mốc (ms): 50 350" in text
    assert "QUÁ GIỚI HẠN THỜI GIAN sau 900,2 s: quá giới hạn 900 giây" in text
    assert "89,4%" in text


def test_cli_bench_align_prompt_option(monkeypatch, tmp_path, capsys):
    got = {}

    def fake_bench(project_dir, models, cfg, log=print, prompts=(True,)):
        got["prompts"] = prompts
        return [BenchRow("small", True, "small (cpu, int8)", 1.0, 1.0, 0.0, 0.0)]

    monkeypatch.setattr(cli, "bench_align", fake_bench)
    for flag, expected in (("on", (True,)), ("off", (False,)), ("both", (True, False))):
        assert cli.main(["bench-align", str(tmp_path), "--prompt", flag]) == 0
        assert got["prompts"] == expected
    with pytest.raises(SystemExit):
        cli.main(["bench-align", str(tmp_path), "--prompt", "maybe"])
