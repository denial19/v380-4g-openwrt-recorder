# v1.0.0 — First experimental release

**V380 4G OpenWrt Recorder** records short clips from a V380 Pro 4G camera through
its cloud relay, storing MP4 files on a mounted USB drive. No direct public IP
or permanent RTSP session is required. Designed for solar cameras that power
off and later reconnect.

### Included

- HEVC/H.265 encrypted fragment assembly and MP4 remux without video transcoding.
- Experimental optional AAC audio track (G.711 A-law or AAC-ADTS source).
- 25-second clips every 15 minutes using OpenWrt cron, next-slot retry after outages.
- 20 GiB circular archive by default, with 3 GiB reserved free space.
- Root-owned password file and configured relay allowlist.
- Bilingual documentation, protocol notes, compatibility table, CI unit checks,
  clean-install dry-run checks and secret/history audit.

### Validated

- One V380 Pro 4G device reporting `HsAKQQCG`, protocol version `32`.
- One apk-based OpenWrt router with ext4 USB storage.
- Video and experimental audio playable on an iPhone.

### Known limitations

- This is independent reverse engineering, **not an official V380 client**.
- Other device types/versions, uptime over months, and new relay regions not verified.
- Relay dispatch is plaintext HTTP; use only independently approved relay IPs.
- Audio detection is heuristic; timestamp/audio sync accuracy may vary.
- OpenWrt FFmpeg may be compiled without HEVC decoding; use an external player.
- Installer will refuse to overwrite an existing working recorder.

**Before installation, read `README.md`, `SECURITY.md`, `docs/COMPATIBILITY.md`
and `docs/TROUBLESHOOTING.md`. Never publish device IDs, passwords or captures.**

Special thanks to protocol research from
[PyanSofyan/V380Decoder](https://github.com/PyanSofyan/V380Decoder) and
[j-bloggs/v380-4g-stream](https://github.com/j-bloggs/v380-4g-stream).
