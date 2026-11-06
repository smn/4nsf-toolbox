#!/usr/bin/env python3
"""Rename the mount folder of the QEMU Compact 7 image's disk to "My Flash Disk".

The Navigon / VW software hardcodes "\\My Flash Disk\\..." paths. The
wince-qemu image mounts its virtio disk as "\\Mounted Volume" (the default
name in exfat.dll, fsdmgr.dll and the boot/default registry hives). The
replacement is one character shorter, so it can be patched in place in the
flat XIP image, which has no checksum.

Usage: patch_image.py IN.raw OUT.raw
"""
import re
import sys


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    d = bytearray(open(sys.argv[1], "rb").read())
    old = "Mounted Volume".encode("utf-16le")
    new = "My Flash Disk".encode("utf-16le") + b"\0\0"
    assert len(old) == len(new)
    hits = [m.start() for m in re.finditer(re.escape(old), d)]
    for h in hits:
        d[h:h + len(old)] = new
    open(sys.argv[2], "wb").write(d)
    print(f"patched {len(hits)} occurrences -> {sys.argv[2]}")
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
