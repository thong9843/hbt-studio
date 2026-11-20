"""Tiến trình con thường trú cho VieNeu-TTS (`python -I -X utf8 resident_worker.py <hf_home>`).

Chỉ dùng thư viện chuẩn + `numpy` + `vieneu` (không import `hbt`), đọc lệnh JSON-line qua stdin
để giữ mô hình ấm trong RAM giữa các lần sinh giọng và tự giải phóng khi nhận `shutdown` hoặc EOF.
"""

from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path


def _write_wav_atomic(path: str, audio: object, sample_rate: int) -> float:
    import numpy as np

    arr = np.asarray(audio).reshape(-1)
    if np.issubdtype(arr.dtype, np.floating):
        pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    else:
        pcm = arr.astype(np.int16)

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.tmp")
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(sample_rate))
            wf.writeframes(pcm.tobytes())
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return round(len(pcm) / float(max(1, int(sample_rate))), 4)


def _reply(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        _reply({"ok": False, "stage": "boot", "error": "Thiếu đường dẫn hf_home"})
        return 1

    os.environ["HF_HOME"] = argv[1]
    os.environ["HF_HUB_OFFLINE"] = "1"

    try:
        from vieneu import Vieneu

        tts = Vieneu()
    except Exception as exc:  # noqa: BLE001
        _reply({"ok": False, "stage": "load", "error": f"{type(exc).__name__}: {exc}"})
        return 1

    _reply({"ok": True, "ready": True, "pid": os.getpid()})
    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                _reply({"ok": False, "error": f"JSON không hợp lệ: {exc}"})
                continue

            cmd = str(req.get("cmd") or "").strip().lower()
            if cmd == "ping":
                _reply({"ok": True, "pong": True, "pid": os.getpid()})
            elif cmd == "shutdown":
                _reply({"ok": True, "bye": True})
                break
            elif cmd == "synth":
                try:
                    text = str(req.get("text") or "")
                    voice = str(req.get("voice") or "Thanh Bình")
                    out_path = str(req.get("out") or "")
                    audio = tts.infer(text, voice=voice, apply_watermark=False)
                    seconds = _write_wav_atomic(out_path, audio, int(tts.sample_rate))
                    _reply({"ok": True, "out": out_path, "seconds": seconds, "pid": os.getpid()})
                except Exception as exc:  # noqa: BLE001
                    _reply({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            else:
                _reply({"ok": False, "error": f"Lệnh không hỗ trợ: {cmd}"})
        return 0
    finally:
        try:
            tts.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv))
