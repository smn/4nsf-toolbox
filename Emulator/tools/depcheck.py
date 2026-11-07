#!/usr/bin/env python3
"""Static dependency check of the flash tree against the QEMU image.

For every EXE/DLL under FLASH, each imported DLL is looked up (1) next to the
importing file, (2) in the image's ROM modules/files (IMAGE_MODULES dir and
its sibling files/), recursively, and missing DLLs are reported with the
chain that needs them. Usage: depcheck.py FLASH_DIR IMAGE_MODULES_DIR
"""
import os
import sys

import pefile

flash, imgmods = sys.argv[1:3]
image = {}
for d in (imgmods, os.path.join(os.path.dirname(imgmods.rstrip("/")), "files")):
    if os.path.isdir(d):
        for f in os.listdir(d):
            image.setdefault(f.lower(), os.path.join(d, f))
cache = {}


def imports_of(path):
    if path in cache:
        return cache[path]
    try:
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        res = [e.dll.decode() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])]
    except Exception:
        res = []
    cache[path] = res
    return res


def resolve(dll, folder):
    for f in os.listdir(folder):
        if f.lower() == dll.lower():
            return os.path.join(folder, f), "local"
    if dll.lower() in image:
        return image[dll.lower()], "image"
    return None, None


missing = {}
def walk(path, folder, chain, seen):
    for dll in imports_of(path):
        p, where = resolve(dll, folder)
        if p is None:
            missing.setdefault(dll, set()).add(" -> ".join(chain + [dll]))
        elif where == "local" and p not in seen:
            seen.add(p)
            walk(p, folder, chain + [dll], seen)


for root, _, files in os.walk(flash):
    for f in files:
        if f.lower().endswith(".exe"):
            walk(os.path.join(root, f), root, [os.path.relpath(os.path.join(root, f), flash)], set())
for dll in sorted(missing):
    print(dll)
    for c in sorted(missing[dll])[:6]:
        print("   ", c)
