#!/usr/bin/env python3
"""Build a raw MBR + FAT32 disk image and copy folders into it.

Usage: mkdisk.py OUTPUT.img SIZE_MB SRC [SRC ...]

Each SRC (file or directory) is copied to the root of the image.
Needs mkfs.vfat (dosfstools) and mcopy (mtools) on PATH; no root needed.
"""
import os
import struct
import subprocess
import sys
import tempfile

SECTOR = 512
PART_START = 2048  # sectors, 1 MiB alignment


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    out, size_mb, sources = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
    total = size_mb * 1024 * 1024 // SECTOR
    part_size = total - PART_START

    with open(out, "wb") as f:
        f.truncate(total * SECTOR)
        # One primary partition, bootable, type 0x0C (FAT32 LBA).
        entry = struct.pack("<B3sB3sII", 0x80, b"\x01\x01\x00", 0x0C,
                            b"\xfe\xff\xff", PART_START, part_size)
        mbr = bytearray(SECTOR)
        mbr[446:462] = entry
        mbr[510:512] = b"\x55\xaa"
        f.seek(0)
        f.write(mbr)

    subprocess.run(["mkfs.vfat", "-F", "32", "-n", "WINCEDISK",
                    "--offset", str(PART_START), out],
                   check=True, stdout=subprocess.DEVNULL)

    with tempfile.NamedTemporaryFile("w", suffix=".mtoolsrc", delete=False) as rc:
        rc.write(f'drive w: file="{os.path.abspath(out)}" offset={PART_START * SECTOR}\n')
        rc_path = rc.name
    env = dict(os.environ, MTOOLSRC=rc_path)
    try:
        for src in sources:
            name = os.path.basename(os.path.normpath(src))
            subprocess.run(["mcopy", "-s", "-o", src, f"w:/{name}"], check=True, env=env)
        subprocess.run(["mdir", "w:/"], check=True, env=env)
    finally:
        os.unlink(rc_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
