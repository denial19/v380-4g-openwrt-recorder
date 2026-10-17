# Changelog

## [1.0.0] - 2026-10-17

First experimental public release.

- V380 Pro 4G cloud-relay capture for the tested `HsAKQQCG` family (device protocol v32).
- HEVC fragment assembly, ticket-derived AES decryption and lightweight MP4 muxing.
- Experimental audio extraction (AAC-ADTS / presumed G.711 A-law) and AAC output.
- Short clips by cron every 15 minutes; offline cameras are retried at next interval.
- Archive rotation limited to a dedicated USB folder, minimum-free-space protection,
  and a lock to prevent overlapping captures.
- Root-only local credentials; repository sample configuration contains placeholders.
- English/Russian usage documentation, protocol field notes, synthetic unit tests,
  CI smoke checks and a Git history secret-audit utility.

**Experimental:** real recording and iPhone MP4 playback have been verified on
one camera and one OpenWrt installation; clean-machine live streaming and all
other firmware versions remain unverified.
