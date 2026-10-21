"""Lossless text-table extraction and fixed-allocation rebuilding.

Supports validated LE32 negotiation tables and BE/LE16 event message tables.
Keeps tables at their original absolute offsets and refuses capacity overflow.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

from localization_inventory import find_tables

ROOT = Path(__file__).resolve().parent


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def parts(data):
    result = []
    pos = 0
    while pos < len(data):
        start = pos
        if data[pos] == 255 and pos + 1 < len(data):
            # FF05 is followed by a two-byte voice ID (including printable bytes).
            pos += 4 if data[pos + 1] == 5 else 2
            pos = min(pos, len(data))
            result.append({"kind": "control", "offset": start, "hex": data[start:pos].hex().upper()})
        elif 32 <= data[pos] <= 126:
            while pos < len(data) and 32 <= data[pos] <= 126:
                pos += 1
            result.append({"kind": "text", "offset": start, "source": data[start:pos].decode("ascii"), "translation": None})
        else:
            pos += 1
            while pos < len(data) and data[pos] != 255 and not 32 <= data[pos] <= 126:
                pos += 1
            result.append({"kind": "raw", "offset": start, "hex": data[start:pos].hex().upper()})
    return result


def terminator(data, start, limit):
    pos = start
    while pos + 1 < limit:
        if data[pos] == 255:
            if data[pos + 1] == 0:
                return pos + 2
            pos += 4 if data[pos + 1] == 5 else 2
        else:
            pos += 1
    return None


def find_event_tables(data):
    candidates = []
    for endian, magic in ((">", b"\x00\x08"), ("<", b"\x08\x00")):
        for match in re.finditer(re.escape(magic), data):
            start = match.start()
            if start + 8 > len(data):
                continue
            a, b, c, d = struct.unpack_from(endian + "4H", data, start)
            if not (a == 8 and a <= b <= c < d < 32768 and all(n % 2 == 0 for n in (a,b,c,d))):
                continue
            if start + d >= len(data):
                continue
            raw_pointers = list(struct.unpack_from(endian + f"{(d-c)//2}H", data, start + c))
            if not raw_pointers or raw_pointers[0] != 0:
                continue
            pointers = raw_pointers[:]
            # The 16-bit pointer array can have one zero alignment word.
            if len(pointers) > 1 and pointers[-1] == 0:
                pointers.pop()
            if not pointers or any(a >= b for a,b in zip(pointers,pointers[1:])):
                continue
            base = start + d
            if base + pointers[-1] + 2 > len(data):
                continue
            if any(data[base + pointer - 2:base + pointer] != b"\xff\x00" for pointer in pointers[1:]):
                continue
            end = terminator(data, base + pointers[-1], min(len(data), base + 65536))
            if end is None:
                continue
            body = data[base:end]
            printable = sum(32 <= value <= 126 for value in body)
            if printable < 12 or printable / len(body) < .35:
                continue
            candidates.append({"offset": start, "data_start": d, "pointer_start": c,
                               "pointer_width": 2, "endian": endian, "entry_count": len(pointers),
                               "pointer_slots": len(raw_pointers), "pointers": pointers,
                               "end": end, "size": end - start, "format": "event16"})
    candidates.sort(key=lambda entry: entry["offset"])
    results = []
    last_end = -1
    for entry in candidates:
        if entry["offset"] >= last_end:
            results.append(entry)
            last_end = entry["end"]
    return results


def discover(data):
    tables = find_event_tables(data)
    for table in find_tables(data):
        if any(t["offset"] <= table["offset"] < t["end"] for t in tables):
            continue
        table.update({"pointer_start": 4, "pointer_width": 4, "endian": "<", "format": "messages32"})
        table["pointer_slots"] = table["entry_count"]
        table["pointers"] = list(struct.unpack_from(f"<{table['entry_count']}I", data, table["offset"] + 4))
        tables.append(table)
    return sorted(tables, key=lambda table: table["offset"])


def export_document(data, source_name):
    tables = discover(data)
    for number, table in enumerate(tables):
        table["id"] = number
        table["sha256"] = checksum(data[table["offset"]:table["end"]])
        table["records"] = []
        base = table["offset"] + table["data_start"]
        ends = table["pointers"][1:] + [table["end"] - base]
        for index, (start, end) in enumerate(zip(table["pointers"], ends)):
            record = data[base + start:base + end]
            table["records"].append({"id": index, "source_offset": base + start,
                                     "source_size": len(record), "tokens": parts(record)})
    return {"format": "soul-hackers-tables-v2", "source": source_name, "sha256": checksum(data),
            "source_size": len(data), "tables": tables}


def encode_tokens(raw, tokens):
    baseline = parts(raw)
    if len(tokens) != len(baseline):
        raise ValueError("Token count changed.")
    built = bytearray()
    for before, after in zip(baseline, tokens):
        comparison = dict(after)
        if before["kind"] == "text":
            comparison["translation"] = None
        if comparison != before:
            raise ValueError("Source tokens or control bytes changed.")
        if before["kind"] == "text":
            text = after.get("translation")
            if text is None:
                text = before["source"]
            if not isinstance(text, str) or any(not 32 <= ord(c) <= 126 for c in text):
                raise ValueError("Translation must use printable ASCII.")
            built.extend(text.encode("ascii"))
        else:
            built.extend(bytes.fromhex(before["hex"]))
    return bytes(built)


def build(data, document):
    if document.get("sha256") != checksum(data):
        raise ValueError("Source binary checksum mismatch.")
    baseline = export_document(data, document["source"])
    if len(document.get("tables", [])) != len(baseline["tables"]):
        raise ValueError("Table list changed.")
    output = bytearray(data)
    budget_report = []
    for old, edited in zip(baseline["tables"], document["tables"]):
        if {k:v for k,v in old.items() if k != "records"} != {k:v for k,v in edited.items() if k != "records"}:
            raise ValueError("Table metadata changed.")
        if len(old["records"]) != len(edited["records"]):
            raise ValueError("Record count changed.")
        start, end = old["offset"], old["end"]
        header = bytearray(data[start:start + old["data_start"]])
        body = bytearray()
        for before, after in zip(old["records"], edited["records"]):
            if {k:v for k,v in before.items() if k != "tokens"} != {k:v for k,v in after.items() if k != "tokens"}:
                raise ValueError("Record metadata changed.")
            relative = len(body)
            maximum = (1 << (old["pointer_width"] * 8)) - 1
            if relative > maximum:
                raise ValueError("Pointer overflow.")
            struct.pack_into(old["endian"] + ("H" if old["pointer_width"] == 2 else "I"), header,
                             old["pointer_start"] + before["id"] * old["pointer_width"], relative)
            raw = data[before["source_offset"]:before["source_offset"] + before["source_size"]]
            body.extend(encode_tokens(raw, after["tokens"]))
        rebuilt = bytes(header + body)
        budget = end - start
        if len(rebuilt) > budget:
            raise ValueError(f"Table {old['id']} at {start}: translation exceeds allocation by {len(rebuilt)-budget} bytes.")
        # All following tables stay at their original offsets, including offsets
        # referenced by the executable. Padding only replaces this table's data.
        output[start:end] = rebuilt + b"\x00" * (budget - len(rebuilt))
        budget_report.append({"table": old["id"], "offset": start, "allocation": budget,
                              "used": len(rebuilt), "spare_bytes": budget - len(rebuilt)})
    if len(output) != len(data):
        raise ValueError("Binary length changed.")
    return bytes(output), budget_report


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "build"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = args.input.read_bytes()
    if args.command == "export":
        document = export_document(data, str(args.input))
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(document, ensure_ascii=True, indent=2), encoding="ascii")
        print(f"Exported {len(document['tables'])} tables, {sum(t['entry_count'] for t in document['tables'])} messages.")
    else:
        if not args.output or args.output.resolve() == args.input.resolve():
            raise ValueError("Use --output with a new file path.")
        rebuilt, report = build(data, json.loads(args.json.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rebuilt)
        args.output.with_suffix(args.output.suffix + ".report.json").write_text(json.dumps(report, indent=2), encoding="ascii")
        print(f"Rebuilt {args.output} with all absolute table offsets and file size preserved.")


if __name__ == "__main__":
    main()
