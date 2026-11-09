#!/usr/bin/env python3
"""Linear Thumb disassembly of a raw ARM binary (no PE header), with literal
pools and ADR targets resolved against a given load address. Written for the
device's ApLoader.bin (loaded at 0x03E00000, Thumb-1, see docs/hardware.md):

  rawthumb.py ApLoader.bin 03E00000 show 7992 7a00     # disassemble a range
  rawthumb.py ApLoader.bin 03E00000 callers 7b90       # bl/blx sites of a function
"""
import struct, re, sys, collections
from capstone import *
import os
# usage: rawthumb.py FILE BASE show LO HI | callers ADDR    (addresses are file offsets, hex)
d = open(sys.argv[1], 'rb').read(); BASE = int(sys.argv[2], 16); sys.argv = sys.argv[:1] + sys.argv[3:]
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB); md.skipdata = True
ins_list = list(md.disasm(d, 0))
def lit(ins):
    m = re.match(r'ldr\s+(\w+),\s*\[pc,\s*#(0x[0-9a-f]+|\d+)\]', ins.mnemonic + ' ' + ins.op_str)
    if not m: return None, None
    a = ((ins.address + 4) & ~3) + int(m.group(2), 0)
    return m.group(1), (struct.unpack_from('<I', d, a)[0] if a + 4 <= len(d) else None)
def note_for(ins):
    r, v = lit(ins); note = ''
    if v is not None:
        note = f'; ={v:#x}'
        if BASE <= v < BASE + len(d):
            t = d[v-BASE:v-BASE+48]
            if all(32 <= c < 127 for c in t[:6]): note += ' ' + repr(t.split(b'\0')[0][:44])
    m = re.match(r'adr\s+\w+,\s*#(0x[0-9a-f]+|\d+)$', ins.mnemonic + ' ' + ins.op_str)
    if m:
        t = ((ins.address + 4) & ~3) + int(m.group(1), 0)
        if t < len(d): note = '; -> ' + repr(d[t:t+60].split(b'\0')[0])
    return note
def show(lo, hi):
    for ins in ins_list:
        if lo <= ins.address < hi:
            print(f'{ins.address:06x}  {ins.mnemonic:7s} {ins.op_str:28s}{note_for(ins)}')
def callers(target):
    out = []
    for ins in ins_list:
        if ins.mnemonic in ('bl', 'blx') and ins.op_str == f'#{target:#x}': out.append(ins.address)
    return out
cmd = sys.argv[1]
if cmd == 'show': show(int(sys.argv[2], 16), int(sys.argv[3], 16))
elif cmd == 'callers': print([hex(a) for a in callers(int(sys.argv[2], 16))])
