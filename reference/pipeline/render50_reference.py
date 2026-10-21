import subprocess, sys, os, time, json, shutil
import numpy as np
FPS=50; X=0.4; SHIFT=0.2; SS=(3240,5760); W,H=1080,1920; FS=W*H*3
CFG={
 "2010":dict(src="/home/claude/v",n=6,b=[3.6,9.2,14.3,18.5,24.1],punch=[],cap="/home/claude/kc/k2010.txt",capdir=("k2010/","/home/claude/kc/k2010/"),
             audio=("/home/claude/v/final_voice.mp4",),out="20-10_vi-sao-2-ngay-phu-nu_50fps.mp4"),
 "cf":dict(src="/home/claude/cf",n=8,b=[4.38,9.20,14.67,19.60,26.49,33.63,37.84],punch=[],cap="/home/claude/kc/kcf.txt",capdir=("kcf/","/home/claude/kc/kcf/"),
             audio=("/home/claude/cf/final_music.mp4",),out="vi-sao-ca-phe-sua-dac_50fps.mp4"),
 "4m":dict(src="/home/claude/s4",n=8,b=[7.50,13.05,18.43,22.48,32.24,38.72,44.83],punch=[],cap="/home/claude/kc/k4m.txt",capdir=("k4m/","/home/claude/kc/k4m/"),
             audio=("/home/claude/s4/mix.wav",),out="vi-sao-co-4-mua_50fps.mp4"),
 "sky":dict(src="/home/claude/s5",n=8,b=[4.04,8.645,14.50,20.05,26.355,30.61,33.825],punch=[1,4,7],cap="/home/claude/s5/cap.txt",capdir=("cap/","/home/claude/s5/cap/"),
             audio=("/home/claude/s5/mix.wav",),out="bau-troi-khong-mau-xanh_50fps.mp4"),
 "muoi":dict(src="/home/claude/s6",n=8,b=[5.13,7.56,12.175,16.055,24.98,28.165,32.595],punch=[],cap="/home/claude/kc/kmuoi.txt",capdir=("kmuoi/","/home/claude/kc/kmuoi/"),
             audio=("/home/claude/s6/mix.wav",),out="vi-sao-muoi-dot-nguoi-nay_50fps.mp4"),
}
def dur(p): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',p]).decode())
def setup(name):
    c=CFG[name]; w=f"/home/claude/r50/{name}"; os.makedirs(w,exist_ok=True)
    for i in range(1,c['n']+1):
        for k in ('b','t'):
            if not os.path.exists(f"{w}/{k}{i}.png"): shutil.copy(f"{c['src']}/{k}{i}.png",f"{w}/{k}{i}.png")
    if not os.path.exists(f"{w}/mix.wav"):
        subprocess.run(['ffmpeg','-v','error','-y','-i',c['audio'][0],'-vn','-ar','44100','-ac','2','-c:a','pcm_s16le',f"{w}/mix.wav"],check=True)
    if not os.path.exists(f"{w}/cap.txt"):
        s=open(c['cap']).read().replace(f"file '{c['capdir'][0]}",f"file '{c['capdir'][1]}")
        open(f"{w}/cap.txt","w").write(s)
    total=dur(f"{w}/mix.wav"); o=[x+SHIFT-X/2 for x in c['b']]
    d=[o[0]+X]+[o[k]-o[k-1]+X for k in range(1,len(o))]+[total-o[-1]]
    return c,w,total,o,d
