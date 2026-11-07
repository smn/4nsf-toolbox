#!/usr/bin/env python3
"""Feed NMEA 0183 sentences into the VM's serial port (COM1: in the guest).

run-emulator.sh exposes QEMU's second UART as a TCP server on 127.0.0.1:5555;
this connects to it and sends a fix at 1 Hz, optionally moving along a
heading. Defaults put the car in Wolfsburg.

  nmea.py                                 # fixed position
  nmea.py --lat 52.42 --lon 10.78 --speed 50 --heading 90   # km/h, degrees
  nmea.py --port 5555 --rate 1
"""
import argparse
import datetime
import math
import socket
import time


def cksum(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"${body}*{c:02X}\r\n"


def dm(v, lat):
    d = int(abs(v)); m = (abs(v) - d) * 60
    if lat:
        return f"{d:02d}{m:07.4f}", "N" if v >= 0 else "S"
    return f"{d:03d}{m:07.4f}", "E" if v >= 0 else "W"


def sentences(lat, lon, speed_kmh, heading, alt=80.0):
    now = datetime.datetime.now(datetime.timezone.utc)
    t = now.strftime("%H%M%S.00"); d = now.strftime("%d%m%y")
    la, ns = dm(lat, True); lo, ew = dm(lon, False)
    kn = speed_kmh / 1.852
    out = [
        cksum(f"GPGGA,{t},{la},{ns},{lo},{ew},1,08,1.0,{alt:.1f},M,46.9,M,,"),
        cksum(f"GPRMC,{t},A,{la},{ns},{lo},{ew},{kn:.1f},{heading:.1f},{d},,,A"),
        cksum("GPGSA,A,3,01,02,03,04,05,06,07,08,,,,,1.8,1.0,1.5"),
        cksum("GPGSV,2,1,08,01,70,045,45,02,60,120,44,03,50,200,43,04,45,280,42"),
        cksum("GPGSV,2,2,08,05,40,010,41,06,35,090,40,07,30,170,39,08,25,250,38"),
        cksum(f"GPVTG,{heading:.1f},T,,M,{kn:.1f},N,{speed_kmh:.1f},K,A"),
    ]
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--lat", type=float, default=52.4227)
    ap.add_argument("--lon", type=float, default=10.7865)
    ap.add_argument("--speed", type=float, default=0.0, help="km/h")
    ap.add_argument("--heading", type=float, default=0.0, help="degrees true")
    ap.add_argument("--rate", type=float, default=1.0, help="fixes per second")
    a = ap.parse_args()
    lat, lon = a.lat, a.lon
    while True:
        try:
            s = socket.create_connection((a.host, a.port))
            print("connected to", a.host, a.port)
            while True:
                s.sendall(sentences(lat, lon, a.speed, a.heading).encode("ascii"))
                dt = 1.0 / a.rate
                dist = a.speed / 3.6 * dt  # metres
                lat += dist * math.cos(math.radians(a.heading)) / 111320.0
                lon += dist * math.sin(math.radians(a.heading)) / (111320.0 * math.cos(math.radians(lat)))
                time.sleep(dt)
        except (ConnectionRefusedError, BrokenPipeError, ConnectionResetError) as e:
            print("serial port not ready:", e, "- retrying")
            time.sleep(2)


if __name__ == "__main__":
    main()
