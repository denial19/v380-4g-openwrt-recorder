# Compatibility / Совместимость

| Item | Tested observation | Confidence |
|---|---|---|
| Mobile application | V380 Pro | Observed |
| Hardware family | `HsAKQQCG` | Observed in app; not a retail model number |
| Device protocol version | 32 | Observed in relay authentication reply |
| Transport | Cloud dispatcher -> relay TCP/8800 | Observed |
| HEVC output | 640×1080, approximately 12 FPS | MP4 played on iPhone |
| Audio | `0x1A` packets, presumed G.711 A-law to AAC | Audible, codec not independently verified |
| Power | 4G, solar-powered, may shut down while battery is empty | Tested use case |
| Recorder | OpenWrt with apk and mounted ext4 USB `/mnt/usb2` | One installation |

**Unconfirmed:** other V380-branded models, firmware, regions, relay servers,
RTSP/ONVIF behavior, multichannel audio, hardware accelerated decoding,
accurate presentation timestamps, and sustained multi-month uptime.

### Contributions

When reporting compatibility, include only generic hardware family, protocol
version, video format and a sanitized log. Do **not** include your device
identifier, QR code, SIM details, passwords, real videos or authentication tokens.
