# Troubleshooting / Диагностика

## Camera offline / solar battery empty

The recorder attempts a short session every 15 minutes. Failure or timeout
means that the next slot is attempted; no lost interval can be recreated.
The recorder should **not** keep a permanent relay connection alive.

## Relay discovery returned no allowed relays

The dispatcher may return new addresses, a different shape, or a response that
isn't on the local `relay_allowlist`. The recorder falls back to previously
approved IP addresses. That can stop working after provider changes. Do **not**
disable allowlisting or automatically trust unverified IPs. Validate new relay
addresses independently before editing `/etc/v380_recorder.json`.

## `Connection reset by peer`

A TCP reset does not, by itself, prove that the password is wrong. Check the
protocol sequence, server selection and network access. The old `8089`
JSON-RPC implementation failed in the tested setup; a different relay workflow
was required.

## `ffprobe` says `Could not find a valid device`

Some OpenWrt FFmpeg packages deliberately disable the software HEVC parser /
demuxer / decoder and expose only the `hevc_v4l2m2m` interface. Without a
hardware decoder, video inspection on the router fails. This does not prove
that the MP4 is broken. The project uses a pure-Python MP4 muxer; test
playback on a device with H.265 support.

## Video has no audio

Audio recording is optional. Check sanitized `cycle.log` lines for `[AUDIO]`
and `Saved with audio`. FFmpeg is required for AAC output. G.711 A-law is
assumed heuristically unless AAC-ADTS is recognized; verify sound quality by
comparing with the official application. Do not publish sample recordings
without protecting privacy.

## USB mount disappears

Do not store the archive on the OpenWrt overlay. Verify the USB is really
mounted: `mount | grep /mnt/usb2` and `df -h /mnt/usb2`. The recorder checks
`os.path.ismount()` and skips writes when the device is not mounted.

## Cron entry duplicates

Only one entry should invoke `v380_cycle_recorder.py`. Check
`grep v380_cycle_recorder.py /etc/crontabs/root`. Recordings are protected
against overlapping invocations by an advisory lock, but duplicate cron jobs
are still unnecessary.

## Example of a *sanitized* successful log

```text
[LOCAL_TIME +0300] Starting scheduled 25-second recording
[LOCAL_TIME +0300] Trying relay APPROVED_RELAY_IP:8800
[LOCAL_TIME +0300] [STREAM] Received bytes: ~1000000
[LOCAL_TIME +0300] [DECODE] Video frames: ~360
[LOCAL_TIME +0300] [DECODE] Fragment errors: 0
[LOCAL_TIME +0300] [AUDIO] Frames: ~480; codec: G.711 A-law (assumed)
[LOCAL_TIME +0300] Saved with audio TIMESTAMP.mp4
```

Numbers are illustrative. A successful field test produced a playable MP4
with H.265 and a sound track; tests have not proved universal compatibility.
