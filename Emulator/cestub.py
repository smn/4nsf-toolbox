#!/usr/bin/env python3
"""Shim missing imports so device binaries load on a generic Windows CE image.

Two sub-commands:

  cestub.py make-stub OUT.dll NAME[=VALUE] [NAME[=VALUE] ...]
      Build a tiny ARM Windows CE DLL that exports each NAME as a function
      returning VALUE (default 0, i.e. FALSE / NULL). No toolchain needed.
      Also handy for replacing a whole OEM library (e.g. WolfSpecial.dll).

  cestub.py patch [--names DEVICE_MODULES_DIR] [--stub-dlls a.dll,b.dll] \
                  IMAGE_MODULES_DIR STUB.dll FILE [FILE ...]
      For each PE FILE, find imports (by ordinal or by name) from DLLs that
      exist in IMAGE_MODULES_DIR (a ceromdump.py "modules" directory of the
      target image) but which that image does not export, plus every import
      from the DLLs named in --stub-dlls. Rewrite them to come from STUB.dll by
      appending a new import section. Files are modified in place; the
      original is kept as FILE.orig. Ordinal imports are named through the
      device ROM's own export tables (--names, a ceromdump.py modules dir).
      Prints the list of shimmed symbols so the stub can be regenerated with
      "make-stub" if it lacks any. DLLs that are neither in the image nor in
      --stub-dlls are left alone (they are expected next to the executable).

The stub functions return 0, which for the functions seen so far
(GetSystemPowerStatusEx, RasDial, lineInitialize, ...) means "failed /
not available", which is what the Navigon software expects on a device
without that hardware.
"""
import os
import struct
import sys

IMAGE_FILE_MACHINE_THUMB = 0x1C2
SUBSYSTEM_WINDOWS_CE_GUI = 9


def align(v, a):
    return (v + a - 1) // a * a


# ---------------------------------------------------------------- make-stub

def make_stub(out, names, base=0x10000):
    # NAME or NAME=VALUE (0..255): the value the stub returns in r0
    rets = {}
    for n in names:
        name, _, val = n.partition("=")
        rets[name] = int(val, 0) if val else 0
    names = sorted(rets)
    file_align, sect_align = 0x200, 0x1000
    # code: DllMain returns 1; each stub: mov r0,#VALUE ; bx lr  (ARM mode)
    code = struct.pack("<II", 0xE3A00001, 0xE12FFF1E)  # entry
    stub_rvas = []
    for n in names:
        stub_rvas.append(len(code))
        code += struct.pack("<II", 0xE3A00000 | (rets[n] & 0xFF), 0xE12FFF1E)
    text_rva = 0x1000
    text_raw = align(len(code), file_align)

    # export directory
    edata_rva = text_rva + align(len(code), sect_align)
    n = len(names)
    dll_name = os.path.basename(out).encode() + b"\0"
    hdr = 40
    addr_funcs = edata_rva + hdr
    addr_names = addr_funcs + 4 * n
    addr_ords = addr_names + 4 * n
    name_blob_rva = addr_ords + 2 * n
    name_blob = b""
    name_rvas = []
    for nm in names:
        name_rvas.append(name_blob_rva + len(name_blob))
        name_blob += nm.encode() + b"\0"
    dllname_rva = name_blob_rva + len(name_blob)
    edata = struct.pack("<IIHHIIIIIII", 0, 0, 0, 0, dllname_rva, 1, n, n, addr_funcs, addr_names, addr_ords)
    edata += b"".join(struct.pack("<I", text_rva + r) for r in stub_rvas)
    edata += b"".join(struct.pack("<I", r) for r in name_rvas)
    edata += b"".join(struct.pack("<H", i) for i in range(n))
    edata += name_blob + dll_name
    edata_raw = align(len(edata), file_align)
    size_of_image = edata_rva + align(len(edata), sect_align)

    hdr_size = 0x400
    pe = bytearray()
    pe += b"MZ" + b"\0" * 0x3A + struct.pack("<I", 0x40)
    pe += b"PE\0\0"
    # characteristics: EXECUTABLE | 32BIT | DLL
    pe += struct.pack("<HHIIIHH", IMAGE_FILE_MACHINE_THUMB, 2, 0, 0, 0, 0xE0, 0x0102 | 0x2000)
    pe += struct.pack("<HBBIIIIIII", 0x10B, 8, 0, text_raw, edata_raw, 0, text_rva, text_rva, edata_rva, base)
    pe += struct.pack("<IIHHHHHHIIIIHHIIIIII", sect_align, file_align, 4, 0, 0, 0, 5, 0, 0,
                      size_of_image, hdr_size, 0, SUBSYSTEM_WINDOWS_CE_GUI, 0, 0x10000, 0x1000, 0x100000, 0x1000, 0, 16)
    dirs = [(0, 0)] * 16
    dirs[0] = (edata_rva, len(edata))
    for rva, size in dirs:
        pe += struct.pack("<II", rva, size)
    pe += b".text\0\0\0" + struct.pack("<IIIIIIHHI", len(code), text_rva, text_raw, hdr_size, 0, 0, 0, 0, 0x60000020)
    pe += b".edata\0\0" + struct.pack("<IIIIIIHHI", len(edata), edata_rva, edata_raw, hdr_size + text_raw, 0, 0, 0, 0, 0x40000040)
    pe += b"\0" * (hdr_size - len(pe))
    pe += code + b"\0" * (text_raw - len(code))
    pe += edata + b"\0" * (edata_raw - len(edata))
    with open(out, "wb") as f:
        f.write(pe)
    print(f"wrote {out}: {n} stub exports")


