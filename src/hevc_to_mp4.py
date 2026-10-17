#!/usr/bin/env python3
"""Remux an Annex B HEVC camera stream into an MP4 (video only, constant FPS).
Pure Python 3, no FFmpeg required. Intended for low-latency streams with no B-frames.
"""
import argparse
import re
import struct
from pathlib import Path
from collections import Counter

U16 = lambda n: struct.pack('>H', n)
U32 = lambda n: struct.pack('>I', n)

def box(t, payload=b''):
    return U32(8 + len(payload)) + t.encode('ascii') + payload

def full(t, payload=b'', flags=0):
    return box(t, bytes((0,)) + flags.to_bytes(3,'big') + payload)

class Bits:
    def __init__(self, data):
        rbsp = bytearray()
        zeros = 0
        for ch in data:
            if zeros == 2 and ch == 3:
                zeros = 0
                continue
            rbsp.append(ch)
            zeros = zeros + 1 if ch == 0 else 0
        self.data = rbsp
        self.offset = 0
    def get(self,n=1):
        if self.offset + n > len(self.data)*8:
            raise ValueError('SPS is truncated')
        val = 0
        for _ in range(n):
            val = (val << 1) | ((self.data[self.offset >> 3] >> (7-(self.offset&7)))&1)
            self.offset += 1
        return val
    def ue(self):
        zeros=0
        while self.get(1)==0:
            zeros+=1
            if zeros>31:
                raise ValueError('Invalid Exp-Golomb code')
        return (1 << zeros)-1+self.get(zeros)

def sps_details(nal):
    b=Bits(nal[2:])
    b.get(4)
    max_layers=b.get(3)
    nested=b.get(1)
    profile_space=b.get(2)
    tier=b.get(1)
    profile=b.get(5)
    compatibility=b.get(32)
    constraints=b.get(48)
    level=b.get(8)
    sub_profile=[]
    sub_level=[]
    for _ in range(max_layers):
        sub_profile.append(b.get(1))
        sub_level.append(b.get(1))
    if max_layers:
        b.get(2*(8-max_layers))
    for i in range(max_layers):
        if sub_profile[i]: b.get(88)
        if sub_level[i]: b.get(8)
    b.ue()  # sps_seq_parameter_set_id
    chroma=b.ue()
    if chroma == 3:
        b.get(1)
    width=b.ue()
    height=b.ue()
    if b.get(1):
        crop=[b.ue() for _ in range(4)]
        sx,sy = ((1,1) if chroma in (0,3) else ((2,2) if chroma==1 else (2,1)))
        width -= (crop[0]+crop[1])*sx
        height -= (crop[2]+crop[3])*sy
    depth_luma=b.ue()
    depth_chroma=b.ue()
    if not 0 < width <= 65535 or not 0 < height <= 65535:
        raise ValueError(f'Invalid dimensions {width}x{height}')
    return dict(width=width, height=height, chroma=chroma, luma=depth_luma, 
                chroma_depth=depth_chroma, space=profile_space, tier=tier, profile=profile,
                compatibility=compatibility, constraints=constraints, level=level,
                layers=max_layers+1, nested=nested)

def split_annexb(data):
    starts=list(re.finditer(b'\x00\x00\x00\x01|\x00\x00\x01', data))
    for i, match in enumerate(starts):
        first=match.end()
        last=starts[i+1].start() if i+1 < len(starts) else len(data)
        nal=data[first:last]
        if len(nal)>2:
            yield (nal[0] >> 1)&0x3f, nal

def hvcc(sps, vps, pps, cfg):
    h=bytearray()
    h+=bytes([1, cfg['space'] << 6 | cfg['tier'] << 5 | cfg['profile']])
    h+=U32(cfg['compatibility'])
    h+=cfg['constraints'].to_bytes(6,'big')
    h+=bytes([cfg['level']])
    h+=U16(0xF000)
    h+=bytes([0xFC, 0xFC | cfg['chroma'],
              0xF8 | cfg['luma'],0xF8 | cfg['chroma_depth']])
    h+=U16(0) # avgFrameRate unknown
    h+=bytes([((cfg['layers'] & 7)<<3) | (cfg['nested']<<2) | 3, 3])
    for t, nal in ((32,vps),(33,sps),(34,pps)):
        h+=bytes([0x80 | t]) + U16(1) + U16(len(nal)) + nal
    return box('hvcC', h)

