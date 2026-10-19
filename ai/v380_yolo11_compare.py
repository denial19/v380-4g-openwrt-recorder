#!/usr/bin/env python3
"""Read-only YOLO11n vs NanoDet comparison on V380 archive clips.
Saves original and boxed PNG/SVG for manual assessment. No mail/state/cron changes.
Requires existing v380_ai_alerts.py only for proven MP4 timing parser.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
from v380_ai_alerts import video_points
from v380_draw_boxes import draw_svg, draw_png

AI=Path('/mnt/usb2/V380/ai')
HEVC=AI/'bin/ffmpeg-hevc'
YOLO=AI/'yolo11n/v380-yolo11n'
MODEL=AI/'yolo11n'
NANO=AI/'nanodet/v380-nanodet'
NANOMODEL=AI/'nanodet'
VEH={'car','truck','bus'}

def run(args,timeout=90):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError(' '.join(map(str,args[:2]))+' '+p.stderr[-280:])
    return p.stdout

def vehicles(d): return sum(x['label'] in VEH for x in d['objects'])

def detect(model,jpeg,threshold):
    if model=='yolo11n': return json.loads(run([YOLO,jpeg,MODEL,str(threshold)],100))
    return json.loads(run([NANO,jpeg,NANOMODEL],35))

def analyze(video,out,frames,threshold):
    points, duration,total=video_points(video,frames)
    out.mkdir(parents=True,exist_ok=True)
    results=[];problems=[]
    with tempfile.TemporaryDirectory(prefix='.yolo11-temp-',dir=AI) as tmp:
        tmp=Path(tmp)
        for idx,t in points:
            full=tmp/'full.jpg'; parking=out/f'parking_frame_{idx:05d}.jpg'
            try:
                run([HEVC,'-hide_banner','-loglevel','error','-threads','1',
                     '-i',video,'-map','0:v:0','-an','-ss',f'{t:.4f}',
                     '-frames:v','1','-update','1','-q:v','2','-y',full],100)
                if not full.exists() or full.stat().st_size<500: raise RuntimeError('No decoded JPEG')
                run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin',
                     '-i',full,'-vf','crop=iw:ih/3:0:ih/3',
                     '-frames:v','1','-update','1','-q:v','2','-y',parking],40)
                for model in ('nanodet','yolo11n'):
                    ts=time.monotonic()
                    d=detect(model,parking,threshold)
                    elapsed=round(time.monotonic()-ts,2)
                    assert d['width']==640 and d['height']==360 and isinstance(d['objects'],list)
                    (out/f'{model}_frame_{idx:05d}.json').write_text(json.dumps(d,indent=2))
                    prefix=out/f'{model}_frame_{idx:05d}'
                    draw_svg(parking,d,str(prefix)+'.svg')
                    try: draw_png(parking,d,str(prefix)+'.png')
                    except (RuntimeError,OSError,subprocess.TimeoutExpired): pass
                    matches=[x for x in d['objects'] if x['label'] in VEH]
                    print(f'  {model:7s} idx={idx:<4d} cars={len(matches)} '
                          f'people={sum(x["label"]=="person" for x in d["objects"])} '
                          f'max_car={max((x["confidence"] for x in matches),default=0):.2f} '
                          f'time={elapsed}s',flush=True)
                    results.append({'model':model,'index':idx,'seconds':round(t,2),
                                    'vehicles':len(matches),'objects':d['objects'],'runtime_s':elapsed})
            except Exception as exc:
                problems.append({'index':idx,'error':str(exc)[:250]})
                print('  ERROR:',idx,str(exc)[:180],flush=True)
            finally: full.unlink(missing_ok=True)
    rows={}
    for mod in ('nanodet','yolo11n'):
        a=[r for r in results if r['model']==mod]
        counts=[r['vehicles'] for r in a]
        count=sorted(counts,reverse=True)[1] if len(counts)>=2 else None
        rows[mod]={'valid_frames':len(a),'vehicle_counts':counts,'inferred_vehicles':count,
                   'any_vehicle_frames':sum(c>0 for c in counts),
                   'avg_runtime_s':round(sum(r['runtime_s'] for r in a)/len(a),2) if a else None}
    report={'file':video.name,'duration_s':duration,'total_frames':total,'samples':len(points),
            'summary':rows,'errors':problems,'detections':results}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('  FINAL:', ' | '.join(f'{k}: {v["inferred_vehicles"]} cars, hits={v["any_vehicle_frames"]}/{v["valid_frames"]}' for k,v in rows.items()))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('videos',nargs='+',type=Path)
    p.add_argument('--frames',type=int,default=6)
    p.add_argument('--confidence',type=float,default=.25)
    p.add_argument('--output',type=Path,default=AI/'yolo11-comparison')
    a=p.parse_args()
    if not 2<=a.frames<=12 or not .05<=a.confidence<=.95: p.error('Invalid frames or confidence')
    if not YOLO.exists() or not (MODEL/'model.ncnn.bin').is_file(): p.error('YOLO11n binary/model missing')
    a.output.mkdir(parents=True,exist_ok=True)
    for f in a.videos:
        if not f.is_file(): print('MISSING:',f);continue
        print('\n===',f.name,'===',flush=True)
        try: analyze(f,a.output/f.stem,a.frames,a.confidence)
        except Exception as exc: print('FAILED:',f.name,type(exc).__name__,str(exc)[:200],flush=True)
    print('RESULTS:',a.output)
    print('READ-ONLY: did not modify AI alert state, email, recorder, or cron.')
if __name__=='__main__':main()
