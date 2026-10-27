import numpy as np
import pytest
from PIL import Image

from hbt.pipeline import thumbnail as th

LINES3 = ["BẠN CÓ PHẢI", "NGƯỜI ĐƯỢC", "MUỖI YÊU?"]


@pytest.fixture
def bg(tmp_path):
    path = tmp_path / "bg.png"
    Image.new("RGB", (1080, 1920), (60, 90, 110)).save(path)
    return path


# ---------------------------------------------------------------- chữ
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("đường", "ĐƯỜNG"),
        ("ư", "Ư"),
        ("ỷ", "Ỷ"),
        ("muỗi yêu?", "MUỖI YÊU?"),
        ("ỷ".replace("ỷ", "ỷ"), "Ỷ"),  # gõ rời dấu (NFD) → NFC rồi in hoa
        ("  hay biết  ", "HAY BIẾT"),
    ],
)
def test_lines_are_nfc_then_upper(raw, expected):
    assert th.title_lines([raw]) == [expected]


def test_variable_font_is_in_the_repo_and_used():
    assert th.title_font_name() == "Bricolage Grotesque"
    f = th.title_font(100)
    axes = {a["name"]: a for a in f.get_variation_axes()}
    assert axes[b"Weight"]["maximum"] == 800 and axes[b"Width"]["minimum"] == 75


def test_falls_back_to_be_vietnam_pro_when_the_font_is_missing(tmp_path):
    (tmp_path / "BeVietnamPro-ExtraBold.ttf").write_bytes(
        (th.FONT_DIR / "BeVietnamPro-ExtraBold.ttf").read_bytes()
    )
    assert th.title_font_name(tmp_path) == "Be Vietnam Pro ExtraBold"
    boxes = th.title_ink_boxes(LINES3, tmp_path)
    assert boxes and all(600 <= b[1] and b[3] <= 1320 for b in boxes)


# ---------------------------------------------------------------- bố cục
@pytest.mark.parametrize(
    "lines",
    [
        LINES3,
        ["HAI DÒNG", "THÔI"],
        ["ẨN Ữ", "ẶỖ ỢỶ ĐẸP", "CHỮ DẤU CHỒNG ẨỮẶ"],  # dấu chồng ở dòng đầu và dòng cuối
        ["MỘT DÒNG RẤT RẤT DÀI CẦN CO NHỎ LẠI", "NGƯỜI ĐƯỢC YÊU QUÝ NHẤT", "ĐƯỢC KHÔNG NHỈ?"],
    ],
)
def test_title_block_stays_inside_the_3x2_safe_zone(lines):
    boxes = th.title_ink_boxes(lines)
    assert min(b[1] for b in boxes) >= 600 and max(b[3] for b in boxes) <= 1320
    assert all(b[0] >= 0 and b[2] <= th.W for b in boxes)
    total = sum(ln.size * 1.02 for ln in th.layout_title(lines))
    assert total <= th.MAX_BLOCK_HEIGHT + 1e-6


def test_sizes_follow_the_reference_rules():
    lay = th.layout_title(LINES3)
    base, last = lay[0].size, lay[-1].size
    assert base <= th.MAX_BASE and last <= th.LAST_MAX and last >= base
    for ln in lay:  # mọi dòng vừa 950 px
        w = th._width(ln.text, th.title_font(ln.size), ln.stroke)
        assert w <= th.MAX_WIDTH + 1
    assert [ln.last for ln in lay] == [False, False, True]
    assert all(ln.stroke == int(ln.size * 0.11) for ln in lay)


# ---------------------------------------------------------------- ảnh
def test_cover_size_accent_and_logo_in_the_safe_band(bg):
    img = th.render_cover(bg, LINES3, "Vì sao vậy ta?", accent="#00FF00")
    assert img.size == (1080, 1920) and img.mode == "RGB"
    arr = np.asarray(img).astype(int)
    green = (arr[..., 1] > 200) & (arr[..., 0] < 60) & (arr[..., 2] < 60)
    ys = np.where(green.any(axis=1))[0]
    assert len(ys) > 50 and ys.min() >= 600 and ys.max() <= 1320  # accent chỉ ở dòng cuối
    last_top = th.layout_title(LINES3)[-1].y
    assert ys.min() >= last_top - 40  # dấu của "Ỗ" nhô lên trên hộp chữ
    logo_h = int(
        Image.open(th.BRAND_DIR / th.LOGO_FILE).height
        * 300
        / Image.open(th.BRAND_DIR / th.LOGO_FILE).width
    )
    assert th.LOGO_Y + logo_h <= 1680
    assert th.PILL_Y >= 240 and th.PILL_Y + th.PILL_H <= 1680


def test_series_pill_is_optional(bg):
    with_pill = np.asarray(th.render_cover(bg, LINES3, "Vì sao vậy ta?")).astype(int)
    without = np.asarray(th.render_cover(bg, LINES3, "  ")).astype(int)
    band = slice(th.PILL_Y, th.PILL_Y + th.PILL_H)
    assert np.abs(with_pill[band] - without[band]).sum() > 0
    assert np.abs(with_pill[1500:] - without[1500:]).sum() == 0  # phần còn lại giữ nguyên


def test_missing_logo_or_background_raises(bg, tmp_path):
    with pytest.raises(FileNotFoundError):
        th.render_cover(bg, LINES3, "S", logo_path=tmp_path / "khong-co.png")
    with pytest.raises(FileNotFoundError):
        th.render_cover(tmp_path / "khong-co.png", LINES3, "S")


def test_save_covers_outputs_and_crop(bg, tmp_path):
    img = th.render_cover(bg, LINES3, "Vì sao vậy ta?")
    cover, youtube = th.save_covers(img, tmp_path)
    assert (cover.name, youtube.name) == ("cover_9x16.jpg", "youtube_3x2.jpg")
    a, b = Image.open(cover), Image.open(youtube)
    assert a.size == (1080, 1920) and b.size == (1080, 720) and a.format == "JPEG"
    assert cover.stat().st_size < 5 << 20 and "icc_profile" not in a.info
    same = np.abs(np.asarray(a.crop(th.CROP_3X2)).astype(int) - np.asarray(b).astype(int)).mean()
    assert same < 2.0  # youtube_3x2 là dải y=600..1320 của cùng ảnh
