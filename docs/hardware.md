# 4NSF hardware notes (from the firmware, not from a teardown)

Everything below was read out of Volkswagen's update package
(`Install_OS.exe`, `Install_BT.exe`, `UpdateMeContent.content`) with the
tools in `Emulator/`. Treat it as strong evidence, not as a datasheet.

## Platform

| Item | Finding | Source |
|---|---|---|
| SoC | STMicroelectronics Cartesio+ (STA2065), xLoader detects "Cartesio PLUS (CUT1)" / "(CUT2)"; ARM1176 core, ~520 MHz (`PLLFR = 0x18002801 ; 520Mz`) | `xL_CPlus.bin`, `config.txt` |
| RAM | 128 MB DDR2 (Denali controller settings in `config.txt`), frame buffer at physical 0x06C11000 | `config.txt` |
| Storage | eMMC ("FLASHING eMMC..."), partitions `MYFLASH` (My Flash Disk) and `MNSET` (MN Settings) on `DSK1:`, SD card `DSK2:` | `ApLoader.bin`, `Watchdog_HW.ini` |
| Display | 480x272 CLCD (PL11x-style timing registers `clcd timer0..3` in `config.txt`), SGA graphics accelerator used by `openGL_ES_STA2065.dll` and `sgalib.dll` | `config.txt`, ROM files |
| Bluetooth | CSR BlueCore 5 (`CSR - bc5` in the DFU firmware `h14423-v2r43`): Bluetooth 2.1+EDR, classic only, **no BLE** | `Install_BT.exe` |
| Bluetooth stack | Navigon's `nfBT.dll` behind `BTCore.exe`: HFP, A2DP, AVRCP, PBAP, MAP, DUN, plus an SPP data path (`SppSend`, `SppSendDataCmd`) | BT folder |
| GPS | integrated in the SoC (ST Teseo), NMEA on `COM2:` at 57600 for Navigon | `UserSettings.default` |
| Car link | BAP protocol on `COM9:` from the cradle connector | `VwCommunicationManager.ini` |
| USB | one mini-USB socket; controller see below | manual, `ApLoader.bin` |

## USB controller: Mentor MUSB OTG, host-capable, at 0x10200000

The ROM's Windows CE driver (`usbfn1.dll`) is a USB *function* (device)
driver only: mass storage, a Microsoft serial class (`serialusbfn.dll`),
RNDIS. Its registry key carries `OTGEnable`, `UseEmbeddedPhy`,
`HighSpeedSupported`, `MemBase`, `SysIntr`, `AvailEndpoints`, `DmaEnabled`.

The boot loader (`ApLoader.bin`, Thumb code loaded at 0x03E00000, vector
table at the start of the file) contains a complete USB **host** path and
identifies the controller unambiguously as a Mentor Graphics MUSB (Inventra
HDRC) OTG core:

- interrupt enable writes to the byte register at base+0x0B with bits
  0x80/0x40/0x20/0x10/0x08/0x04/0x02/0x01 (MUSB `INTRUSBE`: VBus error,
  session request, disconnect, connect, SOF, reset/babble, resume, suspend),
  and to the halfwords at +0x06 / +0x08 (`INTRTXE` / `INTRRXE`);
- mode detection from bit 2 of base+0x60 (`DEVCTL.HostMode`), session
  start/stop by setting and clearing bit 0 of `DEVCTL` (`SESSION`);
- `ULPI_VBUSCONTROL` at base+0x70 set to 0x03 (`UseExtVbus` and
  `UseExtVbusInd`) right before starting a host session, meaning the board
  relies on an **external VBUS supply**;
- the base address 0x10200000 is passed into the host initialisation;
- error paths "USB_IRQ_SRC_VBUSERROR", "USB Device Disconnected",
  "Unsupported USB Host Hardware." (printed when the attached device's
  descriptors are not the expected mass-storage class), followed by
  mounting the attached device as a volume for an OS update from a USB
  stick.

Consequences:

- Host mode works on this board's silicon and wiring (data lines); 5 V must
  come from outside, so a host setup needs a Y-cable or powered hub that
  injects VBUS.
- Windows CE has no host-controller driver for MUSB in this ROM. Public
  CE 6 BSPs for TI OMAP35xx / BeagleBoard contain an Inventra MUSB host
  driver that could be ported (base 0x10200000, interrupt via the OAL).
- With a host driver, a BLE USB dongle would still need a BLE host stack
  (HCI, L2CAP, ATT/GATT, SMP) written for CE, since Microsoft's stack is
  classic-only. That is the "device-only" route to Apple's ANCS; the
  ESP32-as-host bridge in the README discussion is the shorter one.

Other peripherals seen in ApLoader's literal pools (bases only):
0x10100000, 0x10110000, 0x10120000 (UART, PL011 layout), 0x10140000,
0x10180000 / 0x1018C000 (SD/MMC, PL180-like), 0x101C2000, 0x101E0000,
0x101E4000, 0x101E6000 (GPIO/system controller area), 0x101EA000,
0x101EF000, 0x101F5000, 0x101F6000, 0x101FB000, 0x80010000.

## Boot chain and how open it is

1. Boot ROM loads `xL_CPlus.bin` (ST xLoader, 14 KB): DDR init from
   `config.txt`, display setup, detects the Cartesio+ cut, loads ApLoader.
2. `ApLoader.bin` (Navigon, 66 KB): shows the splash, loads `NK.nb0` into RAM
   and jumps. Integrity is a **checksum only** (`NK.sum`/`NK.ver`,
   "Checksum in NK.ver is not matched in NK.sum!!"); there is no signature
   check. It also implements:
   - recovery/update from SD card when the touchscreen is held at power-on
     ("Keep pressing the display for %d sec.", "Starting Recovery Mode."):
     `NK.nb0`, `Aploader.bin`, `Meminit.bin`, `LPHandle.bin` with `.sum`
     files, control files `FlashFor.txt`, `Hardrst.txt`, `MNFormat.txt`,
     `SkipNew.txt`, `NoDelete.txt`, `wolf.reg`;
   - "LIVE OS LOADING": booting an OS image from the SD card without
     flashing it;
   - OS update from a USB mass-storage device (the host path above);
   - an alternative ApLoader copy and an xLoader update path.
3. `NK.nb0`: Windows CE 6.0 R3 image (OS 2.33). Windows CE 6 gives every
   program full system access, so there is nothing to "root" at the OS
   level; the toolbox's apps already run unsigned.

The practical consequence: kernel-level experiments (patched `NK.nb0`, or
another OS) can be test-booted from an SD card with a recomputed `.sum`
without touching the eMMC.

## Hidden flash (2 KB, via `WolfSpecial.dll`)

Layout recovered from `VwBrandDevice.exe` / `VwUserShell.exe`, emulated by
`Emulator/mkflash.py`: `0x10` signature `123Kuckuck123`, `0x1e` VIN,
`0x2f` brand (0 VW, 2 Seat, 3 Skoda), `0x30` `'B'` when paired, `0x31`
feature bits, `0x32..0x35` sound/type/line/class, `0x36` VIN.

## Tools used

`Emulator/sfx_extract.py`, `ceromdump.py`, `celzx.py` for the package and
ROM; `Emulator/tools/disas.py`, `callers.py` for the PE binaries;
`Emulator/tools/rawthumb.py` for the raw Thumb boot loader.
