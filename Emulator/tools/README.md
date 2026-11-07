# Emulator tools

Host-side helpers used to get the VW software running; none of them is
needed just to boot the VM.

| Tool | Purpose |
|---|---|
| `vnc.py` | Mouse-drives the headless VM over VNC: `vnc.py 0emu dbl 188 143 40 shot menu` opens the `0emu` folder, double-clicks `launch-all.exe` and saves `menu.png`. Keyboard input through VNC doubles characters in this guest, so everything is clicks plus screenshot checks (`ref/*.png` are the Explorer address-bar crops it compares against). `pip install vncdotool pillow`. |
| `trace.gdb.py` | Windows CE API tracer on QEMU's gdbstub. It puts breakpoints on coredll exports (addresses from `coredll_exports.txt`, the export table of the image's coredll.dll) and on mmtimer, decodes the interesting arguments (file names, window classes, event names, timer ids) and logs one line per call with the caller's `lr`. See `trace.sh`. |
| `trace.sh` | Starts the tracer against the VM from `run-emulator.sh --headless` (gdb on 127.0.0.1:1234). Attach it after the clicks that need exact timing: breakpoints slow the guest down. |
| `disas.py` | Small capstone/pefile front end for the ARM CE binaries: `xref` (who references a wide string), `dis ADDR LEN [arm]`, `func ADDR` (whole function via `.pdata`), `imports`, `exports`. Resolves literal pools to strings and import names. |
| `callers.py` | Builds a call graph of one binary once (cached as `*.calls.json`) and answers `callers ADDR` and `import NAME` (every call site of an imported function, through its thunk). This is how the hidden-flash layout and the shell's timer bug were found. |

Example session that found why `VwUserShell.exe` died:

```sh
Emulator/run-emulator.sh --navigon --headless &
sleep 90; Emulator/tools/vnc.py 0emu dbl 38 75 5     # start VwCommunicationExe
Emulator/tools/vnc.py dbl 113 75 20                  # VwBrandDevice (exits when paired)
Emulator/tools/trace.sh work/shell.log &             # attach the tracer
Emulator/tools/vnc.py dbl 188 75 60 shot shell       # VwUserShell -ShowWindow=1
grep -n timeKillEvent work/shell.log                  # id=4978548 from lr=0x17d9b0
Emulator/tools/callers.py work/navigon/flash/VwUserShell/VwUserShell.exe import timeKillEvent
Emulator/tools/disas.py work/navigon/flash/VwUserShell/VwUserShell.exe func 0x17d9e8
```
