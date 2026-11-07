/*
 * ceagent - a tiny deploy/run agent for Windows CE devices and the emulator.
 *
 * It serves a framed request/response protocol over a serial port or a TCP
 * socket so a host tool (deploy.py) can copy files in and out, list
 * directories and start programs without rebuilding disk images or touching
 * the device's USB mass-storage mode.
 *
 *   ceagent.exe COM1:          serve on a serial port (115200 8N1)
 *   ceagent.exe tcp:7777       listen on a TCP port (needs a network driver)
 *   ceagent.exe                same as COM1:
 *
 * Frame (little endian): u32 magic 'CEA1' (0x31414543), u8 cmd, u32 len,
 * payload. The reply uses the same layout with the status in place of cmd
 * (0 = OK, otherwise a Win32 error code). Strings are UTF-16LE, NUL
 * terminated. See deploy.py for the host side and the per-command payloads.
 *
 * Built with CeGCC (arm-mingw32ce), no C runtime beyond coredll.
 */
#include <windows.h>

#define MAGIC 0x31414543u
#define MAXPAYLOAD (64 * 1024)

enum {
    CMD_PING = 1,   /* -> "ceagent 1" */
    CMD_PUT = 2,    /* path\0 u32 total   -> OK, then CHUNK frames */
    CMD_CHUNK = 3,  /* raw data appended to the open PUT file -> OK */
    CMD_CLOSE = 4,  /* finish the PUT -> OK */
    CMD_GET = 5,    /* path\0 -> OK u32 size, then the agent streams CHUNK frames + CLOSE */
    CMD_RUN = 6,    /* u32 wait_ms, cmdline\0 -> OK u32 pid u32 exitcode (0xFFFFFFFF if still running) */
    CMD_LIST = 7,   /* path\0 -> OK text lines "name\tsize\tattrs\n" */
    CMD_DEL = 8,    /* path\0 -> OK */
    CMD_MKDIR = 9,  /* path\0 -> OK */
    CMD_REBOOT = 10 /* -> OK, then the agent exits (the watchdog/launcher decides what happens) */
};

typedef struct {
    int (*read)(void *buf, int len);   /* blocking, exact length; 0 on error */
    int (*write)(const void *buf, int len);
} transport_t;

static HANDLE g_com = INVALID_HANDLE_VALUE;
static SOCKET g_sock = INVALID_SOCKET;

/* ---- logging ---------------------------------------------------------- */
static void dbg(const wchar_t *fmt, ...)
{
    wchar_t buf[256];
    va_list ap;
    va_start(ap, fmt);
    wvsprintfW(buf, fmt, ap);
    va_end(ap);
    OutputDebugStringW(buf);
}

/* ---- serial transport -------------------------------------------------- */
static int com_read(void *buf, int len)
{
    BYTE *p = buf;
    while (len > 0) {
        DWORD n = 0;
        if (!ReadFile(g_com, p, len, &n, NULL))
            return 0;
        if (n == 0)
            continue; /* timeout, keep waiting */
        p += n;
        len -= n;
    }
    return 1;
}

static int com_write(const void *buf, int len)
{
    const BYTE *p = buf;
    while (len > 0) {
        DWORD n = 0;
        if (!WriteFile(g_com, p, len, &n, NULL) || n == 0)
            return 0;
        p += n;
        len -= n;
    }
    return 1;
}

