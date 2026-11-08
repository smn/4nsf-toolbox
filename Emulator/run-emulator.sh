#!/usr/bin/env bash
# Boot a Windows Embedded Compact 7 (ARM) virtual machine in QEMU with the
# toolbox's Apps folder attached as a disk, so Windows CE ARM apps can be tried
# without a Garmin 4NSF / Navigon 70 device. See Emulator/README.md.
#
# Usage: Emulator/run-emulator.sh [--headless] [--rebuild-disk] [--navigon] [extra qemu args]
#   --headless       no window; VNC on 127.0.0.1:5901, QEMU monitor on work/mon.sock
#   --rebuild-disk   recreate work/disk.img from ../Apps even if it exists
#   --navigon        boot the patched image with work/navigon-disk.img, the full
#                    VW/Navigon flash tree built by build-navigon.sh
#   --image FILE / --disk FILE   use another flat kernel image / disk image
#   --loadvm NAME    resume a VM snapshot saved with start-vw.sh --save NAME
#                    (needs the qcow2 overlay disk that build-navigon.sh makes)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HERE/work}"
IMAGE_URL="https://github.com/Milek7/wince-qemu/releases/download/2022-04-17/NK.bin.entry-0x800010c0.zip"
IMAGE_ZIP_SHA256="3c2f5a0bf904209b8f22e7d395b17fdd0a3b9e6a36f0cdfe93f3f89e03775485"
IMAGE_RAW="NK.bin.load-0x800010c0.raw"       # name inside the zip
IMAGE_RAW_SHA256="0fef23852d730add79eccf421e7de81336964377089228a49be86c4f754016b9"
LOAD_ADDR=0x80000000
ENTRY_ADDR=0x800010c0
DISK_MB="${DISK_MB:-256}"

headless=0 rebuild=0 image="" disk="" loadvm=""
extra=()
while [ $# -gt 0 ]; do
  case "$1" in
    --headless) headless=1 ;;
    --rebuild-disk) rebuild=1 ;;
    --navigon) image="$WORK/NK.flashdisk.raw"; disk="$WORK/navigon-disk.img"
               [ -f "$WORK/navigon-disk.qcow2" ] && disk="$WORK/navigon-disk.qcow2" ;;
    --image) image="$2"; shift ;;
    --disk) disk="$2"; shift ;;
    --loadvm) loadvm="$2"; shift ;;
    *) extra+=("$1") ;;
  esac
  shift
done

for tool in qemu-system-arm curl unzip mkfs.vfat mcopy python3 sha256sum; do
  command -v "$tool" >/dev/null || { echo "missing: $tool (Debian/Ubuntu: apt install qemu-system-arm curl unzip dosfstools mtools python3)" >&2; exit 1; }
done

mkdir -p "$WORK"
cd "$WORK"

if [ ! -f "$IMAGE_RAW" ] || ! echo "$IMAGE_RAW_SHA256  $IMAGE_RAW" | sha256sum -c --quiet - 2>/dev/null; then
  echo ">> downloading prebuilt WinCE 7 image (Milek7/wince-qemu, ~11 MB)"
  curl -fL -o image.zip "$IMAGE_URL"
  echo "$IMAGE_ZIP_SHA256  image.zip" | sha256sum -c -
  unzip -o image.zip "$IMAGE_RAW"
  echo "$IMAGE_RAW_SHA256  $IMAGE_RAW" | sha256sum -c -
fi

if [ -z "$disk" ] && { [ "$rebuild" = 1 ] || [ ! -f disk.img ]; }; then
  echo ">> building disk.img (${DISK_MB} MB FAT32) with the Apps folder"
  python3 "$HERE/mkdisk.py" disk.img "$DISK_MB" "$HERE/../Apps"
fi
image="${image:-$IMAGE_RAW}"
disk="${disk:-disk.img}"
for f in "$image" "$disk"; do
  [ -f "$f" ] || { echo "missing $f (for --navigon run build-navigon.sh first)" >&2; exit 1; }
done

display=(-display gtk)
if [ "$headless" = 1 ]; then
  display=(-display none -vnc 127.0.0.1:1 -monitor "unix:$WORK/mon.sock,server,nowait")
  echo ">> headless: VNC 127.0.0.1:5901, monitor $WORK/mon.sock, serial log $WORK/serial.log"
fi
# gdbstub for tools/trace.sh. UARTs 1-3 as TCP servers: COM1: on 5555 is
# Navigon's GPS port (tools/nmea.py); COM2: on 5556 and COM3: on 5557 exist
# once the Devkit's addport.exe has loaded its polled driver in the guest
# (launch-all.exe does that); COM2: carries the deploy agent.
extra+=(-gdb tcp:127.0.0.1:1234 -serial tcp:127.0.0.1:5555,server,nowait
        -serial tcp:127.0.0.1:5556,server,nowait -serial tcp:127.0.0.1:5557,server,nowait)

# a qcow2 overlay (writes and VM snapshots) over the raw image, or the raw image
case "$disk" in
  *.qcow2) blockdev=(-blockdev "driver=file,filename=$disk,node-name=f0" -blockdev "driver=qcow2,file=f0,node-name=d0") ;;
  *)       blockdev=(-blockdev "driver=file,filename=$disk,node-name=d0") ;;
esac
[ -n "$loadvm" ] && extra+=(-loadvm "$loadvm")

# a patched QEMU (see README, "VM snapshots") is preferred when present
QEMU="${QEMU:-}"
[ -z "$QEMU" ] && [ -x "$WORK/qemu/qemu-system-arm" ] && QEMU="$WORK/qemu/qemu-system-arm" && extra+=(-L "$WORK/qemu/share")
QEMU="${QEMU:-qemu-system-arm}"

exec "$QEMU" \
  -global virtio-mmio.force-legacy=false \
  -machine type=vexpress-a15,secure=off,virtualization=off -m 256 \
  -device "loader,addr=$LOAD_ADDR,file=$image" \
  -device "loader,addr=$ENTRY_ADDR,cpu-num=0" \
  -device virtio-tablet-device \
  "${blockdev[@]}" -device virtio-blk-device,drive=d0 \
  -serial "file:$WORK/serial.log" \
  -audio none \
  "${display[@]}" "${extra[@]}"
