# Devkit: building your own software for the 4NSF

Everything needed to compile, deploy and run C/C++ programs for the device
(Windows CE 6.0, ARM1176) and for the [emulator](../Emulator/README.md)
(Windows Embedded Compact 7 on QEMU).

| Piece | What it is |
|---|---|
| `cegcc.sh` | Runs the CeGCC cross-compiler (`arm-mingw32ce-gcc`, `g++`, binutils, gdb) from a Docker image, or natively with `CEGCC=/path/to/toolchain` |
| `Makefile` | Builds the samples and the agent into `bin/` with the right flags |
| `samples/hello/` | `hello.c` (plain Win32 CE) and `hellocpp.cpp` (libstdc++, exceptions) |
| `agent/ceagent.c` | In-guest deploy agent: file transfer, directory listing and process start over a serial port or TCP |
| `deploy.py` | Host side of the agent: `put`, `get`, `ls`, `rm`, `mkdir`, `run`, `push --run` |

## Toolchain

The target triple is `arm-mingw32ce`: GCC configured for Windows CE on ARM,
linking against `coredll.dll` like every binary on the device. Two
maintained builds exist as Docker images; both were pulled and checked here:

- `ghcr.io/enlyze/windows-ce-build-environment-arm:latest`: GCC 9.3.0 and
  binutils 2.34 (ENLYZE's [cegcc-build](https://github.com/enlyze/cegcc-build),
  2024). 1.75 GB. The default in `cegcc.sh`.
- `ghcr.io/palian-tech/cegcc:v16.2.0-ce.4`: GCC 16.2 with win32 threads
  (`std::thread`), C++20 libstdc++ and `arm-mingw32ce-gdb`
  ([palian-tech/cegcc-build](https://github.com/palian-tech/cegcc-build),
  2026). 5.4 GB. Select with `CEGCC_IMAGE=...`.

Docker Hub (`paliantech/cegcc`) also carries the second one but rate-limits
anonymous pulls. Without Docker, copy `/opt/cegcc-arm` out of the ENLYZE
image (`docker create` + `docker cp`) or build from source with the
`build_cf.sh` script in either repository; expect an hour or more.

Facts about the generated code that matter on this device:

- Machine type ARM (0x1C0), subsystem 9 (`WINDOWS_CE_GUI`), entry
  `WinMainCRTStartup` which calls your `WinMain` or `main`. The device's own
  binaries are Thumb (0x1C2); the CE loader accepts both.
- Code is ARMv4 (`-marm -msoft-float`), so it runs on the ARM1176 and on
  the emulator's Cortex-A15. Do not pass `-mthumb`: ARMv4T Thumb interworks
  badly with the CE 6 kernel's assumptions, and Thumb-2 does not exist on
  ARM11 (which also rules out LLVM's `arm-windows` target, machine 0x1C4).
- `wchar_t` is 16 bits, `UNICODE`/`_UNICODE` are the norm, and the API is
  Unicode-only. `_WIN32_WCE` is not predefined: pass `-D_WIN32_WCE=0x600`.
- Link with `-static`: there is no `libgcc`/`libstdc++` DLL on the device.
  C++ exceptions are SJLJ and do not cross DLL boundaries.
- No console on the device. Print with `OutputDebugStringW` (the kernel's
  debug UART, `work/serial.log` in the emulator) or write a file.
- MFC 8/9 and `MSVCR80.DLL` ship in Navigon's folders if you ever need them,
  but CeGCC code does not.
- With GCC 9.3 use `-std=gnu++17`, not `-std=c++17`: strict ANSI mode hides
  `atoll` from mingw's `stdlib.h` and `<cstdlib>` then fails to compile.
- `logf` is a math.h builtin; do not name your own functions after it.

## Build

```sh
cd Devkit
make                          # bin/hello.exe bin/hellocpp.exe bin/ceagent.exe
CEGCC=/opt/cegcc-arm make     # with a native toolchain
```

## Deploy and run

In the emulator: `build-navigon.sh` copies `Devkit/bin/*.exe` to
`\My Flash Disk\dev` and the `0emu` folder has a `0 agent COM1` shortcut as
its first icon. Double-click it once per boot (or with `tools/vnc.py`), then
everything is remote:

```sh
Emulator/run-emulator.sh --navigon --headless &
sleep 85; Emulator/tools/vnc.py 0emu dbl 38 75 3  # start "0 agent COM1"
python3 Devkit/deploy.py ping                     # -> ceagent 1
python3 Devkit/deploy.py push bin/hello.exe "\My Flash Disk\dev2" --run --wait 10
python3 Devkit/deploy.py get "\My Flash Disk\dev2\hello.txt" hello.txt
grep -a -o "EMUHELLO[^P]*" Emulator/work/serial.log
```

Verified here: `hello.exe` reports "Windows CE 7.0, cpu type 3087, 115 MB
RAM" and writes its file; `hellocpp.exe` sorts, throws and catches, and its
static destructor runs; a 74 KB push takes 1.6 s over the emulated UART.

The agent uses `COM1:`, which run-emulator.sh exposes on `127.0.0.1:5555`.
That is the same UART the GPS feeder (`tools/nmea.py`) uses, so pick one per
session until the image gets a second serial port (the vexpress board has
four, the Compact 7 image registers one `pl011`).

On the device: copy the files over USB mass storage, start them from
`autorunce.mscr` or a `.lnk`, and run the agent on the debug UART with a
USB-serial adapter (`deploy.py --serial /dev/ttyUSB0`). The protocol is
transport-agnostic, so a Bluetooth SPP channel can carry it later.

## Where to go from here

The emulator README lists the device-side interfaces an app will want:
AppCom (how the VW shell launches and talks to apps), the vehicle-data
shared memory written by `VwCommunicationExe`, `HWLHardwareLayer.dll` for
brightness/power/cradle, and the Bluetooth stack behind `BTCore.exe`. Small
wrapper libraries for those, built with this toolchain and tested in the
emulator, are the next layer.
