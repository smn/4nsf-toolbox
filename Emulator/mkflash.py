#!/usr/bin/env python3
"""Write an emulated hidden flash (2 KB) for the VW "maps + more" apps.

The apps read it through WolfSpecial.dll ReadHiddenFlash(offset, buf, len);
the layout below was recovered from VwBrandDevice.exe and VwUserShell.exe
(every ReadFlash/WriteFlash call site):

  0x10  13  "123Kuckuck123"      validity signature, else the area is re-initialised
  0x1e  17  VIN                   written when the device is paired with a car
  0x2f   1  brand                 0 Volkswagen, 2 Seat, 3 Skoda (skin + splash choice)
  0x30   1  'B' paired / ' ' not  'B' once the pairing data lives in the flash
  0x31   1  feature bits 0..5
  0x32   1  sound system          2 with brand 0 = "Fender" splash screen
  0x33   1  vehicle type
  0x34   1  line
  0x35   1  class (fuel)
  0x36  17  VIN

With 0x30 != 'B' or an unknown brand the brand app shows "Connect your
device to your brand new car and switch the ignition on" and waits for the
car's BAP identification. A dump of a real unit (work/hidden_flash.bin) takes
precedence over this generator in build-navigon.sh.
"""
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="hidden_flash.bin")
ap.add_argument("--vin", default="WVWZZZAAZFD000000")
ap.add_argument("--brand", type=int, default=0)
ap.add_argument("--flags", type=lambda x: int(x, 0), default=0)
ap.add_argument("--sound", type=int, default=2)
ap.add_argument("--type", type=int, default=1)
ap.add_argument("--line", type=int, default=0)
ap.add_argument("--class", dest="cls", type=int, default=0)
ap.add_argument("--unpaired", action="store_true", help="leave 0x30 blank to see the pairing screen")
a = ap.parse_args()
vin = a.vin.encode()
if len(vin) != 17:
    raise SystemExit("VIN must be 17 characters")
d = bytearray(2048)
d[0x10:0x1d] = b"123Kuckuck123"
d[0x1e:0x2f] = vin
d[0x2f] = a.brand
d[0x30] = ord(" ") if a.unpaired else ord("B")
d[0x31] = a.flags
d[0x32], d[0x33], d[0x34], d[0x35] = a.sound, a.type, a.line, a.cls
d[0x36:0x47] = vin
open(a.out, "wb").write(d)
print(f"{a.out}: brand {a.brand} sound {a.sound} type {a.type} line {a.line} class {a.cls} vin {a.vin}"
      + (" (unpaired)" if a.unpaired else ""))
