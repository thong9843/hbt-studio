from tests.helpers import skip_ffmpeg_tests

HAS = lambda _: "/usr/bin/ffmpeg"  # noqa: E731
MISSING = lambda _: None  # noqa: E731


def test_never_skips_when_ffmpeg_is_installed():
    assert skip_ffmpeg_tests({}, HAS) is False
    assert skip_ffmpeg_tests({"CI": "true"}, HAS) is False


def test_skips_on_a_personal_machine_without_ffmpeg():
    assert skip_ffmpeg_tests({}, MISSING) is True
    assert skip_ffmpeg_tests({"CI": "false"}, MISSING) is True


def test_does_not_skip_on_ci_without_ffmpeg_so_tests_fail_loudly():
    assert skip_ffmpeg_tests({"CI": "true"}, MISSING) is False
    assert skip_ffmpeg_tests({"CI": "TRUE"}, MISSING) is False
