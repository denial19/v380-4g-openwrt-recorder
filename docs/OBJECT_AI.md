# Experimental V380 NanoDet ARM64 object detection

This is a **separate experimental component**, not a change to the V380 recorder. The camera continues saving MP4 independently of the AI process.

## What it does

The GitHub Actions workflow produces a self-contained, statically linked AArch64 CPU-only NanoDet inference binary and the pretrained NanoDet-M COCO model. Model labels exported to JSON: person, car, motorcycle, bus, truck. A pretrained generic detector is NOT a vehicle identity recognizer.

References: [NCNN](https://github.com/Tencent/ncnn), [NanoDet](https://github.com/RangiLyu/nanodet), [pre-converted model weights](https://github.com/nihui/ncnn-assets). Retain third-party licenses accompanying the artifact.

## Deploy and test safely on OpenWrt

Download the build artifact from GitHub Actions onto your phone, then transfer it to `/mnt/usb2/V380/ai/v380-nanodet-arm64-static.zip` via SFTP. Extract and verify it using Python, writing the executable and models under `/mnt/usb2/V380/ai/nanodet` (not `/overlay`).

```sh
python3 - <<'PY'
from pathlib import Path
import zipfile,hashlib
src=Path('/mnt/usb2/V380/ai/v380-nanodet-arm64-static.zip')
dst=Path('/mnt/usb2/V380/ai/nanodet')
with zipfile.ZipFile(src) as z:
    items={n:z.read(n) for n in ['v380-nanodet','nanodet_m.param','nanodet_m.bin','SHA256SUMS','NCNN_LICENSE.txt','NANODET_LICENSE.txt']}
checks={line.split()[1]:line.split()[0] for line in items['SHA256SUMS'].decode().splitlines()}
for name,hashvalue in checks.items():
    assert name in items and hashlib.sha256(items[name]).hexdigest()==hashvalue, 'bad checksum: '+name
dst.mkdir(parents=True,exist_ok=True)
for name,b in items.items():
    (dst/name).write_bytes(b)
(dst/'v380-nanodet').chmod(0o755)
print('OK: NanoDet installed on USB')
PY
```

With your existing JPEG of the middle parking camera:

```sh
nice -n 15 /mnt/usb2/V380/ai/nanodet/v380-nanodet \
  /mnt/usb2/V380/ai/parking.jpg \
  /mnt/usb2/V380/ai/nanodet
```

Expect JSON with object labels, confidence, and bounding boxes in **pixels of parking.jpg**. Do not infer a car departed based on a single missed detection. Validate in daylight and at night before enabling notification.

## Emails and temporal logic: next stage

Once the first detections are verified, add an event tracker that compares *individual bounding boxes*, not just whether the parking lot has any cars. Require repeated misses in valid images before emitting `vehicle_missing`; produce `UNKNOWN` on recording errors or low-quality frames. If two cars are swapped at the same parking spot between 15-minute samples, an object detector cannot uniquely establish identity. Notification emails should be opt-in, rate-limited, use an SMTP app password in `/etc` with chmod 600, and must not contain private camera credentials.

**No cron entries or outbound emails are configured by this build.**

## Experimental per-vehicle event tracking (no cron by default)

The `ai/parking_events.py` program accepts detector JSON and maintains per-position vehicle tracks. It raises `vehicle_no_longer_detected` after an object was confirmed in **two distinct observations** and then unmatched in **two further observations**. It is an estimate only: night IR, occlusion, weather, identical parking positions, or 15-minute gaps can produce errors.

First, keep it **manual and without email**:

```sh
AI=/mnt/usb2/V380/ai
REPO=/mnt/usb2/v380-4g-openwrt-recorder-public
nice -n 15 "$AI/nanodet/v380-nanodet" "$AI/parking.jpg" "$AI/nanodet" > "$AI/objects.json"
python3 "$REPO/ai/parking_events.py" "$AI/objects.json" --source "test-$(date +%s)"
```

Later run it with a different source filename for **each new successful MP4**. Inference failures, offline recordings, and badly exposed frames must *not* be entered as empty object arrays; that would generate false departures. The `--roi X0 Y0 X1 Y1` argument limits detections to a specific parking region in 640x360 crop coordinates (object center inside rectangle). Configure this using a parking image before enabling notifications.

### Opt-in SMTP emails

The script accepts `--send-mail`, but only sends if `/etc/v380_ai_mail.json` exists with `enabled: true`. It reads an independent SMTP app password file, never the camera password. Example (edit with your own provider, host, sender, recipient):

```json
{
  "enabled": false,
  "host": "smtp.example.org",
  "port": 465,
  "security": "ssl",
  "username": "sender@example.org",
  "from": "sender@example.org",
  "to": "recipient@example.org",
  "password_file": "/etc/v380_ai_smtp_password"
}
```

Keep both `/etc/v380_ai_mail.json` and `/etc/v380_ai_smtp_password` at mode `600`. Use a provider-specific **application password**, never your mailbox's primary password if the provider supports app passwords. Do not enable cron/email until the detector's night and day accuracy is confirmed and an event-delivery retry queue is implemented. Current experimental email delivery does **not** retry failed SMTP sends automatically; a failure is printed in the log, and the event itself remains in `parking-events.jsonl`.

Test the Python state logic without any model or camera:

```sh
python3 /mnt/usb2/v380-4g-openwrt-recorder-public/ai/test_parking_events.py
```
