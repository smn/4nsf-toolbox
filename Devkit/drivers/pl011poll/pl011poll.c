/*
 * pl011poll - a polled PL011 UART stream driver for Windows CE.
 *
 * The Compact 7 image used by the emulator registers only one of the four
 * UARTs of QEMU's vexpress-a15 board (COM1:). This driver brings up the
 * others without touching the image or needing an interrupt mapping: it
 * maps the UART registers from the registry's IoBase (a kernel virtual
 * address, like the image's own pl011.dll uses) and a thread polls the
 * receive FIFO into a ring buffer. Plenty for a 115200-baud dev channel or
 * an NMEA feed in the emulator; it is not meant for a real device.
 *
 * Loaded at run time by addport.exe (registry key + ActivateDeviceEx), see
 * there for the values. Stream interface: COM_Init/Deinit/Open/Close/
 * Read/Write/Seek/IOControl, with the serial IOCTLs that SetCommState,
 * SetCommTimeouts, SetCommMask, WaitCommEvent and friends in coredll use.
 */
#include <windows.h>

/* PL011 registers (byte offsets) */
#define UARTDR   0x000
#define UARTFR   0x018
#define UARTIBRD 0x024
#define UARTFBRD 0x028
#define UARTLCRH 0x02c
#define UARTCR   0x030
#define UARTIMSC 0x038
#define UARTICR  0x044
#define FR_RXFE  (1 << 4)
#define FR_TXFF  (1 << 5)

/* serial IOCTLs: FILE_DEVICE_SERIAL_PORT = 0x1b, METHOD_BUFFERED, FILE_ANY_ACCESS */
#define SER_IOCTL(f) (((0x1b) << 16) | ((f) << 2))
#define IOCTL_SERIAL_SET_BREAK_ON    SER_IOCTL(1)
#define IOCTL_SERIAL_SET_BREAK_OFF   SER_IOCTL(2)
#define IOCTL_SERIAL_SET_DTR         SER_IOCTL(3)
#define IOCTL_SERIAL_CLR_DTR         SER_IOCTL(4)
#define IOCTL_SERIAL_SET_RTS         SER_IOCTL(5)
#define IOCTL_SERIAL_CLR_RTS         SER_IOCTL(6)
#define IOCTL_SERIAL_SET_XOFF        SER_IOCTL(7)
#define IOCTL_SERIAL_SET_XON         SER_IOCTL(8)
#define IOCTL_SERIAL_GET_WAIT_MASK   SER_IOCTL(9)
#define IOCTL_SERIAL_SET_WAIT_MASK   SER_IOCTL(10)
#define IOCTL_SERIAL_WAIT_ON_MASK    SER_IOCTL(11)
#define IOCTL_SERIAL_GET_COMMSTATUS  SER_IOCTL(12)
#define IOCTL_SERIAL_GET_MODEMSTATUS SER_IOCTL(13)
#define IOCTL_SERIAL_GET_PROPERTIES  SER_IOCTL(14)
#define IOCTL_SERIAL_SET_TIMEOUTS    SER_IOCTL(15)
#define IOCTL_SERIAL_GET_TIMEOUTS    SER_IOCTL(16)
#define IOCTL_SERIAL_PURGE           SER_IOCTL(17)
#define IOCTL_SERIAL_SET_QUEUE_SIZE  SER_IOCTL(18)
#define IOCTL_SERIAL_IMMEDIATE_CHAR  SER_IOCTL(19)
#define IOCTL_SERIAL_GET_DCB         SER_IOCTL(20)
#define IOCTL_SERIAL_SET_DCB         SER_IOCTL(21)
#define IOCTL_SERIAL_ENABLE_IR       SER_IOCTL(22)
#define IOCTL_SERIAL_DISABLE_IR      SER_IOCTL(23)

#define RING 65536

typedef struct { DWORD Errors; COMSTAT ComStat; } SERIAL_DEV_STATUS;   /* from serdev.h */

