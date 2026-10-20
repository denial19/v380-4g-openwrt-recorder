#!/usr/bin/env python3
"""Read-only comparison of deployed YOLO11n vs VisDrone YOLO11s 640/960.

Never changes live detection code, recorder, state, cron or SMTP.
"""
from pathlib import Path
import argparse
import json
import statistics
import subprocess
import tempfile
import time
from v380_ai_alerts import video_points
from v380_draw_boxes import draw_svg, draw_png

AI=Path('/mnt/usb2/V380/ai')
VROOT=AI/'visdrone'
VEXE=VROOT/'v380-visdrone'
YOLO=AI/'yolo11n/v380-yolo11n'
NANO=AI/'nanodet/v380-nanodet'
HEVC=AI/'bin/ffmpeg-hevc'
VEH={'car','van','truck','bus'}


def run(argv, timeout=120):
    p=subprocess.run([str(x) for x in argv], capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(' '.join(str(x) for x in argv[:2])+': '+p.stderr[-350:])
    return p.stdout


def detect(which, jpeg, conf):
    if which=='yolo11n':
        args=[YOLO,jpeg,AI/'yolo11n',str(conf)]
    elif which in ('640','960'):
        args=[VEXE,jpeg,VROOT/'models'/which,str(conf)]
    else:
        raise ValueError(which)
    return json.loads(run(args,timeout=160))


def test_video(video, out, frames, conf):
    out.mkdir(parents=True,exist_ok=True)
    pts,duration,total=video_points(video,frames)
    scores={k:[] for k in ('yolo11n','640','960')}
    errors=[]
    with tempfile.TemporaryDirectory(prefix='.visdrone-cmp-',dir=AI) as tmp:
        tmp=Path(tmp)
        for idx,sec in pts:
            photo=out/f'parking_{idx:05d}.jpg'
            full=tmp/f'full_{idx:05d}.jpg'
            try:
                run([HEVC,'-hide_banner','-loglevel','error','-threads','1','-i',video,
                     '-map','0:v:0','-an','-ss',f'{sec:.4f}','-frames:v','1',
                     '-update','1','-q:v','2','-y',full],timeout=110)
                if not full.is_file() or full.stat().st_size<500:
                    raise RuntimeError('Decoder produced no JPEG')
                run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
                     '-i',full,'-vf','crop=iw:ih/3:0:ih/3,hflip,vflip',
                     '-frames:v','1','-update','1','-q:v','2',photo],timeout=40)
                if not photo.is_file() or photo.stat().st_size<500:
                    raise RuntimeError('No parking crop')
                for model in scores:
                    tic=time.monotonic()
                    d=detect(model,photo,conf)
                    elapsed=round(time.monotonic()-tic,2)
                    if d.get('width')!=640 or d.get('height')!=360:
                        raise ValueError('Wrong detector dimensions')
                    matches=[o for o in d['objects'] if o['label'] in VEH]
                    people=[o for o in d['objects'] if o['label']=='person']
                    score={'frame':idx,'time':sec,'cars':len(matches),
                           'car_conf':[round(o['confidence'],3) for o in matches],
                           'people':len(people),'seconds':elapsed}
                    scores[model].append(score)
                    stem=out/f'{model}_{idx:05d}'
                    (Path(str(stem)+'.json')).write_text(json.dumps(d,indent=2))
                    draw_svg(photo,d,str(stem)+'.svg')
                    try:
                        draw_png(photo,d,str(stem)+'.png')
                    except (RuntimeError,OSError,subprocess.TimeoutExpired) as exc:
                        print('  PNG unavailable:',model,type(exc).__name__,flush=True)
                    print(f'   {model:<8} frame {idx:<4} vehicles={len(matches)} people={len(people)} '
                          f'confidence={[round(o["confidence"],2) for o in matches]} '
                          f'{elapsed:.2f}s',flush=True)
            except Exception as exc:
                errors.append(f'frame={idx}: {type(exc).__name__}: {str(exc)[:250]}')
                print('ERROR:',errors[-1],flush=True)
            finally:
                full.unlink(missing_ok=True)
    summary={}
    for name,rows in scores.items():
        counts=[r['cars'] for r in rows]
        # Existing V380 pipeline takes the SECOND HIGHEST count from different frames.
        count=sorted(counts,reverse=True)[1] if len(counts)>=2 else None
        summary[name]={'inferred_vehicles':count,'frame_counts':counts,'valid_frames':len(rows),
                       'hits':sum(c>0 for c in counts),
                       'avg_seconds':round(statistics.mean(r['seconds'] for r in rows),2) if rows else None}
    report={'video':video.name,'duration':duration,'total_frames':total,
            'summary':summary,'errors':errors,'frame_results':scores}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(' SUMMARY:', ' | '.join(f'{k}:{v["inferred_vehicles"]} ({v["hits"]}/{v["valid_frames"]}) '
                                  f'{v["avg_seconds"]}s' for k,v in summary.items()),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('videos',nargs='+',type=Path)
    ap.add_argument('--frames',type=int,default=6)
    ap.add_argument('--confidence',type=float,default=.25)
    ap.add_argument('--output',type=Path,default=AI/'visdrone-comparison')
    opt=ap.parse_args()
    if not 2<=opt.frames<=12 or not .05<=opt.confidence<=.95:
        ap.error('Expected 2..12 frames and confidence .05..95')
    for path in (VEXE,YOLO,HEVC,VROOT/'models/640/model.ncnn.bin',VROOT/'models/960/model.ncnn.bin'):
        if not path.is_file(): ap.error('Required component missing: '+str(path))
    if not Path('/mnt/usb2').is_mount(): ap.error('USB volume not mounted')
    for v in opt.videos:
        if not v.is_file():
            print('MISSING:',v,flush=True)
            continue
        print('\n===',v.name,'===',flush=True)
        try:test_video(v,opt.output/v.stem,opt.frames,opt.confidence)
        except Exception as ex:print('FAILED:',v.name,type(ex).__name__,str(ex)[:300],flush=True)
    print('RESULTS:',opt.output)
    print('SAFE: no changes to production alerts / recorder / cron / SMTP')
if __name__=='__main__':main()
