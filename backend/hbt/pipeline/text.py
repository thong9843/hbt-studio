"""Phân tích lời đọc của từng cảnh thành token hiển thị + âm tiết được đọc.

Cú pháp lời đọc:
  - Dấu `|`  : ngắt cụm phụ đề (mỗi cụm hiện cùng lúc trên màn hình).
  - `100{một trăm}` : hiển thị "100" nhưng khi đọc là "một trăm"
                      (giúp căn thời gian chính xác cho số, ký hiệu, tiếng nước ngoài).
"""

import re
import unicodedata

TOKEN_RE = re.compile(r"^(?P<disp>.*?)\{(?P<spoken>[^}]*)\}(?P<punct>[,.!?:;…\"”’)]*)$")
# Token: chuỗi ký tự không khoảng trắng, nhưng nhóm `{...}` được giữ nguyên kể cả khi có
# khoảng trắng bên trong ("100{một trăm}"). Bản reference dùng `text.split()` nên chẻ đôi nhóm này.
RAW_TOKEN_RE = re.compile(r"(?:\{[^}]*\}|\S)+")
PHRASE_END = re.compile(r"[,.!?:;…]+[\"”’)]*$")
SENTENCE_END = re.compile(r"[.!?…]+[\"”’)]*$")


def norm(s: str) -> str:
    """Bỏ dấu, chữ thường, chỉ giữ chữ và số — dùng để so khớp với kết quả nhận dạng giọng."""
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^0-9a-z]", "", s.lower())


def parse_voice(text: str):
    """Trả về danh sách token: dict(disp, syl=[âm tiết đã chuẩn hoá], chunk_break, phrase_end)."""
    tokens = []
    pending_break = False
    for raw in RAW_TOKEN_RE.findall(text):
        if raw == "|":
            pending_break = True
            continue
        m = TOKEN_RE.match(raw)
        if m:
            disp = m.group("disp") + m.group("punct")
            spoken = m.group("spoken")
        else:
            disp, spoken = raw, raw
        syl = [n for n in (norm(p) for p in spoken.split()) if n]
        if not syl:
            syl = [norm(disp) or "_"]
        tokens.append(
            {
                "disp": disp,
                "syl": syl,
                "chunk_start": pending_break or not tokens or tokens[-1]["phrase_end"],
                "phrase_end": bool(PHRASE_END.search(disp)),
                "sentence_end": bool(SENTENCE_END.search(disp)),
            }
        )
        pending_break = False
    return tokens


def display(tok: str) -> str:
    """Bỏ dấu câu cuối không cần thiết trên phụ đề."""
    return re.sub(r"[,.:;]+$", "", tok)


def weight(tok: dict) -> float:
    """Độ dài tương đối khi đọc một token (dùng khi phải ước lượng)."""
    return sum(1 + 0.12 * min(len(s), 7) for s in tok["syl"]) + (0.35 if tok["phrase_end"] else 0)
