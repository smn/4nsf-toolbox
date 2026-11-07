#!/usr/bin/env python3
"""Decompress Windows CE 5/6/7 ROM-compressed files (LZX, 4 KB blocks).

Files that ROMIMAGE stores compressed (the ones ceromdump.py writes with a
".cecompressed" suffix) use the layout handled by cecompr.dll's
CEDecompressROM: a table of 24-bit little-endian values, the first being the
uncompressed size and the following ones the end offset of each compressed
block, then the blocks themselves. Each block holds up to 4096 bytes and
starts with a 16-byte header (u32 window bits, u32 uncompressed size, 8
unused bytes) followed by a standard Microsoft LZX bitstream (the same
format as in CAB files: pre-tree, main tree, length tree, aligned-offset
tree, verbatim/aligned/uncompressed blocks, optional E8 translation).

Usage: celzx.py IN.cecompressed OUT [UNCOMPRESSED_SIZE]
       celzx.py --dir FILES_DIR          (decompress every *.cecompressed)
"""
import os
import struct
import sys

POSITION_SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}
EXTRA_BITS = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10,
              11, 11, 12, 12, 13, 13, 14, 14, 15, 15, 16, 16] + [17] * 15
POSITION_BASE = [0] * 51
for _i in range(1, 51):
    POSITION_BASE[_i] = POSITION_BASE[_i - 1] + (1 << EXTRA_BITS[_i - 1])

PRETREE_SYMS, LENTREE_SYMS, ALIGNED_SYMS = 20, 249, 8
MIN_MATCH = 2


class Bits:
    """LZX bit reader: 16-bit little-endian words, bits consumed MSB first."""

    def __init__(self, data, pos=0):
        self.d = data
        self.pos = pos
        self.buf = 0
        self.n = 0

    def ensure(self, k):
        while self.n < k:
            if self.pos + 1 < len(self.d):
                w = self.d[self.pos] | (self.d[self.pos + 1] << 8)
            else:
                w = 0
            self.pos += 2
            self.buf = (self.buf << 16) | w
            self.n += 16

    def peek(self, k):
        self.ensure(k)
        return (self.buf >> (self.n - k)) & ((1 << k) - 1)

    def drop(self, k):
        self.n -= k
        self.buf &= (1 << self.n) - 1

    def read(self, k):
        if k == 0:
            return 0
        v = self.peek(k)
        self.drop(k)
        return v

    def align_byte_stream(self):
        """Return to byte boundary: discard whole buffered words."""
        self.pos -= self.n // 16 * 2
        self.buf = 0
        self.n = 0


class Huffman:
    """Canonical Huffman decoder from code lengths (max 16 bits)."""

    def __init__(self, lengths):
        self.max_len = max(lengths) if any(lengths) else 0
        self.codes = {}
        code = 0
        for bits in range(1, 17):
            for sym, ln in enumerate(lengths):
                if ln == bits:
                    self.codes[(bits, code)] = sym
                    code += 1
            code <<= 1

    def decode(self, br):
        if not self.max_len:
            raise ValueError("empty Huffman table")
        code = 0
        for bits in range(1, 17):
            code = (code << 1) | br.read(1)
            sym = self.codes.get((bits, code))
            if sym is not None:
                return sym
        raise ValueError("bad Huffman code")


def read_lengths(br, lens, first, last):
    pre = Huffman([br.read(4) for _ in range(PRETREE_SYMS)])
    x = first
    while x < last:
        z = pre.decode(br)
        if z == 17:
            n = br.read(4) + 4
            lens[x:x + n] = [0] * n
            x += n
        elif z == 18:
            n = br.read(5) + 20
            lens[x:x + n] = [0] * n
            x += n
        elif z == 19:
            n = br.read(1) + 4
            z = pre.decode(br)
            v = (lens[x] + 17 - z) % 17
            lens[x:x + n] = [v] * n
            x += n
        else:
            lens[x] = (lens[x] + 17 - z) % 17
            x += 1