# -------------------------------------------------------------------- patch

def pe_exports(path):
    """Return (set of ordinals, set of names) exported by a PE file."""
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = pe + 24
    opt_size = struct.unpack_from("<H", d, pe + 20)[0]
    secs = []
    for k in range(nsec):
        o = opt + opt_size + 40 * k
        vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, vs, rp, rs))

    def r2o(rva):
        for va, vs, rp, rs in secs:
            if va <= rva < va + max(vs, rs):
                return rva - va + rp
        raise ValueError(f"rva {rva:#x} not mapped")

    erva, esize = struct.unpack_from("<II", d, opt + 96)
    if not erva:
        return set(), set()
    e = r2o(erva)
    base, nfunc, nnames, afunc, anames, aords = struct.unpack_from("<IIIIII", d, e + 16)
    ords = set()
    for i in range(nfunc):
        if struct.unpack_from("<I", d, r2o(afunc) + 4 * i)[0]:
            ords.add(base + i)
    names = set()
    for i in range(nnames):
        nrva = struct.unpack_from("<I", d, r2o(anames) + 4 * i)[0]
        o = r2o(nrva)
        names.add(d[o:d.index(b"\0", o)].decode())
    return ords, names


def pe_export_names(path):
    """Return {ordinal: name} for a PE file (names only where present)."""
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = pe + 24
    opt_size = struct.unpack_from("<H", d, pe + 20)[0]
    secs = []
    for k in range(nsec):
        o = opt + opt_size + 40 * k
        vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, vs, rp, rs))

    def r2o(rva):
        for va, vs, rp, rs in secs:
            if va <= rva < va + max(vs, rs):
                return rva - va + rp
        raise ValueError(f"rva {rva:#x} not mapped")

    erva, esize = struct.unpack_from("<II", d, opt + 96)
    if not erva:
        return {}
    e = r2o(erva)
    base, nfunc, nnames, afunc, anames, aords = struct.unpack_from("<IIIIII", d, e + 16)
    out = {}
    for i in range(nnames):
        nrva = struct.unpack_from("<I", d, r2o(anames) + 4 * i)[0]
        o = r2o(nrva)
        idx = struct.unpack_from("<H", d, r2o(aords) + 2 * i)[0]
        out[base + idx] = d[o:d.index(b"\0", o)].decode()
    return out


