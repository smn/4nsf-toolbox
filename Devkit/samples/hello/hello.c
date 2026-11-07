/* The smallest useful Windows CE program: says hello on the debug serial
 * line (serial.log in the emulator), in a message box, and in a file next
 * to itself, so each channel can be checked. Build: make hello */
#include <windows.h>

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR cmdline, int show)
{
    wchar_t msg[256], path[MAX_PATH], *slash;
    HANDLE f;
    DWORD n;
    SYSTEM_INFO si;
    OSVERSIONINFOW vi;

    MEMORYSTATUS ms;

    GetSystemInfo(&si);
    vi.dwOSVersionInfoSize = sizeof vi;
    GetVersionExW(&vi);
    ms.dwLength = sizeof ms;
    GlobalMemoryStatus(&ms);
    wsprintfW(msg, L"EMUHELLO: hello from CeGCC on Windows CE %d.%d, cpu type %d, %d MB RAM, args '%s'",
              vi.dwMajorVersion, vi.dwMinorVersion, si.dwProcessorType,
              ms.dwTotalPhys >> 20, cmdline ? cmdline : L"");
    OutputDebugStringW(msg);

    GetModuleFileNameW(NULL, path, MAX_PATH);
    slash = wcsrchr(path, L'\\');
    if (slash)
        lstrcpyW(slash + 1, L"hello.txt");
    f = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        WriteFile(f, msg, lstrlenW(msg) * 2, &n, NULL);
        CloseHandle(f);
    }
    MessageBoxW(NULL, msg, L"hello", MB_OK);
    return 0;
}
