# Local camera AI: phase 1 — HEVC frame extraction

**Status:** experimental build pipeline, not yet tested on the Cudy router. This is *not* a person/car detector. It is the first prerequisite: extracting pixels from V380 MP4 clips.

## Why a private FFmpeg binary?

OpenWrt's stock `libffmpeg-full` may have the HEVC software decoder, parser and demuxer disabled at build time. The V380 recorder can nevertheless make playable HEVC MP4s, because it only repackages encrypted stream data. An AI classifier must decode images first.

This repository includes a **separate, static musl ARM64 FFmpeg** build workflow. It does **not** replace `/usr/bin/ffmpeg` or system `libffmpeg-*` packages. Compatible target: ARMv8 Cortex-A53, Linux/aarch64/musl, such as tested router family Cudy WBR3000UAX v1. FFmpeg source: upstream 6.1.5, SHA256 pinned in the workflow; LGPL license files are bundled.

## Build in GitHub Actions

1. On GitHub, open **Actions → Build standalone HEVC frame extractor (ARM64 musl)**.
2. Select **Run workflow** (or open the automatic run triggered by the workflow's first push).
3. Wait for the `static-arm64` job. It compiles with a native ARM64 runner and tests extraction from a synthetic MP4.
4. Download the artifact named `v380-hevc-aarch64-musl` from the successful run.
5. Transfer the ZIP to your OpenWrt router by SFTP, for example to `/mnt/usb2/V380/ai/build.zip`.

**Do not proceed if the GitHub Actions job is red.** A GitHub-hosted ARM64 test does not guarantee compatibility with every OpenWrt build; confirm locally.

## Install on the router (no APK installation)

The following commands assume the ZIP is `/mnt/usb2/V380/ai/build.zip` and Python3 is installed:

```sh
mkdir -p /mnt/usb2/V380/ai/bin
python3 -m zipfile -e /mnt/usb2/V380/ai/build.zip /mnt/usb2/V380/ai/bin
cd /mnt/usb2/V380/ai/bin
sha256sum -c SHA256SUMS
chmod 755 ffmpeg-hevc
./ffmpeg-hevc -hide_banner -decoders | grep hevc
```

Extract one frame from an existing, already recorded clip (never send private clips to CI):

```sh
CLIP="$(ls -t /mnt/usb2/V380/archive/*.mp4 | head -n 1)"
sh /mnt/usb2/v380-4g-openwrt-recorder-public/scripts/extract-hevc-frame.sh \
  "$CLIP" /mnt/usb2/V380/ai/test-frame.jpg
ls -lh /mnt/usb2/V380/ai/test-frame.jpg
```

Download the JPEG to your phone and visually confirm it is valid.

## Resource policy

- Start manually only; no automatic AI jobs yet.
- Decode **one** 320-pixel-wide frame, using one decoding thread and `nice -n 15`.
- Keep 200 MB or more RAM available when practical. Never run a large ONNX/YOLO Python stack on a production router without measurement.
- Monitor with `free`, `top`, and `dmesg` if decoding is unexpectedly slow or memory-intensive.
- Models and images belong on the USB storage, **never** `/overlay`.

## Future work

1. Measure peak RSS and execution time per clip.
2. Confirm nighttime and daylight frame decoding.
3. Add a CPU-only quantized detector for `person` and `car` (or a simpler region-of-interest occupancy classifier).
4. Track repeated detections before reporting 'car departed' or 'person present'. A 25-second clip every 15 minutes cannot detect all transient events.
5. Keep camera IDs, stream tickets, private footage, and passwords off GitHub.