class PE:
    def __init__(self, path):
        self.path = path
        self.d = bytearray(open(path, "rb").read())
        d = self.d
        self.pe = struct.unpack_from("<I", d, 0x3C)[0]
        self.nsec = struct.unpack_from("<H", d, self.pe + 6)[0]
        self.opt = self.pe + 24
        self.opt_size = struct.unpack_from("<H", d, self.pe + 20)[0]
        self.sect_align, self.file_align = struct.unpack_from("<II", d, self.opt + 32)
        self.sec_table = self.opt + self.opt_size
        self.secs = []
        for k in range(self.nsec):
            o = self.sec_table + 40 * k
            name = d[o:o + 8]
            vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
            self.secs.append(dict(name=name, vs=vs, va=va, rs=rs, rp=rp, off=o))

    def r2o(self, rva):
        for s in self.secs:
            if s["va"] <= rva < s["va"] + max(s["vs"], s["rs"]):
                return rva - s["va"] + s["rp"]
        raise ValueError(f"rva {rva:#x} not mapped")

    def cstr(self, rva):
        o = self.r2o(rva)
        return self.d[o:self.d.index(b"\0", o)].decode()

    def imports(self):
        irva, isize = struct.unpack_from("<II", self.d, self.opt + 104)
        if not irva:
            return []
        out = []
        o = self.r2o(irva)
        while True:
            ilt, ts, fc, name, iat = struct.unpack_from("<IIIII", self.d, o)
            if not name and not iat:
                break
            thunks = []
            src = ilt or iat
            k = 0
            while True:
                v = struct.unpack_from("<I", self.d, self.r2o(src) + 4 * k)[0]
                if not v:
                    break
                if v & 0x80000000:
                    thunks.append(dict(idx=k, ordinal=v & 0xFFFF, name=None))
                else:
                    thunks.append(dict(idx=k, ordinal=None, name=self.cstr(v + 2)))
                k += 1
            out.append(dict(desc_off=o, ilt=ilt, iat=iat, dll=self.cstr(name), name_rva=name, thunks=thunks))
            o += 20
        return out

    def add_section(self, name, data, chars=0xC0000040):
        """Append a section; returns its RVA. Header table must have room."""
        last = self.secs[-1]
        va = align(last["va"] + max(last["vs"], last["rs"]), self.sect_align)
        rp = align(len(self.d), self.file_align)
        self.d += b"\0" * (rp - len(self.d))
        raw = align(len(data), self.file_align)
        self.d += data + b"\0" * (raw - len(data))
        o = self.sec_table + 40 * self.nsec
        hdr_end = struct.unpack_from("<I", self.d, self.opt + 60)[0]
        if o + 40 > hdr_end:
            raise ValueError("no room in section table")
        struct.pack_into("<8sIIIIIIHHI", self.d, o, name.ljust(8, b"\0"), len(data), va, raw, rp, 0, 0, 0, 0, chars)
        self.nsec += 1
        struct.pack_into("<H", self.d, self.pe + 6, self.nsec)
        struct.pack_into("<I", self.d, self.opt + 56, va + align(len(data), self.sect_align))  # SizeOfImage
        self.secs.append(dict(name=name, vs=len(data), va=va, rs=raw, rp=rp, off=o))
        return va


