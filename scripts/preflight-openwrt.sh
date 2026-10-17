#!/bin/sh
# Safe dry-run: copy+compile repo code without modifying any installed recorder.
# Optional --runtime validates USB mount and local config (never prints their values).
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
case "${1:-}" in
    '') ;;
    --runtime) ;;
    *) echo "Usage: $0 [--runtime]" >&2; exit 2 ;;
esac
command -v python3 >/dev/null
echo '[CHECK] Python, Crypto, syntax, clean installation copy'
python3 -c 'from Crypto.Cipher import AES; print("PyCryptodome: OK")'
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for NAME in relay_capture.py v380_hevc_decode.py hevc_to_mp4.py v380_cycle_recorder.py; do
    cp "$ROOT/src/$NAME" "$TMP/$NAME"
done
python3 -m compileall -q "$TMP"
echo '[PASS] Fresh source copy and compile succeeded; live installation untouched'
if [ "${1:-}" = '--runtime' ]; then
    echo '[CHECK] /mnt/usb2 and private config'
    python3 - <<'PY'
import json, os, pathlib
assert os.path.ismount('/mnt/usb2'), '/mnt/usb2 not mounted'
p = pathlib.Path('/etc/v380_recorder.json')
s = pathlib.Path('/etc/v380_camera_password')
assert p.is_file(), 'Missing /etc/v380_recorder.json'
assert s.is_file(), 'Missing private camera password file'
cfg = json.loads(p.read_text())
assert isinstance(cfg['device_id'], int) and cfg['device_id'] > 0
ips = cfg.get('relay_allowlist')
assert isinstance(ips,list) and ips and all(isinstance(x,str) for x in ips)
for f in [p,s]:
    assert f.stat().st_mode & 0o077 == 0, f'{f} must have permissions 600'
print('Mount and private file checks: OK; values not displayed')
PY
fi
echo '[NOTE] Synthetic tests cannot prove live camera interoperability or MP4 playback.'
