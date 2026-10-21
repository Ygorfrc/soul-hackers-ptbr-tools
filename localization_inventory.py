"""Inventory candidate text resources and validate concatenated LE32 message tables."""
import argparse
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASCII = re.compile(rb"[\x20-\x7e]{4,}")
HEADER = re.compile(rb"(?=([\x00-\xff]{2}\x00\x00\x00\x00\x00\x00))")


def parse_table(data, start):
    if start + 12 > len(data):
        return None
    data_start = struct.unpack_from("<I", data, start)[0]
    if data_start < 8 or data_start % 4 or data_start > 32768 or start + data_start + 2 > len(data):
        return None
    count = data_start // 4 - 1
    if struct.unpack_from("<I", data, start + 4)[0] != 0:
        return None
    pointers = struct.unpack_from(f"<{count}I", data, start + 4)
    if pointers[0] != 0 or any(a >= b for a, b in zip(pointers, pointers[1:])):
        return None
    base = start + data_start
    if base + pointers[-1] + 2 > len(data):
        return None
    # Every inter-record boundary must match an explicit FF00 terminator.
    for a, b in zip(pointers, pointers[1:]):
        if b - a < 2 or data[base + b - 2:base + b] != b"\xff\x00":
            return None
    last_end = data.find(b"\xff\x00", base + pointers[-1])
    if last_end < 0:
        return None
    end = last_end + 2
    if end - (base + pointers[-1]) > 65536:
        return None
    spans = [data[base + a:base + b] for a, b in zip(pointers, (*pointers[1:], end - base))]
    readable = sum(len(m.group()) for span in spans for m in ASCII.finditer(span))
    if count < 3 or readable < 16 or readable < (end - base) * 0.30:
        return None
    return {"offset": start, "data_start": data_start, "entry_count": count,
            "end": end, "size": end - start, "ascii_characters": readable}


def find_tables(data):
    tables = []
    end = -1
    for match in HEADER.finditer(data):
        start = match.start()
        if start < end:
            continue
        result = parse_table(data, start)
        if result:
            tables.append(result)
            end = result["end"]
    return tables


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--romfs", type=Path, required=True, help="Extracted local RomFS directory.")
    parser.add_argument("--output", type=Path, required=True, help="Local JSON inventory destination.")
    args = parser.parse_args()
    source = args.romfs.resolve()
    if not source.is_dir():
        parser.error(f"RomFS directory does not exist: {source}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    inventory = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        if relative.startswith(("sound/", "movie/")) or path.suffix.lower() in (".tga", ".tex", ".chr", ".mdl", ".fms", ".bcstm"):
            continue
        if path.stat().st_size > 64 * 1024 * 1024:
            continue
        data = path.read_bytes()
        if b"NW4C_Tga" in data[:512]:
            continue
        print(f"Scanning {relative} ({len(data)} bytes)", flush=True)
        samples = []
        characters = runs = 0
        for match in ASCII.finditer(data):
            raw = match.group()
            letters = sum(65 <= b <= 90 or 97 <= b <= 122 for b in raw)
            if letters < 4 or letters / len(raw) < .55 or b" " not in raw:
                continue
            runs += 1
            characters += len(raw)
            if len(samples) < 8:
                samples.append({"offset": match.start(), "text": raw.decode("ascii")[:150]})
        tables = find_tables(data) if runs >= 3 else []
        if runs or tables:
            record = {"path": relative, "size": len(data), "candidate_text_runs": runs,
                      "candidate_characters": characters, "tables": tables, "samples": samples}
            inventory.append(record)
    inventory.sort(key=lambda item: item["candidate_characters"], reverse=True)
    args.output.write_text(json.dumps(inventory, ensure_ascii=True, indent=2), encoding="ascii")
    for item in inventory[:35]:
        print(f"{item['path']}: {item['candidate_text_runs']} runs, {item['candidate_characters']} chars; "
              f"{len(item['tables'])} validated tables / {sum(t['entry_count'] for t in item['tables'])} entries")
    print(f"Inventory: {args.output}")


if __name__ == "__main__":
    main()
