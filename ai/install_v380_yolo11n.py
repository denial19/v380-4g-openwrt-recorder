#!/usr/bin/env python3
"""Install verified GitHub Actions YOLO11n artifact onto USB. No AI switch/cron/mail changes."""
from pathlib import Path
import hashlib
import os
import sys
import tempfile
import zipfile

AI=Path('/mnt/usb2/V380/ai')
ZIP=AI/'v380-yolo11n-aarch64.zip'
DEST=AI/'yolo11n'
FILES=('v380-yolo11n','model.ncnn.param','model.ncnn.bin','NCNN_LICENSE.txt',
       'ULTRALYTICS_AGPL_LICENSE.txt','MODEL_NOTICE.txt','SHA256SUMS')

def install():
    if not os.path.ismount('/mnt/usb2'):
        raise RuntimeError('USB is not mounted; will not write internal flash')
    if not ZIP.exists(): raise FileNotFoundError('Upload GitHub Actions artifact to '+str(ZIP))
    if DEST.exists():
        raise FileExistsError('Refusing to overwrite existing installation: '+str(DEST))
    with zipfile.ZipFile(ZIP) as z:
        names=set(z.namelist())
        if not set(FILES).issubset(names): raise RuntimeError('Missing artifact files')
        checks=z.read('SHA256SUMS').decode('ascii').splitlines()
        checks={x.split()[1]:x.split()[0] for x in checks if len(x.split())==2}
        if set(checks)!={'v380-yolo11n','model.ncnn.param','model.ncnn.bin'}:
            raise RuntimeError('Unexpected checksum manifest')
        temp=Path(tempfile.mkdtemp(prefix='.v380-yolo11-install-',dir=str(AI)))
        try:
            for name in FILES:
                data=z.read(name)
                if name in checks and hashlib.sha256(data).hexdigest()!=checks[name]:
                    raise RuntimeError('Checksum mismatch: '+name)
                (temp/name).write_bytes(data)
            (temp/'v380-yolo11n').chmod(0o755)
            temp.rename(DEST)
        except BaseException:
            import shutil
            shutil.rmtree(temp)
            raise
    print('OK: YOLO11n installed at',DEST)
    print('Current NanoDet and automated alerts are unchanged.')
if __name__=='__main__':
    try: install()
    except Exception as exc:
        print('ERROR:',type(exc).__name__,exc,file=sys.stderr)
        sys.exit(1)
