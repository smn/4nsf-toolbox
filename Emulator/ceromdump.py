#!/usr/bin/env python3
"""Dump the modules and files of a Windows CE 5/6 ROM image (flat NB0).

Works on the NK.nb0 from the VW "maps + more" Install_OS.exe. Modules are
stored in ROM as pre-relocated sections without their PE headers; this
rebuilds a PE file for each (e32/o32 headers to IMAGE_NT_HEADERS plus
sections), so the result is loadable by other Windows CE systems and by
disassemblers. Plain ROM files are copied; files stored with ROM compression
are written with a ".cecompressed" suffix (the compressor is Microsoft's
proprietary XPR/LZX variant and is not implemented here).

Usage: ceromdump.py NK.nb0 OUTDIR [--list]
"""
import os
import struct
import sys

ROM_SIGNATURE = b"ECEC"
ROMHDR_FMT = "<IIIIIIIIIIIIIIIIIHHIII"
ROMHDR_FIELDS = ("dllfirst dlllast physfirst physlast nummods ulRAMStart "
                 "ulRAMFree ulRAMEnd ulCopyEntries ulCopyOffset ulProfileLen "
                 "ulProfileOffset numfiles ulKernelFlags ulFSRamPercent "
                 "ulDrivglobStart ulDrivglobLen usCPUType usMiscFlags "
                 "pExtensions ulTrackingStart ulTrackingLen").split()
# TOCentry: attrs, FILETIME, size, name ptr, e32 offset, o32 offset, load offset
TOC_FMT = "<IQIIIII"
# FILESentry: attrs, FILETIME, real size, compressed size, name ptr, load offset
FILES_FMT = "<IQIIII"
# e32_rom (CE 5/6): objcnt, imageflags, entryrva, vbase, subsysmajor,
# subsysminor, stackmax, vsize, sect14rva, sect14size, timestamp,
# then 9 (rva,size) info pairs, then subsys
E32_FMT = "<HHIIHHIIIII" + "II" * 9 + "H"
E32_SIZE = struct.calcsize(E32_FMT)
# o32_rom: vsize, rva, psize, dataptr, realaddr, flags
O32_FMT = "<IIIIII"
O32_SIZE = struct.calcsize(O32_FMT)
FILE_ATTRIBUTE_COMPRESSED = 0x800

STD_FLAG_WRITE = 0x80000000
STD_FLAG_DATA = 0x40
STD_FLAG_CODE = 0x20


