"""Lossless pixel access and bounded edits for Soul Hackers NW4C RGBA8 TGAs."""
import struct
import argparse
from pathlib import Path
from inspect_tga import decode, png_chunk
import zlib


def pixel_offset(x, y, width):
    morton = (x&1) | ((y&1)<<1) | ((x&2)<<1) | ((y&2)<<2) | ((x&4)<<2) | ((y&4)<<3)
    return 4*((y//8*(width//8)+x//8)*64+morton)


def save_png(rows, path):
    height, width = len(rows), len(rows[0])//4
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB",width,height,8,6,0,0,0))
    png += png_chunk(b"IDAT",zlib.compress(raw)) + png_chunk(b"IEND",b"")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(png)


def load(path):
    data = path.read_bytes()
    width,height,rows = decode(path)
    id_length = data[0]
    if id_length != 20 or data[18:34] != b"NW4C_Tga Ver1.0\x00":
        raise ValueError("Unsupported NW4C identifier.")
    tag_start = struct.unpack_from("<I",data,34)[0]
    offset = tag_start
    texture = None
    format_name = None
    while offset + 12 <= len(data):
        name = data[offset:offset+8]
        length = struct.unpack_from("<I",data,offset+8)[0]
        if length < 12 or offset + length > len(data):
            break
        if name == b"nw4c_tfm":
            format_name = data[offset+12:offset+length]
        if name == b"nw4c_txd":
            texture = (offset+12,length-12)
        offset += length
    if format_name != b"Rgba8" or texture is None:
        raise ValueError("Only raw RGBA8 NW4C textures are supported.")
    gpu_width, gpu_height = 1 << (width-1).bit_length(),1 << (height-1).bit_length()
    if texture[1] != gpu_width*gpu_height*4:
        raise ValueError("Unexpected RGBA8 texture size or mipmap layout.")
    for y,row in enumerate(rows):
        for x in range(width):
            pos = texture[0]+pixel_offset(x,y,gpu_width)
            if data[pos:pos+4][::-1] != row[x*4:x*4+4]:
                raise ValueError(f"Preview and GPU pixel differ at {x},{y}.")
    return data, [bytearray(row) for row in rows], (tag_start,texture[0],gpu_width)


def rle(pixels):
    output = bytearray()
    pos = 0
    while pos < len(pixels):
        count = 1
        while count < 128 and pos+count < len(pixels) and pixels[pos+count] == pixels[pos]:
            count += 1
        if count >= 2:
            output.append(0x80 | (count-1))
            output.extend(pixels[pos])
            pos += count
        else:
            end = pos + 1
            while end < len(pixels) and end-pos < 128:
                if end+1 < len(pixels) and pixels[end] == pixels[end+1]:
                    break
                end += 1
            output.append(end-pos-1)
            output.extend(b"".join(pixels[pos:end]))
            pos = end
    return bytes(output)


def encode(original, rows, layout):
    tag_start,texture_start,gpu_width = layout
    width,height,bits,flags = struct.unpack_from("<HHBB",original,12)
    if len(rows) != height or any(len(row) != width*4 for row in rows):
        raise ValueError("Image dimensions changed.")
    stride = bits//8
    pixels = []
    for sy in range(height):
        y = sy if flags&32 else height-1-sy
        for sx in range(width):
            x = width-1-sx if flags&16 else sx
            r,g,b,a = rows[y][x*4:x*4+4]
            pixels.append(bytes((b,g,r,a))[:stride])
    preview = rle(pixels)
    image_start = 18+original[0]
    if len(preview) > tag_start-image_start:
        raise ValueError("Edited preview exceeds its original allocation.")
    result = bytearray(original)
    result[2] = 10
    result[image_start:tag_start] = preview + b"\x00"*(tag_start-image_start-len(preview))
    for y,row in enumerate(rows):
        for x in range(width):
            pos = texture_start+pixel_offset(x,y,gpu_width)
            result[pos:pos+4] = row[x*4:x*4+4][::-1]
    if len(result) != len(original):
        raise ValueError("Texture file size changed.")
    return bytes(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional PNG destination after the pixel comparison.")
    args = parser.parse_args()
    if args.output and args.input.resolve() == args.output.resolve():
        parser.error("Output must be separate from the input texture.")
    original, rows, layout = load(args.input)
    if args.output:
        save_png(rows, args.output)
    print("Full preview/GPU pixel comparison passed; source texture unchanged.")