def patch_file(path, image_exports, stub_name, stub_dlls=(), ref_names=None):
    ref_names = ref_names or {}
    pe = PE(path)
    descs = pe.imports()
    shimmed = []
    new_descs = []  # (dll_name, [thunk values], iat_rva)
    for desc in descs:
        dll = desc["dll"].lower()
        if dll == stub_name.lower():
            continue
        if dll in image_exports:
            ords, names = image_exports[dll]
            missing = [t for t in desc["thunks"]
                       if (t["ordinal"] is not None and t["ordinal"] not in ords)
                       or (t["name"] is not None and t["name"] not in names)]
            if not missing:
                continue
            # replace the missing entries in the original thunk array with a
            # valid export, then shim each slot from the stub
            any_ord = min(ords) if ords else None
            src = desc["ilt"] or desc["iat"]
            for t in missing:
                o = pe.r2o(src) + 4 * t["idx"]
                if any_ord is None:
                    raise ValueError(f"{dll} exports nothing usable")
                struct.pack_into("<I", pe.d, o, 0x80000000 | any_ord)
                sym = t["name"] or ref_names.get(dll, {}).get(t["ordinal"]) or f"{dll}_ord{t['ordinal']}"
                shimmed.append(sym)
                new_descs.append((sym, desc["iat"] + 4 * t["idx"]))
        elif dll in stub_dlls:
            # DLL missing entirely: point the whole descriptor at the stub
            syms = [t["name"] or ref_names.get(dll, {}).get(t["ordinal"]) or f"{dll}_ord{t['ordinal']}" for t in desc["thunks"]]
            shimmed += syms
            new_descs.append((syms, desc["iat"], desc["desc_off"]))
    if not new_descs:
        return []

    # build new section: descriptors + ILTs + names
    blob = bytearray()
    desc_count = len(descs) + sum(1 for x in new_descs if len(x) == 2)
    desc_bytes = 20 * (desc_count + 1)
    blob += b"\0" * desc_bytes
    # copy original descriptors (whole-DLL redirects get renamed below)
    for i, desc in enumerate(descs):
        struct.pack_into("<IIIII", blob, 20 * i, desc["ilt"], 0, 0, desc["name_rva"], desc["iat"])
    stub_name_rva_off = len(blob)
    blob += stub_name.encode() + b"\0"

    def add_name(sym):
        off = len(blob)
        blob.extend(struct.pack("<H", 0) + sym.encode() + b"\0")
        if len(blob) % 2:
            blob.append(0)
        return off

    di = len(descs)
    for item in new_descs:
        if len(item) == 2:
            sym, iat_rva = item
            ilt_off = len(blob)
            blob += b"\0" * 8  # one entry + terminator, filled after RVA known
            name_off = add_name(sym)
            struct.pack_into("<IIIII", blob, 20 * di, 0, 0, 0, 0, iat_rva)
            blob_fix.append((di, ilt_off, [name_off]))
            di += 1
        else:
            syms, iat_rva, desc_off = item
            # find index of this descriptor in original list
            idx = next(i for i, dsc in enumerate(descs) if dsc["desc_off"] == desc_off)
            ilt_off = len(blob)
            blob += b"\0" * (4 * (len(syms) + 1))
            name_offs = [add_name(s) for s in syms]
            struct.pack_into("<IIIII", blob, 20 * idx, 0, 0, 0, 0, iat_rva)
            blob_fix.append((idx, ilt_off, name_offs))
    rva = pe.add_section(b".shim", bytes(blob))
    d = pe.d
    sec_rp = pe.secs[-1]["rp"]
    for di, ilt_off, name_offs in blob_fix:
        struct.pack_into("<I", d, sec_rp + 20 * di, rva + ilt_off)       # OriginalFirstThunk
        struct.pack_into("<I", d, sec_rp + 20 * di + 12, rva + stub_name_rva_off)  # Name
        for k, no in enumerate(name_offs):
            struct.pack_into("<I", d, sec_rp + ilt_off + 4 * k, rva + no)
    struct.pack_into("<II", d, pe.opt + 104, rva, desc_bytes)
    os.replace(path, path + ".orig") if not os.path.exists(path + ".orig") else None
    with open(path, "wb") as f:
        f.write(d)
    return shimmed


blob_fix = []


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "make-stub":
        make_stub(sys.argv[2], sys.argv[3:])
        return 0
    if cmd == "patch":
        argv = sys.argv[2:]
        stub_dlls, ref_dir = set(), None
        while argv and argv[0].startswith("--"):
            if argv[0] == "--stub-dlls":
                stub_dlls = set(x.lower() for x in argv[1].split(","))
            elif argv[0] == "--names":
                ref_dir = argv[1]
            argv = argv[2:]
        moddir, stub, files = argv[0], argv[1], argv[2:]
        ref_names = {}
        if ref_dir:
            for n in os.listdir(ref_dir):
                if n.lower().endswith((".dll", ".cpl")):
                    try:
                        ref_names[n.lower()] = pe_export_names(os.path.join(ref_dir, n))
                    except Exception:
                        pass
        image_exports = {}
        for n in os.listdir(moddir):
            if n.lower().endswith((".dll", ".cpl")):
                try:
                    image_exports[n.lower()] = pe_exports(os.path.join(moddir, n))
                except Exception as ex:
                    print(f"warning: cannot read exports of {n}: {ex}")
        stub_name = os.path.basename(stub)
        allsyms = set()
        for f in files:
            blob_fix.clear()
            try:
                syms = patch_file(f, image_exports, stub_name, stub_dlls, ref_names)
            except Exception as ex:
                print(f"{f}: FAILED {ex}")
                continue
            if syms:
                print(f"{f}: shimmed {syms}")
                allsyms.update(syms)
        if allsyms:
            print("stub must export:", " ".join(sorted(allsyms)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
