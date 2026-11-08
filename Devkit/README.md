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
| `drivers/pl011poll/` | `pl011poll.dll`, a polled PL011 UART stream driver (kernel mode, loaded at run time), and `addport.exe`, which registers it as `COM2:`/`COM3:` in the emulator so GPS, the agent and a third channel each get a port |
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

In the emulator: `build-navigon.sh` copies `Devkit/bin/*` to
`\My Flash Disk\dev`, and `launch-all.exe` runs `addport.exe` (adds `COM2:`
and `COM3:`) and the agent on `COM2:` before the VW apps. So:

```sh
Emulator/start-vw.sh --gps                        # boot + launch-all + GPS feed
python3 Devkit/deploy.py ping                     # -> ceagent 1  (COM2: = port 5556)
python3 Devkit/deploy.py push bin/hello.exe "\My Flash Disk\dev2" --run --wait 10
python3 Devkit/deploy.py get "\My Flash Disk\dev2\hello.txt" hello.txt
grep -a -o "EMUHELLO[^P]*" Emulator/work/serial.log
```

Without `launch-all`, the `0 agent COM1` shortcut (first icon in `0emu`)
runs the agent on `COM1:` instead (`deploy.py --port 5555`). The kernel
log shows `ADDPORT: COM2: at 910b0000 -> ok` and `CEAGENT: starting on
COM2:` when the ports came up.

Verified here: `hello.exe` reports "Windows CE 7.0, cpu type 3087, 115 MB
RAM" and writes its file; `hellocpp.exe` sorts, throws and catches, and its
static destructor runs; a 74 KB push takes 1.6 s over the emulated UART.

How the extra ports work: the image's own `pl011.dll` reads a kernel
virtual address (`IoBase`, 0x910a0000 for UART1) and an interrupt from the
registry. `addport.exe` creates `HKLM\Drivers\BuiltIn\PL011POLLn` keys
with `IoBase` + n*0x10000, copies `pl011poll.dll` into `\Windows` (device
manager loads kernel-mode drivers by name from there) and calls
`ActivateDeviceEx`. The driver polls the receive FIFO from a thread, so no
interrupt mapping is needed; it implements the serial IOCTLs that
`SetCommState`, `SetCommTimeouts`, `WaitCommEvent` and friends use. The
registry is not persisted in this image, hence once per boot.

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