def make_moov(w,h, samples, sizes, keys, fps, offset, vps,sps,pps,cfg):
    scale=12000
    assert 12000 % fps == 0, 'FPS must divide 12000'
    step=scale//fps
    duration=len(samples)*step
    matrix=U32(0x10000)+U32(0)+U32(0)+U32(0)+U32(0x10000)+U32(0)+U32(0)+U32(0)+U32(0x40000000)
    mvhd=full('mvhd',U32(0)*2+U32(scale)+U32(duration)+U32(0x10000)+U16(0x100)+b'\0'*10+matrix+b'\0'*24+U32(2))
    tkhd=full('tkhd', U32(0)*2 + U32(1)+U32(0)+U32(duration)+b'\0'*8+U16(0)*4+matrix+U32(w<<16)+U32(h<<16),flags=7)
    lang=(21<<10)|(14<<5)|4
    mdhd=full('mdhd', U32(0)*2 + U32(scale)+U32(duration)+U16(lang)+U16(0))
    hdlr=full('hdlr',U32(0)+b'vide'+b'\0'*12+b'VideoHandler\0')
    video=box('vmhd',b'\0\0\0\1'+U16(0)*4)
    dref=full('dref',U32(1)+full('url ',flags=1))
    dinf=box('dinf',dref)
    compressor=b'HEVC video'
    visual=(b'\0'*6+U16(1)+b'\0'*16+U16(w)+U16(h)+U32(0x480000)*2+U32(0)+U16(1)+bytes([len(compressor)])+compressor.ljust(31,b'\0')+U16(24)+U16(0xffff))
    stsd=full('stsd',U32(1)+box('hvc1',visual+hvcc(sps,vps,pps,cfg)))
    stts=full('stts',U32(1)+U32(len(samples))+U32(step))
    stsc=full('stsc',U32(1)+U32(1)+U32(len(samples))+U32(1))
    stsz=full('stsz',U32(0)+U32(len(samples))+b''.join(U32(s) for s in sizes))
    stco=full('stco',U32(1)+U32(offset))
    stss=full('stss',U32(len(keys))+b''.join(U32(k) for k in keys))
    stbl=box('stbl',stsd+stts+stsc+stsz+stco+stss)
    minf=box('minf',video+dinf+stbl)
    mdia=box('mdia',mdhd+hdlr+minf)
    trak=box('trak',tkhd+mdia)
    return box('moov',mvhd+trak)

def run(source, dest, fps):
    data=source.read_bytes()
    params={}
    nals=[]
    stats=Counter()
    for t,nal in split_annexb(data):
        stats[t]+=1
        if t in (32,33,34):
            params.setdefault(t,nal)
        elif t<32:
            # The V380 camera captures one VCL NAL per picture in stream order.
            nals.append((t,nal))
    for p in (32,33,34):
        if p not in params:
            raise ValueError(f'Missing NAL {p} (VPS/SPS/PPS)')
    if not nals or nals[0][0] not in (16,17,18,19,20,21):
        raise ValueError('Capture does not begin with an independent HEVC key frame')
    cfg=sps_details(params[33])
    samples=[U32(len(nal))+nal for t,nal in nals]
    sizes=[len(s) for s in samples]
    keys=[idx for idx,(t,nal) in enumerate(nals,1) if 16<=t<=21]
    ftyp=box('ftyp',b'isom'+U32(512)+b'isomiso6mp41hvc1')
    moov=make_moov(cfg['width'],cfg['height'], samples,sizes,keys,fps,0,
                   params[32],params[33],params[34],cfg)
    offset=len(ftyp)+len(moov)+8
    moov=make_moov(cfg['width'],cfg['height'], samples,sizes,keys,fps,offset,
                   params[32],params[33],params[34],cfg)
    assert len(moov) + len(ftyp) + 8 == offset
    with dest.open('wb') as out:
        out.write(ftyp)
        out.write(moov)
        out.write(U32(8+sum(sizes)) + b'mdat')
        for sample in samples:
            out.write(sample)
    print(f'Written: {dest}')
    print(f"Resolution: {cfg['width']}x{cfg['height']}, frames: {len(samples)}, keyframes: {len(keys)}")
    print(f'FPS: {fps}, duration: {len(samples)/fps:.2f} sec, size: {dest.stat().st_size} bytes')
    print('Video only; play to verify. Assumes no frame reordering (B frames).')

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('input',type=Path)
    a.add_argument('--fps',type=int,default=12)
    a.add_argument('-o','--output',type=Path)
    v=a.parse_args()
    run(v.input, v.output or v.input.with_suffix('.mp4'),v.fps)
