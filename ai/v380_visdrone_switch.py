#!/usr/bin/env python3
"""Enable *parking-only* VisDrone after passing pre-recorded daytime+night tests.

Leaves YOLO11n for upper/lower people. No cron, SMTP, recorder or state reset.
Usage: v380_visdrone_switch.py status|apply 640|apply 960|rollback
"""
from pathlib import Path
import fcntl
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

AI=Path('/mnt/usb2/V380/ai')
TARGET=AI/'v380_ai_alerts.py'
BACKUP=AI/'v380_ai_alerts.py.bak-before-visdrone-parking'
LOCK=AI/'.v380_ai_alerts.lock'
VIS=AI/'visdrone/v380-visdrone'
MODELDIR=AI/'visdrone/models'
REPORTS=AI/'visdrone-comparison'
MARKER='# V380_VISDRONE_PARKING_ONLY'

# The expected counts refer to clips manually inspected together with the camera owner.
CASES={'2026-10-19_09-45-01':1,'2026-10-19_10-00-01':1,
       '2026-10-19_10-15-01':0,'2026-10-19_19-30-00':0,
       '2026-10-19_19-45-00':1,'2026-10-19_20-00-00':1}


def verify_comparison(size):
    print('Validating saved side-by-side reports for model',size)
    for name,expected in CASES.items():
        file=REPORTS/name/'report.json'
        if not file.is_file():
            raise RuntimeError('No comparison for '+name+', run v380_visdrone_compare.py first')
        d=json.loads(file.read_text())
        if d.get('errors'):
            raise RuntimeError(name+' comparison had errors: '+repr(d['errors'][:2]))
        a=d.get('summary',{}).get(size,{})
        got=a.get('inferred_vehicles')
        hits=a.get('hits',0)
        valid=a.get('valid_frames',0)
        secs=a.get('avg_seconds')
        print(f'  {name} expected={expected}, detected={got}, hits={hits}/{valid}, runtime={secs}s')
        if valid < 4 or got!=expected or secs is None or secs>16:
            raise RuntimeError('Quality gate FAILED for '+name+' (do not activate)')
        if expected>0 and hits<2:
            raise RuntimeError('Insufficient repeated detection: '+name)
    # Extra two-car night case: expected two if the recording is actually of the shown two cars.
    extra=REPORTS/'2026-10-20_18-30-00'/'report.json'
    if extra.is_file():
        d=json.loads(extra.read_text())
        if d.get('errors'): raise RuntimeError('Two-car night test produced errors')
        a=d.get('summary',{}).get(size,{})
        if a.get('inferred_vehicles',0)<2:
            raise RuntimeError('Two-car nighttime test FAILED (18:30); keeping old model')
    print('All available quality checks passed for',size)


def patched(src,sz):
    if MARKER in src:
        raise RuntimeError('Already switched; rollback before reinstalling')
    # This is version-pinned to the live script on which orientation fix v2 was applied.
    must=("DETECTOR = AI / 'yolo11n/v380-yolo11n'", "MODEL = AI / 'yolo11n'",
          "def detect(jpeg):", 'objects = detect(jpeg)', "VEHICLES = {'car', 'truck', 'bus'}",
          'V380_ORIENTATION_V2', 'V380_VISUAL_V1')
    for m in must:
        if src.count(m)!=1:raise RuntimeError('Unexpected V380 source, expected one '+m)
    src=src.replace("VEHICLES = {'car', 'truck', 'bus'}",
                    "VEHICLES = {'car', 'truck', 'bus', 'van'}",1)
    p="MODEL = AI / 'yolo11n'"
    src=src.replace(p,p+"\n"+MARKER+"\nVISDRONE_EXEC = AI / 'visdrone/v380-visdrone'\n"+
                    f"VISDRONE_MODEL = AI / 'visdrone/models/{sz}'\n",1)
    orig='''def detect(jpeg):
    return safe_objects(shell([str(DETECTOR), str(jpeg), str(MODEL)], timeout=40))'''
    patch='''def detect(jpeg, view=None):
    if view == 'parking':
        return safe_objects(shell([str(VISDRONE_EXEC), str(jpeg), str(VISDRONE_MODEL), '0.25'], timeout=160))
    return safe_objects(shell([str(DETECTOR), str(jpeg), str(MODEL)], timeout=40))'''
    if src.count(orig)!=1: raise RuntimeError('Unknown detection function, cannot safely patch')
    src=src.replace(orig,patch,1)
    src=src.replace('objects = detect(jpeg)','objects = detect(jpeg, key)',1)
    # Validate component paths before normal processing, too.
    look='for path in (ARCHIVE, HEVC, DETECTOR, MODEL):'
    if src.count(look)!=1: raise RuntimeError('Unknown USB preflight')
    src=src.replace(look,'for path in (ARCHIVE, HEVC, DETECTOR, MODEL, VISDRONE_EXEC, VISDRONE_MODEL):',1)
    src=src.replace('Количество определено нейросетью YOLO11n;',
                    'Количество автомобилей определено VisDrone YOLO11s;',1)
    compile(src,str(TARGET),'exec')
    return src


