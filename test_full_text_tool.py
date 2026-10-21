import copy
import struct
import unittest
from full_text_tool import parts, export_document, build


def messages32(strings):
    size = 4 * (len(strings) + 1)
    pointers, body = [], b""
    for string in strings:
        pointers.append(len(body))
        body += string + b"\xff\x00"
    return struct.pack("<I", size) + struct.pack(f"<{len(strings)}I", *pointers) + body


class FullTextTests(unittest.TestCase):
    def sample(self):
        first = messages32([b"Hello there", b"Good evening", b"See you later"])
        second = messages32([b"Second table", b"Remain here", b"Goodbye now"])
        return first, first + b"\x00\x00" + second + b"\x13\x37"

    def test_roundtrip_preserves_every_byte(self):
        _, original = self.sample()
        catalog = export_document(original, "sample.bin")
        self.assertEqual(len(catalog["tables"]), 2)
        rebuilt, _ = build(original, catalog)
        self.assertEqual(rebuilt, original)

    def test_shortening_does_not_move_next_table(self):
        first, original = self.sample()
        catalog = export_document(original, "sample.bin")
        catalog["tables"][0]["records"][0]["tokens"][0]["translation"] = "Oi"
        rebuilt, report = build(original, catalog)
        self.assertEqual(len(rebuilt), len(original))
        self.assertEqual(rebuilt[len(first):], original[len(first):])
        self.assertGreater(report[0]["spare_bytes"], 0)

    def test_capacity_overflow_is_rejected(self):
        _, original = self.sample()
        catalog = export_document(original, "sample.bin")
        catalog["tables"][0]["records"][0]["tokens"][0]["translation"] = "x" * 200
        with self.assertRaisesRegex(ValueError, "exceeds allocation"):
            build(original, catalog)

    def test_voice_operands_are_not_exported_as_text(self):
        self.assertEqual(parts(b"\xff\x05ABHello\xff\x00")[0]["hex"], "FF054142")
        self.assertEqual(parts(b"\xff\x05ABHello\xff\x00")[1]["source"], "Hello")

    def test_control_mutation_rejected(self):
        _, original = self.sample()
        catalog = export_document(original, "sample.bin")
        catalog["tables"][0]["records"][0]["tokens"][-1]["hex"] = "FF01"
        with self.assertRaisesRegex(ValueError, "Source tokens"):
            build(original, catalog)


if __name__ == "__main__":
    unittest.main()