def smooth(p): return f"(({p})*({p})*(3-2*({p})))"
def scene(c,w,d,i):
    out=f"{w}/c{i}.mp4"
    if os.path.exists(out): return False
    dur_=d[i-1]; n=int(round(dur_*FPS)); p=f"(on/{n})"
    if i in c['punch']:
        k=int(0.45*FPS); q=f"(on/{k})"; p2=f"((on-{k})/{n-k})"
        Z=f"if(lt(on,{k}),1.18-0.18*(1-pow(1-{q},3)),1+0.05*{smooth(p2)})"; st=0.15
    elif i%2: Z=f"1+0.08*{smooth(p)}"; st=0.3
    else: Z=f"1.08-0.08*{smooth(p)}"; st=0.3
    fc=(f"[0]scale={SS[0]}:{SS[1]}:flags=lanczos,zoompan=z='{Z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s=1080x1920:fps={FPS}[bg];"
        f"[1]format=rgba,fade=in:st={st}:d=0.35:alpha=1[t];[bg][t]overlay=shortest=1,format=yuv420p[out]")
    subprocess.run(['ffmpeg','-v','error','-y','-i',f"{w}/b{i}.png",'-loop','1','-t',f'{dur_:.3f}','-i',f"{w}/t{i}.png",'-filter_complex',fc,
        '-map','[out]','-frames:v',str(n),'-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','12',out+'.tmp.mp4'],check=True)
    os.rename(out+'.tmp.mp4',out); return True
class Reader:
    def __init__(s,path):
        s.p=subprocess.Popen(['ffmpeg','-v','error','-i',path,'-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,bufsize=FS*2)
        s.idx=-1; s.frame=None; s.done=False
    def get(s,i):
        while s.idx<i and not s.done:
            b=s.p.stdout.read(FS)
            if len(b)<FS: s.done=True; break
            s.frame=np.frombuffer(b,np.uint8).reshape(H,W,3); s.idx+=1
        return s.frame
    def close(s): s.p.stdout.close(); s.p.kill()
def ease(p): p=min(max(p,0),1); return 4*p*p*p if p<0.5 else 1-pow(-2*p+2,3)/2
def compose(c,w,total,o):
    n=c['n']; starts=[0]+o; N=int(round(total*FPS)); TN=int(round(X*FPS)); S=6
    enc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
      '-f','concat','-safe','0','-i',f"{w}/cap.txt",'-i',f"{w}/mix.wav",'-filter_complex',
      f'[1:v]fps={FPS},format=rgba[cap];[0:v][cap]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]',
      '-map','[v]','-map','2:a','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','16','-profile:v','high','-g',str(2*FPS),
      '-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',f"{w}/final.mp4"],stdin=subprocess.PIPE)
    readers={}
    def R(k):
        if k not in readers: readers[k]=Reader(f"{w}/c{k}.mp4")
        return readers[k]
    for f in range(N):
        t=f/FPS; j=max(j for j in range(n) if starts[j]<=t+1e-9)
        if j>=1 and t<starts[j]+X-1e-9:
            A=R(j).get(int(round((t-starts[j-1])*FPS))); lb=int(round((t-starts[j])*FPS)); B=R(j+1).get(lb)
            acc=np.zeros((H,W,3),np.float32)
            for s_ in range(S):
                sh=int(round(ease((lb+0.5*(s_+0.5)/S)/TN)*W)); comp=np.empty_like(A)
                comp[:,:W-sh]=A[:,sh:]; comp[:,W-sh:]=B[:,:sh]; acc+=comp
            out=(acc/S).astype(np.uint8)
        else:
            if j>=1 and j in readers: readers.pop(j).close()
            out=R(j+1).get(int(round((t-starts[j])*FPS)))
        enc.stdin.write(out.tobytes())
    enc.stdin.close(); enc.wait()
    for r in readers.values(): r.close()
if __name__=="__main__":
    name,step=sys.argv[1],sys.argv[2]; c,w,total,o,d=setup(name)
    if step=="scenes":
        t0=time.time(); budget=float(sys.argv[3]) if len(sys.argv)>3 else 250
        for i in range(1,c['n']+1):
            if os.path.exists(f"{w}/c{i}.mp4"): continue
            if time.time()-t0+d[i-1]*3.6>budget: print("stop before scene",i); break
            scene(c,w,d,i); print("scene",i,"done",round(time.time()-t0))
        print("missing:",[i for i in range(1,c['n']+1) if not os.path.exists(f"{w}/c{i}.mp4")])
    elif step=="compose":
        t0=time.time(); compose(c,w,total,o); print("composed",round(time.time()-t0),"s")
        os.makedirs("/mnt/user-data/outputs",exist_ok=True); shutil.copy(f"{w}/final.mp4",f"/mnt/user-data/outputs/{c['out']}")
        print(dur(f"{w}/final.mp4"),total)
