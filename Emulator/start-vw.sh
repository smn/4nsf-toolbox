#!/usr/bin/env bash
# One command to a running VW environment with the deploy agent up.
#
#   Emulator/start-vw.sh                boot headless, start launch-all, wait for the agent
#   Emulator/start-vw.sh --save vw      ...then save a VM snapshot named "vw"
#   Emulator/start-vw.sh --resume vw    resume that snapshot instead of booting (a few seconds)
#   Emulator/start-vw.sh --gps          also run tools/nmea.py on COM1:
#
# Afterwards: Devkit/deploy.py talks to the agent (COM2: = 127.0.0.1:5556),
# VNC is on 127.0.0.1:5901, the kernel log is work/serial.log. Snapshots live
# in work/navigon-disk.qcow2 and are invalidated by build-navigon.sh when the
# raw disk is rebuilt. Needs the venv/pip packages vncdotool and pillow for
# the mouse automation (PYTHON=/path/to/python to pick an interpreter).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="${WORK:-$HERE/work}"
PY="${PYTHON:-python3}"
save="" resume="" gps=0
while [ $# -gt 0 ]; do
  case "$1" in
    --save) save="$2"; shift ;;
    --resume) resume="$2"; shift ;;
    --gps) gps=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

monitor() {  # send one QEMU monitor command, print the reply
  "$PY" - "$WORK/mon.sock" "$1" <<'EOF'
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.settimeout(60)
def until(tok):
    buf = b""
    while tok not in buf:
        buf += s.recv(4096)
    return buf
until(b"(qemu)")
s.sendall((sys.argv[2] + "\n").encode())
out = until(b"(qemu)").decode(errors="replace")
print("\n".join(l for l in out.splitlines()[1:] if not l.startswith("(qemu)")))
EOF
}

if pgrep -f "qemu-system-arm.*navigon-disk" >/dev/null; then
  echo ">> a navigon VM is already running (pkill -f qemu-system-arm to stop it)"; exit 1
fi
rm -f "$WORK/serial.log"
if [ -n "$resume" ]; then
  echo ">> resuming snapshot '$resume'"
  nohup "$HERE/run-emulator.sh" --navigon --headless --loadvm "$resume" > "$WORK/qemu.out" 2>&1 &
  sleep 4
else
  echo ">> booting (about 90 s)"
  nohup "$HERE/run-emulator.sh" --navigon --headless > "$WORK/qemu.out" 2>&1 &
  for i in $(seq 1 30); do
    sleep 10
    if "$PY" "$HERE/tools/vnc.py" 0emu >/dev/null 2>&1; then break; fi
    [ "$i" = 30 ] && { echo "the Explorer window did not come up; see $WORK/qemu.out and $WORK/serial.log" >&2; exit 1; }
  done
  echo ">> launch-all (ports, agent, VwCommunicationExe, VwBrandDevice, VwUserShell)"
  "$PY" "$HERE/tools/vnc.py" dbl 263 143 2 >/dev/null
  for i in $(seq 1 30); do
    sleep 5
    grep -a -q "CEAGENT: starting on COM2" "$WORK/serial.log" 2>/dev/null && break
  done
  # launch-all logs the window list every 10 s; wait for the shell's window
  for i in $(seq 1 24); do
    sleep 5
    grep -a -q "class='VwUserShell' title='VwUserShell' vis=1" "$WORK/serial.log" 2>/dev/null && break
  done
  sleep 15
fi
if [ "$gps" = 1 ]; then
  nohup "$PY" -u "$HERE/tools/nmea.py" --speed 30 --heading 45 > "$WORK/nmea.out" 2>&1 &
  echo ">> GPS feeder running (work/nmea.out)"
fi
if "$PY" "$HERE/../Devkit/deploy.py" --timeout 10 ping >/dev/null 2>&1; then
  echo ">> agent answers on 127.0.0.1:5556"
else
  echo ">> agent not answering yet on 5556 (Devkit built? see work/serial.log)"
fi
if [ -n "$save" ]; then
  echo ">> saving snapshot '$save'"
  monitor "savevm $save"
  monitor "info snapshots" | tail -n +1
fi
echo ">> ready: VNC 127.0.0.1:5901, log $WORK/serial.log"
