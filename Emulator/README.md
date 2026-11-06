# Emulating the 4NSF (Windows CE) in QEMU

This folder boots a Windows Embedded Compact 7 ARM virtual machine in QEMU
and can load the complete VW "maps + more" software (Navigon 7.16.9, OS
2.33) into it from Volkswagen's own update package. Nothing from the device
or the package is committed to git; the scripts rebuild everything into
`Emulator/work/`.

![Total Commander/CE from this repo running inside QEMU](screenshot-totalcommander-in-qemu.png)

## What the real device is

| Item | Value |
|---|---|
| Device | Garmin 4NSF / Navigon 70 series / VW, Seat, Skoda PID ("maps + more") |
| SoC | STMicroelectronics Cartesio+ STA2064 (ARM1176 core, integrated GPS) |
| RAM / flash | 128 MB / 4 GB |
| OS | Windows CE 6.0, OS image version 2.33, Navigon MobileNavigator 7.16.9 build 314 |
| App binaries | PE32 for Windows CE, ARM Thumb, subsystem 9 |

QEMU has no machine model for the STA2064, so the device's own `NK.nb0`
(kernel plus Cartesio drivers for display, NAND, GPS, CAN, USB) cannot be
booted as-is. The approach here is the other way round: run a generic
Compact 7 image on QEMU's `vexpress-a15` board and move the device's
user-mode software onto it.

## Quick start

Requirements (Debian/Ubuntu): `apt install qemu-system-arm curl unzip dosfstools mtools python3`.
No root is needed anywhere.

```sh
Emulator/run-emulator.sh                 # generic CE 7 VM, Apps/ attached as a disk
Emulator/run-emulator.sh --headless      # same, VNC on 127.0.0.1:5901

Emulator/build-navigon.sh                # ~1 min after the 3.5 GB download
Emulator/run-emulator.sh --navigon       # VM with the whole \My Flash Disk tree
```

`run-emulator.sh` downloads the prebuilt Compact 7 image from
[Milek7/wince-qemu](https://github.com/Milek7/wince-qemu) (SHA-256 checked),
builds a FAT32 disk and starts QEMU. The disk shows up in the guest as
`\Mounted Volume` (generic mode) or `\My Flash Disk` (`--navigon`). Boot takes
about a minute. Kernel debug output goes to `work/serial.log`; in headless
mode a QEMU monitor socket is at `work/mon.sock`.

To start a program in the guest use **Start > Run...** with a quoted path:

```
"\Mounted Volume\Apps\TotalCommander\tc.exe"
"\My Flash Disk\MortScript.exe" "\My Flash Disk\emu_start.mscr"
```

## Where the Navigon software comes from

Volkswagen still hosts the Garmin-labelled PID update at
`https://navigation-maps.volkswagen.com/vw-maps/Central_Europe.zip`
(3.5 GB, May 2022; other regions come through the myVolkswagen portal with
an Up! VIN). `build-navigon.sh` downloads it and verifies the package's own
MD5 list. It contains:

| File | What it is |
|---|---|
| `Install_OS.exe` | ExtractorCE self-extractor with the OS: `NK.nb0` (25 MB Windows CE ROM), `ApLoader.bin`, `xL_CPlus.bin`, `Meminit.bin`, `LPHandle.bin`, boot `config.txt`, splash screens |
| `UpdateMeContent.content` | Same container, 769 files: the `\My Flash Disk` tree (VwUserShell, VwBrandDevice, NAVIGON, BT, MediaPlayer, PictureViewer, Apps, watchdog configs, maps) |
| `Install_BT.exe`, `FullInstaller.exe`, `autorunce.mscr` | Bluetooth firmware and the SD-card installer chain |

The install guide says the package is only for units with the GARMIN label on
the back. The emulator never flashes anything, it only unpacks files.

## Tools in this folder

| Script | Purpose |
|---|---|
| `sfx_extract.py` | Unpacks the ExtractorCE `!NAVIGON_SFX!` archives (format documented in the file) with per-file MD5 check |
| `ceromdump.py` | Dumps a Windows CE ROM image: rebuilds every XIP module as a loadable PE file, copies the ROM files, flags compressed ones |
| `celzx.py` | Decompresses ROM-compressed files (24-bit block table, 4 KB LZX blocks); verified byte-exact against a copy of the same DLL on the flash disk |
| `patch_image.py` | Renames the Compact 7 image's disk mount from `Mounted Volume` to `My Flash Disk` |
| `cestub.py` | `make-stub` builds an ARM CE DLL of stub exports with chosen return values without a toolchain; `patch` rewrites a PE's import table so symbols the target image lacks come from the stub |
| `mkdisk.py` | MBR + FAT32 disk image from folders, using mtools |
| `emu_start.mscr` | MortScript for the guest: registry setup from the device's `autorunce.mscr`, then the application chain from `Watchdog_HW.ini`. MortScript itself runs in the VM, but this script has not yet been seen to start the chain; the three Run commands below are the verified route |

`cestub.py patch` found only 16 coredll functions (RAS and TAPI used by
`BTCore.exe` and `navigon.exe`, `GetSystemPowerStatusEx` used by every
hardware-layer DLL) and one DLL (`svoxdll.dll`) that the Compact 7 image lacks.
The device ROM's own DLLs that the apps load at run time (`WolfSpecial.dll`,
`nfVR.dll`, `openGL_ES_STA2065.dll`, MFC 9.0, fonts) are copied next to each
executable.

