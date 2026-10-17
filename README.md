# V380 4G OpenWrt Recorder

**Experimental, lightweight, intermittent cloud-relay recorder** for selected V380 Pro 4G cameras on OpenWrt. Records a short HEVC/H.265 MP4 clip every 15 minutes, optionally with AAC audio, to a mounted USB drive. Designed for off-grid/solar cameras that may sleep or turn off when their battery is discharged.

[Документация на русском](README.ru.md)

> **Status:** Successfully tested on a V380 Pro 4G camera reporting the hardware family `HsAKQQCG`, relay device protocol version **32**, with a 640×1080 HEVC stream. This is not an official V380 project. Other models and firmware versions are **not confirmed**.

## Features

- Cloud relay access, even if the camera is behind mobile-carrier CGNAT (no direct inbound RTSP/IP access required).
- Time-limited capture (~25 seconds) on a `*/15` cron schedule. No permanent connection or streaming requirement.
- Automatically skips unavailable/offline cameras; retries at the next scheduled time.
- Reassembles V380 video fragments; decrypts HEVC for tested device protocol version 32.
- Produces iPhone-playable MP4 from raw HEVC **without transcoding** (custom Python MP4 muxer).
- Experimental G.711 A-law or AAC-ADTS extraction and optional AAC audio track (requires FFmpeg for audio).
- Rotating archive (default maximum 20 GiB; preserve at least 3 GiB free) with deletion limited to the archive directory.
- Refuses to write if `/mnt/usb2` is not a mounted filesystem; cron overlap prevented by file lock.
- Password is read from a private root-owned file and is not checked into Git.

## Requirements

- OpenWrt 25.12+ (`apk`), Python 3, `python3-cryptodome`, mounted ext4 USB storage at `/mnt/usb2`.
- `ffmpeg` to include audio; **video-only MP4 does not need FFmpeg**. OpenWrt may ship FFmpeg with HEVC parser/decoder disabled.
- A V380 Pro 4G camera, its device ID, and a separately set device password.
- Access to approved/verified relay server IPs on TCP 8800.

## Install

**Do not install over an existing working recorder without a backup.** This installer refuses to overwrite source files.

```sh
apk update
apk add python3 python3-cryptodome ca-bundle ffmpeg
# Mount and verify a USB drive at /mnt/usb2; stop if not mounted:
mount | grep ' on /mnt/usb2 '
```

Copy `config.example.json` to **`/etc/v380_recorder.json`** and edit it with your **own** `device_id` and `relay_allowlist` (IPs must be verified independently). Example relay IPs in the sample configuration are reserved documentation addresses and **will not work**. The script uses a restrictive allowlist because the dispatcher endpoint currently speaks unauthenticated HTTP.

Save the device password in a separate file (the terminal will not echo it):

```sh
umask 077
read -r -s -p 'Camera device password: ' PWD  # On BusyBox ash, use stty -echo if -s unsupported
printf '\n'
printf '%s\n' "$PWD" > /etc/v380_camera_password
unset PWD
chmod 600 /etc/v380_camera_password
chmod 600 /etc/v380_recorder.json
```

Alternatively, use `stty -echo; read -r PWD; stty echo` when your BusyBox shell lacks `read -s`. Never put the password into shell history or a public repository. The sample configuration contains no credentials.

Install the scripts (from your checked-out repository):

```sh
sh scripts/install-openwrt.sh
python3 /mnt/usb2/V380/v380_cycle_recorder.py
tail -n 30 /mnt/usb2/V380/cycle.log
```

After confirming that the MP4 plays on another device, enable a 15-minute schedule:

```sh
echo '*/15 * * * * /usr/bin/python3 /mnt/usb2/V380/v380_cycle_recorder.py >/dev/null 2>&1' >> /etc/crontabs/root
/etc/init.d/cron enable
/etc/init.d/cron restart
```

Avoid duplicate cron entries. Change the system timezone in `/etc/config/system` if you need local file timestamps.

## Storage & recordings

- Archive: `/mnt/usb2/V380/archive/*.mp4`
- Temporary working files: `/mnt/usb2/V380/work/`
- Log: `/mnt/usb2/V380/cycle.log`
- Private config: `/etc/v380_recorder.json`
- Private credential: `/etc/v380_camera_password`

Archive rotation only deletes the oldest `*.mp4` inside the dedicated `archive` folder. Keep test recordings and unrelated files elsewhere. No attempt is made to access the camera when the next slot has not arrived.

## Limitations

- Experimental protocol; tested only with `HsAKQQCG`-family V380 Pro camera in device version 32, not every camera or region.
- The cloud-relay discovery endpoint is plain HTTP, not an authenticated discovery channel; whitelist relay IPs you explicitly trust. Do not provide your camera password to unverified relay servers.
- Source currently assumes the on-router install root `/mnt/usb2/V380`; configurable USB mounts can be a future improvement.
- Approximate constant 12 FPS for MP4; timestamps and A/V sync may drift; low-latency no-B-frame HEVC is assumed.
- The audio codec detector is heuristic; G.711 A-law is assumed when AAC/ADTS is not recognized. Test sound quality.
- The recorded MP4 has been played on an iPhone in one successful field test; cross-platform compatibility is not guaranteed.
- Solar camera may be off for hours; a missed slot is **not** backfilled.

## Security & privacy

- Camera IDs, passwords, ICCID/IMEI, live captures, and relay session tickets must never be committed.
- Change a password immediately if it was ever posted publicly or in an issue report.
- Python source in `src/` is generated by sanitizing a known-working local setup; review before running on your hardware.
- **Never** run `git add -A` on your live `/mnt/usb2/V380` working directory.

## Protocol research / attribution

This project is an independent OpenWrt/Python implementation informed by public V380 protocol discussions and research:

- [PyanSofyan/V380Decoder](https://github.com/PyanSofyan/V380Decoder) — video/audio decryption, cloud relay research.
- [j-bloggs/v380-4g-stream](https://github.com/j-bloggs/v380-4g-stream) — early 4G streaming experiments and issue discussion.

This repository does **not** vendor either upstream project's source code or use their logos. V380 Pro and associated trademarks belong to their respective owners. Not affiliated with the camera vendor.

## License

MIT license for the original repository code. No license is granted for the device manufacturer's proprietary software, firmware, or protocols.
