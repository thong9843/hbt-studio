"""Ảnh bìa (thumbnail) HBT. Khung 1080x1920 (9:16).
Vùng an toàn: chữ tiêu đề nằm trong dải y=600..1320 (cắt 3:2 của YouTube Shorts); logo/nhãn nằm trong y=240..1680 (cắt 3:4 lưới hồ sơ TikTok)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
W,H=1080,1920
RED=(178,34,40); CREAM=(247,238,218); INK=(30,24,22); YEL=(255,212,59); DARK=(18,14,26)
FD='/home/claude/fonts/'
def brik(size,wght=800,wdth=78):
    f=ImageFont.truetype(FD+'Bricolage.ttf',int(size)); f.set_variation_by_axes([96,wght,wdth]); return f
def bvp(w,s): return ImageFont.truetype(FD+f'BeVietnamPro-{w}.ttf',int(s))
_d=ImageDraw.Draw(Image.new('L',(1,1)))
def width(t,f,stroke): return _d.textlength(t,font=f)+2*stroke
def make(bg_path,lines,series,out_prefix,accent=YEL,logo_path='/home/claude/ava/hbt-logo-mark.png'):
    bg=Image.open(bg_path).convert('RGB').resize((W,H),Image.LANCZOS)
    bg=ImageEnhance.Brightness(bg).enhance(0.82); bg=ImageEnhance.Color(bg).enhance(1.1)
    # dải tối mềm sau chữ
    ys=np.arange(H)[:,None]; a=np.clip(1-np.abs(ys-960)/560,0,1)**1.3*0.50
    shade=np.zeros((H,W,4),np.uint8); shade[...,:3]=(10,8,18); shade[...,3]=(a*255).astype(np.uint8).repeat(W,1)
    im=bg.convert('RGBA'); im.alpha_composite(Image.fromarray(shade,'RGBA'))
    d=ImageDraw.Draw(im)
    # cỡ chữ: dòng dài nhất vừa 940px, tối đa 150
    maxw=950; base=185
    while base>60 and max(width(t,brik(base),base*0.11) for t in lines)>maxw: base-=2
    sizes=[base]*len(lines)
    last=min(base*1.12,205)
    if width(lines[-1],brik(last),last*0.11)<=maxw: sizes[-1]=last
    while sum(x*1.02 for x in sizes)>610:   # tổng chiều cao chữ phải lọt dải 3:2 (720 px) kèm lề
        sizes=[x*0.96 for x in sizes]
    lh=[s*1.02 for s in sizes]; total=sum(lh); y=960-total/2
    for i,(t,s) in enumerate(zip(lines,sizes)):
        f=brik(s); st=int(s*0.11); w=width(t,f,st); x=(W-w)/2+st
        fill=accent if i==len(lines)-1 else (255,255,255)
        d.text((x+10,y+12),t,font=f,fill=(0,0,0,150),stroke_width=st,stroke_fill=(0,0,0,150))
        d.text((x,y),t,font=f,fill=fill,stroke_width=st,stroke_fill=DARK)
        y+=lh[i]
    # nhãn series (trên, trong vùng 3:4)
    pf=bvp('ExtraBold',44); tw=_d.textlength(series,font=pf); pw,ph=int(tw)+84,84; px=(W-pw)//2; py=330
    d.rounded_rectangle((px+6,py+8,px+pw+6,py+ph+8),ph//2,fill=(0,0,0,130))
    d.rounded_rectangle((px,py,px+pw,py+ph),ph//2,fill=CREAM,outline=INK,width=5)
    d.text((px+42,py+ph/2-27),series,font=pf,fill=RED)
    # logo HBT (dưới, trong vùng 3:4)
    lg=Image.open(logo_path).convert('RGBA'); LW=300; lg=lg.resize((LW,int(lg.height*LW/lg.width)),Image.LANCZOS)
    im.alpha_composite(lg,((W-LW)//2,1385))
    rgb=im.convert('RGB')
    rgb.save(out_prefix+'_cover_9x16.jpg',quality=93,subsampling=0)
    rgb.crop((0,600,W,1320)).save(out_prefix+'_youtube_3x2.jpg',quality=93,subsampling=0)
    return rgb
