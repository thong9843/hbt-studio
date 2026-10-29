"""Thẻ bài PostV vẽ bằng Pillow (docs/postv/IMPLEMENT-POSTV.md mục 6)."""

import io

import numpy as np
import pytest
from PIL import Image, ImageFont

from hbt.postv.card import (
    FONT_DIR,
    composite_preview,
    hook_text_from_post,
    load_template,
    render_card,
    render_hook,
)
from hbt.postv.censor import CensorStore, compile_censor
from hbt.sensitive import SensitiveStore
from tests.test_api import client  # noqa: F401

TPL = load_template()
GREEN = (0x38, 0xE1, 0x78, 255)


@pytest.fixture(scope="module")
def censor(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("words")
    return compile_censor(SensitiveStore(tmp).load(), CensorStore(tmp).load())


def bbox(img):
    return img.getchannel("A").getbbox()


def diff(a, b):
    """Hộp bao các điểm ảnh khác nhau (cả RGB lẫn alpha); None nếu hai ảnh giống hệt."""
    changed = np.argwhere(
        (np.asarray(a.convert("RGBA")) != np.asarray(b.convert("RGBA"))).any(axis=2)
    )
    if len(changed) == 0:
        return None
    return (*changed.min(axis=0)[::-1], *(changed.max(axis=0)[::-1] + 1))


def card(text="Hôm qua mình quên ví ở quán cà phê.", **kw):
    return render_card("user_a", "17 giờ", text, **kw)


def count_color(img, rgba):
    return int((np.asarray(img.convert("RGBA")) == np.array(rgba)).all(axis=2).sum())


# ------------------------------------------------------------------ mẫu
def test_template_fonts_exist_and_card_fits_the_canvas():
    for part in ("header", "body", "stats", "hook"):
        for key, value in TPL[part].items():
            if key.endswith("font"):
                assert (FONT_DIR / value).is_file(), (part, key, value)
    assert TPL["card"]["x"] + TPL["card"]["w"] <= TPL["canvas"]["w"]


# ------------------------------------------------------------------ thẻ bài/bình luận
def test_card_is_a_transparent_1080x1920_layer_with_the_measured_geometry():
    img, bottom = card()
    assert img.mode == "RGBA" and img.size == (1080, 1920)
    left, top, right, low = bbox(img)
    assert (left, right) == (72, 72 + 936)  # đo từ video mẫu: rộng ~87 %
    assert top == 282 and abs(low - bottom) <= 1
    assert img.getpixel((0, 0))[3] == 0  # ngoài thẻ trong suốt
    assert img.getpixel((600, top + 20))[:3] == (0xFD, 0xFD, 0xFD)  # nền thẻ


def test_card_top_can_be_moved():
    img, _ = card(top=700)
    assert bbox(img)[1] == 700


def test_header_shows_a_plain_grey_person_avatar_not_a_real_photo():
    img, _ = card()
    x = 72 + TPL["card"]["pad"]
    y = 282 + TPL["card"]["pad"]
    inner = [img.getpixel((x + dx, y + dy)) for dx in range(15, 55, 4) for dy in range(15, 55, 4)]
    greys = {px[:3] for px in inner if px[3] == 255}
    assert greys and all(abs(r - g) < 12 and abs(g - b) < 12 for r, g, b in greys)  # chỉ có màu xám
    assert img.getpixel((x, y))[:3] == (0xFD, 0xFD, 0xFD)  # góc ô avatar là nền thẻ (hình tròn)


def test_height_grows_with_text_and_stops_at_max_lines():
    short = bbox(card("Ngắn")[0])[3]
    mid = bbox(card("Một câu dài hơn một chút " * 3)[0])[3]
    long = bbox(card("Rất dài " * 400)[0])[3]
    longer = bbox(card("Rất dài " * 800)[0])[3]
    assert short < mid < long
    assert long == longer  # cắt ở số dòng tối đa, thêm `…`


def test_stats_row_and_views_line_only_appear_when_given():
    none = bbox(card()[0])[3]
    likes = bbox(card(likes=1200)[0])[3]
    full = bbox(card(likes=1200, replies=3, reposts=4, shares=5, views=185000)[0])[3]
    assert none < likes < full


def test_stats_are_drawn_in_the_row_not_hidden():
    plain, _ = card(likes=1)
    more, _ = card(likes=1, replies=2)
    assert diff(plain, more) is not None  # thêm một số liệu thì hàng số liệu đổi


def test_vietnamese_diacritics_have_glyphs_in_every_font():
    """Pillow vẽ ô vuông `.notdef` cho chữ thiếu: mọi dấu tiếng Việt phải khác ô đó."""
    letters = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ"
    for name in ("BeVietnamPro-Medium.ttf", "BeVietnamPro-Bold.ttf", "BeVietnamPro-ExtraBold.ttf"):
        font = ImageFont.truetype(str(FONT_DIR / name), 60)
        missing = bytes(font.getmask(""))
        for ch in letters:
            assert bytes(font.getmask(ch)) != missing, (name, ch)


def test_different_text_draws_different_pixels():
    assert diff(card("Cà phê")[0], card("Cà phê ệ")[0]) is not None


# ------------------------------------------------------------------ che từ
def test_censor_blurs_only_the_hit_word(censor):
    text = "Thật sự peak vcl luôn đấy"
    plain, _ = card(text)
    blurred, _ = card(text, censor=censor)
    stars, _ = card(text, censor=censor, censor_mode="stars")
    assert diff(plain, blurred) is not None and diff(blurred, stars) is not None
    # dòng đầu của chữ: nửa trái (trước từ bị che) không đổi
    x0 = 72 + TPL["card"]["pad"]
    y0 = 282 + TPL["card"]["pad"] + TPL["header"]["avatar"] + TPL["body"]["gap"]
    left = (x0, y0, x0 + 200, y0 + 56)
    assert diff(plain.crop(left), blurred.crop(left)) is None


def test_censor_without_hit_or_without_list_changes_nothing(censor):
    text = "Đọc mà thấy ấm lòng ghê"
    assert diff(card(text)[0], card(text, censor=censor)[0]) is None
    assert diff(card("peak vcl")[0], card("peak vcl", censor=None)[0]) is None


def test_censor_does_not_hit_a_different_accent(censor):
    assert diff(card("đeo kính")[0], card("đeo kính", censor=censor)[0]) is None


# ------------------------------------------------------------------ thẻ tiêu đề
def test_hook_card_is_centered_with_an_accent_pill():
    img, bottom = render_hook("Nhờ AI viết văn chê AI", "chê ai")
    assert img.size == (1080, 1920)
    left, top, right, low = bbox(img)
    assert (left, right) == (72, 72 + 936) and top == TPL["hook"]["top"] and abs(low - bottom) <= 1
    assert count_color(img, GREEN) > 2000  # ô nhấn màu xanh có thật


def test_hook_without_matching_accent_has_no_pill():
    assert count_color(render_hook("Nhờ AI viết văn chê AI", "")[0], GREEN) == 0
    assert count_color(render_hook("Nhờ AI viết văn chê AI", "không có")[0], GREEN) == 0


def test_hook_accent_is_case_insensitive_and_censor_applies(censor):
    assert count_color(render_hook("Nhờ AI viết văn CHÊ AI", "chê ai")[0], GREEN) > 2000
    a, _ = render_hook("Peak vcl luôn", "", censor=censor)
    b, _ = render_hook("Peak vcl luôn", "")
    assert diff(a, b) is not None


def test_hook_is_cut_at_max_lines():
    short = render_hook("Từ " * 10)[1]
    huge = render_hook("Rất dài " * 300)[1]
    huger = render_hook("Rất dài " * 600)[1]
    assert short < huge == huger


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Câu một. Câu hai dài hơn.", "Câu một."),
        ("Không có dấu chấm nhưng ngắn", "Không có dấu chấm nhưng ngắn"),
        ("", ""),
        ("Dòng một\nDòng hai", "Dòng một Dòng hai"),
    ],
)
def test_hook_text_from_post(text, expected):
    assert hook_text_from_post(text) == expected


