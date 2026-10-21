"""Regression checks for NCCH RomFS offsets and bounded hashing."""
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from repack_soul_hackers import ncch_romfs_region, sha


class RepackHeaderTests(unittest.TestCase):
    def header(self):
        result = bytearray(512)
        struct.pack_into("<II", result, 0x1B0, 8, 16)
        # The erroneous address points at unrelated SHA-256 bytes.
        result[0x1D0:0x1D8] = b"\xff" * 8
        return result

    def test_romfs_fields_are_read_before_hashes(self):
        self.assertEqual(ncch_romfs_region(self.header(), 12288), (4096, 8192))

    def test_truncated_romfs_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid NCCH RomFS region"):
            ncch_romfs_region(self.header(), 12287)

    def test_media_unit_shift_is_applied(self):
        header = self.header()
        header[0x18E] = 1
        self.assertEqual(ncch_romfs_region(header, 24576), (8192, 16384))

    def test_hash_range_and_out_of_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.bin"
            path.write_bytes(b"0123456789")
            self.assertEqual(sha(path, 2, 5), hashlib.sha256(b"23456").hexdigest())
            self.assertEqual(sha(path, 10, 0), hashlib.sha256(b"").hexdigest())
            for offset, size in ((11, 0), (-1, 1), (5, 6), (0, -1)):
                with self.subTest(offset=offset, size=size), self.assertRaises(ValueError):
                    sha(path, offset, size)


if __name__ == "__main__":
    unittest.main()
