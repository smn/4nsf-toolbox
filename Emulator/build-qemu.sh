#!/usr/bin/env bash
# Build a qemu-system-arm with the one-line virtio fix that makes VM snapshots
# of the Compact 7 image restorable (see qemu-virtio-loadvm.patch). The
# binary lands in work/qemu/ and run-emulator.sh prefers it automatically.
#
#   Emulator/build-qemu.sh            # ~20 min on 4 cores, ~2 GB in work/qemu-src
#
# Needs: git, ninja-build, python3, pkg-config, libglib2.0-dev, libpixman-1-dev
# (apt install ninja-build libglib2.0-dev libpixman-1-dev). Any 8.2.x should
# do; other versions need the patch re-applied by hand if the context moved.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HERE/work}"
QEMU_TAG="${QEMU_TAG:-v8.2.2}"
SRC="$WORK/qemu-src"

mkdir -p "$WORK"
if [ ! -d "$SRC/.git" ]; then
  echo ">> cloning QEMU $QEMU_TAG"
  git clone -q --depth 1 -b "$QEMU_TAG" https://github.com/qemu/qemu.git "$SRC"
fi
cd "$SRC"
if ! grep -q "virtio_host_has_feature(vdev, VIRTIO_F_VERSION_1)) {" hw/virtio/virtio.c; then
  echo ">> applying qemu-virtio-loadvm.patch"
  patch -p1 < "$HERE/qemu-virtio-loadvm.patch"
fi
if [ ! -f build/build.ninja ]; then
  echo ">> configure (arm-softmmu only, VNC, no GTK/SDL)"
  ./configure --target-list=arm-softmmu --disable-docs --disable-werror \
    --disable-gtk --disable-sdl --disable-opengl --enable-vnc --disable-slirp > "$WORK/qemu-configure.log" 2>&1 \
    || { tail -20 "$WORK/qemu-configure.log"; exit 1; }
fi
echo ">> building (log: $WORK/qemu-build.log)"
ninja -C build -j"$(nproc)" qemu-system-arm > "$WORK/qemu-build.log" 2>&1 || { tail -20 "$WORK/qemu-build.log"; exit 1; }
mkdir -p "$WORK/qemu"
cp build/qemu-system-arm "$WORK/qemu/"
# data files (VNC keymaps etc.); run-emulator.sh passes this directory with -L
rm -rf "$WORK/qemu/share"; mkdir -p "$WORK/qemu/share"
cp -r pc-bios/keymaps "$WORK/qemu/share/"
echo "done: $WORK/qemu/qemu-system-arm ($("$WORK/qemu/qemu-system-arm" --version | head -1))"
