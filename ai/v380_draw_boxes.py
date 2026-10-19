#!/usr/bin/env python3
"""Draw detector JSON on the exact JPEG: PNG + standalone SVG, no Pillow required.
Uses system FFmpeg to decode JPEG to raw RGB for PNG; SVG is written even if
rawvideo output is unavailable on a stripped-down OpenWrt FFmpeg build.
"""
import argparse
import base64
import html
import json
import math
from pathlib import Path
import struct
import subprocess
import zlib

GLYPHS = {
 'A':['01110','10001','10001','11111','10001','10001','10001'],
 'B':['11110','10001','10001','11110','10001','10001','11110'],
 'C':['01111','10000','10000','10000','10000','10000','01111'],
 'D':['11110','10001','10001','10001','10001','10001','11110'],
 'E':['11111','10000','10000','11110','10000','10000','11111'],
 'F':['11111','10000','10000','11110','10000','10000','10000'],
 'G':['01111','10000','10000','10111','10001','10001','01111'],
 'H':['10001','10001','10001','11111','10001','10001','10001'],
 'I':['11111','00100','00100','00100','00100','00100','11111'],
 'J':['00111','00010','00010','00010','10010','10010','01100'],
 'K':['10001','10010','10100','11000','10100','10010','10001'],
 'L':['10000','10000','10000','10000','10000','10000','11111'],
 'M':['10001','11011','10101','10101','10001','10001','10001'],
 'N':['10001','11001','10101','10011','10001','10001','10001'],
 'O':['01110','10001','10001','10001','10001','10001','01110'],
 'P':['11110','10001','10001','11110','10000','10000','10000'],
 'Q':['01110','10001','10001','10001','10101','10010','01101'],
 'R':['11110','10001','10001','11110','10100','10010','10001'],
 'S':['01111','10000','10000','01110','00001','00001','11110'],
 'T':['11111','00100','00100','00100','00100','00100','00100'],
 'U':['10001','10001','10001','10001','10001','10001','01110'],
 'V':['10001','10001','10001','10001','10001','01010','00100'],
 'W':['10001','10001','10001','10101','10101','10101','01010'],
 'X':['10001','10001','01010','00100','01010','10001','10001'],
 'Y':['10001','10001','01010','00100','00100','00100','00100'],
 'Z':['11111','00001','00010','00100','01000','10000','11111'],
 '0':['01110','10011','10101','10101','11001','10001','01110'],
 '1':['00100','01100','00100','00100','00100','00100','01110'],
 '2':['01110','10001','00001','00110','01000','10000','11111'],
 '3':['11110','00001','00001','01110','00001','00001','11110'],
 '4':['00010','00110','01010','10010','11111','00010','00010'],
 '5':['11111','10000','10000','11110','00001','00001','11110'],
 '6':['01110','10000','10000','11110','10001','10001','01110'],
 '7':['11111','00001','00010','00100','01000','01000','01000'],
 '8':['01110','10001','10001','01110','10001','10001','01110'],
 '9':['01110','10001','10001','01111','00001','00001','01110'],
 '.':['00000','00000','00000','00000','00000','00110','00110'],
 '-':['00000','00000','00000','11111','00000','00000','00000'],
 ' ':['00000']*7,
}
COLORS = {'person': (255,74,79), 'car': (50,225,107),
          'truck': (255,196,51), 'bus': (255,196,51), 'motorcycle': (71,178,255)}

def inspect(input_json):
    d=json.loads(Path(input_json).read_text())
    w,h=d['width'], d['height']
    if not (32 <= w <= 4096 and 32 <= h <= 4096 and w*h<=8000000):
        raise ValueError('Unsafe image dimensions')
    for obj in d['objects']:
        b=obj['bbox']
        if len(b)!=4 or any(not math.isfinite(float(t)) for t in b):
            raise ValueError('Invalid bbox')
    return d

def boxlabel(obj):
    return '{} {:.0f}%'.format(obj['label'].upper(),float(obj['confidence'])*100)

def png_chunk(code,data):
    return struct.pack('>I',len(data))+code+data+struct.pack('>I',zlib.crc32(code+data)&0xffffffff)

def png_write(path,raw,w,h):
    stride=w*3
    payload=b''.join(b'\0'+raw[y*stride:(y+1)*stride] for y in range(h))
    png=b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))
    png+=png_chunk(b'IDAT',zlib.compress(payload,6))+png_chunk(b'IEND',b'')
    Path(path).write_bytes(png)

