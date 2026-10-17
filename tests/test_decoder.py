"""Decrypt a synthetic single fragment with a made-up ticket; no camera access."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from Crypto.Cipher import AES

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v380_hevc_decode', ROOT/'src'/'v380_hevc_decode.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class DecoderTest(unittest.TestCase):
    def test_one_fragment_roundtrip(self):
        ticket = 42  # illustrative, not a live ticket
        key = struct.pack('<IQI', ticket, 0x618123462C14795C, 0x82800DF0)
        aes = AES.new(key, AES.MODE_ECB)
        # A recognizable Annex B marker plus a synthetic 64-byte video chunk.
        plain = (b'\x00\x00\x00\x01\x26\x01' + b'\xaa' * 74)
        ciphertext = aes.encrypt(plain[:64]) + plain[64:]
        inner = b'\x00' * 16 + ciphertext
        packet = b'\x7f\x28\x01' + struct.pack('<HHH', 1, 0, len(inner)) + b'\x00'*3 + inner
        with tempfile.TemporaryDirectory() as td:
            capture = Path(td)/'capture_test.bin'
            capture.write_bytes(b'\x00'*12 + packet)
            result = mod.decode_capture(capture, ticket)
            self.assertEqual(result.read_bytes(), plain)


if __name__ == '__main__':
    unittest.main()
