import sys
src=open(sys.argv[0].replace("mksock2","mkexe")).read().split("asm='''")[0]
m={}; exec(src, m)
# helper macro: print string then value
def P(label, reg="r0"):
    return f'''
    mov r2, {reg}
    ldr r1, =$f_{label}
    add r0, sp, #0x80
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x80
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
'''
asm=f'''
    push {{r4-r11, lr}}
    sub sp, sp, #0x200
    mov r0, #0x202
    add r1, sp, #0x100
    ldr r4, =@WSAStartup
    ldr r4, [r4]
    blx r4
    {P("wsa")}
    @ sockaddr at sp+0x40: AF_INET, port 27011, 127.0.0.1
    ldr r2, =0x83690002
    str r2, [sp, #0x40]
    ldr r2, =0x0100007f
    str r2, [sp, #0x44]
    mov r2, #0
    str r2, [sp, #0x48]
    str r2, [sp, #0x4c]
    mov r0, #2
    mov r1, #1
    mov r2, #6
    ldr r4, =@socket
    ldr r4, [r4]
    blx r4
    mov r5, r0
    {P("srv", "r5")}
    mov r0, r5
    add r1, sp, #0x40
    mov r2, #16
    ldr r4, =@bind
    ldr r4, [r4]
    blx r4
    {P("bind")}
    mov r0, r5
    mov r1, #5
    ldr r4, =@listen
    ldr r4, [r4]
    blx r4
    {P("listen")}
    mov r0, #2
    mov r1, #1
    mov r2, #6
    ldr r4, =@socket
    ldr r4, [r4]
    blx r4
    mov r6, r0
    mov r0, r6
    add r1, sp, #0x40
    mov r2, #16
    ldr r4, =@connect
    ldr r4, [r4]
    blx r4
    {P("connect")}
    mov r0, r5
    mov r1, #0
    mov r2, #0
    ldr r4, =@accept
    ldr r4, [r4]
    blx r4
    mov r7, r0
    {P("accept", "r7")}
    mov r0, r6
    add r1, sp, #0x60
    mov r2, #1
    mov r3, #0
    ldr r4, =@send
    ldr r4, [r4]
    blx r4
    {P("send")}
    mov r0, r7
    add r1, sp, #0x68
    mov r2, #1
    mov r3, #0
    ldr r4, =@recv
    ldr r4, [r4]
    blx r4
    {P("recv")}
    mov r0, r7
    mov r1, #2
    ldr r4, =@shutdown
    ldr r4, [r4]
    blx r4
    {P("shutdown")}
    mov r0, r7
    ldr r4, =@closesocket
    ldr r4, [r4]
    blx r4
    mov r0, r6
    ldr r4, =@closesocket
    ldr r4, [r4]
    blx r4
    mov r0, r5
    ldr r4, =@closesocket
    ldr r4, [r4]
    blx r4
    {P("closed")}
    mov r0, #0
    add sp, sp, #0x200
    pop {{r4-r11, pc}}
'''
strings={f"f_{k}":f"EMUTEST2: {k} -> %d" for k in ("wsa","srv","bind","listen","connect","accept","send","recv","shutdown","closed")}
m["build"](sys.argv[1], asm, {"COREDLL.dll":["OutputDebugStringW","wsprintfW"],"WINSOCK.dll":["WSAStartup","socket","bind","listen","connect","accept","send","recv","shutdown","closesocket"]}, strings)