def write_atomic(data):
    mode=stat.S_IMODE(TARGET.stat().st_mode)
    fd,tmp=tempfile.mkstemp(prefix='.v380-visdrone-switch-',dir=str(AI))
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),mode)
            f.write(data.encode())
            f.flush();os.fsync(f.fileno())
        os.replace(tmp,TARGET)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def smoke(sz):
    imgs=list(AI.glob('preview_2026-10-19_09-45-01/parking.jpg'))
    if not imgs:imgs=list(AI.glob('yolo11-comparison/2026-10-19_09-45-01/parking_frame_*.jpg'))
    if not imgs:raise RuntimeError('Missing known daylight parking JPEG')
    cmd=[str(VIS),str(imgs[0]),str(MODELDIR/sz),'0.25']
    result=subprocess.run(cmd,text=True,capture_output=True,timeout=170)
    if result.returncode:raise RuntimeError('Model smoke failed: '+result.stderr[-280:])
    d=json.loads(result.stdout)
    if (d.get('width'),d.get('height'),d.get('model'))!=(640,360,'visdrone-yolo11s'):
        raise RuntimeError('Wrong model output schema')
    print('Smoke JSON correct:',len(d.get('objects',[])),'detections')


def main():
    args=sys.argv[1:]
    if args not in (['status'],['rollback'],['apply','640'],['apply','960']):
        raise RuntimeError('Usage: status | apply 640 | apply 960 | rollback')
    if os.geteuid() or not os.path.ismount('/mnt/usb2'):
        raise RuntimeError('Run as root with /mnt/usb2 mounted')
    with LOCK.open('a+') as file:
        fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        src=TARGET.read_text()
        if args==['status']:
            print('Parking detector:', 'VisDrone YOLO11s '+('960' if "visdrone/models/960" in src else '640')
                  if MARKER in src else 'Existing YOLO11n')
            print('Upper/lower people: YOLO11n; recorder and SMTP unaffected')
            print('Saved rollback:',BACKUP.exists())
            return
        if args==['rollback']:
            if MARKER not in src or not BACKUP.exists():
                raise RuntimeError('No active VisDrone or no backup; nothing done')
            original=BACKUP.read_text()
            compile(original,str(TARGET),'exec')
            write_atomic(original)
            print('ROLLED BACK parking only: old YOLO11n source restored. AI state unchanged.')
            return
        sz=args[1]
        if not (VIS.is_file() and (MODELDIR/sz/'model.ncnn.bin').is_file()):
            raise RuntimeError('VisDrone model not installed')
        verify_comparison(sz)
        smoke(sz)
        updated=patched(src,sz)
        if BACKUP.exists():
            raise RuntimeError('Old VisDrone backup already exists; refusing to overwrite')
        # Refuse change if user has altered source unexpectedly since backup checks.
        shutil.copy2(TARGET,BACKUP)
        BACKUP.chmod(0o600)
        write_atomic(updated)
        print('ACTIVE: VisDrone YOLO11s',sz,'for PARKING only; YOLO11n for people.')
        print('Backups:',BACKUP)
        print('Recorder/cron/SMTP/pending mail/confirmed vehicle state UNCHANGED')

if __name__=='__main__':
    try:main()
    except BlockingIOError:
        print('ERROR: V380 AI busy, retry after cron finishes',file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print('ERROR:',type(exc).__name__,exc,file=sys.stderr)
        raise SystemExit(1)
