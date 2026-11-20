"""Kiểm thử bộ mẫu phong cách, làm sạch chữ trích và sinh kịch bản tự động PVA."""

from pathlib import Path

from hbt.postv.auto_script import (
    build_auto_script,
    clean_voice_text,
    extract_hook_text,
    filter_comments,
    load_script_styles,
    shorten_comment,
)
from hbt.postv.models import PostvComment, PostvProject


def test_load_script_styles(tmp_path: Path):
    styles = load_script_styles()
    assert len(styles) == 5
    ids = [s.id for s in styles]
    assert "ke-chuyen" in ids
    assert "hai-huoc" in ids
    assert "drama" in ids
    assert "hong" in ids
    assert "cam-dong" in ids

    # Kiểm tra nạp từ file cấu hình người dùng
    user_file = tmp_path / "postv_script_styles.json"
    cfg = (
        '[{"id": "custom", "name": "Tuỳ chỉnh", "hook": ["{text}"], "intro_post": ["Bài:"], '
        '"intro_comment": ["Hỏi:"], "commentary": ["Ý:"], "outro": ["Hết."]}]'
    )
    user_file.write_text(cfg, encoding="utf-8")
    custom = load_script_styles(tmp_path)
    assert len(custom) == 1
    assert custom[0].id == "custom"


def test_clean_voice_text():
    raw = "Hôm nay ko đi chơi dc vs bạn =)) https://example.com/link ghé qua trc nhé :D {100} |"
    cleaned = clean_voice_text(raw)
    assert "không" in cleaned
    assert "được" in cleaned
    assert "với" in cleaned
    assert "trước" in cleaned
    assert "=))" not in cleaned
    assert ":D" not in cleaned
    assert "https://" not in cleaned
    assert "{" not in cleaned
    assert "}" not in cleaned
    assert "|" not in cleaned


def test_shorten_comment():
    short = "Bình luận ngắn gọn."
    assert shorten_comment(short) == "Bình luận ngắn gọn."

    long_text = "Câu một khá dài ở đây. " + ("Câu tiếp theo nội dung dài liên tục lặp lại. " * 10)
    res = shorten_comment(long_text, max_chars=100)
    assert len(res) <= 100
    assert res.endswith(".")


def test_filter_comments():
    comments = [
        PostvComment(id="c1", text="Ngắn", likes=100),  # < 8 ký tự -> bỏ
        PostvComment(id="c2", text="Bình luận có link https://spam.com", likes=200),  # link -> bỏ
        PostvComment(id="c3", text="Bình luận hợp lệ số 1 rất hay", likes=50),
        PostvComment(id="c4", text="Bình luận hợp lệ số 2 nhiều like", likes=500),
        PostvComment(id="c5", text="Bình luận hợp lệ số 3 vừa phải", likes=150),
        PostvComment(id="c6", text="Bình luận hợp lệ số 3 vừa phải", likes=80),  # trùng -> bỏ
    ]
    picked = filter_comments(comments, max_comments=2)
    assert len(picked) == 2
    # c4 (500 likes) và c5 (150 likes) được ưu tiên
    assert picked[0].id == "c4"
    assert picked[1].id == "c5"


def test_extract_hook_text():
    text = "Hôm qua mình bỏ quên ví ở quán cà phê. May mà bạn nhân viên cất giữ hộ cẩn thận."
    hook = extract_hook_text(text, max_chars=40)
    assert hook == "Hôm qua mình bỏ quên ví ở quán cà phê"
    assert len(hook) <= 40


def test_build_auto_script():
    project = PostvProject(
        slug="demo-pva",
        title="Demo PVA",
    )
    project.post.text = (
        "Hôm qua mình bỏ quên ví ở quán cà phê. May mà bạn nhân viên cất giữ hộ cẩn thận."
    )
    project.comments = [
        PostvComment(id="c1", text="Quán ở đâu vậy bạn ơi?", likes=20),
        PostvComment(id="c2", text="Người tốt việc tốt quá chừng luôn nè!", likes=35),
    ]

    p = build_auto_script(project, style_id="ke-chuyen", comments_count=2, seed=42)
    assert len(p.segments) >= 6
    roles = [s.role for s in p.segments]
    assert roles[0] == "hook"
    assert roles[1] == "post"
    assert roles[2] == "post"
    assert "comment" in roles
    assert "commentary" in roles

    # Đoạn dẫn dùng narrator, đoạn trích dùng tác giả/bình luận
    assert p.segments[0].speaker == "narrator"
    assert p.segments[1].speaker == "narrator"
    assert p.segments[2].speaker == "post"

    # Seed giống nhau tạo ra kết quả giống nhau
    p2 = PostvProject(slug="demo-pva", title="Demo PVA")
    p2.post.text = project.post.text
    p2.comments = [c.model_copy() for c in project.comments]
    build_auto_script(p2, style_id="ke-chuyen", comments_count=2, seed=42)
    assert [s.voice for s in p.segments] == [s.voice for s in p2.segments]
