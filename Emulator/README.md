# Emulating the 4NSF (Windows CE) in QEMU

This folder lets you boot a Windows Embedded Compact 7 ARM virtual machine in
QEMU with the toolbox's `Apps` folder attached as a disk, so you can try
Windows CE ARM apps and custom app packages without touching a real device.

![Total Commander/CE from this repo running inside QEMU](screenshot-totalcommander-in-qemu.png)

## What the real device is

| Item | Value |
|---|---|
| Device | Garmin 4NSF / Navigon 70 series / VW, Seat, Skoda PID |
| SoC | STMicroelectronics Cartesio+ STA2064 (ARM1176 core, integrated GPS) |
| RAM / flash | 128 MB / 4 GB |
| OS | Windows CE 6.0 |
| App binaries in this repo | PE32 for Windows CE, ARM Thumb, subsystem 9, OS version 6.0 |

The SoC matters: QEMU has no machine model for the STA2064, so the device's own
OS image (`NK.bin` with the Cartesio board support package and its display,
NAND, GPS, CAN and USB drivers) cannot be booted as-is. There is no
"drop the firmware in and run it" option for this hardware, and the only
existing WinCE-on-QEMU project targets a different (virtual) board.

## What you can emulate today

The [Milek7/wince-qemu](https://github.com/Milek7/wince-qemu) project is a
Windows Embedded Compact 7 board support package for QEMU's `vexpress-a15`
machine, with a prebuilt kernel image on its releases page. Compact 7 runs
Windows CE 6.0 ARM user-mode applications, so it works as a test bench for:

- Windows CE ARM apps such as the Total Commander/CE build in `Apps/TotalCommander` (verified, see screenshot).
- Your own CE 6.0 apps or shortcuts before copying them to the device.
- Inspecting Navigon app packages (`.nfs`, `.kbi`, `NgAppInfo.xml`) on a CE file system.

What it does not give you:

- The Navigon shell, its `AppCom` launcher, the `\My Flash Disk` layout or the
  Navigon DLLs that live in the device's `\Windows`. `VwPaint.exe` starts
  without a missing-DLL error but shows no window, because it expects to be
  launched by the Navigon framework.
- Device hardware: GPS, CAN/vehicle data, the 480x272 touch panel, real NAND.
- Anything that lives in the device's `NK.bin` (drivers, registry, OEM shell).

## Running it

Requirements (Debian/Ubuntu): `apt install qemu-system-arm curl unzip dosfstools mtools python3`.
No root is needed; the disk image is built with mtools.

```sh
Emulator/run-emulator.sh                 # opens a QEMU window (1024x600)
Emulator/run-emulator.sh --headless      # no window: VNC on 127.0.0.1:5901
Emulator/run-emulator.sh --rebuild-disk  # refresh work/disk.img from ../Apps
```

The script:

1. Downloads the prebuilt image (about 11 MB) into `Emulator/work/` and checks its SHA-256.
2. Builds `work/disk.img`, a 256 MB MBR + FAT32 image, and copies `Apps/` into it (`mkdisk.py`).
3. Boots QEMU with the image loaded at `0x80000000` and the CPU started at `0x800010c0`.

Boot takes about a minute. The disk shows up in the guest as `\Mounted Volume`.
To start an app, use **Start > Run...** and type the quoted path, for example:

```
"\Mounted Volume\Apps\TotalCommander\tc.exe"
```

Kernel debug output goes to `work/serial.log`. In headless mode a QEMU
monitor socket is at `work/mon.sock` (`screendump file.ppm` takes a screenshot).

To put other files into the guest, add them to the `Apps` folder and run with
`--rebuild-disk`, or pass extra files to `mkdisk.py` directly:

```sh
python3 Emulator/mkdisk.py Emulator/work/disk.img 256 Apps path/to/my-app
```

## Getting closer to the real device

If the goal is to run the device's own firmware, the options are, in order of effort:

1. **Dump the device's `\Windows` folder** (Explorer app or Total Commander on
   the device, copy to the SD card) and place the Navigon DLLs next to the apps
   on the emulator disk, so more of the Navigon apps start. CE loads DLLs from
   the executable's folder first.
2. **Extract `NK.bin`** from a firmware dump with Windows CE tools (viewbin,
   cvrtbin, dumprom) to get the OEM shell, registry and DLLs as files, then
   try them on the Compact 7 image. Kernel-mode drivers will not run.
3. **Write a QEMU board model for the STA2064.** This is a large project: the
   Cartesio user manual is public, but the display controller, interrupt
   controller, timers, NAND and USB would all need to be modelled before the
   stock `NK.bin` gets past the OEM Abstraction Layer. Nobody has done this.

Microsoft's own Device Emulator (ARMv4i) is another option on a Windows host,
but it also only runs images built for its virtual board, not the device image.