static int com_open(const wchar_t *name)
{
    DCB dcb;
    COMMTIMEOUTS to;
    g_com = CreateFileW(name, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (g_com == INVALID_HANDLE_VALUE) {
        dbg(L"CEAGENT: cannot open %s (%d)", name, GetLastError());
        return 0;
    }
    memset(&dcb, 0, sizeof dcb);
    dcb.DCBlength = sizeof dcb;
    GetCommState(g_com, &dcb);
    dcb.BaudRate = 115200;
    dcb.ByteSize = 8;
    dcb.Parity = NOPARITY;
    dcb.StopBits = ONESTOPBIT;
    dcb.fBinary = TRUE;
    dcb.fOutxCtsFlow = FALSE;
    dcb.fOutxDsrFlow = FALSE;
    dcb.fDtrControl = DTR_CONTROL_ENABLE;
    dcb.fRtsControl = RTS_CONTROL_ENABLE;
    dcb.fOutX = dcb.fInX = FALSE;
    SetCommState(g_com, &dcb);
    memset(&to, 0, sizeof to);
    to.ReadIntervalTimeout = 50;
    to.ReadTotalTimeoutConstant = 500;
    to.WriteTotalTimeoutConstant = 5000;
    SetCommTimeouts(g_com, &to);
    SetupComm(g_com, 65536, 65536);
    PurgeComm(g_com, PURGE_RXCLEAR | PURGE_TXCLEAR);
    return 1;
}

/* ---- TCP transport (ws2.dll loaded at run time so the serial build has
 *      no import on it) ------------------------------------------------- */
typedef int (WINAPI *pfn_WSAStartup)(WORD, LPWSADATA);
typedef SOCKET (WINAPI *pfn_socket)(int, int, int);
typedef int (WINAPI *pfn_bind)(SOCKET, const struct sockaddr *, int);
typedef int (WINAPI *pfn_listen)(SOCKET, int);
typedef SOCKET (WINAPI *pfn_accept)(SOCKET, struct sockaddr *, int *);
typedef int (WINAPI *pfn_recv)(SOCKET, char *, int, int);
typedef int (WINAPI *pfn_send)(SOCKET, const char *, int, int);
typedef int (WINAPI *pfn_closesocket)(SOCKET);
static pfn_recv p_recv;
static pfn_send p_send;
static pfn_closesocket p_closesocket;

static int tcp_read(void *buf, int len)
{
    char *p = buf;
    while (len > 0) {
        int n = p_recv(g_sock, p, len, 0);
        if (n <= 0)
            return 0;
        p += n;
        len -= n;
    }
    return 1;
}

static int tcp_write(const void *buf, int len)
{
    const char *p = buf;
    while (len > 0) {
        int n = p_send(g_sock, p, len, 0);
        if (n <= 0)
            return 0;
        p += n;
        len -= n;
    }
    return 1;
}

static SOCKET tcp_listen(int port)
{
    HMODULE ws2 = LoadLibraryW(L"ws2.dll");
    pfn_WSAStartup p_WSAStartup;
    pfn_socket p_socket;
    pfn_bind p_bind;
    pfn_listen p_listen;
    WSADATA wd;
    struct sockaddr_in sa;
    SOCKET s;
    if (!ws2) {
        dbg(L"CEAGENT: no ws2.dll");
        return INVALID_SOCKET;
    }
    p_WSAStartup = (pfn_WSAStartup)GetProcAddressW(ws2, L"WSAStartup");
    p_socket = (pfn_socket)GetProcAddressW(ws2, L"socket");
    p_bind = (pfn_bind)GetProcAddressW(ws2, L"bind");
    p_listen = (pfn_listen)GetProcAddressW(ws2, L"listen");
    p_recv = (pfn_recv)GetProcAddressW(ws2, L"recv");
    p_send = (pfn_send)GetProcAddressW(ws2, L"send");
    p_closesocket = (pfn_closesocket)GetProcAddressW(ws2, L"closesocket");
    if (!p_WSAStartup || !p_socket || !p_bind || !p_listen || !p_recv || !p_send || !p_closesocket)
        return INVALID_SOCKET;
    p_WSAStartup(MAKEWORD(2, 2), &wd);
    s = p_socket(AF_INET, SOCK_STREAM, 0);
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_port = (unsigned short)(((port & 0xff) << 8) | ((port >> 8) & 0xff));
    sa.sin_addr.s_addr = 0; /* INADDR_ANY */
    if (p_bind(s, (struct sockaddr *)&sa, sizeof sa) != 0 || p_listen(s, 1) != 0) {
        dbg(L"CEAGENT: bind/listen failed");
        return INVALID_SOCKET;
    }
    return s;
}

/* ---- framing ----------------------------------------------------------- */
static int send_frame(transport_t *t, BYTE status, const void *payload, DWORD len)
{
    BYTE hdr[9];
    *(DWORD *)hdr = MAGIC;
    hdr[4] = status;
    memcpy(hdr + 5, &len, 4);
    if (!t->write(hdr, 9))
        return 0;
    return len ? t->write(payload, len) : 1;
}

static int recv_frame(transport_t *t, BYTE *cmd, BYTE *payload, DWORD *len)
{
    BYTE hdr[9];
    DWORD magic;
    /* resynchronise on the magic byte by byte */
    for (;;) {
        if (!t->read(hdr, 1))
            return 0;
        if (hdr[0] != 'C')
            continue;
        if (!t->read(hdr + 1, 8))
            return 0;
        memcpy(&magic, hdr, 4);
        if (magic == MAGIC)
            break;
    }
    *cmd = hdr[4];
    memcpy(len, hdr + 5, 4);
    if (*len > MAXPAYLOAD)
        return 0;
    return *len ? t->read(payload, *len) : 1;
}

static int ok(transport_t *t) { return send_frame(t, 0, NULL, 0); }
static int err(transport_t *t, DWORD code)
{
    if (code == 0 || code > 254)
        code = 1;
    return send_frame(t, (BYTE)code, NULL, 0);
}

/* ---- commands ---------------------------------------------------------- */
static HANDLE g_put = INVALID_HANDLE_VALUE;

static void cmd_put(transport_t *t, BYTE *p, DWORD len)
{
    const wchar_t *path = (const wchar_t *)p;
    if (g_put != INVALID_HANDLE_VALUE)
        CloseHandle(g_put);
    g_put = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (g_put == INVALID_HANDLE_VALUE) {
        dbg(L"CEAGENT: put %s failed (%d)", path, GetLastError());
        err(t, GetLastError());
        return;
    }
    dbg(L"CEAGENT: put %s", path);
    ok(t);
}

static void cmd_chunk(transport_t *t, BYTE *p, DWORD len)
{
    DWORD n;
    if (g_put == INVALID_HANDLE_VALUE || !WriteFile(g_put, p, len, &n, NULL) || n != len) {
        err(t, ERROR_WRITE_FAULT);
        return;
    }
    ok(t);
}

static void cmd_close(transport_t *t)
{
    if (g_put != INVALID_HANDLE_VALUE)
        CloseHandle(g_put);
    g_put = INVALID_HANDLE_VALUE;
    ok(t);
}

static void cmd_get(transport_t *t, BYTE *p, BYTE *buf)
{
    const wchar_t *path = (const wchar_t *)p;
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    DWORD size, n;
    if (h == INVALID_HANDLE_VALUE) {
        err(t, GetLastError());
        return;
    }
    size = GetFileSize(h, NULL);
    send_frame(t, 0, &size, 4);
    while (ReadFile(h, buf, 32768, &n, NULL) && n > 0)
        if (!send_frame(t, CMD_CHUNK, buf, n))
            break;
    send_frame(t, CMD_CLOSE, NULL, 0);
    CloseHandle(h);
}

static void cmd_run(transport_t *t, BYTE *p, DWORD len)
{
    DWORD wait_ms, result[2];
    wchar_t *cmd, *app, *args;
    PROCESS_INFORMATION pi;
    if (len < 6) {
        err(t, ERROR_INVALID_PARAMETER);
        return;
    }
    memcpy(&wait_ms, p, 4);
    cmd = (wchar_t *)(p + 4);
    /* first token (optionally quoted) is the executable */
    if (*cmd == L'"') {
        app = cmd + 1;
        args = app;
        while (*args && *args != L'"')
            args++;
        if (*args) *args++ = 0;
    } else {
        app = cmd;
        args = app;
        while (*args && *args != L' ')
            args++;
        if (*args) *args++ = 0;
    }
    while (*args == L' ')
        args++;
    dbg(L"CEAGENT: run '%s' '%s'", app, args);
    if (!CreateProcessW(app, *args ? args : NULL, NULL, NULL, FALSE, 0, NULL, NULL, NULL, &pi)) {
        err(t, GetLastError());
        return;
    }
    result[0] = pi.dwProcessId;
    result[1] = 0xFFFFFFFF;
    if (wait_ms) {
        if (WaitForSingleObject(pi.hProcess, wait_ms) == WAIT_OBJECT_0)
            GetExitCodeProcess(pi.hProcess, &result[1]);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    send_frame(t, 0, result, 8);
}

static void cmd_list(transport_t *t, BYTE *p, BYTE *buf)
{
    wchar_t pattern[MAX_PATH + 4];
    WIN32_FIND_DATAW fd;
    HANDLE h;
    wchar_t *out = (wchar_t *)buf;
    int used = 0, cap = MAXPAYLOAD / 2 - MAX_PATH - 64;
    wsprintfW(pattern, L"%s\\*", (const wchar_t *)p);
    h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) {
        err(t, GetLastError());
        return;
    }
    do {
        used += wsprintfW(out + used, L"%s\t%u\t%x\n", fd.cFileName, fd.nFileSizeLow, fd.dwFileAttributes);
    } while (used < cap && FindNextFileW(h, &fd));
    FindClose(h);
    send_frame(t, 0, out, used * 2);
}

/* ---- main loop --------------------------------------------------------- */
static void serve(transport_t *t)
{
    BYTE *payload = (BYTE *)LocalAlloc(LMEM_FIXED, MAXPAYLOAD + 16);
    BYTE *buf = (BYTE *)LocalAlloc(LMEM_FIXED, MAXPAYLOAD + 16);
    BYTE cmd;
    DWORD len;
    for (;;) {
        if (!recv_frame(t, &cmd, payload, &len))
            break;
        if (len < MAXPAYLOAD) { payload[len] = 0; payload[len + 1] = 0; }
        switch (cmd) {
        case CMD_PING: send_frame(t, 0, L"ceagent 1", 20); break;
        case CMD_PUT: cmd_put(t, payload, len); break;
        case CMD_CHUNK: cmd_chunk(t, payload, len); break;
        case CMD_CLOSE: cmd_close(t); break;
        case CMD_GET: cmd_get(t, payload, buf); break;
        case CMD_RUN: cmd_run(t, payload, len); break;
        case CMD_LIST: cmd_list(t, payload, buf); break;
        case CMD_DEL: DeleteFileW((wchar_t *)payload) ? ok(t) : err(t, GetLastError()); break;
        case CMD_MKDIR: CreateDirectoryW((wchar_t *)payload, NULL) ? ok(t) : err(t, GetLastError()); break;
        case CMD_REBOOT: ok(t); return;
        default: err(t, ERROR_INVALID_FUNCTION); break;
        }
    }
    LocalFree(payload);
    LocalFree(buf);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR cmdline, int show)
{
    transport_t t;
    const wchar_t *where = (cmdline && *cmdline) ? cmdline : L"COM1:";
    dbg(L"CEAGENT: starting on %s", where);
    if (where[0] == L't' && where[1] == L'c' && where[2] == L'p' && where[3] == L':') {
        int port = 0;
        const wchar_t *q = where + 4;
        while (*q >= L'0' && *q <= L'9')
            port = port * 10 + (*q++ - L'0');
        SOCKET ls = tcp_listen(port ? port : 7777);
        if (ls == INVALID_SOCKET)
            return 1;
        t.read = tcp_read;
        t.write = tcp_write;
        for (;;) {
            g_sock = ((pfn_accept)GetProcAddressW(GetModuleHandleW(L"ws2.dll"), L"accept"))(ls, NULL, NULL);
            if (g_sock == INVALID_SOCKET)
                break;
            dbg(L"CEAGENT: client connected");
            serve(&t);
            p_closesocket(g_sock);
        }
        return 0;
    }
    if (!com_open(where))
        return 1;
    t.read = com_read;
    t.write = com_write;
    for (;;) {
        serve(&t);          /* returns only on REBOOT or a transport error */
        PurgeComm(g_com, PURGE_RXCLEAR | PURGE_TXCLEAR);
        Sleep(200);
    }
}
