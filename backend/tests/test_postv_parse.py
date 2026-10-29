"""Tách bài/bình luận từ chữ dán và đọc số liệu (docs/postv/IMPLEMENT-POSTV.md mục 5b)."""

import json
import socket
import unicodedata
from pathlib import Path

import pytest

from hbt.postv.counts import parse_count
from hbt.postv.parse import MAX_TEXT, age_label, parse_threads_text

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "shared" / "count_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tách chữ là hàm thuần: không được mở kết nối nào (docs/postv D2, D3)."""

    def boom(*_a, **_k):
        raise AssertionError("parse không được dùng mạng")

    monkeypatch.setattr(socket.socket, "connect", boom)


@pytest.mark.parametrize("case", CASES, ids=[c["in"] or "rong" for c in CASES])
def test_parse_count_shared_cases(case):
    assert parse_count(case["in"]) == case["out"]


def test_parse_count_accepts_none():
    assert parse_count(None) is None


# Mẫu 1: tuổi dạng `17h`; thân có 2 dấu cách cuối dòng và emoji (tên tài khoản là giả).
SAMPLE_AGE = (
    "user_a\n17h\nThương chị tài xế chắc chị chặn khách ngồi sau  \n"
    "user_b\n14h\nBớt suy diễn đi má ơi  \n"
    "user_c\n14h\nNhưng tài xế nam cũng bị mà :))  \n"
    "user_d\n13h\nXin link mua\n"
    "user_e\n9h\nUi hay mà tinh tế lắm 👌 đỡ đụng chạm  \n"
    "user_f\n1h\nMé đàn ông bị dê ngược\nĐúng bọn xàm.\n"
)


def test_sample_with_relative_age():
    r = parse_threads_text(SAMPLE_AGE)
    assert r.guess == "threads_text" and r.source_url is None
    assert (r.post.handle, r.post.age) == ("user_a", "17 giờ")
    assert r.post.text == "Thương chị tài xế chắc chị chặn khách ngồi sau"
    assert [c.id for c in r.comments] == ["c1", "c2", "c3", "c4", "c5"]
    assert [c.handle for c in r.comments][:2] == ["user_b", "user_c"]
    assert r.comments[3].text == "Ui hay mà tinh tế lắm 👌 đỡ đụng chạm"
    assert r.comments[4].text == "Mé đàn ông bị dê ngược\nĐúng bọn xàm."  # thân nhiều dòng
    assert r.hints == [] and r.warnings == []


def test_first_three_comments_are_picked_by_default():
    r = parse_threads_text(SAMPLE_AGE)
    assert [c.picked for c in r.comments] == [True, True, True, False, False]


# Mẫu 2: ngày tuyệt đối MM/DD/YY, dòng nhiễu `1`, `/`, `2` và chữ giao diện `Translate`.
SAMPLE_DATE = (
    "user_a\n08/25/26\nRồi câu này liên quan gì vậy  \n \n1\n/\n2\n"
    "user_b\n08/25/26\nÍ là ngón tay út liên quan gì lời hứa?  \n"
    "user_c\n08/26/26\nTranslate\nCâu đó xuất phát từ tiếng anh  \n"
    "user_a\n08/25/26\nUpdate là chủ thớt khoá nick  \n2/2\n"
)


def test_sample_with_absolute_date_and_page_counter():
    r = parse_threads_text(SAMPLE_DATE)
    assert r.post.age == "25/08/2026"
    assert r.post.text == "Rồi câu này liên quan gì vậy"  # bộ ba `1 / 2` bị bỏ
    assert r.comments[0].age == "25/08/2026" and r.comments[1].age == "26/08/2026"
    assert r.comments[1].text == "Câu đó xuất phát từ tiếng anh"  # `Translate` bị bỏ


def test_same_author_continuation_is_flagged():
    r = parse_threads_text(SAMPLE_DATE)
    assert [c.same_author for c in r.comments] == [False, False, True]


