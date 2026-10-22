import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_annotate.py"


@pytest.fixture(scope="module")
def ci():
    spec = importlib.util.spec_from_file_location("ci_annotate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REPORT = """<testsuites><testsuite name="pytest" tests="3">
<testcase classname="tests.test_a" name="test_ok"/>
<testcase classname="tests.test_a" name="test_bad[x:y,z]">
  <failure message="assert 1 == 2">E   assert 1 == 2
E   100% sure</failure>
</testcase>
<testcase classname="tests.test_b" name="test_err"><error message="boom">trace</error></testcase>
</testsuite></testsuites>"""


def test_failures_lists_failed_and_errored_tests(ci, tmp_path):
    import xml.etree.ElementTree as ET

    bad = ci.failures(ET.fromstring(REPORT))
    assert [n for n, _ in bad] == ["tests.test_a.test_bad[x:y,z]", "tests.test_b.test_err"]
    assert "assert 1 == 2" in bad[0][1] and bad[1][1].startswith("boom")


def test_main_prints_github_annotations_with_escaping(ci, tmp_path, capsys):
    report = tmp_path / "r.xml"
    report.write_text(REPORT, encoding="utf-8")
    assert ci.main(str(report)) == 0
    lines = capsys.readouterr().out.splitlines()
    errors = [line for line in lines if line.startswith("::error ")]
    assert len(errors) == 2
    # title: ":" và "," được mã hoá; data: xuống dòng và "%" được mã hoá
    assert errors[0].startswith("::error title=tests.test_a.test_bad[x%3Ay%2Cz]::assert 1 == 2%0A")
    assert "100%25 sure" in errors[0] and "\n" not in errors[0]
    assert lines[-1] == "::notice title=pytest::2 test lỗi"


def test_main_reports_an_unreadable_report(ci, tmp_path, capsys):
    assert ci.main(str(tmp_path / "missing.xml")) == 1
    assert capsys.readouterr().out.startswith("::error title=pytest::Không đọc được báo cáo")


def test_main_limits_the_number_of_annotations(ci, tmp_path, capsys):
    cases = "".join(
        f'<testcase classname="t" name="n{i}"><failure message="m">x</failure></testcase>'
        for i in range(15)
    )
    report = tmp_path / "r.xml"
    report.write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8")
    ci.main(str(report))
    out = capsys.readouterr().out.splitlines()
    assert sum(line.startswith("::error ") for line in out) == ci.MAX_ANNOTATIONS
    assert any("Còn 5 test lỗi nữa" in line for line in out)
