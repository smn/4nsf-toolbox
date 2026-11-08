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
[ -f "$WORK/NK.flashdisk.raw" ] || python3 -I "$HERE/patch_image.py" --display 480x272 "$IMAGE_RAW" "$WORK/NK.flashdisk.raw"

echo ">> 6. import shims"
if [ ! -f "$NAV/flash_shim/.done" ]; then
  rm -rf "$NAV/flash_shim"
  cp -al "$NAV/flash" "$NAV/flash_shim"
  # first pass learns which symbols are missing, second pass builds the stub
  find "$NAV/flash_shim" -type f \( -iname '*.exe' -o -iname '*.dll' \) -print0 \
    | xargs -0 python3 -I "$HERE/cestub.py" patch --names "$NAV/os/rom/modules" \
        --stub-dlls svoxdll.dll "$WORK/rom_vexpress/modules" cestub.dll \
    | tee "$NAV/shim.log"
  syms=$(grep '^stub must export:' "$NAV/shim.log" | sed 's/^stub must export: //' | tr ' ' '\n' | grep -v '^GetSystemPowerStatusEx$' | tr '\n' ' ')
  # GetSystemPowerStatusEx must fill its 24-byte SYSTEM_POWER_STATUS_EX: AC
  # on-line, battery high, 100 %, unknown lifetimes, backup battery 100 %.
  # (Exactly 24 bytes: the callers keep the struct on the stack.)
  printf '\1\1\144\0\377\377\377\377\377\377\377\377\0\1\144\0\377\377\377\377\377\377\377\377' > "$WORK/powerstatus.bin"
  (cd "$WORK" && python3 -I "$HERE/cestub.py" make-stub "$NAV/cestub.dll" GetSystemPowerStatusEx=fill:powerstatus.bin $syms)
  find "$NAV/flash_shim" -name '*.orig' -delete
  # the stub and the device's \Windows DLLs next to every executable.
  # cp -n: the package's own copy wins (BT\MAPBL.dll is newer than the ROM's,
  # and flash_shim is hard-linked to flash, so a plain cp would overwrite the
  # pristine tree through the link).
  for d in $(find "$NAV/flash_shim" -iname '*.exe' -not -path '*/0emu/*' -printf '%h\n' | sort -u) "$NAV/flash_shim"; do
    cp "$NAV/cestub.dll" "$d/"
    cp -n "$NAV"/os/rom/files/*.[dD][lL][lL] "$NAV"/os/rom/files/*.ttf "$d/" 2>/dev/null || true
  done
  cp "$HERE/emu_start.mscr" "$NAV/flash_shim/"
  touch "$NAV/flash_shim/.done"
fi

echo ">> 6b. emulated hidden flash (WolfSpecial.dll replacement)"
# The real WolfSpecial.dll talks to the HFC1:/GMD1:/WDT1:/BKL1: drivers of the
# Cartesio board. This stub serves a 2 KB hidden-flash image from a file
# instead. Drop a dump of your own unit's hidden flash in work/hidden_flash.bin
# to get its brand / VIN pairing / serial; set WOLF_STUB=0 to keep the real DLL.
# Calling conventions were recovered from HWLHardwareLayer.dll's call sites:
# GetHWVersion(index, wbuf, len), GetOSVersion/GetBTVersion(wbuf, len),
# GetDeviceID(wbuf, len), ReadBTAddressFromHF(buf6, 6), GetPowerSource() ->
# 1 charger / 2 usb / 3 cradle, GetDeviceBrightness() -> value, cradle = not docked.
if [ "${WOLF_STUB:-1}" = 1 ]; then
  # Without a dump, mkflash.py writes a flash that says "paired with a VW
  # (Fender sound) with this VIN", which is what gets the apps past the
  # "connect your device to your brand new car" screen. VIN=... overrides.
  [ -f "$WORK/hidden_flash.bin" ] || python3 -I "$HERE/mkflash.py" --out "$WORK/hidden_flash.bin" ${VIN:+--vin "$VIN"}
  mkdir -p "$NAV/wolfstub"
  (cd "$WORK" && python3 -I "$HERE/cestub.py" make-stub "$NAV/wolfstub/WolfSpecial.dll" \
    ReadHiddenFlash=blob:hidden_flash.bin WriteHiddenFlash=blobw:hidden_flash.bin \
    GetDeviceID=wstr:EMU0000001 GetHWVersion=wstr1:1.0 GetBTVersion=wstr:1.0 GetOSVersion=wstr:2.33 \
    GetBootLoaderVersion=wstr:1.0 ReadBTAddressFromHF=0 \
    BackToFactorySettings=1 GetDeviceBrightness=80 GetDisplayState=1 GetExternalAudioMutePin=1 \
    GetGPRSModemPowerState=1 GetHWWatchdogState=1 GetHWWatchdogTimeout=1 GetPowerSource=1 \
    GetSpeakerMode=1 Gpio_control=1 IsCradleStatusConnected=0 RefreshHWWatchdog=1 ResetBTChip=1 \
    ResetGPRSModemState=1 SetDeviceBrightness=1 SetDisplayState=1 SetExternalAudioMutePin=1 \
    SetGPRSModemPowerState=1 SetHWWatchdogState=1 SetHWWatchdogTimeout=1 SetLoaderTextColor=1 \
    SetNoSWFoundImagePath=1 SetSpeakerMode=1 SetSplashImagePath=1 SetTCPWindowSize=1 \
    SetUSBModeImagePath=1 TouchCalibration=1 WriteBTAddressToHF=1)
  for d in $(find "$NAV/flash_shim" -iname '*.exe' -not -path '*/0emu/*' -printf '%h\n' | sort -u); do
    cp "$NAV/wolfstub/WolfSpecial.dll" "$d/"
  done
fi

echo ">> 6b2. optional: replace the whole hardware layer (HWL_STUB=1)"
# With HWL_STUB=1 HWLHardwareLayer.dll itself is replaced by a stub that
# answers every call with success / canned values (device not docked). Used
# to prove the hardware layer is not what keeps the VW shell from drawing.
if [ "${HWL_STUB:-0}" = 1 ]; then
  python3 -I "$HERE/cestub.py" make-stub "$NAV/wolfstub/HWLHardwareLayer.dll" $(sed -n '/^HWL_STUB_EXPORTS=/,/^HWL_STUB_END/p' "$HERE/build-navigon.sh" | sed '1d;$d')
  for d in $(find "$NAV/flash_shim" -iname '*.exe' -printf '%h\n' | sort -u); do
    [ -f "$d/HWLHardwareLayer.dll" ] && cp --remove-destination "$NAV/wolfstub/HWLHardwareLayer.dll" "$d/"
  done
fi

echo ">> 6b3. DirectDraw and GL ES"
# navigon.exe needs openGL_ES_STA2065.dll (device ROM), which imports
# DirectDrawCreate from a ddraw.dll the Compact 7 image does not have. A stub
# that fails the call lets the DLL load. GL_STUB=1 replaces the GL ES DLL
# itself (it drives the Cartesio SGA) with a stub of all its exports.
python3 -I "$HERE/cestub.py" make-stub "$NAV/wolfstub/ddraw.dll" DirectDrawCreate=0x80004005
for d in $(find "$NAV/flash_shim" -iname '*.exe' -not -path '*/0emu/*' -printf '%h\n' | sort -u); do
  cp "$NAV/wolfstub/ddraw.dll" "$d/"
done
if [ "${GL_STUB:-0}" = 1 ]; then
  python3 -I "$HERE/cestub.py" make-stub "$NAV/wolfstub/openGL_ES_STA2065.dll" $(python3 -I "$HERE/cestub.py" exports "$NAV/os/rom/files/openGL_ES_STA2065.dll")
  for d in $(find "$NAV/flash_shim" -iname '*.exe' -not -path '*/0emu/*' -printf '%h\n' | sort -u); do
    [ -f "$d/openGL_ES_STA2065.dll" ] && cp --remove-destination "$NAV/wolfstub/openGL_ES_STA2065.dll" "$d/"
  done
fi

echo ">> 6c. emulator extras on the disk"
# Shortcuts (CE .lnk = "<len>#<command line>") in a folder that sorts first,
# so everything can be started with the mouse; an empty BrandDevice.reg
# resets the car pairing; the DevMode file is the well-known way to feed a
# VIN without a car (edit the placeholder).
mkdir -p "$NAV/flash_shim/0emu" "$NAV/flash_shim/VwBrandDevice/Settings"
mklnk() { local c="$2"; printf '%d#%s' "${#c}" "$c" > "$NAV/flash_shim/0emu/$1.lnk"; }
mklnk "1 com"      '"\My Flash Disk\VwUserShell\VwCommunicationExe.exe"'
mklnk "2 brand"    '"\My Flash Disk\VwBrandDevice\VwBrandDevice.exe"'
mklnk "3 shell"    '"\My Flash Disk\VwUserShell\VwUserShell.exe" -ShowWindow=1'
mklnk "4 navigon"  '"\My Flash Disk\NAVIGON\navigon.exe"'
mklnk "5 script"   '"\My Flash Disk\MortScript.exe" "\My Flash Disk\emu_start.mscr"'
mklnk "6 tc"       '"\My Flash Disk\Apps\TotalCommander\tc.exe"'
mklnk "7 watchdog" '"\My Flash Disk\WatchdogPuppy.exe" Watchdog_HW.ini'
mklnk "t1 load MAPBL" '"\My Flash Disk\0emu\loadtest.exe" "\My Flash Disk\BT\MAPBL.dll"'
mklnk "t2 load SyncBL" '"\My Flash Disk\0emu\loadtest.exe" "\My Flash Disk\BT\SyncBL.dll"'
mklnk "t3 load GLES"   '"\My Flash Disk\0emu\loadtest.exe" "\My Flash Disk\NAVIGON\openGL_ES_STA2065.dll"'
mklnk "t4 load ddraw"  '"\My Flash Disk\0emu\loadtest.exe" ddraw.dll'
cp "$HERE"/guest-tools/bin/*.exe "$NAV/flash_shim/0emu/"
# programs built with the Devkit (CeGCC) go to \My Flash Disk\dev; the
# deploy agent has the first shortcut in 0emu (always created, so the icon
# positions the docs quote do not move: agent 38,75 / launch-all 263,143)
mkdir -p "$NAV/flash_shim/dev"
ls "$HERE"/../Devkit/bin/*.exe >/dev/null 2>&1 && cp "$HERE"/../Devkit/bin/*.exe "$HERE"/../Devkit/bin/*.dll "$NAV/flash_shim/dev/"
mklnk "0 agent COM1" '"\My Flash Disk\dev\ceagent.exe" COM1:'
: > "$NAV/flash_shim/BrandDevice.reg"
# GPS: the device's receiver is on COM2:; the image has exactly one pl011
# serial port, COM1: = QEMU's second UART, which run-emulator.sh exposes on
# 127.0.0.1:5555 for tools/nmea.py. (The car's BAP link, COM9: on the
# device, stays unconnected.) Without a fix Navigon resets the device after
# NoGpsCheckTime seconds, so that is raised to a day. flash_shim is
# hard-linked to flash, so files are replaced, never edited in place.
us="$NAV/flash_shim/NAVIGON/Settings/UserSettings.default"
# Navigon's "old" map drawer is its eGML software renderer; the default GL ES
# one needs the Cartesio accelerator and crashes without it. OLD_MAP_DRAWER=0
# keeps the device setting (for working on GL ES emulation).
sed -e 's|<GPSPort>2</GPSPort>|<GPSPort>1</GPSPort>|' -e "s|<OldMapDrawer>0</OldMapDrawer>|<OldMapDrawer>${OLD_MAP_DRAWER:-1}</OldMapDrawer>|" "$NAV/flash/NAVIGON/Settings/UserSettings.default" > "$us.new" && mv -f "$us.new" "$us"
as="$NAV/flash_shim/NAVIGON/Settings/ApplicationSettings.xml"
sed 's|<NoGpsCheckTime>300</NoGpsCheckTime>|<NoGpsCheckTime>86400</NoGpsCheckTime>|' "$NAV/flash/NAVIGON/Settings/ApplicationSettings.xml" > "$as.new" && mv -f "$as.new" "$as"
# SplashAnimation.exe needs sgalib.dll (the Cartesio graphics accelerator);
# the brand app starts it after pairing and it only produces an error box here.
[ -f "$NAV/flash_shim/SplashAnimation.exe" ] && mv "$NAV/flash_shim/SplashAnimation.exe" "$NAV/flash_shim/SplashAnimation.exe.off"
[ -f "$NAV/flash_shim/VwBrandDevice/Settings/UserSettingsDevMode.default" ] || cat > "$NAV/flash_shim/VwBrandDevice/Settings/UserSettingsDevMode.default" <<'XML'
<?xml version="1.0" encoding="ISO-8859-1"?>
<Settings>
	<Active>1</Active>
	<VehicleIdentificationNumber>WVWZZZAAZFD000000</VehicleIdentificationNumber>
</Settings>
XML

echo ">> 7. disk image"
if [ ! -f "$WORK/navigon-disk.img" ]; then
  rm -rf "$NAV/stage"; mkdir -p "$NAV/stage"
  cp -al "$NAV"/flash_shim/* "$NAV/stage/"
  cp -al "$NAV/os/rom" "$NAV/stage/rom"
  cp -r "$HERE/../Apps/." "$NAV/stage/Apps/"
  python3 -I "$HERE/mkdisk.py" "$WORK/navigon-disk.img.part" "$DISK_MB" "$NAV"/stage/* | tail -2
  mv "$WORK/navigon-disk.img.part" "$WORK/navigon-disk.img"
fi
# qcow2 overlay on top of the raw disk: the guest's writes and VM snapshots
# (start-vw.sh --save) go there, the raw image stays as built. Recreated
# whenever the raw image is newer.
if command -v qemu-img >/dev/null && { [ ! -f "$WORK/navigon-disk.qcow2" ] || [ "$WORK/navigon-disk.img" -nt "$WORK/navigon-disk.qcow2" ]; }; then
  rm -f "$WORK/navigon-disk.qcow2"
  qemu-img create -q -f qcow2 -b "$WORK/navigon-disk.img" -F raw "$WORK/navigon-disk.qcow2"
  echo "overlay: $WORK/navigon-disk.qcow2"
fi

echo "done. Boot with: $HERE/run-emulator.sh --navigon"

exit 0
# Export list for HWL_STUB=1 (read by the sed above; keep the markers).
HWL_STUB_EXPORTS=
'?Connect@HardwareLayer@@YAXPAVIHWLPowerButtonListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLPowerButtonListener@1@@Z'
'?Connect@HardwareLayer@@YAXPAVIHWLCardListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLCardListener@1@@Z'
'?Connect@HardwareLayer@@YAXPAVIHWLCradleListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLCradleListener@1@@Z'
'?Connect@HardwareLayer@@YAXPAVIHWLUSBListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLUSBListener@1@@Z'
'?Connect@HardwareLayer@@YAXPAVIHWLPowerListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLPowerListener@1@@Z'
'?Connect@HardwareLayer@@YAXPAVIHWLSuspendResumeDeviceListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLSuspendResumeDeviceListener@1@@Z'
'?Connect@HardwareLayer@@YAXPAVIHWLProximityListener@1@@Z' '?Disconnect@HardwareLayer@@YAXPAVIHWLProximityListener@1@@Z'
'?GetBrightness@HardwareLayer@@YA_NAAE@Z=1' '?SetBrightness@HardwareLayer@@YA_NABM@Z=1' '?GetPowerInfo@HardwareLayer@@YA_NAAUCHWLPowerInfo@1@@Z=1'
'?GetDriveFromPath@HardwareLayer@@YA_NPB_WPA_WK@Z=0' '?ShutdownDevice@HardwareLayer@@YA_NXZ=1' '?ResetDevice@HardwareLayer@@YA_NXZ=1' '?SuspendDevice@HardwareLayer@@YA_NXZ=1'
'?GetDeviceID@HardwareLayer@@YA_NPA_WI@Z=wstr:EMU0000001' '?GetBtMACAddr@HardwareLayer@@YA_NPA_WH@Z=wstr:00:11:22:33:44:55'
'?CalibrateTouchscreen@HardwareLayer@@YA_NXZ=1' '?EnableAutoSwitchOn@HardwareLayer@@YA_NAB_N@Z=1' '?IsNavigonChargerConnected@HardwareLayer@@YA_NXZ=1'
'?ReadFlash@HardwareLayer@@YA_NKPAEK@Z=blob_obl:hidden_flash.bin' '?WriteFlash@HardwareLayer@@YA_NKPBEK@Z=1'
'?ActivateMic@HardwareLayer@@YA_NAB_N@Z=1' '?SetMicVolume@HardwareLayer@@YA_NABI@Z=1' '?GetMicVolume@HardwareLayer@@YA_NAAI@Z=1'
'?SetMuteDeviceSpeakers@HardwareLayer@@YA_NAB_N@Z=1' '?GetMuteDeviceSpeakers@HardwareLayer@@YA_NAA_N@Z=1'
'?SetCradleDetectAutomaticSwitchOffInternalSpeakers@HardwareLayer@@YA_NAB_N@Z=1' '?GetCradleDetectAutomaticSwitchOffInternalSpeakers@HardwareLayer@@YA_NAA_N@Z=1'
'?IsCradleStatusConnected@HardwareLayer@@YA_NXZ=0' '?ChangeStartupScreen@HardwareLayer@@YA_NPB_W@Z=1'
'?DismountPartition@HardwareLayer@@YA_NPB_W0@Z=1' '?MountPartition@HardwareLayer@@YA_NPB_W0@Z=1' '?GetCeVersion@HardwareLayer@@YA_NPA_W@Z=wstr:7.0'
'?GetBTVersion@HardwareLayer@@YA_NAAV?$StringProxy@VNgStringImpl@String@@@String@@@Z=0'
'?GetHWVersion@HardwareLayer@@YA_NKAAV?$StringProxy@VNgStringImpl@String@@@String@@@Z=0'
'?SetProximitySensorState@HardwareLayer@@YA_NAB_N@Z=1' '?SetProximitySensorSensitivity@HardwareLayer@@YA_NABH0@Z=1'
'?SetProximitySensorRate@HardwareLayer@@YA_NABI@Z=1' '?SetProximitySensorCombo@HardwareLayer@@YA_NABI@Z=1'
'?GetStorageCardId@HardwareLayer@@YA_NPB_WPA_WABI@Z=0' '?IsUSBPowerConnected@HardwareLayer@@YA_NXZ=0' '?ResetToFactorySettings@HardwareLayer@@YA_NXZ=1'
HWL_STUB_END
