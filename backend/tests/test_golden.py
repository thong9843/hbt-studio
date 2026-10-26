"""golden-import: nhãn Audacity → golden_marks.json (IMPLEMENT.md 10b)."""

import json

import pytest

import cli
from hbt.pipeline import golden
from hbt.pipeline.golden import GoldenError, import_labels

DATA = {
    "tolerance_sec": 0.2,
    "marks": [
        {"index": i, "scene": 1 + i // 2, "text": f"cụm {i}", "start": None} for i in (1, 2, 3)
    ],
}


def labels(*rows):
    return "\n".join("\t".join(str(x) for x in r) for r in rows) + "\n"


def test_full_labels_fill_start_and_keep_the_rest():
    text = labels((0.1234, 0.2, ""), (1.5, 1.6, "2"), (2.0004, 2.1, "x"))
    out = import_labels(DATA, text, duration=10)
    assert [m["start"] for m in out["marks"]] == [0.123, 1.5, 2.0]
    assert [(m["index"], m["scene"], m["text"]) for m in out["marks"]] == [
        (m["index"], m["scene"], m["text"]) for m in DATA["marks"]
    ]
    assert DATA["marks"][0]["start"] is None  # đầu vào không bị sửa


def test_backslash_and_blank_lines_are_ignored():
    text = "\\\t100.000000\t2000.000000\n\n" + labels((0.5, 0.6, ""), (1, 1.1, ""), (2, 2.1, ""))
    assert len(import_labels(DATA, text, 10)["marks"]) == 3


@pytest.mark.parametrize(
    ("rows", "msg"),
    [
        ([(1, 1, ""), (2, 2, "")], "Thiếu 1 nhãn"),
        ([(1, 1, ""), (2, 2, ""), (3, 3, ""), (4, 4, "")], "Thừa 1 nhãn"),
        ([(1, 1, ""), (1, 1, ""), (3, 3, "")], "không lớn hơn nhãn trước"),
        ([(2, 2, ""), (1, 1, ""), (3, 3, "")], "không lớn hơn nhãn trước"),
        ([(1, 1, ""), (2, 2, "3"), (3, 3, "")], "phải bằng thứ tự 2"),
        ([(-1, 1, ""), (2, 2, ""), (3, 3, "")], "nằm ngoài file giọng"),
        ([(1, 1, ""), (2, 2, ""), (10, 11, "")], "nằm ngoài file giọng"),
    ],
)
def test_invalid_labels_raise_vietnamese_error(rows, msg):
    with pytest.raises(GoldenError, match=msg):
        import_labels(DATA, labels(*rows), duration=10)


def test_import_file_writes_nothing_when_invalid(tmp_path):
    marks = tmp_path / "golden_marks.json"
    marks.write_text(json.dumps(DATA), encoding="utf-8")
    (tmp_path / "labels.txt").write_text(labels((1, 1, "")), encoding="utf-8")
    with pytest.raises(GoldenError):
        golden.import_file(tmp_path, None, 10)
    assert json.loads(marks.read_text(encoding="utf-8")) == DATA


def test_cli_golden_import_ok_and_error(tmp_path, monkeypatch, capsys):
    (tmp_path / "golden_marks.json").write_text(json.dumps(DATA), encoding="utf-8")
    monkeypatch.setattr(cli, "media_duration", lambda p: 10.0)
    lab = tmp_path / "l.txt"
    lab.write_text(labels((1, 1, ""), (2, 2, ""), (3, 3, "")), encoding="utf-8")
    assert cli.main(["golden-import", str(tmp_path), "--labels", str(lab)]) == 0
    saved = json.loads((tmp_path / "golden_marks.json").read_text(encoding="utf-8"))
    assert [m["start"] for m in saved["marks"]] == [1, 2, 3]
    lab.write_text(labels((1, 1, "")), encoding="utf-8")
    assert cli.main(["golden-import", str(tmp_path), "--labels", str(lab)]) == 1
    assert "Thiếu 2 nhãn" in capsys.readouterr().err
