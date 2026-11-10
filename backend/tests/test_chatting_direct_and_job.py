"""Tests cho chế độ Dán kịch bản trực tiếp (Bypass LLM) và lưu trữ job.json."""

from pathlib import Path

from hbt.chatting.sources import parse_direct_script
from hbt.chatting.stickers import count_stickers_per_tag, pick_sticker
from hbt.chatting.store import load_job, save_job


def test_parse_direct_script_two_characters():
    text = """
    Minh: Ê nay rảnh không đi cafe?
    Linh: Tầm mấy giờ thế? (cười)
    Minh: 8h tối nha [sticker: ok]
    Linh: Ok bạn ơi!
    """
    res = parse_direct_script(text)
    assert res["title"] != ""
    assert len(res["characters"]) == 2

    # Người đầu tiên phải bên phải ('me')
    c_me = res["characters"][0]
    assert c_me["id"] == "me"
    assert c_me["name"] == "Minh"
    assert c_me["side"] == "right"

    # Người thứ hai phải bên trái
    c_linh = res["characters"][1]
    assert c_linh["name"] == "Linh"
    assert c_linh["side"] == "left"

    assert len(res["messages"]) == 4
    # Kiểm tra sticker bóc tách
    assert res["messages"][1]["sticker"] == "cuoi"
    assert res["messages"][2]["sticker"] == "ok"


def test_save_and_load_job(tmp_path: Path):
    workspace = tmp_path
    slug = "test-job-slug"

    assert load_job(workspace, slug) is None

    job_data = {
        "slug": slug,
        "status": "running",
        "phase": "fetch",
        "percent": 15,
        "text": "Đang lấy bài...",
    }
    save_job(workspace, slug, job_data)

    loaded = load_job(workspace, slug)
    assert loaded is not None
    assert loaded["status"] == "running"
    assert loaded["percent"] == 15
    assert loaded["phase"] == "fetch"


def test_pick_meme_from_library(tmp_path: Path):
    # Tạo cấu trúc library/memes giả lập
    library = tmp_path / "library"
    memes = library / "memes"
    memes.mkdir(parents=True)
    idx = {"soc": ["shocked_cat.mp4"], "cuoi": ["laugh_cat.mp4"]}
    (memes / "index.json").write_text(__import__("json").dumps(idx), encoding="utf-8")
    (memes / "shocked_cat.mp4").write_bytes(b"fake video")

    counts = count_stickers_per_tag(library)
    assert counts["soc"] == 1
    assert counts["cuoi"] == 1

    picked = pick_sticker(library, "soc", seed=0)
    assert picked is not None
    assert picked.name == "shocked_cat.mp4"