typedef struct {
    volatile BYTE *base;
    BYTE ring[RING];
    volatile DWORD head, tail;      /* producer: poll thread; consumer: readers */
    HANDLE rxEvent;                 /* set when data arrives */
    HANDLE pollThread;
    volatile BOOL stop;
    DCB dcb;
    COMMTIMEOUTS to;
    DWORD waitMask;
    LONG openCount;
} PORT;

static DWORD reg32(PORT *p, DWORD off) { return *(volatile DWORD *)(p->base + off); }
static void wreg32(PORT *p, DWORD off, DWORD v) { *(volatile DWORD *)(p->base + off) = v; }

static DWORD WINAPI pollProc(LPVOID ctx)
{
    PORT *p = ctx;
    while (!p->stop) {
        BOOL got = FALSE;
        while (!(reg32(p, UARTFR) & FR_RXFE)) {
            DWORD next = (p->head + 1) % RING;
            BYTE c = (BYTE)reg32(p, UARTDR);
            if (next != p->tail) {      /* drop on overflow */
                p->ring[p->head] = c;
                p->head = next;
            }
            got = TRUE;
        }
        if (got)
            SetEvent(p->rxEvent);
        Sleep(got ? 0 : 2);
    }
    return 0;
}

static BOOL regDword(LPCWSTR key, LPCWSTR name, DWORD *out)
{
    HKEY h;
    DWORD type, size = sizeof(DWORD);
    LONG r = RegOpenKeyExW(HKEY_LOCAL_MACHINE, key, 0, 0, &h);
    if (r != ERROR_SUCCESS)
        return FALSE;
    r = RegQueryValueExW(h, name, NULL, &type, (LPBYTE)out, &size);
    RegCloseKey(h);
    return r == ERROR_SUCCESS;
}

/* ---- stream interface -------------------------------------------------- */
DWORD COM_Init(LPCWSTR context)
{
    PORT *p;
    DWORD iobase = 0;
    /* context is the active key; the driver's own key is in its "Key" value */
    HKEY h;
    wchar_t key[256];
    DWORD type, size = sizeof key;
    key[0] = 0;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, context, 0, 0, &h) == ERROR_SUCCESS) {
        RegQueryValueExW(h, L"Key", NULL, &type, (LPBYTE)key, &size);
        RegCloseKey(h);
    }
    if (!key[0] || !regDword(key, L"IoBase", &iobase) || !iobase) {
        OutputDebugStringW(L"PL011POLL: no IoBase");
        return 0;
    }
    p = (PORT *)LocalAlloc(LPTR, sizeof(PORT));
    if (!p)
        return 0;
    p->base = (volatile BYTE *)iobase;
    p->rxEvent = CreateEventW(NULL, FALSE, FALSE, NULL);
    p->dcb.DCBlength = sizeof(DCB);
    p->dcb.BaudRate = 115200;
    p->dcb.ByteSize = 8;
    p->dcb.fBinary = TRUE;
    p->to.ReadIntervalTimeout = MAXDWORD;       /* default: return immediately */
    /* enable the UART: 8N1, FIFOs, TX+RX, no interrupts */
    wreg32(p, UARTIMSC, 0);
    wreg32(p, UARTICR, 0x7ff);
    wreg32(p, UARTLCRH, 0x70);
    wreg32(p, UARTCR, 0x301);
    p->pollThread = CreateThread(NULL, 0, pollProc, p, 0, NULL);
    {
        wchar_t msg[96];
        wsprintfW(msg, L"PL011POLL: up at %08x (%s)", iobase, key);
        OutputDebugStringW(msg);
    }
    return (DWORD)p;
}

BOOL COM_Deinit(DWORD ctx)
{
    PORT *p = (PORT *)ctx;
    if (!p)
        return FALSE;
    p->stop = TRUE;
    WaitForSingleObject(p->pollThread, 1000);
    CloseHandle(p->pollThread);
    CloseHandle(p->rxEvent);
    LocalFree(p);
    return TRUE;
}

