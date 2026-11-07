# Guest diagnostic tools

Tiny Windows CE ARM programs built without a toolchain: `mkexe.py` assembles
ARM code with keystone and wraps it in a PE with an import table (fixed base
0x10000, which is fine for CE executables). Rebuild with
`pip install keystone-engine` and `python mk<name>.py out.exe`.

They print to the kernel debug output, which `run-emulator.sh` writes to
`work/serial.log`. `build-navigon.sh` copies `bin/*.exe` into the disk's
`0emu` folder so they can be started with a double click in Explorer.

| Program | What it does |
|---|---|
| `socktest.exe` | WINSOCK.dll socket/bind/listen/connect/accept/send/recv on 127.0.0.1 |
| `timertest7.exe` | periodic `timeSetEvent` callbacks from the image's mmtimer.dll |
| `gditest.exe` | popup window + 16 bpp DIB section + BitBlt, the way the Navigon apps draw |
| `wintest.exe` | enumerates every top-level window (class, title, visible, rect) 12 times |
| `stacks.exe` | lists processes, modules and the call stack of every thread (toolhelp + GetThreadCallStack), 6 samples |
| `loadtest.exe PATH` | `LoadLibraryW(PATH)`, then a message box and an `EMULOAD:` serial line with the handle and `GetLastError` (which DLL the loader really rejects) |
| `launch-all.exe` / `launch-brand.exe` / `launch-shell.exe` | start the VW apps with their real command lines, then log windows for two minutes |

Results on the 2022-04-17 Compact 7 image: sockets, timers and GDI blits all
work; the VW apps create their windows and sit idle in their message loops
without ever blitting.
