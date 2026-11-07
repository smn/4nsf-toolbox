#!/usr/bin/env python3
"""Unpack a Navigon/Garmin "ExtractorCE" self-extracting archive.

The VW "maps + more" update package ships two of these: Install_OS.exe (the
Windows CE OS image and bootloader files) and UpdateMeContent.content (the
full \\My Flash Disk tree: Navigon software, apps, skins, maps). Both are a
Windows CE PE stub followed by raw file data, a table of contents, and the
trailer marker "!NAVIGON_SFX!".

Layout (all integers little-endian; 64-bit values are stored high dword
first):
  [stub exe][file data ...][TOC][trailer]
  TOC header : u32 0, u32 data_start (== stub size)
  TOC record : u64 size, wide path, u32 path_bytes, 32 wide hex chars (MD5),
               u32 attrs, FILETIME, FILETIME, u64 end_offset (absent on the
               last record)
  trailer    : u32 0, u8 0, u32 file_count, u32 2, u8 1, wide dest_root, u32 len,
               wide source path, u32 len, ..., "!NAVIGON_SFX!"

Usage: sfx_extract.py ARCHIVE OUTDIR [--list] [--no-verify]
"""
import hashlib
import os
import struct
import sys

MARKER = "!NAVIGON_SFX!".encode("utf-16le")


def read_wide(buf, pos):
    """Read a wide string followed by its u32 byte length; return (str, next)."""
    n = 0
    while True:
        cand = struct.unpack_from("<I", buf, pos + 2 * n)[0]
        if n and cand == 2 * n:
            s = buf[pos:pos + 2 * n].decode("utf-16le")
            return s, pos + 2 * n + 4
        n += 1
        if n > 4096:
            raise ValueError(f"unterminated wide string at {pos:#x}")


def pe_overlay_offset(f):
    """Offset of the first byte after the last section of a PE file."""
    f.seek(0)
    hdr = f.read(4096)
    e_lfanew, = struct.unpack_from("<I", hdr, 0x3C)
    nsec, = struct.unpack_from("<H", hdr, e_lfanew + 6)
    opt_size, = struct.unpack_from("<H", hdr, e_lfanew + 20)
    sec = e_lfanew + 24 + opt_size
    end = 0
    for k in range(nsec):
        raw_size, raw_ptr = struct.unpack_from("<II", hdr, sec + 40 * k + 16)
        end = max(end, raw_ptr + raw_size)
    return end


def parse_toc(f, file_size):
    """Return (records, dest_root). Each record: dict(path, size, start, md5)."""
    tail_len = min(file_size, 128 * 1024 * 1024)
    f.seek(file_size - tail_len)
    tail = f.read(tail_len)
    base = file_size - tail_len
    if not tail.endswith(MARKER):
        raise ValueError("not a NAVIGON_SFX archive (marker missing)")

    # The data starts right after the PE stub, so the TOC header is
    # (u32 0, u32 overlay_offset, u32 size_hi=0, u32 size_lo, wide path).
    data_start = pe_overlay_offset(f)
    pat = struct.pack("<III", 0, data_start, 0)
    pos = None
    i = len(tail)
    while True:
        i = tail.rfind(pat, 0, i)
        if i < 0:
            break
        if tail[i + 16:i + 18] == b"\\\x00":
            pos = i
            break
    if pos is None:
        raise ValueError("TOC header not found")
    p = pos + 8
    records = []
    start = data_start
    while True:
        size_hi, size_lo = struct.unpack_from("<II", tail, p)
        size = (size_hi << 32) | size_lo
        path, p = read_wide(tail, p + 8)
        md5 = tail[p:p + 64].decode("utf-16le")
        p += 64
        attrs, = struct.unpack_from("<I", tail, p)
        p += 4 + 16  # attrs + two FILETIMEs
        records.append({"path": path, "size": size, "start": start,
                        "md5": md5, "attrs": attrs})
        start += size
        end_hi, end_lo = struct.unpack_from("<II", tail, p)
        if ((end_hi << 32) | end_lo) == start:
            p += 8
            continue
        # trailer: u32 0, u8 0, u32 count, u32 2, u8 1, wide dest_root
        count, = struct.unpack_from("<I", tail, p + 5)
        if count != len(records):
            raise ValueError(f"file count mismatch: trailer says {count}, parsed {len(records)}")
        p += 5 + 4 + 4 + 1
        dest_root, p = read_wide(tail, p)
        break
    if start != base + pos:
        raise ValueError(f"data does not end where the TOC starts ({start:#x} vs {base + pos:#x})")
    return records, dest_root


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    if len(args) < 1 or (len(args) < 2 and "--list" not in flags):
        print(__doc__)
        return 2
    archive = args[0]
    outdir = args[1] if len(args) > 1 else None
    size = os.path.getsize(archive)
    with open(archive, "rb") as f:
        records, root = parse_toc(f, size)
        print(f"{len(records)} files, destination root {root!r}")
        if "--list" in flags:
            for r in records:
                print(f"{r['size']:12d}  {r['md5']}  {r['path']}")
            return 0
        bad = 0
        for r in records:
            rel = r["path"]
            if rel.lower().startswith(root.lower()):
                rel = rel[len(root):]
            rel = rel.replace("\\", "/").lstrip("/")
            dst = os.path.join(outdir, rel)
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            f.seek(r["start"])
            h = hashlib.md5()
            remaining = r["size"]
            with open(dst, "wb") as o:
                while remaining:
                    chunk = f.read(min(remaining, 8 * 1024 * 1024))
                    if not chunk:
                        raise IOError(f"short read in {r['path']}")
                    o.write(chunk)
                    h.update(chunk)
                    remaining -= len(chunk)
            ok = ("--no-verify" in flags) or h.hexdigest() == r["md5"]
            if not ok:
                bad += 1
            print(f"{'ok ' if ok else 'MD5'} {r['size']:12d}  {rel}")
        print(f"done: {len(records)} files, {bad} checksum failures")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
