"""Decode standard TGA previews without modifying embedded NW4C GPU data."""
import struct
import argparse
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def decode(path, destination=None):
    data = path.read_bytes()
    id_length, palette, image_type = data[:3]
    width, height, bits, flags = struct.unpack_from("<HHBB", data, 12)
    if palette or image_type not in (2,10) or bits not in (24,32):
        raise ValueError(f"Unsupported TGA: {path}")
    stride = bits // 8
    pos = 18 + id_length
    pixels = []
    while len(pixels) < width * height:
        if image_type == 10:
            packet = data[pos]
            pos += 1
            count = (packet & 127) + 1
            if packet & 128:
                raw = data[pos:pos+stride]
                pos += stride
                pixels.extend([raw] * count)
            else:
                pixels.extend(data[i:i+stride] for i in range(pos, pos + count*stride, stride))
                pos += count * stride
        else:
            pixels.append(data[pos:pos+stride])
            pos += stride
    rows = []
    for y in range(height):
        source_y = y if flags & 32 else height - 1 - y
        row = bytearray(b"\x00")
        for x in range(width):
            source_x = width - 1 - x if flags & 16 else x
            pixel = pixels[source_y * width + source_x]
            b,g,r = pixel[:3]
            a = pixel[3] if stride == 4 else 255
            row.extend((r,g,b,a))
        rows.append(bytes(row))
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width,height,8,6,0,0,0))
    png += png_chunk(b"IDAT", zlib.compress(b"".join(rows))) + png_chunk(b"IEND", b"")
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(png)
    return width, height, [row[1:] for row in rows]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Output must be a new path, separate from the input texture.")
    width, height, _ = decode(args.input, args.output)
    print(f"Preview saved: {args.output} ({width}x{height}); source texture unchanged.")