def lzx_decompress(data, out_len, window_bits):
    """Decode one LZX stream (CAB-style framing) producing out_len bytes."""
    if window_bits not in POSITION_SLOTS:
        raise ValueError(f"bad window bits {window_bits}")
    main_syms = 256 + (POSITION_SLOTS[window_bits] << 3)
    br = Bits(data)
    out = bytearray()
    r0 = r1 = r2 = 1
    main_lens = [0] * main_syms
    len_lens = [0] * LENTREE_SYMS
    intel_started = False

    intel_filesize = 0
    if br.read(1):
        intel_filesize = (br.read(16) << 16) | br.read(16)

    while len(out) < out_len:
        btype = br.read(3)
        bsize = (br.read(16) << 8) | br.read(8)
        if btype == 1 or btype == 2:
            aligned = None
            if btype == 2:
                aligned = Huffman([br.read(3) for _ in range(ALIGNED_SYMS)])
            read_lengths(br, main_lens, 0, 256)
            read_lengths(br, main_lens, 256, main_syms)
            main = Huffman(main_lens)
            if main_lens[0xE8]:
                intel_started = True
            read_lengths(br, len_lens, 0, LENTREE_SYMS)
            lentree = Huffman(len_lens) if any(len_lens) else None
            remaining = bsize
            while remaining > 0 and len(out) < out_len:
                sym = main.decode(br)
                if sym < 256:
                    out.append(sym)
                    remaining -= 1
                    continue
                sym -= 256
                mlen = sym & 7
                if mlen == 7:
                    mlen += lentree.decode(br)
                mlen += MIN_MATCH
                slot = sym >> 3
                if slot > 2:
                    extra = EXTRA_BITS[slot]
                    if aligned is not None and extra >= 3:
                        verb = br.read(extra - 3) << 3
                        off = POSITION_BASE[slot] + verb + aligned.decode(br) - 2
                    else:
                        off = POSITION_BASE[slot] + br.read(extra) - 2
                    r2, r1, r0 = r1, r0, off
                elif slot == 0:
                    off = r0
                elif slot == 1:
                    off = r1
                    r1, r0 = r0, off
                else:
                    off = r2
                    r2, r0 = r0, off
                start = len(out) - off
                if start < 0:
                    raise ValueError("match before start of output")
                for i in range(mlen):
                    out.append(out[start + i])
                remaining -= mlen
        elif btype == 3:
            # uncompressed block: realign to 16-bit boundary, then R0..R2, raw bytes
            br.ensure(16)
            br.align_byte_stream()
            p = br.pos
            r0, r1, r2 = struct.unpack_from("<III", data, p)
            p += 12
            out += data[p:p + bsize]
            p += bsize
            if bsize & 1:
                p += 1
            br = Bits(data, p)
        else:
            raise ValueError(f"bad block type {btype}")

    out = out[:out_len]
    if intel_started and out_len >= 10 and intel_filesize:
        i = 0
        while i < out_len - 10:
            if out[i] == 0xE8:
                abs_off = struct.unpack_from("<i", out, i + 1)[0]
                if -i <= abs_off < intel_filesize:
                    rel = abs_off - i if abs_off >= 0 else abs_off + intel_filesize
                    struct.pack_into("<i", out, i + 1, rel)
                i += 4
            i += 1
    return bytes(out)


def ce_decompress(data, out_len=None):
    """Decode a CE ROM compressed file (24-bit block table + LZX blocks)."""
    total = int.from_bytes(data[0:3], "little")
    if out_len is None:
        out_len = total
    nblocks = (max(total, 1) - 1 >> 12) + 1
    table = [int.from_bytes(data[3 + 3 * i:6 + 3 * i], "little") for i in range(nblocks)]
    start = 3 * (nblocks + 1)
    out = bytearray()
    for i, end in enumerate(table):
        blk = data[start:end]
        if len(blk) < 16:
            raise ValueError(f"block {i} too short")
        wbits, usize = struct.unpack_from("<II", blk, 0)
        out += lzx_decompress(blk[16:], usize, wbits)
        start = end
    if len(out) < out_len:
        raise ValueError(f"short output {len(out)} < {out_len}")
    return bytes(out[:out_len])


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--dir":
        d = args[1]
        ok = bad = 0
        for n in sorted(os.listdir(d)):
            if not n.endswith(".cecompressed"):
                continue
            src = os.path.join(d, n)
            dst = os.path.join(d, n[:-len(".cecompressed")])
            try:
                out = ce_decompress(open(src, "rb").read())
                open(dst, "wb").write(out)
                os.unlink(src)
                ok += 1
                print(f"ok  {len(out):9d}  {dst}")
            except Exception as ex:
                bad += 1
                print(f"ERR {src}: {ex}")
        print(f"decompressed {ok}, failed {bad}")
        return 1 if bad else 0
    src, dst = args[0], args[1]
    size = int(args[2]) if len(args) > 2 else None
    out = ce_decompress(open(src, "rb").read(), size)
    open(dst, "wb").write(out)
    print(f"wrote {dst}: {len(out)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