def test_hook_text_from_post_cuts_long_first_sentences_at_a_word():
    out = hook_text_from_post("từ " * 40 + "hết.", limit=30)
    assert out.endswith("…") and len(out) <= 31 and " …" not in out


# ------------------------------------------------------------------ xem trước
def test_composite_preview_on_flat_colour_and_on_a_frame():
    layer, _ = card()
    flat = composite_preview(layer, None)
    assert flat.mode == "RGB" and flat.size == (1080, 1920)
    assert flat.getpixel((5, 5)) == (0x6D, 0xB3, 0x3F)
    frame = Image.new("RGB", (270, 480), (10, 20, 200))
    on_frame = composite_preview(layer, frame)
    assert on_frame.getpixel((5, 5)) == (10, 20, 200)
    assert on_frame.getpixel((600, 300)) == (0xFD, 0xFD, 0xFD)  # thẻ vẫn nằm trên nền


# ------------------------------------------------------------------ API
@pytest.fixture
def pv(client):  # noqa: F811
    r = client.post("/api/projects", json={"title": "Bài thẻ", "kind": "postv"})
    body = r.json()
    body["post"].update(handle="user_a", age="17 giờ", text="Hôm qua mình quên ví ở quán cà phê.")
    body["post"].update(likes=27600, replies=351, shares=210)
    body["comments"] = [
        {"id": "c1", "handle": "user_b", "age": "14 giờ", "text": "Peak vcl thật", "picked": True}
    ]
    assert client.put("/api/projects/bai-the", json=body).status_code == 200
    return body


