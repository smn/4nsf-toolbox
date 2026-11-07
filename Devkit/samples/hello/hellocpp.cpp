// C++ smoke test for the toolchain: libstdc++ containers and strings, a
// static object with a destructor, and an exception caught in the same
// module (SJLJ exceptions work inside one EXE/DLL, not across DLLs).
// C++ headers before windows.h: CeGCC's windows.h drags in the C runtime
// headers in a way that hides atoll from <cstdlib> otherwise.
#include <string>
#include <vector>
#include <algorithm>
#include <stdexcept>
#include <windows.h>

struct AtExit {
    ~AtExit() { OutputDebugStringW(L"EMUHELLO: static destructor ran"); }
} g_atexit;

static std::wstring describe()
{
    std::vector<int> v = {5, 3, 9, 1};
    std::sort(v.begin(), v.end());
    std::wstring s = L"EMUHELLO: C++ ok, sorted:";
    for (int x : v)
        s += L" " + std::to_wstring(x);
    try {
        throw std::runtime_error("caught");
    } catch (const std::exception &e) {
        s += L", exception ";
        for (const char *p = e.what(); *p; ++p)
            s += (wchar_t)*p;
    }
    return s;
}

int WINAPI WinMain(HINSTANCE, HINSTANCE, LPWSTR, int)
{
    std::wstring s = describe();
    OutputDebugStringW(s.c_str());
    MessageBoxW(NULL, s.c_str(), L"hello c++", MB_OK);
    return 0;
}
