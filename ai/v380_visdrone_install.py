#!/usr/bin/env python3
"""Install GitHub Actions VisDrone model onto external USB only; do NOT activate."""
from pathlib import Path
import hashlib
import os
import shutil
import sys
import tempfile
import zipfile

AI = Path('/mnt/usb2/V380/ai')
ZIP = AI / 'v380-visdrone-yolo11s-arm64.zip'
DEST = AI / 'visdrone'
REQUIRED = ('v380-visdrone','models/640/model.ncnn.param','models/640/model.ncnn.bin',
            'models/640/model_size.txt','models/960/model.ncnn.param','models/960/model.ncnn.bin',
            'models/960/model_size.txt','SHA256SUMS','MODEL_NOTICE.txt',
            'NCNN_LICENSE.txt','ULTRALYTICS_AGPL_LICENSE.txt')

def main():
    if os.geteuid() or not os.path.ismount('/mnt/usb2'):
        raise RuntimeError('Run as root and mount /mnt/usb2; internal flash must not be used')
    if not ZIP.is_file(): raise RuntimeError('Upload artifact ZIP via SFTP to '+str(ZIP))
    if DEST.exists(): raise RuntimeError('Already installed, refusing to overwrite '+str(DEST))
    with zipfile.ZipFile(ZIP) as z:
        names=set(z.namelist())
        if not set(REQUIRED).issubset(names):
            raise RuntimeError('Missing entries: '+repr(set(REQUIRED)-names))
        manifest=z.read('SHA256SUMS').decode('ascii').splitlines()
        hashes={}
        for row in manifest:
            parts=row.split()
            if len(parts)!=2: raise RuntimeError('Invalid SHA256SUMS line')
            hashes[parts[1]]=parts[0]
        expected=set(REQUIRED[:7])
        if set(hashes)!=expected: raise RuntimeError('Unexpected SHA256SUMS contents')
        tmp=Path(tempfile.mkdtemp(prefix='.v380-visdrone-',dir=str(AI)))
        try:
            for name in REQUIRED:
                # no untrusted paths from the ZIP are written: explicit list only
                target=tmp/name
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(name) as reader, target.open('wb') as f:
                    h=hashlib.sha256()
                    while True:
                        block=reader.read(1024*1024)
                        if not block:break
                        f.write(block)
                        h.update(block)
                if name in hashes and hashes[name]!=h.hexdigest():
                    raise RuntimeError('Wrong hash: '+name)
            for size in ('640','960'):
                if (tmp/'models'/size/'model_size.txt').read_text().strip()!=size:
                    raise RuntimeError('Incorrect model size')
            (tmp/'v380-visdrone').chmod(0o755)
            tmp.rename(DEST)
        except BaseException:
            shutil.rmtree(tmp,ignore_errors=True)
            raise
    print('INSTALLED:',DEST)
    print('Current recorder, YOLO11n, SMTP and cron: UNCHANGED.')
    print('Next: run side-by-side validation before switching.')

if __name__=='__main__':
    try:main()
    except Exception as ex:
        print('INSTALL ERROR:',type(ex).__name__,ex,file=sys.stderr)
        raise SystemExit(1)