def draw_png(jpg,jdata,out):
    w,h=jdata['width'],jdata['height']
    p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-i',str(jpg),
         '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],
         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25)
    if p.returncode or len(p.stdout)!=w*h*3:
        raise RuntimeError('System ffmpeg cannot output RGB24 ('+p.stderr.decode(errors='replace')[-120:]+')')
    buf=bytearray(p.stdout)
    def fill(x0,y0,x1,y1,c):
        x0=max(0,min(w,int(x0)));x1=max(0,min(w,int(x1)))
        y0=max(0,min(h,int(y0)));y1=max(0,min(h,int(y1)))
        span=bytes(c)*(x1-x0)
        for y in range(y0,y1): buf[(y*w+x0)*3:(y*w+x1)*3]=span
    for item in jdata['objects']:
        col=COLORS.get(item['label'],(232,232,232))
        x,y,bw,bh=[int(round(float(t))) for t in item['bbox']]
        x0=max(0,min(w-1,x));y0=max(0,min(h-1,y))
        x1=max(0,min(w,x+bw));y1=max(0,min(h,y+bh))
        if x1<=x0 or y1<=y0: continue
        for t in range(2):
            fill(x0+t,y0+t,x1-t,y0+t+1,col)
            fill(x0+t,y1-t-1,x1-t,y1-t,col)
            fill(x0+t,y0+t,x0+t+1,y1-t,col)
            fill(x1-t-1,y0+t,x1-t,y1-t,col)
        lbl=boxlabel(item)
        scale=2
        tw=(len(lbl)*6-1)*scale+8; th=7*scale+8
        tx=min(x0,max(0,w-tw));ty=(y0-th if y0>=th else y0)
        fill(tx,ty,tx+tw,ty+th,col)
        for i,ch in enumerate(lbl):
            rows=GLYPHS.get(ch,'') or GLYPHS[' ']
            for yy,pattern in enumerate(rows):
                for xx,on in enumerate(pattern):
                    if on=='1': fill(tx+4+i*6*scale+xx*scale,ty+4+yy*scale,
                                     tx+4+i*6*scale+(xx+1)*scale,ty+4+(yy+1)*scale,(0,0,0))
    png_write(out,buf,w,h)

def draw_svg(jpg,d,out):
    w,h=d['width'],d['height']
    mime='image/png' if jpg.suffix.lower()=='.png' else 'image/jpeg'
    b64=base64.b64encode(jpg.read_bytes()).decode('ascii')
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
           f'<image width="{w}" height="{h}" href="data:{mime};base64,{b64}"/>']
    for obj in d['objects']:
        x,y,bw,bh=obj['bbox']
        rgb=COLORS.get(obj['label'],(232,232,232));color='#{:02x}{:02x}{:02x}'.format(*rgb)
        text=html.escape(boxlabel(obj));tw=min(w,9*len(text)+14)
        ty=max(0,y-22)
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" stroke="{color}" stroke-width="2" fill="none"/>')
        parts.append(f'<rect x="{min(x,w-tw):.1f}" y="{ty:.1f}" width="{tw}" height="21" fill="{color}"/>')
        parts.append(f'<text x="{min(x,w-tw)+5:.1f}" y="{ty+15:.1f}" font-size="14" font-family="Arial, sans-serif" font-weight="bold" fill="#080808">{text}</text>')
    parts.append('</svg>')
    Path(out).write_text('\n'.join(parts),encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('detections_json',type=Path)
    p.add_argument('output_prefix',type=Path)
    args=p.parse_args()
    data=inspect(args.detections_json)
    args.output_prefix.parent.mkdir(parents=True,exist_ok=True)
    draw_svg(args.image,data,str(args.output_prefix)+'.svg')
    print('Annotated SVG:',str(args.output_prefix)+'.svg')
    try:
        draw_png(args.image,data,str(args.output_prefix)+'.png')
        print('Annotated PNG:',str(args.output_prefix)+'.png')
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as e:
        print('PNG unavailable; SVG works without FFmpeg rawvideo:',str(e)[:220])
    print('Detected:', ', '.join(boxlabel(o) for o in data['objects']) or '(none)')

if __name__=='__main__':main()
