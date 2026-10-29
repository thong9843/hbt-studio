"""Tiến trình con giọng VieNeu: `python -I -X utf8 voice_worker.py <request.json>`.

Chạy bằng Python của `backend/.venv-tts` (không có pydantic, Pillow, hbt…), nên file này chỉ dùng
thư viện chuẩn + `numpy` + `vieneu`, và KHÔNG import gì từ `hbt` (cờ `-I` cũng không thêm thư mục
file này vào `sys.path`). Chạy ở tiến trình riêng để kill được khi huỷ hoặc hết giờ, và để RAM tự
giải phóng khi thoát (IMPLEMENT-POSTV mục 6c).

Request: {"mode": "voices" | "synth", "hf_home": ..., "out": ..., "progress": ...,
          "items": [{"text": ..., "voice": ..., "out": ...}]}
Kết quả ghi vào file `out`:
  {"ok": true, "voices": [[nhãn, id], ...]}            (mode voices)
  {"ok": true, "files": [{"out": ..., "seconds": ...}]}  (mode synth)
  {"ok": false, "stage": "load" | "run", "error": "..."}
Tiến độ (mode synth): mỗi dòng của file `progress` là `begin <i>` hoặc `done <i>` (i từ 0).
Trọng số chỉ đọc ở `hf_home`; luôn đặt HF_HUB_OFFLINE=1 nên không bao giờ tải gì từ mạng (N4).
"""

from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path


def _write_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    Path(tmp).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _write_wav(path: str, audio, sample_rate: int) -> float:
    """Ghi WAV mono 16-bit (ghi file tạm rồi đổi tên, để file dở không bị coi là bản cache)."""
    import numpy as np

    a = np.asarray(audio).reshape(-1)
    if np.issubdtype(a.dtype, np.floating):
        a = (np.clip(a, -1.0, 1.0) * 32767.0).astype(np.int16)
    else:
        a = a.astype(np.int16)
    tmp = path + ".tmp"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(a.tobytes())
    os.replace(tmp, path)
    return len(a) / float(sample_rate)


def _note(path: str | None, line: str) -> None:
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def main(request_path: str) -> int:
    req = json.loads(Path(request_path).read_text(encoding="utf-8"))
    out = req["out"]
    os.environ["HF_HOME"] = req["hf_home"]
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        from vieneu import Vieneu

        tts = Vieneu()
    except Exception as e:  # noqa: BLE001
        _write_json(out, {"ok": False, "stage": "load", "error": f"{type(e).__name__}: {e}"})
        return 1
    try:
        if req["mode"] == "voices":
            voices = [[label, vid] for label, vid in tts.list_preset_voices()]
            _write_json(out, {"ok": True, "voices": voices})
            return 0
        files = []
        for i, item in enumerate(req["items"]):
            _note(req.get("progress"), f"begin {i}")
            audio = tts.infer(item["text"], voice=item["voice"], apply_watermark=False)
            seconds = _write_wav(item["out"], audio, int(tts.sample_rate))
            files.append({"out": item["out"], "seconds": seconds})
            _note(req.get("progress"), f"done {i}")
        _write_json(out, {"ok": True, "files": files})
        return 0
    except Exception as e:  # noqa: BLE001
        _write_json(out, {"ok": False, "stage": "run", "error": f"{type(e).__name__}: {e}"})
        return 1
    finally:
        try:
            tts.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
