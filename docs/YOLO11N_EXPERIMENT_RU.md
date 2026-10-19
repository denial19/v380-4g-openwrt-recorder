# V380 AI: YOLO11n NCNN comparison (experimental)

## Purpose

Previous NanoDet 320-based CPU detector repeatedly labelled a night-time **car** as **person**. The new YOLO11n gets a 640×640 tensor; compare on identical images before changing production alert logic. This **does not automatically change** `v380_ai_alerts.py`, the 15-minute recorder, cron, person threshold, SMTP, or status monitor.

**Model weights**: Ultralytics YOLO11n COCO 80-class, AGPL-3.0. Source: [Ultralytics](https://github.com/ultralytics/ultralytics); preexported by [taiji1985/yolo11-ncnn](https://github.com/taiji1985/yolo11-ncnn) (pinned Git commit and blob hashes in workflow). NCNN BSD-3-Clause. GitHub Actions artifact includes corresponding license notices. Review AGPL source/redistribution obligations before merging/releasing publicly. The GitHub repo contains *no weights* or camera images.

## 1. GitHub build

Include `.github/workflows/build-yolo11n-arm64.yml`, `ai/yolo11n_main.cpp`, other scripts from the patch. Push a **new feature branch**. Wait for `Build V380 YOLO11n NCNN (ARM64 CPU)` to succeed. This build produces `v380-yolo11n-aarch64` artifact. The smoke test checks real COCO objects in a real image, not merely that inference returns valid JSON.

## 2. Router install

Save Actions downloaded ZIP via iPhone SFTP as `/mnt/usb2/V380/ai/v380-yolo11n-aarch64.zip`. Then:

```sh
python3 /mnt/usb2/V380/ai/install_v380_yolo11n.py
```

Checks sha256s from Actions before installing in `/mnt/usb2/V380/ai/yolo11n` (on USB). The old detector remains intact.

## 3. Test one already-created JPEG

```sh
AI=/mnt/usb2/V380/ai
PHOTO="$AI/preview_2026-10-19_19-45-00/parking.jpg"
time nice -n 15 "$AI/yolo11n/v380-yolo11n" "$PHOTO" "$AI/yolo11n" 0.25 > "$AI/yolo11_1945.json"
python3 -m json.tool "$AI/yolo11_1945.json"
python3 "$AI/v380_draw_boxes.py" "$PHOTO" "$AI/yolo11_1945.json" "$AI/yolo11_1945_annotated"
```

Files `yolo11_1945_annotated.png` and `.svg` contain **colored bounding boxes with class names/confidence**, including `CAR`, `PERSON`. Download the PNG via SFTP to iPhone. SVG is standalone with the JPEG embedded; works even without Pillow/FFmpeg rawvideo encoder.

For illustration, visualize the previous model misclassification:

```sh
AI=/mnt/usb2/V380/ai
DIR="$AI/preview_2026-10-19_19-45-00"
python3 "$AI/v380_draw_boxes.py" "$DIR/parking-zoom.jpg" "$DIR/objects-zoom.json" "$DIR/nanodet_wrong_person"
```

`parking-zoom.jpg` is 256×192. The red `PERSON` box around the car is a false positive.

## 4. Read-only comparison on six known clips

```sh
AI=/mnt/usb2/V380/ai
ARCH=/mnt/usb2/V380/archive
nice -n 15 python3 "$AI/v380_yolo11_compare.py" --frames 6 \
 "$ARCH/2026-10-19_09-45-01.mp4" \
 "$ARCH/2026-10-19_10-00-01.mp4" \
 "$ARCH/2026-10-19_10-15-01.mp4" \
 "$ARCH/2026-10-19_19-30-00.mp4" \
 "$ARCH/2026-10-19_19-45-00.mp4" \
 "$ARCH/2026-10-19_20-00-00.mp4" \
 | tee "$AI/yolo11-comparison.log"
```

The runner crops the **middle** camera only, extracts frame indices proportionally to actual available MP4 frames, runs NanoDet and YOLO11n **on exactly the same JPEG**, and generates original JPG, JSON, annotated SVG, and annotated PNG (if FFmpeg supports raw RGB). Results stored under `ai/yolo11-comparison/<clip-basename>/`. Analyze rate of correct detections and false positives. At night the actual car might remain unrecognized; a newer model is not a guarantee.

**Do not auto-switch alerts or lower YOLO threshold for event emails until compared on real clips**, including several cars, absent cars, day, night, people in all views. The first deployment runs at priority 15 and never touches SMTP/AI state/cron.
