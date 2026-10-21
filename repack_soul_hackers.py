"""Build a standalone decrypted CCI from the original ROM and a RomFS overlay.

Requires Python 3.10+ and a separately installed 3dstool executable.
Use --help for the required paths. Input must already be decrypted.
Original ROM/RomFS are read-only inputs. No game keys are downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = Path("app_bin/btl_talk/TK_MDT.BIN")
CHUNK = 4 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path, offset=0, length=None):
    size = path.stat().st_size
    require(0 <= offset <= size, f"Hash offset {offset} is outside file of {size} bytes: {path}")
    require(length is None or 0 <= length <= size - offset,
            f"Hash range exceeds file bounds: offset={offset}, length={length}, file_size={size}: {path}")
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = path.stat().st_size - offset if length is None else length
        while remaining:
            block = stream.read(min(CHUNK, remaining))
            require(bool(block), f"Unexpected EOF: {path}")
            checksum.update(block)
            remaining -= len(block)
    return checksum.hexdigest()


def ncsd(path):
    with path.open("rb") as stream:
        header = stream.read(0x200)
    require(len(header) == 0x200 and header[0x100:0x104] == b"NCSD", "Input must be an NCSD cartridge image.")
    unit = 1 << (9 + header[0x18E])
    partitions = {}
    for index in range(8):
        start, size = struct.unpack_from("<II", header, 0x120 + 8 * index)
        if size:
            require(start != 0 and (start + size) * unit <= path.stat().st_size,
                    f"Partition {index} extends beyond the cartridge image.")
            partitions[index] = (start * unit, size * unit)
    require(0 in partitions, "No executable partition 0 found.")
    return partitions


def ncch(path, offset=0):
    with path.open("rb") as stream:
        stream.seek(offset)
        header = stream.read(0x200)
    require(len(header) == 0x200 and header[0x100:0x104] == b"NCCH", "Missing NCCH partition header.")
    return header


def ncch_romfs_region(header, file_size):
    # 0x1B0 contains RomFS offset/size. 0x1D0 is the ExeFS SHA-256,
    # not an offset. NCCH offsets are relative to their partition.
    start, count = struct.unpack_from("<II", header, 0x1B0)
    unit = 1 << (9 + header[0x18E])
    start, size = start * unit, count * unit
    require(start >= 0x200 and size > 0 and start + size <= file_size,
            f"Invalid NCCH RomFS region: offset={start}, size={size}, file_size={file_size}")
    return start, size


def tool_command(executable, work, log, *arguments):
    command = [str(executable)] + [str(argument) for argument in arguments]
    print(subprocess.list2cmdline(command), flush=True)
    with log.open("ab") as stream:
        stream.write(("\nCOMMAND: " + subprocess.list2cmdline(command) + "\n").encode("utf-8"))
        result = subprocess.run(command, cwd=work, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = log.read_bytes()[-6000:].decode("utf-8", errors="replace")
        raise RuntimeError(f"3dstool exited with {result.returncode}. Log: {log}\n{tail}")


def stage_files(source, destination, replacement):
    """Hard-link immutable assets where possible; copy the changed file separately."""
    require((source / TARGET).is_file(), f"Missing RomFS file: {source / TARGET}")
    for path in source.rglob("*"):
        require(not path.is_symlink(), f"Symbolic links are not supported: {path}")
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == TARGET:
                shutil.copy2(replacement, target)
            else:
                try:
                    os.link(path, target)
                except OSError:
                    shutil.copy2(path, target)


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True, help="Local decrypted NCSD image.")
    parser.add_argument("--romfs", type=Path, required=True, help="Complete extracted RomFS directory.")
    parser.add_argument("--text", type=Path, required=True, help="Replacement TK_MDT.BIN from the lossless builder.")
    parser.add_argument("--tool", type=Path, required=True, help="Separately installed 3dstool executable.")
    parser.add_argument("--output", type=Path, required=True, help="New local .cci path; must not exist.")
    parser.add_argument("--check-only", action="store_true", help="Check inputs without building anything.")
    parser.add_argument("--resume-work", type=Path,
                        help="Reuse the extracted components and RomFS from an interrupted build.")
    args = parser.parse_args()
    args.rom = args.rom.resolve()
    args.romfs = args.romfs.resolve()
    args.text = args.text.resolve()
    args.tool = args.tool.resolve()
    args.output = args.output.resolve()
    require(args.rom.is_file(), f"ROM not found: {args.rom}")
    require(args.romfs.is_dir(), f"RomFS directory not found: {args.romfs}")
    require(args.text.is_file(), f"Translated binary not found: {args.text}")
    require((args.romfs / TARGET).is_file(), "RomFS does not contain the expected TK_MDT.BIN path.")
    partitions = ncsd(args.rom)
    header = ncch(args.rom, partitions[0][0])
    title_id = struct.unpack_from("<Q", header, 0x118)[0]
    print(f"Title ID: {title_id:016X}; partitions: {list(partitions)}")
    require(header[0x18F] & 4, "Partition 0 is flagged as encrypted. This script requires a decrypted ROM.")
    require(args.tool.is_file(),
            "3dstool.exe is missing. Download the Windows release from "
            "https://github.com/dnasdw/3dstool/releases and unpack the executable and its DLLs here.")
    require(args.output != args.rom, "Output must not overwrite the original ROM.")
    require(not args.output.exists(), f"Output already exists; choose a new --output: {args.output}")
    require(args.output.parent.is_dir(), "Output parent directory must already exist.")
    # Intermediate partitions, old/new RomFS, verified extraction and final image.
    required = args.rom.stat().st_size * (2 if args.resume_work else 7) + 512 * 1024 * 1024
    free = min(shutil.disk_usage(ROOT).free, shutil.disk_usage(args.output.parent).free)
    require(free >= required, f"Reserve at least {required / (1024**3):.1f} GiB of free disk space for the build.")
    print("Preflight passed.")
    if args.check_only:
        return

    if args.resume_work:
        work = args.resume_work.resolve()
        require(work.is_dir() and work.parent == ROOT and work.name.startswith("repack_work_"),
                "Resume directory must be an existing repack_work_* directory in the project.")
    else:
        work = ROOT / ("repack_work_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
        work.mkdir()
    log = work / "3dstool.log"
    original_digest = sha(args.rom)
    source_text_digest = sha(args.romfs / TARGET)
    replacement_digest = sha(args.text)
    staged = work / "romfs_staged"
    staged.mkdir(exist_ok=True)
    print("1/6: Staging RomFS with translated TK_MDT.BIN...", flush=True)
    if not args.resume_work:
        stage_files(args.romfs, staged, args.text)
    require(sha(staged / TARGET) == replacement_digest, "Staged text differs from translation.")

    print("2/6: Extracting original cartridge partitions and executable components...", flush=True)
    partition_paths = {index: work / (f"partition_{index}.cxi" if index == 0 else f"partition_{index}.cfa")
                       for index in partitions}
    options = []
    for index, path in partition_paths.items():
        options += [f"-{index}", path]
    if not args.resume_work:
        tool_command(args.tool, work, log, "-xvtf", "cci", args.rom,
                     "--header", work / "ncsd_header.bin", *options)
    for index, path in partition_paths.items():
        require(path.is_file() and path.stat().st_size == partitions[index][1], f"Partition {index} extraction failed.")
        if args.resume_work:
            require(sha(path) == sha(args.rom, *partitions[index]), f"Stale extracted partition {index}; start a fresh build.")
    components = {"exh": work / "exheader.bin", "logo": work / "logo.bin",
                  "plain": work / "plain.bin", "exefs": work / "exefs.bin", "romfs": work / "romfs_original.bin"}
    component_options = []
    for key, path in components.items():
        component_options += ["--" + key, path]
    if not args.resume_work:
        tool_command(args.tool, work, log, "-xvtf", "cxi", partition_paths[0],
                     "--header", work / "ncch_header.bin", *component_options)
    for key in ("exh", "exefs", "romfs"):
        require(components[key].is_file() and components[key].stat().st_size > 0, f"Missing {key} component.")

    print("3/6: Building and checking the new RomFS...", flush=True)
    new_romfs = work / "romfs_ptbr.bin"
    if not args.resume_work:
        tool_command(args.tool, work, log, "-cvtf", "romfs", new_romfs,
                     "--romfs-dir", staged, "--romfs", components["romfs"])
    require(new_romfs.is_file(), "Resume requires an already built romfs_ptbr.bin.")
    verified = work / "romfs_verified"
    verified.mkdir(exist_ok=True)
    tool_command(args.tool, work, log, "-xvtf", "romfs", new_romfs, "--romfs-dir", verified)
    staged_files = {path.relative_to(staged) for path in staged.rglob("*") if path.is_file()}
    verified_files = {path.relative_to(verified) for path in verified.rglob("*") if path.is_file()}
    require(staged_files == verified_files, "Built RomFS file list differs from staged directory.")
    source_files = {path.relative_to(args.romfs) for path in args.romfs.rglob("*") if path.is_file()}
    require(staged_files == source_files, "Staged RomFS file list differs from current source.")
    for relative in sorted(staged_files):
        require(sha(staged / relative) == sha(verified / relative), f"RomFS file mismatch: {relative}")
        expected_source = args.text if relative == TARGET else args.romfs / relative
        require(sha(staged / relative) == sha(expected_source), f"Stale staged file: {relative}")

    print("4/6: Rebuilding decrypted executable partition...", flush=True)
    new_cxi = work / "partition_0_ptbr.cxi"
    build_options = []
    for key, path in components.items():
        if key == "romfs":
            path = new_romfs
        if path.is_file() and path.stat().st_size:
            build_options += ["--" + key, path]
    tool_command(args.tool, work, log, "-cvtf", "cxi", new_cxi, "--header", work / "ncch_header.bin",
                 *build_options, "--not-encrypt")
    new_header = ncch(new_cxi)
    require(new_header[0x118:0x120] == header[0x118:0x120], "Executable Title ID changed.")
    require(new_header[0x18F] & 4, "Rebuilt executable is not flagged as decrypted.")
    romfs_offset, romfs_size = ncch_romfs_region(new_header, new_cxi.stat().st_size)
    require(romfs_size >= new_romfs.stat().st_size, "NCCH RomFS region is too small.")
    require(sha(new_cxi, romfs_offset, new_romfs.stat().st_size) == sha(new_romfs),
            "Embedded NCCH RomFS does not match the verified RomFS image.")

    print("5/6: Reassembling standalone cartridge image...", flush=True)
    partition_paths[0] = new_cxi
    options = []
    for index, path in partition_paths.items():
        options += [f"-{index}", path]
    temporary = args.output.with_suffix(".building.cci")
    require(not temporary.exists(), f"Partial output already exists: {temporary}")
    tool_command(args.tool, work, log, "-cvtf", "cci", temporary, "--header", work / "ncsd_header.bin",
                 *options, "--not-pad")

    print("6/6: Checking final partitions and original inputs...", flush=True)
    final_parts = ncsd(temporary)
    require(set(final_parts) == set(partitions), "Final partition list changed.")
    for index, path in partition_paths.items():
        offset, size = final_parts[index]
        require(size >= path.stat().st_size, f"Final partition {index} is too small.")
        require(sha(temporary, offset, path.stat().st_size) == sha(path), f"Final partition {index} differs from input.")
    require(sha(args.rom) == original_digest, "Original ROM changed unexpectedly.")
    require(sha(args.romfs / TARGET) == source_text_digest, "Original RomFS text changed unexpectedly.")
    require(sha(args.text) == replacement_digest, "Replacement text changed during build.")
    temporary.rename(args.output)
    report = {"output": str(args.output), "title_id": f"{title_id:016X}",
              "partitions": list(partitions), "romfs_files_verified": len(staged_files),
              "translated_text_sha256": replacement_digest, "source_sha256": original_digest,
              "output_sha256": sha(args.output), "decrypted_partition_0": True,
              "original_inputs_unchanged": True, "runtime_tested": False, "work_directory": str(work)}
    (work / "build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Finished: {args.output}\nBuild report: {work / 'build_report.json'}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Build stopped: {error}", file=sys.stderr)
        sys.exit(1)
