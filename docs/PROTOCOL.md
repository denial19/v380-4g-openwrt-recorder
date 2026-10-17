# V380 4G relay protocol: field observations

> **Experimental reverse-engineering notes, not a vendor specification.** The offsets and
> command meanings below were validated only for one V380 Pro camera in the
> `HsAKQQCG` hardware family, reporting **device protocol version 32**.
> Other firmware, regions and camera models may behave differently.

## Connection diagram

```text
OpenWrt / Python        V380 dispatcher          Relay (TCP/8800)          4G camera
       |                       |                       |                      |
       | POST /api/v1/get_stream_server              |                      |
       |---------------------->|                       |                      |
       |<--- candidate IPs ---|                       |                      |
       |                                               |                      |
       |-- 1167 (auth) ------------------------------->|                      |
       |<---------------------- 1168 (status 1001) ---|                      |
       |                                               |                      |
       |-- 301 (open stream, session ticket) -------->|                      |
       |<---------------------- 401 ------------------|                      |
       |-- 303 (start stream, same TCP connection) -->|                      |
       |<---------------- encrypted A/V fragments ----|<------ via 4G -----|
```

The camera uses its own mobile-data connection; direct inbound access is typically
unavailable with carrier CGNAT. A short clip is captured and the TCP connection is closed;
there is **no continuous background camera connection**.

## Observed handshake

1. **Dispatcher**: `POST http://dispa1.av380.net:8001/api/v1/get_stream_server` with
   device identifier, timestamp, platform and SHA-1 request signature. An observed
   successful response had HTTP `200`, application code `2000`, and a list of relays.
2. **Relay authentication**: binary command `1167` to TCP port `8800` with device ID,
   username (device ID for the tested camera), and encrypted device password.
   Observed reply: command `1168`, status `1001`, device version `32`, and an
   in-memory session ticket. No raw ticket or authentication packet is logged.
3. **Stream setup**: command `301` on a new TCP connection containing the session
   information. Observed reply: command `401` with fields `100, 4, 269`.
   These are observations, **not a complete interpretation** of all response fields.
4. **Stream request**: command `303` **on the same TCP connection as `301`**.
   The relay then sent encrypted video and audio fragments.

The previously tried legacy JSON-RPC server on port `8089` reset the TCP connection
and was not used in the working path.

## Media structure

- The observed relay payload began with a 12-byte non-fragment preamble.
- Fragment marker `0x7F`, followed by a 12-byte header. Fragmented frames were
  reassembled using fragment count/index, without assuming that TCP `recv()` aligns
  with fragment boundaries.
- Observed packet types: `0x28` (key video), `0x29` (inter video), `0x1A` (audio),
  and `0x5B`/`0x5C` (control/metadata). Treat these meanings as model-specific.
- For the tested version 32, HEVC data was decrypted using ticket-derived AES-ECB:
  64 bytes decrypted and the next 16 bytes left untouched, repeating every 80 bytes.
  An internal 16-byte frame header precedes the video elementary stream.
- Audio packets use AES on complete 16-byte blocks; the implementation recognizes
  AAC with ADTS sync and otherwise **assumes** G.711 A-law, 8 kHz mono.
- Raw Annex B HEVC is muxed to MP4 without transcoding. VPS/SPS/PPS/IDR were
  observed and an MP4 was played on an iPhone.

## Safety and limitations

- The dispatcher API observed here is **HTTP rather than HTTPS**. Relay results
  must **not** be treated as trustworthy solely because the dispatcher returned them.
  The recorder uses an explicit locally configured allowlist of vetted IP addresses.
  Manual review is needed when relay addresses change.
- Camera authentication runs over a vendor-specific channel **without TLS server
  identity verification**. A relay's TCP port being open does not establish its
  trustworthiness. Do not send credentials to arbitrary relay addresses.
- The stream implementation uses a fixed nominal FPS of 12 and assumes low-latency
  HEVC with no B-frame reordering. Synchronization can drift.
- Audio recognition is heuristic; wind noise alone does not verify the codec.
- Do not publish captures, full authentication traces, QR labels, IMEI, ICCID,
  device ID, passwords or session tickets.

## Sources and attribution

- https://github.com/PyanSofyan/V380Decoder — publicly documented reverse engineering
  and A/V decryption behavior.
- https://github.com/j-bloggs/v380-4g-stream — early 4G cloud transport experiments.
- https://github.com/j-bloggs/v380-4g-stream/issues/1 — reports about similar hardware.

This repository is independent of V380 Pro's vendor. Names and command values
here are intended for interoperability research for cameras you own or manage.
