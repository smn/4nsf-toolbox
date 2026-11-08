/*
 * addport - register and start pl011poll.dll for the emulator's extra UARTs.
 *
 *   addport.exe              COM2: (UART2) and COM3: (UART3)
 *   addport.exe 2            only COM2:
 *   addport.exe 2 AB0B0000   explicit IoBase (kernel virtual address)
 *
 * The image's own COM1: driver key (HKLM\Drivers\BuiltIn\pl011) holds the
 * virtual address of UART1; the vexpress UARTs are 0x10000 apart, so UARTn
 * is IoBase1 + (n-1) * 0x10000 in the same static mapping. The registry is
 * not persisted in this image, so this runs once per boot (launch-all does
 * it when dev\addport.exe exists).
 */
#include <windows.h>

static DWORD readIoBase1(void)
{
    HKEY h;
    DWORD v = 0, type, size = sizeof v;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"Drivers\\BuiltIn\\pl011", 0, 0, &h) != ERROR_SUCCESS)
        return 0;
    RegQueryValueExW(h, L"IoBase", NULL, &type, (LPBYTE)&v, &size);
    RegCloseKey(h);
    return v;
}

static int addport(int index, DWORD iobase, const wchar_t *dllpath)
{
    wchar_t key[80], msg[200];
    HKEY h;
    DWORD disp, idx = index;
    HANDLE dev;
    wsprintfW(key, L"Drivers\\BuiltIn\\PL011POLL%d", index);
    if (RegCreateKeyExW(HKEY_LOCAL_MACHINE, key, 0, NULL, 0, 0, NULL, &h, &disp) != ERROR_SUCCESS) {
        OutputDebugStringW(L"ADDPORT: RegCreateKeyEx failed");
        return 1;
    }
    RegSetValueExW(h, L"Dll", 0, REG_SZ, (const BYTE *)dllpath, (lstrlenW(dllpath) + 1) * 2);
    RegSetValueExW(h, L"Prefix", 0, REG_SZ, (const BYTE *)L"COM", 8);
    RegSetValueExW(h, L"Index", 0, REG_DWORD, (const BYTE *)&idx, 4);
    RegSetValueExW(h, L"IoBase", 0, REG_DWORD, (const BYTE *)&iobase, 4);
    RegCloseKey(h);
    dev = ActivateDeviceEx(key, NULL, 0, NULL);
    wsprintfW(msg, L"ADDPORT: COM%d: at %08x -> %s (handle %08x, error %d)", index, iobase,
              dev ? L"ok" : L"FAILED", (DWORD)dev, dev ? 0 : GetLastError());
    OutputDebugStringW(msg);
    if (!dev)
        MessageBoxW(NULL, msg, L"addport", MB_OK);
    return dev ? 0 : 1;
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR cmdline, int show)
{
    wchar_t dll[MAX_PATH], *slash;
    DWORD base1 = readIoBase1();
    int first = 2, last = 3, rc = 0;
    DWORD explicitBase = 0;

    /* the device manager loads kernel-mode drivers by name from \Windows,
     * so copy the DLL there (the RAM file system, gone after a reboot) */
    GetModuleFileNameW(NULL, dll, MAX_PATH);
    slash = wcsrchr(dll, L'\\');
    lstrcpyW(slash ? slash + 1 : dll, L"pl011poll.dll");
    if (!CopyFileW(dll, L"\\Windows\\pl011poll.dll", FALSE)) {
        wchar_t m[160];
        wsprintfW(m, L"ADDPORT: copy of %s to \\Windows failed (%d)", dll, GetLastError());
        OutputDebugStringW(m);
    }
    lstrcpyW(dll, L"pl011poll.dll");

    if (cmdline && *cmdline) {
        first = last = (int)wcstoul(cmdline, NULL, 10);
        while (*cmdline && *cmdline != L' ') cmdline++;
        while (*cmdline == L' ') cmdline++;
        if (*cmdline)
            explicitBase = wcstoul(cmdline, NULL, 16);
    }
    if (!base1 && !explicitBase) {
        MessageBoxW(NULL, L"no HKLM\\Drivers\\BuiltIn\\pl011\\IoBase and no address given", L"addport", MB_OK);
        return 2;
    }
    for (; first <= last; first++)
        rc |= addport(first, explicitBase ? explicitBase : base1 + (first - 1) * 0x10000, dll);
    return rc;
}
