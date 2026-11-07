#!/usr/bin/env python3
"""Host side of ceagent: copy files to and from a Windows CE device or the
emulator, list directories and run programs.

The agent speaks over a serial port or TCP. In the emulator its COM1: is
QEMU's second UART, exposed by run-emulator.sh on 127.0.0.1:5555, so the
default target is that socket. On a real device use a USB-serial adapter on
the debug UART (--serial /dev/ttyUSB0) or, once networking exists, --host.

  deploy.py ping
  deploy.py put  hello.exe  "\\My Flash Disk\\0emu\\hello.exe"
  deploy.py get  "\\My Flash Disk\\log.txt" log.txt
  deploy.py ls   "\\My Flash Disk\\0emu"
  deploy.py rm   "\\My Flash Disk\\0emu\\hello.exe"
  deploy.py mkdir "\\My Flash Disk\\dev"
  deploy.py run  "\\My Flash Disk\\0emu\\hello.exe" [--wait SECONDS] [-- args...]
  deploy.py push hello.exe "\\My Flash Disk\\dev" --run     # put + run in one go

Protocol: frames of u32 magic 'CEA1', u8 cmd/status, u32 len, payload
(see agent/ceagent.c). Needs pyserial only for --serial.
"""
import argparse
import os
import socket
import struct
import sys
import time

MAGIC = 0x31414543
PING, PUT, CHUNK, CLOSE, GET, RUN, LIST, DEL, MKDIR, REBOOT = range(1, 11)
CHUNK_SIZE = 16384


class Link:
    def __init__(self, a):
        if a.serial:
            import serial  # pyserial
            self.port = serial.Serial(a.serial, a.baud, timeout=a.timeout)
            self._read, self._write = self.port.read, self.port.write
        else:
            self.sock = socket.create_connection((a.host, a.port), timeout=a.timeout)
            self._read, self._write = self.sock.recv, self.sock.sendall

    def read_exact(self, n):
        buf = b""
        while len(buf) < n:
            part = self._read(n - len(buf))
            if not part:
                raise IOError("link closed")
            buf += part
        return buf

    def send(self, cmd, payload=b""):
        self._write(struct.pack("<IBI", MAGIC, cmd, len(payload)) + payload)

    def recv(self):
        # resynchronise on the magic (the serial line may carry old bytes)
        hdr = b""
        while True:
            hdr += self.read_exact(1)
            if hdr[-1:] != b"C":
                hdr = b""
                continue
            hdr += self.read_exact(8)
            magic, status, length = struct.unpack("<IBI", hdr)
            if magic == MAGIC:
                break
            hdr = b""
        return status, self.read_exact(length)

    def call(self, cmd, payload=b""):
        self.send(cmd, payload)
        status, data = self.recv()
        if status:
            raise RuntimeError(f"agent error {status} (Win32 code) for command {cmd}")
        return data


def wstr(s):
    return s.encode("utf-16le") + b"\0\0"


def put(link, local, remote):
    data = open(local, "rb").read()
    link.call(PUT, wstr(remote) + struct.pack("<I", len(data)))
    t0 = time.time()
    for off in range(0, len(data), CHUNK_SIZE):
        link.call(CHUNK, data[off:off + CHUNK_SIZE])
        sys.stdout.write(f"\r{remote}: {min(off + CHUNK_SIZE, len(data))}/{len(data)} bytes")
        sys.stdout.flush()
    link.call(CLOSE)
    dt = time.time() - t0
    print(f"\r{remote}: {len(data)} bytes in {dt:.1f}s" + " " * 20)


def get(link, remote, local):
    size, = struct.unpack("<I", link.call(GET, wstr(remote)))
    out = b""
    while True:
        status, data = link.recv()
        if status == CLOSE:
            break
        if status != CHUNK:
            raise RuntimeError(f"unexpected frame {status} during GET")
        out += data
    open(local, "wb").write(out)
    print(f"{local}: {len(out)} bytes (agent said {size})")


def run(link, cmdline, wait_s):
    data = link.call(RUN, struct.pack("<I", int(wait_s * 1000)) + wstr(cmdline))
    pid, code = struct.unpack("<II", data)
    if code == 0xFFFFFFFF:
        print(f"started pid {pid:#x}" + (" (still running)" if wait_s else ""))
        return 0
    print(f"pid {pid:#x} exited with {code}")
    return code


def remote_join(folder, name):
    return folder.rstrip("\\") + "\\" + os.path.basename(name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--serial", help="serial device instead of TCP, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=30)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    p = sub.add_parser("put"); p.add_argument("local"); p.add_argument("remote")
    p = sub.add_parser("get"); p.add_argument("remote"); p.add_argument("local")
    p = sub.add_parser("ls"); p.add_argument("remote")
    p = sub.add_parser("rm"); p.add_argument("remote")
    p = sub.add_parser("mkdir"); p.add_argument("remote")
    p = sub.add_parser("run"); p.add_argument("exe"); p.add_argument("--wait", type=float, default=0); p.add_argument("args", nargs="*")
    p = sub.add_parser("push"); p.add_argument("local", nargs="+"); p.add_argument("folder"); p.add_argument("--run", action="store_true"); p.add_argument("--wait", type=float, default=0)
    sub.add_parser("reboot")
    a = ap.parse_args()

    link = Link(a)
    if a.cmd == "ping":
        print(link.call(PING).decode("utf-16le").rstrip("\0"))
    elif a.cmd == "put":
        put(link, a.local, a.remote)
    elif a.cmd == "get":
        get(link, a.remote, a.local)
    elif a.cmd == "ls":
        text = link.call(LIST, wstr(a.remote)).decode("utf-16le")
        for line in text.splitlines():
            name, size, attrs = line.split("\t")
            kind = "<DIR>" if int(attrs, 16) & 0x10 else size
            print(f"{kind:>10}  {name}")
    elif a.cmd == "rm":
        link.call(DEL, wstr(a.remote)); print("deleted")
    elif a.cmd == "mkdir":
        link.call(MKDIR, wstr(a.remote)); print("created")
    elif a.cmd == "run":
        cmdline = f'"{a.exe}"' + (" " + " ".join(a.args) if a.args else "")
        sys.exit(run(link, cmdline, a.wait))
    elif a.cmd == "push":
        try:
            link.call(MKDIR, wstr(a.folder))
        except RuntimeError:
            pass
        for f in a.local:
            put(link, f, remote_join(a.folder, f))
        if a.run:
            sys.exit(run(link, f'"{remote_join(a.folder, a.local[0])}"', a.wait))
    elif a.cmd == "reboot":
        link.call(REBOOT); print("agent stopped")


if __name__ == "__main__":
    main()
