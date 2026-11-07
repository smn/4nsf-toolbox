#!/usr/bin/env python3
r"""Drive the headless VM over VNC (127.0.0.1:5901) with the mouse.

Typing into the guest doubles characters (both VNC and the QEMU monitor), so
everything is mouse-driven and verified with screenshots.

  vnc.py 0emu                       open \My Flash Disk\0emu in the Explorer window
  vnc.py dbl X Y WAIT               double-click, then wait WAIT seconds
  vnc.py click X Y WAIT             single click
  vnc.py shot NAME                  save NAME.png in $OUT (default: cwd)
  vnc.py sleep SECONDS
  vnc.py 0emu dbl 188 143 40 shot menu   (actions chain; 188,143 is launch-all.exe)

Needs: pip install vncdotool pillow
"""
import os
import sys
import time

from PIL import Image, ImageChops
from vncdotool import api

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("OUT", ".")
c = api.connect(os.environ.get("VNC", "127.0.0.1::5901"))
BAR = (60, 30, 300, 46)  # Explorer address bar at 480x272
REFS = {k: Image.open(f"{HERE}/ref/{k}.png").convert("RGB") for k in ("mydevice", "flash", "emu")}


def shot(name):
    path = f"{OUT}/{name}.png"
    c.captureScreen(path)
    return Image.open(path)


def dbl(x, y, wait):
    c.mouseMove(x, y); c.mousePress(1); time.sleep(0.12); c.mousePress(1); time.sleep(wait)


def state(img):
    for k, r in REFS.items():
        if ImageChops.difference(img.crop(BAR).convert("RGB"), r).getbbox() is None:
            return k
    return None


def open_0emu():
    # My Device (37,25) -> My Flash Disk (188,75) -> 0emu (38,75)
    plan = [("mydevice", (37, 25)), ("flash", (188, 75)), ("emu", (38, 75))]
    cur = state(shot("_nav"))
    for want, (x, y) in plan:
        if cur == want or (want == "mydevice" and cur in ("flash", "emu")) or (want == "flash" and cur == "emu"):
            continue
        for attempt in range(4):
            dbl(x, y, 5)
            cur = state(shot("_nav"))
            if cur == want:
                break
            print(f"attempt {attempt}: wanted {want}, got {cur}")
        if cur != want:
            print("navigation failed at", want)
            return False
    print("in 0emu")
    return True


args = sys.argv[1:]
i = 0
ok = True
while i < len(args):
    a = args[i]
    if a == "0emu":
        ok = open_0emu(); i += 1
        if not ok:
            break
    elif a == "dbl":
        dbl(int(args[i + 1]), int(args[i + 2]), float(args[i + 3])); i += 4
    elif a == "click":
        c.mouseMove(int(args[i + 1]), int(args[i + 2])); c.mousePress(1); time.sleep(float(args[i + 3])); i += 4
    elif a == "shot":
        shot(args[i + 1]); i += 2
    elif a == "sleep":
        time.sleep(float(args[i + 1])); i += 2
    else:
        print(__doc__); ok = False; break
api.shutdown()
sys.exit(0 if ok else 1)
