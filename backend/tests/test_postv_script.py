"""Từ che và kiểm tra kịch bản PostV (docs/postv/IMPLEMENT-POSTV.md mục 6b)."""

import pytest

from hbt.postv.censor import CensorStore, compile_censor, find_censor_hits, normalize
from hbt.postv.models import PostvProject
from hbt.postv.script import LONG_SECONDS, READ_CPS, check_script, estimate_seconds, voice_chars
from hbt.sensitive import SensitiveStore


@pytest.fixture
def lists(tmp_path):
    return SensitiveStore(tmp_path).load(), CensorStore(tmp_path).load()


@pytest.fixture
def censor(lists):
    return compile_censor(*lists)


def hits(text, matchers):
    return [h.word for h in find_censor_hits(text, matchers)]


def project(voices, **over):
    return PostvProject.model_validate(
        {
            "slug": "a",
            "title": "A",
            "segments": [{"role": "commentary", "voice": v} for v in voices],
            **over,
        }
    )


def test_default_list_has_swear_words_at_block_level(lists):
    _, mine = lists
    assert [(c.id, c.level) for c in mine.categories] == [("tuc", "block")]
    assert {"vcl", "đéo", "địt"} <= set(mine.categories[0].words)


def test_censor_matches_whole_words_with_accents(censor):
    assert hits("peak vcl thật", censor) == ["vcl"]
    assert hits("Đéo hiểu", censor) == ["đéo"]
    assert hits("đeo kính và dẻo dai", censor) == []  # khác dấu, không bị nhầm
    assert hits("vclone và avl", censor) == []  # chỉ khớp nguyên từ


def test_censor_is_case_insensitive_and_nfc(censor):
    import unicodedata

    assert hits("VCL!!", censor) == ["vcl"]
    assert hits(unicodedata.normalize("NFD", "ĐÉO"), censor) == ["đéo"]


def test_censor_multiword_phrase(censor):
    assert hits("đụ   má nó", censor) == ["đụ má"]


def test_censor_hit_positions_follow_the_text(censor):
    text = "peak vcl rồi vl"
    found = find_censor_hits(text, censor)
    assert [(h.word, normalize(text)[h.start : h.end]) for h in found] == [
        ("vcl", "vcl"),
        ("vl", "vl"),
    ]
    assert [h.start for h in found] == sorted(h.start for h in found)


def test_only_block_level_words_are_censored_by_default(lists, censor):
    assert hits("uống bia và rượu", censor) == []  # mức cảnh báo của HBT: chỉ nhắc
    assert hits("dính ma tuý", censor) == ["ma tuý"]  # mức chặn của HBT cũng bị che
    assert hits("uống bia", compile_censor(*lists, levels=("block", "warn"))) == ["bia"]


def test_voice_chars_counts_like_one_space_between_words():
    assert voice_chars("  Xin   chào \n bạn ") == len("Xin chào bạn")


def test_estimate_seconds_uses_measured_reading_rate():
    assert estimate_seconds(165) == pytest.approx(10.0)
    assert READ_CPS == 16.5


def test_check_reports_seconds_chars_and_segments(censor):
    r = check_script(project(["a" * 33, "b" * 66]), censor)
    assert r["chars"] == 99 and r["seconds"] == 6.0 and r["long"] is False
    assert [s["seconds"] for s in r["segments"]] == [2.0, 4.0]
    assert r["issues"] == []


def test_long_video_is_only_a_reminder(censor):
    chars = int(LONG_SECONDS * READ_CPS)
    r = check_script(project(["x" * chars]), censor)
    assert r["long"] is True
    assert [(i["level"], i["where"]) for i in r["issues"]] == [("warn", "Cả video")]
    short = check_script(project(["x" * (chars - 20)]), censor)
    assert short["long"] is False and short["issues"] == []


def test_no_lower_limit_and_no_commentary_or_copy_warnings(censor):
    only_post = PostvProject.model_validate(
        {"slug": "a", "title": "A", "segments": [{"role": "post", "voice": "Ngắn"}]}
    )
    assert check_script(only_post, censor)["issues"] == []  # K-39: không nhắc commentary/nguyên văn


def test_censored_words_are_reported_as_info_per_place(censor):
    p = project(["peak vcl", "ổn"], post={"text": "đéo hiểu"})
    r = check_script(p, censor)
    assert r["censored"] == 2
    assert [(i["where"], i["level"], i["word"]) for i in r["issues"]] == [
        ("Bài gốc", "info", "đéo"),
        ("Đoạn 1", "info", "vcl"),
    ]


def test_only_picked_comments_are_scanned(censor):
    p = project(
        ["ok"],
        comments=[
            {"id": "c1", "text": "vcl", "picked": True},
            {"id": "c2", "text": "vl", "picked": False},
        ],
    )
    assert [i["where"] for i in check_script(p, censor)["issues"]] == ["Bình luận c1"]


def test_censor_off_turns_hits_into_reminders(censor):
    p = project(["vcl"], settings={"censor": {"enabled": False}})
    r = check_script(p, censor)
    assert r["censored"] == 0 and [i["level"] for i in r["issues"]] == ["warn"]


def test_hbt_warning_words_are_reminders_not_censored(lists, censor):
    hbt, _ = lists
    r = check_script(project(["uống bia vui lắm"]), censor, hbt)
    assert r["censored"] == 0
    assert [(i["level"], i["word"]) for i in r["issues"]] == [("warn", "bia")]


def test_censor_store_user_file_overrides_default(tmp_path):
    store = CensorStore(tmp_path)
    words = store.load()
    words.categories[0].words.append("xyz")
    store.save(words)
    assert (tmp_path / "settings" / "postv_censor_words.json").is_file()
    assert "xyz" in CensorStore(tmp_path).load().categories[0].words
