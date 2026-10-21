"""Create and localize a synthetic table; no ROM or external tools required.

Run from the repository root: py examples/demo_roundtrip.py
All generated files stay in the ignored out/demo directory.
"""
import json
import struct
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from full_text_tool import build, export_document


def main():
    # These sentences are invented fixtures, not extracted game dialogue.
    messages = [b"Hello, traveler!", b"The terminal is ready.", b"See you later!"]
    body = bytearray()
    pointers = []
    for message in messages:
        pointers.append(len(body))
        body.extend(message + b"\xff\x00")
    data_start = 4 * (len(messages) + 1)
    original = struct.pack("<I", data_start) + struct.pack("<3I", *pointers) + body
    document = export_document(bytes(original), "synthetic.bin")
    translations = ["Ola, viajante!", "O terminal esta pronto.", "Ate mais!"]
    for record, translation in zip(document["tables"][0]["records"], translations):
        record["tokens"][0]["translation"] = translation
    localized, budget = build(bytes(original), document)
    destination = REPOSITORY / "out/demo"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "synthetic.bin").write_bytes(original)
    (destination / "localized.bin").write_bytes(localized)
    (destination / "catalog.json").write_text(json.dumps(document, ensure_ascii=True, indent=2), encoding="ascii")
    (destination / "budget.json").write_text(json.dumps(budget, indent=2), encoding="ascii")
    print(f"Synthetic demonstration written to {destination}")
    print(f"Original: {len(original)} bytes; localized: {len(localized)} bytes.")


if __name__ == "__main__":
    main()
