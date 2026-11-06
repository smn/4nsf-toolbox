#!/usr/bin/env python3
"""Patch the QEMU Compact 7 image: disk mount name and display resolution.

Mount name: the Navigon / VW software hardcodes "\\My Flash Disk\\..." paths,

the wince-qemu image mounts its virtio disk as "\\Mounted Volume" (the default
name in exfat.dll, fsdmgr.dll and the boot/default registry hives). The
replacement is one character shorter, so it can be patched in place in the
flat XIP image, which has no checksum.

Display: the image's OAL (nk.exe) answers the display driver's IOCTL with a
hardcoded 1024x600x32 mode and programs the PL111 timing registers from
immediates. The device is 480x272 and the Navigon skins are keyed on that
("R480x272"), so --display 480x272 rewrites those immediates. The patch
checks every original instruction word before touching it.

Usage: patch_image.py [--display 480x272] IN.raw OUT.raw
"""
import re
import struct
import sys

# (virtual address, expected word, replacement) for the 480x272 mode; the
# image is loaded at 0x80000000 so file offset = va - 0x80000000.
DISPLAY_480x272 = [
    (0x80002134, 0xE3A08996, 0xE3A08702),  # frame buffer length 0x258000 -> 0x80000
    (0x80002138, 0xE3A09A01, 0xE3A09D1E),  # stride 4096 -> 1920
    (0x80002148, 0xE3A02B01, 0xE3A02E1E),  # width 1024 -> 480
    (0x8000214C, 0xE3A01F96, 0xE3A01E11),  # height 600 -> 272
    (0x800021BC, 0xE3A020FC, 0xE3A02074),  # PL111 TIM0: PPL 63 -> 29
    (0x800021C4, 0xE3001259, 0xE300110F),  # PL111 TIM1: LPP 601 -> 271
    (0x8000222C, 0xE3A03B01, 0xE3A03E1E),  # width (second query)
    (0x80002230, 0xE3A02F96, 0xE3A02E11),  # height (second query)
]


def main():
    args = sys.argv[1:]
    display = None
    if args[:1] == ["--display"]:
        display = args[1]
        args = args[2:]
    if len(args) != 2:
        print(__doc__)
        return 2
    sys.argv = [sys.argv[0]] + args
    d = bytearray(open(sys.argv[1], "rb").read())
    if display:
        if display != "480x272":
            print("only 480x272 is supported")
            return 2
        for va, old, new in DISPLAY_480x272:
            off = va - 0x80000000
            cur = struct.unpack_from("<I", d, off)[0]
            if cur != old:
                print(f"unexpected word {cur:#x} at {va:#x} (wanted {old:#x}); is this the 2022-04-17 image?")
                return 1
            struct.pack_into("<I", d, off, new)
        print(f"display patched to {display}")
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
