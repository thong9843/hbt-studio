"""Outro HBT 4,0 giây, 1080x1920, 50fps. Logo bật nảy, lời kêu gọi, 2 nút TikTok / YouTube (chữ thuần, không dùng logo nền tảng)."""
import math, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
W,H,FPS,DUR=1080,1920,50,4.0
RED=(178,34,40); DEEP=(120,16,22); CREAM=(247,238,218); INK=(30,24,22); MUST=(244,182,48)
FD='/home/claude/fonts/'
def brik(size,wght=800,wdth=85):
    f=ImageFont.truetype(FD+'Bricolage.ttf',size); f.set_variation_by_axes([96,wght,wdth]); return f
def bvp(w,s): return ImageFont.truetype(FD+f'BeVietnamPro-{w}.ttf',s)
# nền chấm bi như avatar
bg=Image.new('RGBA',(W,H),RED+(255,)); d=ImageDraw.Draw(bg); step=46; C=(W/2,H/2)
for y in range(0,H+step,step):
    for x in range(0,W+step,step):
        ox=x+(step//2 if (y//step)%2 else 0); r=math.hypot(ox-C[0],y-C[1])/(H*0.62); rad=2+13*r**1.6
        d.ellipse((ox-rad,y-rad,ox+rad,y+rad),fill=DEEP+(255,))
logo=Image.open('/home/claude/ava/hbt-logo-mark.png').convert('RGBA'); LW=780; logo=logo.resize((LW,int(logo.height*LW/logo.width)),Image.LANCZOS)
def text_layer(lines,font,fill,gap=12,stroke=0,sf=None):
    d0=ImageDraw.Draw(Image.new('L',(1,1))); ws=[d0.textlength(t,font=font) for t in lines]; lh=int(font.size*1.12)
    im=Image.new('RGBA',(int(max(ws))+40,lh*len(lines)+20),(0,0,0,0)); dd=ImageDraw.Draw(im)
    for i,t in enumerate(lines):
        x=(im.width-ws[i])/2; y=i*lh+8
        dd.text((x+4,y+6),t,font=font,fill=(0,0,0,110))
        dd.text((x,y),t,font=font,fill=fill,stroke_width=stroke,stroke_fill=sf)
    return im
title=text_layer(['Theo dõi để','biết tuốt mọi chuyện!'],brik(92),CREAM+(255,),stroke=0)
def pill(label,w,h,fill,tc):
    im=Image.new('RGBA',(w+30,h+30),(0,0,0,0)); dd=ImageDraw.Draw(im)
    dd.rounded_rectangle((8,12,w+8,h+12),h//2,fill=(0,0,0,120))
    dd.rounded_rectangle((0,0,w,h),h//2,fill=fill+(255,),outline=INK+(255,),width=5)
    f=bvp('ExtraBold',50); tw=dd.textlength(label,font=f); bb=dd.textbbox((0,0),label,font=f)
    dd.text(((w-tw)/2,(h-(bb[1]+bb[3]))/2),label,font=f,fill=tc); return im
btn_follow=pill('THEO DÕI',560,120,MUST,INK)
btn_tt=pill('TikTok',330,100,CREAM,INK); btn_yt=pill('YouTube',330,100,CREAM,INK)
name=text_layer(['Hay Biết Tuốt'],bvp('Bold',54),CREAM+(255,))
def ease_out_back(p,s=1.9): p=min(max(p,0),1); p-=1; return 1+(s+1)*p**3+s*p**2
def ease_out(p): p=min(max(p,0),1); return 1-(1-p)**3
def put(frame,im,cx,cy,scale=1.0,alpha=1.0):
    if scale<=0.01 or alpha<=0: return
    if scale!=1.0: im=im.resize((max(1,int(im.width*scale)),max(1,int(im.height*scale))),Image.LANCZOS)
    if alpha<1.0: im=im.copy(); im.putalpha(im.getchannel('A').point(lambda v:int(v*alpha)))
    frame.alpha_composite(im,(int(cx-im.width/2),int(cy-im.height/2)))
out=sys.argv[1] if len(sys.argv)>1 else 'outro.mp4'
enc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
  '-c:v','libx264','-preset','medium','-crf','14','-pix_fmt','yuv420p','-r',str(FPS),out],stdin=subprocess.PIPE)
for f in range(int(DUR*FPS)):
    t=f/FPS; fr=bg.copy()
    # logo bật nảy 0.10–0.70s, rồi lơ lửng nhẹ
    s=ease_out_back((t-0.10)/0.60); bob=6*math.sin(2*math.pi*max(t-0.7,0)/2.2)
    put(fr,logo,W/2,640+bob,s*(1+0.0),1.0)
    # tiêu đề trượt lên + hiện 0.75–1.25s
    p=ease_out((t-0.75)/0.5); put(fr,title,W/2,1010+(1-p)*50,1.0,p)
    # nút THEO DÕI bật 1.15–1.65s, nhịp đập sau đó
    s=ease_out_back((t-1.15)/0.5); pulse=1+0.035*math.sin(2*math.pi*max(t-1.7,0)/0.9) if t>1.7 else 1
    put(fr,btn_follow,W/2,1230,s*pulse,1.0)
    # 2 nút nền tảng lần lượt 1.45s, 1.65s
    s=ease_out_back((t-2.15)/0.45); put(fr,btn_tt,W/2-190,1385,s,1.0)
    s=ease_out_back((t-2.55)/0.45); put(fr,btn_yt,W/2+190,1385,s,1.0)
    # tên kênh 1.9s
    p=ease_out((t-2.85)/0.4); put(fr,name,W/2,1505+(1-p)*20,1.0,p)
    # mờ vào đầu, mờ ra cuối
    if t<0.12 or t>DUR-0.25:
        a=min(t/0.12,1) if t<0.12 else max((DUR-t)/0.25,0)
        black=Image.new('RGBA',(W,H),(0,0,0,int(255*(1-a)))); fr.alpha_composite(black)
    enc.stdin.write(fr.convert('RGB').tobytes())
enc.stdin.close(); enc.wait()