DWORD COM_Open(DWORD ctx, DWORD access, DWORD share)
{
    PORT *p = (PORT *)ctx;
    if (InterlockedIncrement(&p->openCount) > 1) {   /* exclusive, like a real COM port */
        InterlockedDecrement(&p->openCount);
        SetLastError(ERROR_ACCESS_DENIED);
        return 0;
    }
    return ctx;
}

BOOL COM_Close(DWORD open)
{
    PORT *p = (PORT *)open;
    InterlockedDecrement(&p->openCount);
    SetEvent(p->rxEvent);        /* release a WaitCommEvent */
    return TRUE;
}

static DWORD available(PORT *p) { return (p->head + RING - p->tail) % RING; }

DWORD COM_Read(DWORD open, LPVOID buf, DWORD len)
{
    PORT *p = (PORT *)open;
    BYTE *out = buf;
    DWORD got = 0, start = GetTickCount();
    DWORD total = p->to.ReadTotalTimeoutConstant + p->to.ReadTotalTimeoutMultiplier * len;
    DWORD interval = p->to.ReadIntervalTimeout;
    while (got < len) {
        if (p->tail != p->head) {
            out[got++] = p->ring[p->tail];
            p->tail = (p->tail + 1) % RING;
            continue;
        }
        /* nothing buffered: decide whether to wait */
        if (interval == MAXDWORD && total == 0)
            break;                                   /* non-blocking mode */
        if (got && interval != MAXDWORD && interval != 0) {
            /* wait at most the inter-byte interval for the next byte */
            if (WaitForSingleObject(p->rxEvent, interval) != WAIT_OBJECT_0)
                break;
            continue;
        }
        if (total) {
            DWORD elapsed = GetTickCount() - start;
            if (elapsed >= total)
                break;
            if (WaitForSingleObject(p->rxEvent, total - elapsed) != WAIT_OBJECT_0)
                break;
        } else {
            WaitForSingleObject(p->rxEvent, INFINITE);
        }
        if (p->openCount <= 0)
            break;
    }
    return got;
}

DWORD COM_Write(DWORD open, LPCVOID buf, DWORD len)
{
    PORT *p = (PORT *)open;
    const BYTE *in = buf;
    DWORD i;
    for (i = 0; i < len; i++) {
        while (reg32(p, UARTFR) & FR_TXFF)
            Sleep(0);
        wreg32(p, UARTDR, in[i]);
    }
    return len;
}

DWORD COM_Seek(DWORD open, long pos, DWORD type) { return (DWORD)-1; }
void COM_PowerUp(DWORD ctx) {}
void COM_PowerDown(DWORD ctx) {}

