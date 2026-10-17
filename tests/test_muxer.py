"""Synthetic MP4 tests; no user camera data and no network access."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
mod_spec = importlib.util.spec_from_file_location('hevc_to_mp4', ROOT/'src'/'hevc_to_mp4.py')
mux = importlib.util.module_from_spec(mod_spec)
mod_spec.loader.exec_module(mux)

# Self-generated HEVC parameter sets from a synthetic 320x240 test pattern;
# no real camera footage or private metadata.
VPS = bytes.fromhex('40010c01ffff01600000030090000003000003003cba0240')
SPS = bytes.fromhex('42010101600000030090000003000003003ca00a080f165ba4a4c2f0168080000003008000000604')
PPS = bytes.fromhex('4401c073c189')


class MuxerTest(unittest.TestCase):
    def test_sps_resolution(self):
        self.assertEqual((mux.sps_details(SPS)['width'], mux.sps_details(SPS)['height']), (320, 240))

    def test_split_annexb(self):
        stream = b'\x00\x00\x00\x01' + VPS + b'\x00\x00\x01' + SPS
        nals = list(mux.split_annexb(stream))
        self.assertEqual([kind for kind, _ in nals], [32, 33])

    def test_mp4_box_and_samples(self):
        self.assertEqual(mux.box('free', b'abc'), struct.pack('>I', 11) + b'freeabc')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src, out = root/'sample.h265', root/'sample.mp4'
            # NAL 19 = IDR; NAL 1 = TRAIL_R. Synthetic payload, not a playable video.
            frames = [(32, VPS), (33, SPS), (34, PPS),
                      (19, bytes([19 << 1, 1]) + b'\x44\x55\x66'),
                      (1, bytes([1 << 1, 1]) + b'\x11\x22')]
            src.write_bytes(b''.join(b'\0\0\0\1' + n for _, n in frames))
            mux.run(src, out, 12)
            data = out.read_bytes()
            self.assertEqual(data[4:8], b'ftyp')
            self.assertIn(b'moov', data)
            self.assertIn(b'mdat', data)
            self.assertIn(b'hvc1', data)
            self.assertIn(b'hvcC', data)
            self.assertGreater(len(data), 200)

    def test_invalid_sps(self):
        with self.assertRaises(ValueError):
            mux.sps_details(b'\x42\x01')


if __name__ == '__main__':
    unittest.main()
