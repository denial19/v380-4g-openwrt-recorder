# V380 VisDrone YOLO11s experiment (OpenWrt ARM64)

**This is an experiment; do not activate before checking real camera clips.**
The new detector is ONLY for the **middle parking view**. The upper and lower views use the current YOLO11n person detection. Neither camera recorder nor SMTP, recipients, existing history, cron or AI state are changed by the build/installation/comparison.

## Build

Source weights: `dronefreak/visdrone-yolo11s/best.pt` from Hugging Face. AGPL-3.0; pinned SHA256 `3134756bf29e761550991c0f1e5d91b262736e1c383082172691503227f645e7`. Trained on VisDrone aerial RGB images at 1280. No accuracy guarantee for night IR camera. Benchmark per-class `car` mAP50 81.9% is **NOT** an expected accuracy on our camera. See model card.

One workflow exports 640 and 960 model inputs on an x86 GitHub Actions worker using Ultralytics; a second ARM64 worker builds an NCNN static executable. This CPU binary uses real model decoding; it is not a dummy. It expects 11 VisDrone classes, NOT COCO's 80. VisDrone 3=car, 4=van, 5=truck, 8=bus. Inference outputs these four labels and retains `person` only for other view debug; automated people alerts are **unchanged** and remain YOLO11n.

Artifact name: `v380-visdrone-yolo11s-arm64`.

## Install on OpenWrt USB

Transfer **GitHub Actions artifact** via SFTP to:
`/mnt/usb2/V380/ai/v380-visdrone-yolo11s-arm64.zip`.

Install (does not enable):

```sh
AI=/mnt/usb2/V380/ai
REPO=/mnt/usb2/v380-4g-openwrt-recorder-public
cp "$REPO/ai/v380_visdrone_install.py" "$AI/"
cp "$REPO/ai/v380_visdrone_compare.py" "$AI/"
cp "$REPO/ai/v380_visdrone_switch.py" "$AI/"
python3 "$AI/v380_visdrone_install.py"
python3 "$AI/v380_visdrone_switch.py" status
```

Test first on image from current old YOLO comparison:

```sh
PHOTO="$AI/preview_2026-10-19_19-45-00/parking.jpg"
time nice -n 15 "$AI/visdrone/v380-visdrone" "$PHOTO" "$AI/visdrone/models/640" 0.25
```

## Read-only benchmarking on video files (two model input sizes)

```sh
ARCH=/mnt/usb2/V380/archive
nice -n 15 python3 "$AI/v380_visdrone_compare.py" --frames 6 \
  "$ARCH/2026-10-19_09-45-01.mp4" \
  "$ARCH/2026-10-19_10-00-01.mp4" \
  "$ARCH/2026-10-19_10-15-01.mp4" \
  "$ARCH/2026-10-19_19-30-00.mp4" \
  "$ARCH/2026-10-19_19-45-00.mp4" \
  "$ARCH/2026-10-19_20-00-00.mp4" \
  "$ARCH/2026-10-20_18-30-00.mp4" \
  | tee "$AI/visdrone-comparison.log"
```

Results and annotated `.png`/`.svg` saved at `$AI/visdrone-comparison/<clip>/`. Comparison uses same park view orientation as current YOLO11n (crop center and rotate 180°). Unlike email display, this does NOT apply the cosmetic 40° rotation. Thus detection and bounding boxes are in the same coordinates as the live detector. The 18:30 clip can be missing; the comparator prints `MISSING`.

## Safe activation ONLY IF quality gate passed

The switch requires the two daytime car clips, both empty controls, and *both* nighttime car clips to be detected correctly (at least 2 of 6 samples). If there is an 18:30 nighttime **two-car** comparison, it must recognize >=2. Inference must take no more than 16s per frame on average. Otherwise the switch refuses activation. No way to bypass gate silently.

Test patch dry-run, reading existing LIVE code without edits:

```sh
cd "$REPO"
python3 ai/test_visdrone_upgrade.py
```

Activate selectively (use the variant that actually passed):

```sh
python3 "$AI/v380_visdrone_switch.py" apply 640
# or only if 960 passed:
python3 "$AI/v380_visdrone_switch.py" apply 960
python3 "$AI/v380_visdrone_switch.py" status
v380ai status
```

This changes only which model sees the middle camera, leaves upper/lower on YOLO11n and keeps labeled photo support. A backup is saved as `$AI/v380_ai_alerts.py.bak-before-visdrone-parking`.

Rollback (if necessary):

```sh
python3 "$AI/v380_visdrone_switch.py" rollback
```

**Important:** when switching models, existing confirmed car count is preserved, so the first changed predictions can produce an apparent arrival/departure. Only activate after verification. The old 15-minute camera power schedule is preserved.
