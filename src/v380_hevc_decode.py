from collections import Counter
from pathlib import Path
import struct
from Crypto.Cipher import AES

def decode_capture(raw_filename, auth_ticket):
    raw_path = Path(raw_filename)
    out_path = raw_path.with_suffix('.h265')

    key = struct.pack(
        '<IQI',
        auth_ticket,
        0x618123462C14795C,
        0x82800DF0
    )
    aes = AES.new(key, AES.MODE_ECB)
    data = raw_path.read_bytes()

    pos = 0
    frame_parts = bytearray()
    expected_total = 0
    next_fragment = 0
    active_type = -1
    frames = Counter()
    bad_start = 0
    discontinuities = 0
    skipped_bytes = 0
    nal_types = Counter()
    frame_rates = Counter()

    with out_path.open('wb') as dst:
        while pos + 12 <= len(data):
            if data[pos] != 0x7F:
                pos += 1
                skipped_bytes += 1
                continue

            typ = data[pos + 1]
            total, index, size = struct.unpack_from(
                '<HHH', data, pos + 3
            )

            if not (
                1 <= total <= 4096
                and index < total
                and 1 <= size <= 20000
            ):
                pos += 1
                skipped_bytes += 1
                continue

            end = pos + 12 + size
            if end > len(data):
                print('[WARN] Incomplete trailing packet')
                break

            frag = data[pos + 12:end]
            pos = end

            if typ not in (0x00, 0x01, 0x28, 0x29):
                continue

            if index == 0:
                frame_parts.clear()
                expected_total = total
                next_fragment = 0
                active_type = typ

            if (
                total != expected_total
                or index != next_fragment
                or typ != active_type
            ):
                discontinuities += 1
                frame_parts.clear()
                expected_total = 0
                continue

            frame_parts.extend(frag)
            next_fragment += 1

            if next_fragment != total:
                continue

            full = frame_parts
            frame_parts = bytearray()
            expected_total = 0

            if len(full) <= 16:
                continue

            # Skip 16-byte inner frame header.
            video = bytearray(full[16:])

            # AES-ECB: decrypt 64 bytes per 80-byte block.
            for off in range(0, len(video) - 63, 80):
                video[off:off + 64] = aes.decrypt(
                    bytes(video[off:off + 64])
                )

            start = -1
            for i in range(min(16, len(video) - 3)):
                if video[i:i + 3] == b'\x00\x00\x01':
                    start = (
                        i - 1
                        if i and video[i - 1] == 0
                        else i
                    )
                    break

            if start < 0:
                bad_start += 1
                continue

            video = video[start:]

            sc_len = (
                4 if video.startswith(b'\x00\x00\x00\x01')
                else 3
            )
            if len(video) >= sc_len + 2:
                nal_types[
                    (video[sc_len] >> 1) & 0x3F
                ] += 1

            dst.write(video)
            frames[typ] += 1
            frame_rates[
                struct.unpack_from('<H', full, 6)[0]
            ] += 1

    print('[DECODE] Video frames:', sum(frames.values()))
    print('[DECODE] Keyframes:', frames[0x00] + frames[0x28])
    print('[DECODE] Rejected frames:', bad_start)
    print('[DECODE] Fragment errors:', discontinuities)
    print('[DECODE] Skipped bytes:', skipped_bytes)
    print('[DECODE] HEVC NAL types:', dict(nal_types))
    print('[DECODE] FrameRate fields:', dict(frame_rates))
    print('[DECODE] File:', out_path)
    print('[DECODE] Size:', out_path.stat().st_size)

    return out_path
