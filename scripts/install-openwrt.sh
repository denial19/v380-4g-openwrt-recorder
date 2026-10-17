#!/bin/sh
set -eu
SRC="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
BASE=/mnt/usb2/V380
if ! mount | grep -q ' on /mnt/usb2 '; then
    echo 'ERROR: USB /mnt/usb2 not mounted; refusing to write internal flash' >&2
    exit 1
fi
if [ ! -f /etc/v380_recorder.json ] || [ ! -f /etc/v380_camera_password ]; then
    echo 'ERROR: first configure /etc/v380_recorder.json and /etc/v380_camera_password' >&2
    exit 1
fi
mkdir -p "$BASE"
for name in relay_capture.py v380_hevc_decode.py hevc_to_mp4.py v380_cycle_recorder.py; do
    if [ -e "$BASE/$name" ]; then
        echo "ERROR: $BASE/$name exists, refusing to overwrite working files" >&2
        exit 1
    fi
done
for name in relay_capture.py v380_hevc_decode.py hevc_to_mp4.py v380_cycle_recorder.py; do
    cp "$SRC/src/$name" "$BASE/$name"
done
echo 'Installed. Test one run with:'
echo 'python3 /mnt/usb2/V380/v380_cycle_recorder.py'
echo 'Then add cron: */15 * * * * /usr/bin/python3 /mnt/usb2/V380/v380_cycle_recorder.py >/dev/null 2>&1'