class Rom:
    def __init__(self, data):
        self.d = data
        if data[0x40:0x44] != ROM_SIGNATURE:
            raise ValueError("no ROM signature at offset 0x40")
        romhdr_addr, = struct.unpack_from("<I", data, 0x44)
        # physfirst is the address of offset 0; find ROMHDR by consistency.
        for o in range(0, len(data) - 0x60, 4):
            physfirst, = struct.unpack_from("<I", data, o + 8)
            if physfirst and romhdr_addr - physfirst == o:
                break
        else:
            raise ValueError("ROMHDR not found")
        self.physfirst = physfirst
        self.hdr = dict(zip(ROMHDR_FIELDS, struct.unpack_from(ROMHDR_FMT, data, o)))
        self.romhdr_off = o

    def off(self, addr):
        o = addr - self.physfirst
        if not 0 <= o < len(self.d):
            raise ValueError(f"address {addr:#x} outside image")
        return o

    def cstr(self, addr):
        o = self.off(addr)
        e = self.d.index(b"\0", o)
        return self.d[o:e].decode("latin-1")

    def modules(self):
        base = self.romhdr_off + struct.calcsize(ROMHDR_FMT)
        n = struct.calcsize(TOC_FMT)
        for i in range(self.hdr["nummods"]):
            attrs, ft, size, name, e32, o32, load = struct.unpack_from(TOC_FMT, self.d, base + i * n)
            yield dict(attrs=attrs, size=size, name=self.cstr(name), e32=e32, o32=o32, load=load)

    def files(self):
        base = self.romhdr_off + struct.calcsize(ROMHDR_FMT) + self.hdr["nummods"] * struct.calcsize(TOC_FMT)
        n = struct.calcsize(FILES_FMT)
        for i in range(self.hdr["numfiles"]):
            attrs, ft, real, comp, name, load = struct.unpack_from(FILES_FMT, self.d, base + i * n)
            yield dict(attrs=attrs, real=real, comp=comp, name=self.cstr(name), load=load)

    def build_pe(self, mod):
        d = self.d
        e = struct.unpack_from(E32_FMT, d, self.off(mod["e32"]))
        objcnt, imageflags, entryrva, vbase, submaj, submin, stackmax, vsize, s14rva, s14size, timestamp = e[:11]
        info = [(e[11 + 2 * k], e[12 + 2 * k]) for k in range(9)]
        subsys = e[29]
        secs = []
        for k in range(objcnt):
            vs, rva, psize, dataptr, realaddr, flags = struct.unpack_from(O32_FMT, d, self.off(mod["o32"]) + k * O32_SIZE)
            secs.append(dict(vsize=vs, rva=rva, psize=psize, dataptr=dataptr, realaddr=realaddr, flags=flags))

        file_align = 0x200
        sect_align = 0x1000
        hdr_size = 0x400
        # section bodies: ROM keeps psize bytes at dataptr (physical address)
        bodies = []
        for s in secs:
            if s["psize"] and s["dataptr"]:
                try:
                    body = d[self.off(s["dataptr"]):self.off(s["dataptr"]) + s["psize"]]
                except ValueError:
                    body = b""
            else:
                body = b""
            bodies.append(body)

        names = {}
        def secname(s, idx):
            f = s["flags"]
            if f & 0x02000000 and s["rva"] == info[5][0]:
                n = ".reloc"
            elif s["rva"] == info[2][0] and info[2][1]:
                n = ".rsrc"
            elif s["rva"] == info[1][0] and info[1][1] and not (f & STD_FLAG_CODE):
                n = ".idata"
            elif f & STD_FLAG_CODE:
                n = ".text"
            elif f & STD_FLAG_WRITE:
                n = ".data"
            else:
                n = ".rdata"
            if n in names:
                names[n] += 1
                n = f"{n[:6]}{names[n]}"
            else:
                names[n] = 0
            return n.encode().ljust(8, b"\0")

        out = bytearray()
        # DOS header
        out += b"MZ" + b"\0" * 0x3a + struct.pack("<I", 0x40)
        out += b"PE\0\0"
        out += struct.pack("<HHIIIHH", 0x1C2, objcnt, timestamp, 0, 0, 0xE0,
                           0x0102 | (0x2000 if imageflags & 0x2000 else 0))
        # optional header
        code_size = sum(len(b) for s, b in zip(secs, bodies) if s["flags"] & STD_FLAG_CODE)
        data_size = sum(len(b) for s, b in zip(secs, bodies) if not s["flags"] & STD_FLAG_CODE)
        code_base = next((s["rva"] for s in secs if s["flags"] & STD_FLAG_CODE), 0)
        data_base = next((s["rva"] for s in secs if not s["flags"] & STD_FLAG_CODE), 0)
        out += struct.pack("<HBBIIIIIII", 0x10B, 8, 0, code_size, data_size, 0, entryrva, code_base, data_base, vbase)
        out += struct.pack("<IIHHHHHHIIIIHHIIIIII", sect_align, file_align, 4, 0, 0, 0, submaj, submin, 0,
                           vsize, hdr_size, 0, subsys, 0, stackmax, 0x1000, 0x100000, 0x1000, 0, 16)
        dirs = [(0, 0)] * 16
        # e32 info order: EXP, IMP, RES, EXC, SEC, FIX, DEB, IMD, MSP ; CE 5+ also has sect14 (COM descriptor)
        for k, idx in enumerate((0, 1, 2, 3, 4, 5, 6, 7, 8)):
            dirs[idx] = info[k]
        dirs[14] = (s14rva, s14size)
        for rva, size in dirs:
            out += struct.pack("<II", rva, size)
        # section table
        ptr = hdr_size
        table = bytearray()
        layout = []
        for s, body in zip(secs, bodies):
            raw = (len(body) + file_align - 1) // file_align * file_align
            chars = 0
            if s["flags"] & STD_FLAG_CODE:
                chars |= 0x20000020
            if s["flags"] & STD_FLAG_WRITE:
                chars |= 0x80000040 | 0x40000000
            elif not s["flags"] & STD_FLAG_CODE:
                chars |= 0x40000040
            table += secname(s, 0) + struct.pack("<IIIIIIHHI", s["vsize"], s["rva"], raw, ptr if raw else 0, 0, 0, 0, 0, chars)
            layout.append((ptr, raw, body))
            ptr += raw
        out += table
        out += b"\0" * (hdr_size - len(out))
        for p, raw, body in layout:
            out += body + b"\0" * (raw - len(body))
        return bytes(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    if len(args) < 1 or (len(args) < 2 and "--list" not in flags):
        print(__doc__)
        return 2
    rom = Rom(open(args[0], "rb").read())
    h = rom.hdr
    print(f"ROMHDR at {rom.romhdr_off:#x}: physfirst={h['physfirst']:#x} physlast={h['physlast']:#x} "
          f"modules={h['nummods']} files={h['numfiles']} cpu={h['usCPUType']:#x} "
          f"RAM {h['ulRAMStart']:#x}-{h['ulRAMEnd']:#x}")
    if "--list" in flags:
        for m in rom.modules():
            print(f"MODULE {m['size']:9d}  {m['name']}")
        for f in rom.files():
            c = "compressed" if f["attrs"] & FILE_ATTRIBUTE_COMPRESSED or f["comp"] != f["real"] else ""
            print(f"FILE   {f['real']:9d}  {f['name']}  {c}")
        return 0
    out = args[1]
    os.makedirs(os.path.join(out, "modules"), exist_ok=True)
    os.makedirs(os.path.join(out, "files"), exist_ok=True)
    nm = nf = nc = 0
    for m in rom.modules():
        try:
            pe = rom.build_pe(m)
        except Exception as ex:  # keep going, report
            print(f"module {m['name']}: {ex}")
            continue
        with open(os.path.join(out, "modules", m["name"]), "wb") as o:
            o.write(pe)
        nm += 1
    for f in rom.files():
        compressed = f["comp"] != f["real"]
        data = rom.d[rom.off(f["load"]):rom.off(f["load"]) + f["comp"]]
        name = f["name"] + (".cecompressed" if compressed else "")
        with open(os.path.join(out, "files", name), "wb") as o:
            o.write(data)
        nf += 1
        nc += compressed
    print(f"wrote {nm} modules, {nf} files ({nc} still ROM-compressed) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
