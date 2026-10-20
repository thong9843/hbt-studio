"""THAM KHẢO — các lệnh FFmpeg đã chạy thực tế để dựng 6 video đầu tiên của kênh.
Claude Code dùng file này làm chuẩn khi viết app/pipeline/render.py (giữ nguyên tham số
trừ khi IMPLEMENT.md nói khác). Không chạy trực tiếp file này.
"""
import subprocess

X = 0.4          # thời lượng hiệu ứng chuyển cảnh (giây)
VOICE_DELAY = 0.2
TAIL = 1.6       # giữ hình sau câu cuối


# 1) Chuẩn hoá giọng đọc -------------------------------------------------------
def prep_voice(src, dst):
    subprocess.run(["ffmpeg", "-y", "-i", src, "-af",
                    f"highpass=f=70,adelay={int(VOICE_DELAY*1000)},apad=pad_dur={TAIL},"
                    "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100",
                    "-ac", "1", dst], check=True)


# 2) Thời điểm chuyển cảnh: giữa khoảng nghỉ giữa 2 đoạn lời ----------------------
def scene_offsets(para_first_start, para_last_end):
    """Trả về offset xfade (giây) cho cảnh 2..n và thời lượng từng clip."""
    cuts = [(para_last_end[k - 1] + para_first_start[k]) / 2 for k in range(1, len(para_first_start))]
    return [c - X / 2 for c in cuts]


def durations(offsets, total):
    o = offsets
    return [o[0] + X] + [o[k] - o[k - 1] + X for k in range(1, len(o))] + [total - o[-1]]


# 3) Một cảnh: ảnh nền phóng to/thu nhỏ chậm + thẻ chữ hiện dần --------------------
def render_scene(base_png, card_png, dur, idx, fps, punch, out):
    n = int(round(dur * fps))
    if punch:   # cú lật: phóng giật 1.18 -> 1.0 trong 0.4s rồi trôi chậm
        k = int(0.4 * fps)
        z = f"if(lt(on,{k}),1.18-0.18*on/{k},1+0.05*(on-{k})/{n})"
        card_start = 0.15
    else:       # cảnh lẻ phóng vào, cảnh chẵn lùi ra
        z = f"1+0.08*on/{n}" if idx % 2 else f"1.08-0.08*on/{n}"
        card_start = 0.3
    vf = (f"[0]scale=2160:3840,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={n}:s=1080x1920:fps={fps}[bg];"
          f"[1]format=rgba,fade=in:st={card_start}:d=0.3:alpha=1[t];"
          f"[bg][t]overlay=shortest=1,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-i", base_png, "-loop", "1", "-t", f"{dur:.3f}", "-i", card_png,
                    "-filter_complex", vf, "-t", f"{dur:.3f}", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", out], check=True)


# 4) Nhạc nền: cắt đoạn, fade, hạ âm lượng khi có giọng (ducking) -------------------
def mix_audio(voice_wav, music_src, music_start, total, sfx=(), out="mix.wav"):
    subprocess.run(["ffmpeg", "-y", "-ss", str(music_start), "-t", str(total), "-i", music_src, "-af",
                    f"aresample=44100,afade=t=in:d=0.8,afade=t=out:st={total-2.5}:d=2.5,"
                    "loudnorm=I=-27:TP=-6:LRA=11", "-ac", "2", "music_cut.wav"], check=True)
    inputs = ["-i", voice_wav, "-i", "music_cut.wav"]
    fc = ("[0:a]pan=stereo|c0=0.707*c0|c1=0.707*c0,asplit=2[v][sc];"
          "[1:a][sc]sidechaincompress=threshold=0.03:ratio=3:attack=40:release=350[md];")
    labels = "[v][md]"
    for i, (path, at, vol) in enumerate(sfx):          # hiệu ứng âm thanh (tuỳ chọn)
        inputs += ["-i", path]
        ms = int(at * 1000)
        fc += f"[{i+2}:a]volume={vol},adelay={ms}|{ms}[s{i}];"
        labels += f"[s{i}]"
    fc += (f"{labels}amix=inputs={2+len(sfx)}:normalize=0,atrim=0:{total},"
           "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100")
    subprocess.run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-c:a", "pcm_s16le", out], check=True)


def synth_whoosh(out="whoosh.wav"):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.7:c=pink:a=0.6", "-af",
                    "highpass=f=300,lowpass=f=6000,afade=t=in:d=0.35,afade=t=out:st=0.35:d=0.35",
                    "-ar", "44100", "-ac", "2", out], check=True)


# 5) Ghép cảnh bằng xfade + phủ phụ đề + gắn tiếng ----------------------------------
def assemble(clips, offsets, captions_list, audio, fps, out):
    """captions_list: file concat (ffconcat) gồm các PNG trạng thái phụ đề + thời lượng."""
    inp = []
    for c in clips:
        inp += ["-i", c]
    fc, prev = "", "[0]"
    for k in range(1, len(clips)):
        lab = f"[v{k}]"
        fc += f"{prev}[{k}]xfade=transition=slideleft:duration={X}:offset={offsets[k-1]:.3f}{lab};"
        prev = lab
    n = len(clips)
    fc += (f"[{n}:v]fps={fps},format=rgba[cap];{prev}[cap]overlay=0:0:shortest=1:format=auto,"
           "format=yuv420p[v]")
    subprocess.run(["ffmpeg", "-y", *inp, "-f", "concat", "-safe", "0", "-i", captions_list, "-i", audio,
                    "-filter_complex", fc, "-map", "[v]", "-map", f"{n+1}:a",
                    "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