def png(client, slug="bai-the", **params):  # noqa: F811
    r = client.get(f"/api/projects/{slug}/postv/card.png", params=params)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    return Image.open(io.BytesIO(r.content))


def test_api_card_defaults_and_resize(client, pv):  # noqa: F811
    full = png(client)
    assert full.size == (1080, 1920) and full.mode == "RGB"
    assert png(client, w=288).size == (288, 512)
    layer = png(client, layer="true")
    assert layer.mode == "RGBA" and layer.getpixel((0, 0))[3] == 0


def test_api_all_card_kinds(client, pv):  # noqa: F811
    hook = png(client, kind="hook", layer="true")
    post = png(client, kind="post", layer="true")
    comment = png(client, kind="comment", ref="c1", layer="true")
    assert bbox(hook)[1] == TPL["hook"]["top"] and bbox(post)[1] == bbox(comment)[1] == 282
    assert diff(post, comment) is not None


def test_api_hook_uses_saved_text_else_the_first_sentence(client, pv):  # noqa: F811
    before = png(client, kind="hook", layer="true")
    pv["hook"] = {"text": "Quên ví ở quán cà phê", "accent": "quên ví"}
    assert client.put("/api/projects/bai-the", json=pv).status_code == 200
    after = png(client, kind="hook", layer="true")
    assert diff(before, after) is not None and count_color(after, GREEN) > 1000
    assert count_color(before, GREEN) == 0


def test_api_blur_card_switch_changes_the_comment_card(client, pv):  # noqa: F811
    on = png(client, kind="comment", ref="c1", layer="true")
    pv["settings"]["censor"]["blur_card"] = False
    client.put("/api/projects/bai-the", json=pv)
    off = png(client, kind="comment", ref="c1", layer="true")
    assert diff(on, off) is not None
    pv["settings"]["censor"].update(blur_card=True, text="stars")
    client.put("/api/projects/bai-the", json=pv)
    stars = png(client, kind="comment", ref="c1", layer="true")
    assert diff(on, stars) is not None and diff(off, stars) is not None


def test_api_card_errors(client, pv):  # noqa: F811
    base = "/api/projects/bai-the/postv/card.png"
    assert client.get(base, params={"kind": "comment"}).status_code == 422
    assert client.get(base, params={"kind": "comment", "ref": "c9"}).status_code == 404
    assert client.get(base, params={"kind": "to"}).status_code == 422
    assert client.get(base, params={"w": 5}).status_code == 422
    assert client.get("/api/projects/khong-co/postv/card.png").status_code == 404
    video = client.post("/api/projects", json={"title": "Muỗi", "scene_count": 3}).json()
    assert client.get(f"/api/projects/{video['slug']}/postv/card.png").status_code == 400
