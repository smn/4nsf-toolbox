#!/usr/bin/env bash
# Build the "full Navigon environment" disk for the QEMU emulator from the
# official VW "maps + more" update package. Nothing from the package is
# committed to git; everything lands in Emulator/work/ (gitignored).
#
# Steps (each is skipped when its output already exists):
#   1. download Central_Europe.zip (3.5 GB) from Volkswagen's map server
#   2. unzip, verify the package's own MD5 list
#   3. unpack the two ExtractorCE archives: Install_OS.exe -> work/navigon/os,
#      UpdateMeContent.content -> work/navigon/flash (the \My Flash Disk tree)
#   4. dump the Windows CE ROM (NK.nb0) into modules and files, decompress the
#      ROM-compressed files (LZX)
#   5. dump the wince-qemu Compact 7 image too (for its export tables) and patch
#      a copy so its disk mounts as "\My Flash Disk"
#   6. shim the flash binaries' imports that the Compact 7 image lacks
#   7. build a 4 GB FAT32 disk: flash tree + ROM dump + this repo's Apps
#
# Afterwards:  Emulator/run-emulator.sh --navigon
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HERE/work}"
NAV="$WORK/navigon"
PKG_URL="${PKG_URL:-https://navigation-maps.volkswagen.com/vw-maps/Central_Europe.zip}"
PKG_ZIP="$NAV/$(basename "$PKG_URL")"
DISK_MB="${DISK_MB:-4000}"
IMAGE_RAW="$WORK/NK.bin.load-0x800010c0.raw"

for tool in curl unzip python3 mkfs.vfat mcopy md5sum; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done
mkdir -p "$NAV"

echo ">> 1. package"
if [ ! -f "$PKG_ZIP" ]; then
  curl -fL -A "Mozilla/5.0" -o "$PKG_ZIP.part" "$PKG_URL"
  mv "$PKG_ZIP.part" "$PKG_ZIP"
fi

echo ">> 2. unzip + MD5"
if [ ! -f "$NAV/pkg/.verified" ]; then
  mkdir -p "$NAV/pkg"
  unzip -q -o "$PKG_ZIP" -d "$NAV/pkg"
  (cd "$NAV/pkg" && tr -d '\r' < *.md5 | sed 's/ \*/  /' | md5sum -c --quiet -) && touch "$NAV/pkg/.verified"
fi

echo ">> 3. ExtractorCE archives"
[ -f "$NAV/os/NK.nb0" ] || python3 -I "$HERE/sfx_extract.py" "$NAV/pkg/Install_OS.exe" "$NAV/os" | tail -1
[ -f "$NAV/flash/NAVIGON/navigon.exe" ] || python3 -I "$HERE/sfx_extract.py" "$NAV/pkg/UpdateMeContent.content" "$NAV/flash" | tail -1

echo ">> 4. ROM dump + LZX"
if [ ! -d "$NAV/os/rom/modules" ]; then
  python3 -I "$HERE/ceromdump.py" "$NAV/os/NK.nb0" "$NAV/os/rom" | tail -1
  python3 -I "$HERE/celzx.py" --dir "$NAV/os/rom/files" | tail -1
fi

echo ">> 5. Compact 7 image"
if [ ! -f "$IMAGE_RAW" ]; then
  echo "   run Emulator/run-emulator.sh once first (it downloads the image)" >&2
  exit 1
fi
[ -d "$WORK/rom_vexpress/modules" ] || python3 -I "$HERE/ceromdump.py" "$IMAGE_RAW" "$WORK/rom_vexpress" | tail -1
[ -f "$WORK/NK.flashdisk.raw" ] || python3 -I "$HERE/patch_image.py" "$IMAGE_RAW" "$WORK/NK.flashdisk.raw"

echo ">> 6. import shims"
if [ ! -f "$NAV/flash_shim/.done" ]; then
  rm -rf "$NAV/flash_shim"
  cp -al "$NAV/flash" "$NAV/flash_shim"
  # first pass learns which symbols are missing, second pass builds the stub
  find "$NAV/flash_shim" -type f \( -iname '*.exe' -o -iname '*.dll' \) -print0 \
    | xargs -0 python3 -I "$HERE/cestub.py" patch --names "$NAV/os/rom/modules" \
        --stub-dlls svoxdll.dll "$WORK/rom_vexpress/modules" cestub.dll \
    | tee "$NAV/shim.log"
  syms=$(grep '^stub must export:' "$NAV/shim.log" | sed 's/^stub must export: //')
  python3 -I "$HERE/cestub.py" make-stub "$NAV/cestub.dll" $syms
  find "$NAV/flash_shim" -name '*.orig' -delete
  # the stub and the device's \Windows DLLs next to every executable
  for d in $(find "$NAV/flash_shim" -iname '*.exe' -printf '%h\n' | sort -u) "$NAV/flash_shim"; do
    cp "$NAV/cestub.dll" "$d/"
    cp "$NAV"/os/rom/files/*.[dD][lL][lL] "$d/" 2>/dev/null || true
  done
  cp "$HERE/emu_start.mscr" "$NAV/flash_shim/"
  touch "$NAV/flash_shim/.done"
fi

echo ">> 7. disk image"
if [ ! -f "$WORK/navigon-disk.img" ]; then
  rm -rf "$NAV/stage"; mkdir -p "$NAV/stage"
  cp -al "$NAV"/flash_shim/* "$NAV/stage/"
  cp -al "$NAV/os/rom" "$NAV/stage/rom"
  cp -r "$HERE/../Apps/." "$NAV/stage/Apps/"
  python3 -I "$HERE/mkdisk.py" "$WORK/navigon-disk.img.part" "$DISK_MB" "$NAV"/stage/* | tail -2
  mv "$WORK/navigon-disk.img.part" "$WORK/navigon-disk.img"
fi

echo "done. Boot with: $HERE/run-emulator.sh --navigon"
