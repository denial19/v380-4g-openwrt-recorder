# Clean OpenWrt installation checklist

This is an **installation procedure**, not a promise of universal compatibility.
The project's author verified recordings on one OpenWrt installation with one
V380 Pro 4G device; automatic fresh-router setup has not been field tested.

## Requirements

- OpenWrt with `apk`, writable overlay with enough room for Python and AES.
- USB media with a Linux filesystem such as ext4, stably mounted at `/mnt/usb2`
  using filesystem UUID (`block-mount`).
- Camera's device ID and a separate password set in the official V380 Pro app.
- Known approved relay addresses, independently verified before authentication.

## Dependencies

```sh
apk update
apk add python3 python3-cryptodome ca-bundle
# Optional if you want AAC audio:
apk add ffmpeg
```

If the overlay is nearly full, stop; never install large packages blindly.
If `/mnt/usb2` isn't mounted, stop. The recorder refuses to write into rootfs.

## Local configuration (DO NOT COMMIT)

Copy `config.example.json` to `/etc/v380_recorder.json`; replace all sample
values (the sample relay IP is deliberately non-routable). Set mode `600`:

```sh
cp config.example.json /etc/v380_recorder.json
chmod 600 /etc/v380_recorder.json
```

Edit it with a suitable local editor. **Do not paste your camera ID or password
into GitHub issues.** Enter the password locally with terminal echo disabled;
this writes a root-only file without embedding a password in a command:

```sh
umask 077
stty -echo
printf 'Camera password: '
IFS= read -r CAMERA_PASSWORD
stty echo
printf '\n'
printf '%s\n' "$CAMERA_PASSWORD" > /etc/v380_camera_password
unset CAMERA_PASSWORD
chmod 600 /etc/v380_camera_password
```

If the SSH terminal is interrupted while echo is disabled, use `stty echo` to
restore it. Never commit the two `/etc` files.

## Dry-run / smoke tests

From the checked-out repository on the router:

```sh
sh scripts/preflight-openwrt.sh
# Once config and mount are prepared, optionally:
sh scripts/preflight-openwrt.sh --runtime
python3 -m unittest discover -s tests -v
python3 scripts/security_audit.py
```

The first command simulates a clean source copy into a **temporary directory**,
compiles it, and removes the temporary copy. It does not connect to the camera.

## Installation and scheduling

```sh
sh scripts/install-openwrt.sh
# Only if there is no existing recorder at /mnt/usb2/V380:
python3 /mnt/usb2/V380/v380_cycle_recorder.py
```

After confirming a new clip plays on a separate device, add **one** cron entry
(never duplicate an existing entry):

```sh
grep v380_cycle_recorder.py /etc/crontabs/root || \
  echo '*/15 * * * * /usr/bin/python3 /mnt/usb2/V380/v380_cycle_recorder.py >/dev/null 2>&1' >> /etc/crontabs/root
/etc/init.d/cron enable
/etc/init.d/cron restart
```

## Verify operation

```sh
mount | grep /mnt/usb2
tail -n 20 /mnt/usb2/V380/cycle.log
ls -lht /mnt/usb2/V380/archive/ | head
```

**Field checks still required:** camera online/offline transitions, successful
MP4 playback, audio quality, schedule after restart, free-space and archive
rotation, and behavior when the relay server changes.