BOOL COM_IOControl(DWORD open, DWORD code, PBYTE in, DWORD inLen, PBYTE out, DWORD outLen, PDWORD ret)
{
    PORT *p = (PORT *)open;
    if (ret) *ret = 0;
    switch (code) {
    case IOCTL_SERIAL_SET_DCB:
        if (in && inLen >= sizeof(DCB)) memcpy(&p->dcb, in, sizeof(DCB));
        return TRUE;
    case IOCTL_SERIAL_GET_DCB:
        if (!out || outLen < sizeof(DCB)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        memcpy(out, &p->dcb, sizeof(DCB)); if (ret) *ret = sizeof(DCB);
        return TRUE;
    case IOCTL_SERIAL_SET_TIMEOUTS:
        if (in && inLen >= sizeof(COMMTIMEOUTS)) memcpy(&p->to, in, sizeof(COMMTIMEOUTS));
        return TRUE;
    case IOCTL_SERIAL_GET_TIMEOUTS:
        if (!out || outLen < sizeof(COMMTIMEOUTS)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        memcpy(out, &p->to, sizeof(COMMTIMEOUTS)); if (ret) *ret = sizeof(COMMTIMEOUTS);
        return TRUE;
    case IOCTL_SERIAL_SET_WAIT_MASK:
        if (in && inLen >= 4) p->waitMask = *(DWORD *)in;
        SetEvent(p->rxEvent);            /* a mask change aborts a pending WaitCommEvent */
        return TRUE;
    case IOCTL_SERIAL_GET_WAIT_MASK:
        if (!out || outLen < 4) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        *(DWORD *)out = p->waitMask; if (ret) *ret = 4;
        return TRUE;
    case IOCTL_SERIAL_WAIT_ON_MASK: {
        DWORD ev = 0;
        if (!out || outLen < 4) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        while (p->openCount > 0) {
            if ((p->waitMask & EV_RXCHAR) && p->tail != p->head) { ev = EV_RXCHAR; break; }
            if (!(p->waitMask & EV_RXCHAR)) { WaitForSingleObject(p->rxEvent, 100); break; }
            WaitForSingleObject(p->rxEvent, INFINITE);
        }
        *(DWORD *)out = ev; if (ret) *ret = 4;
        return TRUE;
    }
    case IOCTL_SERIAL_GET_COMMSTATUS: {
        SERIAL_DEV_STATUS *s = (SERIAL_DEV_STATUS *)out;
        if (!out || outLen < sizeof(SERIAL_DEV_STATUS)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        memset(s, 0, sizeof *s);
        s->ComStat.cbInQue = available(p);
        if (ret) *ret = sizeof *s;
        return TRUE;
    }
    case IOCTL_SERIAL_GET_MODEMSTATUS:
        if (!out || outLen < 4) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        *(DWORD *)out = MS_CTS_ON | MS_DSR_ON | MS_RLSD_ON; if (ret) *ret = 4;
        return TRUE;
    case IOCTL_SERIAL_GET_PROPERTIES: {
        COMMPROP *cp = (COMMPROP *)out;
        if (!out || outLen < sizeof(COMMPROP)) { SetLastError(ERROR_INVALID_PARAMETER); return FALSE; }
        memset(cp, 0, sizeof *cp);
        cp->wPacketLength = sizeof(COMMPROP);
        cp->dwServiceMask = SP_SERIALCOMM;
        cp->dwMaxBaud = BAUD_USER;
        cp->dwSettableBaud = BAUD_9600 | BAUD_19200 | BAUD_38400 | BAUD_57600 | BAUD_115200 | BAUD_USER;
        cp->wSettableData = DATABITS_8;
        cp->wSettableStopParity = STOPBITS_10 | PARITY_NONE;
        cp->dwCurrentRxQueue = RING;
        cp->dwCurrentTxQueue = 16;
        if (ret) *ret = sizeof *cp;
        return TRUE;
    }
    case IOCTL_SERIAL_PURGE:
        if (in && inLen >= 4 && (*(DWORD *)in & (PURGE_RXCLEAR | PURGE_RXABORT)))
            p->tail = p->head;
        return TRUE;
    case IOCTL_SERIAL_IMMEDIATE_CHAR:
        if (in && inLen >= 1) COM_Write(open, in, 1);
        return TRUE;
    case IOCTL_SERIAL_SET_QUEUE_SIZE:
    case IOCTL_SERIAL_SET_BREAK_ON: case IOCTL_SERIAL_SET_BREAK_OFF:
    case IOCTL_SERIAL_SET_DTR: case IOCTL_SERIAL_CLR_DTR:
    case IOCTL_SERIAL_SET_RTS: case IOCTL_SERIAL_CLR_RTS:
    case IOCTL_SERIAL_SET_XOFF: case IOCTL_SERIAL_SET_XON:
    case IOCTL_SERIAL_ENABLE_IR: case IOCTL_SERIAL_DISABLE_IR:
        return TRUE;
    default:
        SetLastError(ERROR_INVALID_PARAMETER);
        return FALSE;
    }
}

BOOL WINAPI DllMain(HANDLE h, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
        DisableThreadLibraryCalls((HMODULE)h);
    return TRUE;
}
