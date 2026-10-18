#!/bin/sh
# Extract exactly one JPEG from an already recorded local MP4.
# Does NOT contact any camera or server; does NOT change V380 recording.
set -eu
BIN='/mnt/usb2/V380/ai/bin/ffmpeg-hevc'
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: sh $0 INPUT_MP4 [OUTPUT_JPG]" >&2
  exit 2
fi
VIDEO=$1
OUT=${2:-/mnt/usb2/V380/ai/test-frame.jpg}
[ -f "$VIDEO" ] || { echo "Missing input: $VIDEO" >&2; exit 1; }
[ -x "$BIN" ] || { echo "Missing executable: $BIN" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"
# 1 decoding thread and low scheduling priority to protect the router.
nice -n 15 "$BIN" -hide_banner -loglevel warning -y \
  -threads 1 -i "$VIDEO" -vf 'scale=320:-2' \
  -frames:v 1 -q:v 5 "$OUT"
[ -s "$OUT" ] || { echo 'Failed to produce JPEG' >&2; exit 1; }
echo "JPEG saved: $OUT"