@pytest.mark.parametrize(
    ("raw", "label"),
    [
        ("17h", "17 giờ"),
        ("5d", "5 ngày"),
        ("30m", "30 phút"),
        ("2w", "2 tuần"),
        ("10s", "10 giây"),
        ("3 giờ", "3 giờ"),
        ("08/25/26", "25/08/2026"),
        ("25/12/2026", "25/12/2026"),
        ("12/05/26", "05/12/2026"),
        ("hôm qua", "hôm qua"),
    ],
)
def test_age_label(raw, label):
    assert age_label(raw) == label


def test_stat_lines_are_reported_not_kept_in_text():
    r = parse_threads_text("user_a\n1h\nBài gốc\nuser_b\n2h\nHay quá\n1.2K\n")
    assert r.comments[0].text == "Hay quá"
    assert [(h.block, h.raw, h.value) for h in r.hints] == [(1, "1.2K", 1200)]
    assert any("số liệu" in w for w in r.warnings)


def test_a_body_that_is_only_a_number_is_kept():
    r = parse_threads_text("user_a\n1h\nBài gốc\nuser_b\n2h\n1\n")
    assert r.comments[0].text == "1" and r.hints == []


def test_handle_without_age_line_is_not_a_header():
    r = parse_threads_text("user_a\nxin chào\nuser_b\n1h\nbody")
    assert r.guess == "threads_text" and r.post.handle == "user_b"  # chỉ khối có dòng tuổi


def test_single_block_warns_there_are_no_comments():
    r = parse_threads_text("user_a\n1h\nChỉ có bài")
    assert r.comments == [] and any("chưa có bình luận" in w for w in r.warnings)


def test_empty_body_block_warns():
    r = parse_threads_text("user_a\n1h\nuser_b\n2h\nCó chữ")
    assert r.post.text == "" and any("không có chữ" in w for w in r.warnings)


def test_unknown_text_falls_back_to_unknown():
    r = parse_threads_text("Xin chào, đây chỉ là một đoạn văn bình thường.")
    assert r.guess == "unknown" and r.post is None and r.warnings


def test_windows_line_endings_and_nfc():
    decomposed = unicodedata.normalize("NFD", "Đọc mà thấy ấm lòng")
    r = parse_threads_text(f"user_a\r\n1h\r\n{decomposed}\r\nuser_b\r\n2h\r\nok\r\n")
    assert r.post.text == "Đọc mà thấy ấm lòng"
    assert unicodedata.is_normalized("NFC", r.post.text)
    assert r.comments[0].text == "ok"


def test_share_link_on_top_is_kept_as_source_only():
    r = parse_threads_text("https://www.threads.com/share/ABC123/\nuser_a\n1h\nBài\n")
    assert r.source_url == "https://www.threads.com/share/ABC123/"
    assert r.post.text == "Bài"


EMBED = (
    '<blockquote class="text-post-media" data-text-post-permalink='
    '"https://www.threads.com/@user_a/post/ABC" data-text-post-version="0" id="ig-tp-ABC">'
    '<a href="https://www.threads.com/@user_a/post/ABC"><svg><path d="M1 1"/></svg>'
    "View on Threads</a></blockquote>\n"
    '<script async src="https://www.threads.com/embed.js"></script>\n'
)


def test_embed_code_only_gives_the_link():
    r = parse_threads_text(EMBED)
    assert r.guess == "embed" and r.post is None and r.comments == []
    assert r.source_url == "https://www.threads.com/@user_a/post/ABC"
    assert any("Mã nhúng" in w for w in r.warnings)


def test_embed_code_followed_by_text_parses_the_text():
    r = parse_threads_text(EMBED + "user_a\n17h\nBài gốc\nuser_b\n1h\nBình luận\n")
    assert r.guess == "threads_text"
    assert r.source_url == "https://www.threads.com/@user_a/post/ABC"
    assert "View on Threads" not in r.post.text and "<script" not in r.post.text
    assert len(r.comments) == 1


def test_embed_with_non_https_permalink_is_ignored():
    r = parse_threads_text(
        '<blockquote data-text-post-permalink="javascript:alert(1)">x</blockquote>'
    )
    assert r.source_url is None


def test_too_long_text_is_rejected():
    with pytest.raises(ValueError, match="dài quá"):
        parse_threads_text("a" * (MAX_TEXT + 1))
