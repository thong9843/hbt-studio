"""Giọng VieNeu cho HBT: tiền xử lý `{}` và `|`, sinh theo cảnh, nối, cache, lời đã đổi (G3, E4)."""

import json
import wave

import pytest

from hbt.gd2.prefs import Gd2Prefs
from hbt.gd2.voice import (
    build_hbt_plan,
    is_stale,
    read_meta,
    spoken_chunks,
    synthesize_hbt,
)
from hbt.models import Project, Scene, Voice
from hbt.pipeline.cancel import CancelToken, RenderCancelled, use_token
from hbt.postv.voice import GAP_SECONDS, FakeVoice, VoiceError, wav_seconds


def project_of(*voices, slug="muoi"):
    return Project(slug=slug, title="Muỗi", scenes=[Scene(voice=v) for v in voices])


def three():
    return project_of(
        "Có người ngồi cả buổi không sao, | có người bị đốt sưng cả chân.",
        "Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét.",
        "Thở nhiều | thì muỗi tìm bạn dễ hơn.",
    )


# ------------------------------------------------------------------ tiền xử lý lời
def test_braces_replace_display_text_and_keep_punctuation():
    assert spoken_chunks("Cao 10{mười} mét.") == ["Cao mười mét."]
    assert spoken_chunks("Có CO2{xi ô hai}, nhưng ít.") == ["Có xi ô hai, nhưng ít."]
    assert spoken_chunks("Gấp 100{một trăm}!") == ["Gấp một trăm!"]
    assert spoken_chunks("Năm 2024{hai nghìn không trăm hai mươi bốn}.") == [
        "Năm hai nghìn không trăm hai mươi bốn."
    ]


def test_pipe_splits_into_chunks_and_empty_ones_vanish():
    assert spoken_chunks("Một, | hai.") == ["Một,", "hai."]
    assert spoken_chunks("| Một | | hai |") == ["Một", "hai"]
    assert spoken_chunks("  ") == []
    assert spoken_chunks("|") == []
    assert spoken_chunks("{}") == []


def test_plain_text_is_unchanged():
    assert spoken_chunks("Xin chào các bạn.") == ["Xin chào các bạn."]


# ------------------------------------------------------------------ kế hoạch
def test_plan_has_one_chunk_per_piece_with_scene_index():
    plan = build_hbt_plan(three(), "v1")
    assert [(c.scene, c.text) for c in plan] == [
        (0, "Có người ngồi cả buổi không sao,"),
        (0, "có người bị đốt sưng cả chân."),
        (1, "Muỗi đánh hơi khí CO2 từ xa khoảng mười mét."),
        (2, "Thở nhiều"),
        (2, "thì muỗi tìm bạn dễ hơn."),
    ]


def test_plan_skips_scenes_without_text_and_fails_when_none():
    plan = build_hbt_plan(project_of("A.", "", "|", "B."), "v1")
    assert [c.scene for c in plan] == [0, 3]
    with pytest.raises(VoiceError):
        build_hbt_plan(project_of("", " ", "|"), "v1")


# ------------------------------------------------------------------ sinh giọng
def run(folder, project, voice_id="Adam", provider=None, progress=None):
    provider = provider or FakeVoice()
    plan = build_hbt_plan(project, voice_id)
    return synthesize_hbt(plan, folder, provider, progress), provider