## How far it runs

Verified in this repository's history, screenshots in this folder:

- Generic mode: Windows CE desktop, disk mounts, Total Commander/CE from `Apps` runs.
- Navigon mode: the disk mounts as `\My Flash Disk`
  (`screenshot-my-flash-disk.png`). Started one after the other from
  **Start > Run...**:

  ```
  "\My Flash Disk\VwUserShell\VwCommunicationExe.exe"
  "\My Flash Disk\VwBrandDevice\VwBrandDevice.exe"
  "\My Flash Disk\VwUserShell\VwUserShell.exe" -ShowWindow=1
  ```

  all three start and keep running, appear in the taskbar, and load
  `WolfSpecial.dll` and the hardware layer. MortScript runs in the guest too.
- Not yet: the VW shell never paints its window. The serial log shows the
  hardware layer failing on the OEM stream drivers it opens through
  `WolfSpecial.dll`: `GMD1:` (GarminDrv), `HFC1:` (hidden flash, where the
  device ID, VIN and brand live), `WDT1:` (watchdog), `BKL1:` (backlight). The
  shell loops on `CHWLWolf::ReadFlash` and does not get to its UI. A
  `WolfSpecial.dll` built with `cestub.py make-stub ... ReadHiddenFlash=1 ...`
  (every function reporting success) is not enough on its own.

## Next steps for a working UI

1. **Hidden flash contents.** Dump the real unit's hidden flash through the
   device's `WolfSpecial.dll` `ReadHiddenFlash` (or Total Commander on the
   device reading `HFC1:`) and serve it from a stub `HFC1:` stream driver or a
   stub `WolfSpecial.dll` that copies it into the caller's buffer. This is the
   device-specific data the apps key on (brand, VIN pairing, serial).
2. **Stub drivers.** `GMD1:`, `WDT1:` and `BKL1:` only need Init/Open/IOControl
   entry points that return success; `cestub.py make-stub` can build the DLL,
   the registry entries under `HKLM\Drivers\BuiltIn` can be set from
   `emu_start.mscr`, and `ActivateDevice` loads them.
3. **Display.** The apps draw with plain GDI (`CreateDIBSection` + `BitBlt`)
   into skins named `R480x272`, so the 1024x600 PL111 is fine once they get
   past the hardware checks. `ChangeDisplaySettingsEx` is called and will fail
   harmlessly.
4. **GPS.** The Compact 7 image maps QEMU's second UART to `COM1:`; feed NMEA
   from `gpsfake` through `-serial` once `navigon.exe` is up.
5. **Map licence.** Navigon maps are keyed to the device serial from the OEM
   layer; expect a licence error until the serial is served by step 1.

## Files that stay out of git

`Emulator/work/` is ignored. It holds the Compact 7 image, the VW package,
its unpacked trees, the ROM dump and the disk images (about 20 GB in total).
