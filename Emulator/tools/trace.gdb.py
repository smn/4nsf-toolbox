import gdb, struct
LOG=open(gdb.parameter("logging file") or "/tmp/trace.log","a")
def wstr(addr, maxlen=200):
    try:
        if addr==0: return "NULL"
        mem=gdb.selected_inferior().read_memory(addr, maxlen*2).tobytes()
        s=mem.decode("utf-16le","replace")
        return repr(s.split("\0")[0])
    except Exception as e: return f"<bad {addr:#x}>"
def reg(n): return int(gdb.parse_and_eval(f"${n}")) & 0xffffffff
def stack(i):
    sp=reg("sp"); return struct.unpack("<I", gdb.selected_inferior().read_memory(sp+4*i,4).tobytes())[0]
def h(): return f"h={reg('r0'):#x}"
def lrok():
    lr=reg("lr"); return lr<0x40000000 or 0x41200000<=lr<0x41800000
HOOKS2={
 "CreateThread": lambda: f"start={reg('r2'):#x} param={reg('r3'):#x}",
 "WaitForSingleObject": lambda: f"h={reg('r0'):#x} ms={reg('r1'):#x}",
 "WaitForMultipleObjects": lambda: f"n={reg('r0')} ms={reg('r3'):#x}",
 "EventModify": lambda: f"h={reg('r0'):#x} action={reg('r1')}",
 "CreateFontIndirectW": lambda: f"name={wstr(reg('r0')+28)} height={struct.unpack('<i',gdb.selected_inferior().read_memory(reg('r0'),4).tobytes())[0]}",
 "GetDeviceCaps": lambda: f"hdc={reg('r0'):#x} index={reg('r1')}",
 "ReadFile": lambda: f"h={reg('r0'):#x} n={reg('r2')}",
 "SetFilePointer": lambda: f"h={reg('r0'):#x} off={reg('r1')}",
 "GetFileSize": h, "ExtEscape": lambda: f"hdc={reg('r0'):#x} esc={reg('r1')}",
 "CreateDCW": lambda: f"drv={wstr(reg('r0'))}", "GetSystemMetrics": lambda: f"idx={reg('r0')}",
 "CreateCompatibleDC": h, "SelectObject": lambda: f"hdc={reg('r0'):#x} obj={reg('r1'):#x}",
 "CreateDIBSection": lambda: f"hdc={reg('r0'):#x} bmi={reg('r1'):#x}", "GetDC": lambda: f"hwnd={reg('r0'):#x}",
 "MapViewOfFile": h, "OpenFileMappingW": lambda: f"name={wstr(reg('r2'))}",
 "CreateSemaphoreW": lambda: f"init={reg('r1')} max={reg('r2')} name={wstr(reg('r3'))}", "ReleaseSemaphore": h,
 "SetThreadPriority": lambda: f"h={reg('r0'):#x} prio={reg('r1')}", "CeSetThreadPriority": lambda: f"h={reg('r0'):#x} prio={reg('r1')}",
 "TerminateThread": h, "GetExitCodeThread": h, "MsgWaitForMultipleObjectsEx": lambda: f"n={reg('r0')} ms={reg('r2'):#x}",
 "GetModuleFileNameW": h, "RegQueryValueExW": lambda: f"hkey={reg('r0'):#x} val={wstr(reg('r1'))}",
 "RegCreateKeyExW": lambda: f"hkey={reg('r0'):#x} sub={wstr(reg('r1'))}", "GetFileAttributesW": lambda: f"name={wstr(reg('r0'))}",
 "FindFirstFileW": lambda: f"name={wstr(reg('r0'))}", "CreateDirectoryW": lambda: f"name={wstr(reg('r0'))}",
 "DeleteFileW": lambda: f"name={wstr(reg('r0'))}", "WriteFile": lambda: f"h={reg('r0'):#x} n={reg('r2')}",
 "SetWindowPos": lambda: f"hwnd={reg('r0'):#x} x={reg('r2')} y={reg('r3')} cx={stack(0)} cy={stack(1)} flags={stack(2):#x}",
 "MoveWindow": lambda: f"hwnd={reg('r0'):#x} x={reg('r1')} y={reg('r2')} w={reg('r3')} h={stack(0)}",
 "UpdateWindow": lambda: f"hwnd={reg('r0'):#x}", "InvalidateRect": lambda: f"hwnd={reg('r0'):#x}",
 "SetForegroundWindow": lambda: f"hwnd={reg('r0'):#x}", "RegisterClassW": lambda: f"name={wstr(struct.unpack('<I',gdb.selected_inferior().read_memory(reg('r0')+36,4).tobytes())[0])}",
 "PostMessageW": lambda: f"hwnd={reg('r0'):#x} msg={reg('r1'):#x} w={reg('r2'):#x} l={reg('r3'):#x}",
 "SendMessageW": lambda: f"hwnd={reg('r0'):#x} msg={reg('r1'):#x} w={reg('r2'):#x} l={reg('r3'):#x}",
 "socket": lambda: f"af={reg('r0')} type={reg('r1')}", "bind": lambda: f"s={reg('r0')}", "WSAStartup": lambda: "",
 "Sleep": lambda: f"ms={reg('r0')}",
 "PostQuitMessage": lambda: f"code={reg('r0')}", "DestroyWindow": lambda: f"hwnd={reg('r0'):#x}",
 "GetSystemPowerStatusEx": lambda: f"buf={reg('r0'):#x} update={reg('r1')}",
}
HOOKS={
 "CreateFileW":      lambda: f"name={wstr(reg('r0'))} access={reg('r1'):#x}",
 "LoadLibraryW":     lambda: f"name={wstr(reg('r0'))}",
 "LoadLibraryExW":   lambda: f"name={wstr(reg('r0'))}",
 "RegOpenKeyExW":    lambda: f"hkey={reg('r0'):#x} sub={wstr(reg('r1'))}",
 "CreateEventW":     lambda: f"manual={reg('r1')} init={reg('r2')} name={wstr(reg('r3'))}",
 "OpenEventW":       lambda: f"name={wstr(reg('r2'))}",
 "CreateMutexW":     lambda: f"name={wstr(reg('r2'))}",
 "CreateFileMappingW": lambda: f"name={wstr(stack(1))}",
 "CreateProcessW":   lambda: f"app={wstr(reg('r0'))} cmd={wstr(reg('r1'))}",
 "FindWindowW":      lambda: f"class={wstr(reg('r0'))} title={wstr(reg('r1'))}",
 "RegisterWindowMessageW": lambda: f"name={wstr(reg('r0'))}",
 "timeSetEvent":     lambda: f"delay={reg('r0')} res={reg('r1')} cb={reg('r2'):#x} user={reg('r3'):#x} flags={stack(0):#x}",
 "timeKillEvent":    lambda: f"id={reg('r0')}",
 "ChangeDisplaySettingsEx": lambda: f"dev={wstr(reg('r0'))} devmode={reg('r1'):#x} flags={reg('r3'):#x}",
 "BitBlt":           lambda: f"hdc={reg('r0'):#x} x={reg('r1')} y={reg('r2')} w={reg('r3')} h={stack(0)} src={stack(1):#x}",
 "StretchBlt":       lambda: f"hdc={reg('r0'):#x} x={reg('r1')} y={reg('r2')} w={reg('r3')}",
 "MessageBoxW":      lambda: f"text={wstr(reg('r1'))} caption={wstr(reg('r2'))}",
 "ShowWindow":       lambda: f"hwnd={reg('r0'):#x} cmd={reg('r1')}",
 "CreateWindowExW":  lambda: f"class={wstr(reg('r1'))} title={wstr(reg('r2'))} style={reg('r3'):#x}",
 "TerminateProcess": lambda: f"h={reg('r0'):#x} code={reg('r1')}",
 "ExitThread":       lambda: f"code={reg('r0')}",
 "DeviceIoControl":  lambda: f"h={reg('r0'):#x} code={reg('r1'):#x}",
 "SetTimer":         lambda: f"hwnd={reg('r0'):#x} id={reg('r1')} ms={reg('r2')}",
 "sendto":           lambda: f"s={reg('r0')} len={reg('r2')}",
 "recvfrom":         lambda: f"s={reg('r0')} len={reg('r2')}",
 "GetProcAddressW":  lambda: f"mod={reg('r0'):#x} name={wstr(reg('r1'))}",
}
HOOKS.update(HOOKS2)
class Hook(gdb.Breakpoint):
    def __init__(self, name, addr):
        super().__init__(f"*{addr:#x}", internal=True)
        self.name=name
    def stop(self):
        if self.name in HOOKS2 and not lrok(): return False
        try: info=HOOKS[self.name]()
        except Exception as e: info=f"<err {e}>"
        LOG.write(f"{self.name} lr={reg('lr'):#x} {info}\n"); LOG.flush()
        return False
import os
for line in open(os.environ["COREDLL_EXPORTS"]):
    a,n=line.split()
    if n in HOOKS: Hook(n, int(a,16))
# mmtimer exports (image addresses)
Hook("timeSetEvent",0x404819bc); Hook("timeKillEvent",0x40481b4c)
HOOKS["timeGetDevCaps"]=lambda: ""; HOOKS["timeBeginPeriod"]=lambda: f"ms={reg('r0')}"
Hook("timeGetDevCaps",0x40481538); Hook("timeBeginPeriod",0x404813e8)
# ws2 sendto/recvfrom not hooked by name list (in ws2.dll); skip
LOG.write("=== hooks installed\n"); LOG.flush()
gdb.execute("continue")