def test_synthesize_sends_only_spoken_text_and_joins_with_gaps(tmp_path):
    result, provider = run(tmp_path, three())
    assert [t for t, _ in provider.calls][2] == "Muỗi đánh hơi khí CO2 từ xa khoảng mười mét."
    assert all("{" not in t and "|" not in t for t, _ in provider.calls)
    assert result.file == tmp_path / "voice.wav" and result.file.is_file()
    # tổng = độ dài các đoạn + 4 khoảng nghỉ 0,25 s (5 đoạn)
    parts = sum(max(0.3, len(t) / 16.5) for t, _ in provider.calls)
    assert wav_seconds(result.file) == pytest.approx(parts + 4 * GAP_SECONDS, abs=0.05)
    with wave.open(str(result.file), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
    assert [s["scene"] for s in result.scenes] == [0, 1, 2]
    assert result.scenes[0]["start"] == 0
    assert result.scenes[1]["start"] > result.scenes[0]["end"]  # có khoảng nghỉ giữa cảnh


def test_scene_spans_cover_their_chunks(tmp_path):
    result, provider = run(tmp_path, three())
    first = max(0.3, len(provider.calls[0][0]) / 16.5)
    second = max(0.3, len(provider.calls[1][0]) / 16.5)
    assert result.scenes[0]["end"] == pytest.approx(first + GAP_SECONDS + second, abs=0.05)


def test_cache_reuses_chunks_and_changed_text_regenerates_only_that_chunk(tmp_path):
    _, first = run(tmp_path, three())
    assert len(first.calls) == 5
    result, again = run(tmp_path, three())
    assert again.calls == [] and result.cached == 5 and result.generated == 0
    edited = project_of(
        "Có người ngồi cả buổi không sao, | có người bị đốt sưng cả chân.",
        "Muỗi đánh hơi khí CO2 từ xa khoảng 10{mười} mét.",
        "Thở nhiều | thì muỗi tìm bạn khó hơn.",
    )
    result, third = run(tmp_path, edited)
    assert [t for t, _ in third.calls] == ["thì muỗi tìm bạn khó hơn."]
    assert result.generated == 1 and result.cached == 4


def test_other_voice_is_a_different_cache_entry(tmp_path):
    run(tmp_path, three(), "Adam")
    _, other = run(tmp_path, three(), "Trúc Ly")
    assert len(other.calls) == 5 and {v for _, v in other.calls} == {"Trúc Ly"}


def test_progress_reports_scene_x_of_n(tmp_path):
    msgs = []
    run(tmp_path, three(), progress=lambda pct, step, msg: msgs.append((pct, step, msg)))
    texts = [m for _, _, m in msgs]
    assert "Đang đọc cảnh 1/3" in texts and "Xong cảnh 2/3" in texts
    assert "Đang đọc cảnh 3/3" in texts
    pcts = [p for p, _, _ in msgs]
    assert pcts == sorted(pcts) and pcts[-1] >= 96


def test_replaces_old_voice_files_of_other_extensions(tmp_path):
    (tmp_path / "voice.mp3").write_bytes(b"ID3")
    (tmp_path / "voice.wav").write_bytes(b"old")
    run(tmp_path, three())
    assert not (tmp_path / "voice.mp3").exists()
    assert wav_seconds(tmp_path / "voice.wav") > 1
    assert not (tmp_path / "build" / "hbt_voice.joined.wav").exists()


def test_failure_keeps_the_old_voice(tmp_path):
    (tmp_path / "voice.wav").write_bytes(b"old")
    # lỗi xảy ra trước khi nối: file cũ còn nguyên
    project = project_of("Một.", "Hai khó hơn.", "Ba.")
    with pytest.raises(VoiceError):
        run(tmp_path, project, provider=FakeVoice(fail_on="khó hơn"))
    assert (tmp_path / "voice.wav").read_bytes() == b"old"


def test_cancel_stops_and_keeps_old_voice(tmp_path):
    (tmp_path / "voice.wav").write_bytes(b"old")
    token = CancelToken()
    token.cancel()
    with use_token(token), pytest.raises(RenderCancelled):
        run(tmp_path, three(), provider=FakeVoice(delay=0.05))
    assert (tmp_path / "voice.wav").read_bytes() == b"old"


# ------------------------------------------------------------------ lời đã đổi
def test_is_stale_unknown_without_meta_or_when_voice_is_not_ours(tmp_path):
    p = three()
    assert is_stale(p, tmp_path) is None  # chưa sinh
    run(tmp_path, p)
    p.voice = Voice(file="voice.wav")
    assert is_stale(p, tmp_path) is False
    p.voice = Voice(file="voice.mp3")  # thả file Vbee sau đó
    assert is_stale(p, tmp_path) is None
    p.voice = None
    assert is_stale(p, tmp_path) is None


def test_is_stale_when_text_changes_not_when_only_other_fields_change(tmp_path):
    p = three()
    run(tmp_path, p)
    p.voice = Voice(file="voice.wav")
    p.scenes[0].punch = True  # đổi thẻ / hiệu ứng: lời không đổi
    assert is_stale(p, tmp_path) is False
    p.scenes[1].voice = "Muỗi bay xa 20{hai mươi} mét."
    assert is_stale(p, tmp_path) is True


def test_missing_or_broken_meta_means_unknown_not_stale(tmp_path):
    p = three()
    run(tmp_path, p)
    p.voice = Voice(file="voice.wav")
    meta = tmp_path / "build" / "hbt_voice.json"
    meta.unlink()
    assert is_stale(p, tmp_path) is None and read_meta(tmp_path) is None
    meta.write_text("{không phải json", encoding="utf-8")
    assert is_stale(p, tmp_path) is None
    meta.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert is_stale(p, tmp_path) is None


# ------------------------------------------------------------------ giọng nhớ
def test_prefs_roundtrip_atomic_and_tolerant(tmp_path):
    prefs = Gd2Prefs(tmp_path)
    assert prefs.voice_id() is None
    prefs.set_voice_id("Mai Anh")
    assert prefs.voice_id() == "Mai Anh"
    assert Gd2Prefs(tmp_path).voice_id() == "Mai Anh"  # nhớ qua lần mở sau
    assert not (tmp_path / "settings" / "gd2.json.tmp").exists()
    prefs.set_voice_id(None)
    assert prefs.voice_id() is None
    (tmp_path / "settings" / "gd2.json").write_text("{hỏng", encoding="utf-8")
    assert Gd2Prefs(tmp_path).voice_id() is None
    prefs.set_voice_id("Adam")  # ghi đè được file hỏng
    assert prefs.voice_id() == "Adam"
