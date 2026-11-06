import sys
src=open(sys.argv[0].replace("mktimertest","mkexe")).read().split("asm='''")[0]
m={}; exec(src, m)
out, dll = sys.argv[1], sys.argv[2]
asm='''
    push {r4-r7, lr}
    sub sp, sp, #0x100
    ldr r0, =$s0
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #1
    ldr r4, =@timeBeginPeriod
    ldr r4, [r4]
    blx r4
    @ timeSetEvent(500, 1, cb, 0x1234, TIME_PERIODIC=1)
    mov r0, #500
    mov r1, #1
    ldr r2, =cb
    ldr r3, =0x1234
    mov r4, #1
    str r4, [sp]
    ldr r4, =@timeSetEvent
    ldr r4, [r4]
    blx r4
    mov r5, r0
    ldr r1, =$s1
    mov r2, r5
    add r0, sp, #0x40
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x40
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #6000
    ldr r4, =@Sleep
    ldr r4, [r4]
    blx r4
    mov r0, r5
    ldr r4, =@timeKillEvent
    ldr r4, [r4]
    blx r4
    ldr r1, =$s2
    mov r2, r0
    add r0, sp, #0x40
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x40
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #0
    add sp, sp, #0x100
    pop {r4-r7, pc}
cb:
    push {r4, lr}
    ldr r0, =$tick
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    pop {r4, pc}
'''
m["build"](out, asm, {"COREDLL.dll":["OutputDebugStringW","wsprintfW","Sleep"], dll:["timeSetEvent","timeKillEvent","timeBeginPeriod"]},
   {"s0":"EMUTIMER: start "+dll,"s1":"EMUTIMER: timeSetEvent -> id=%d","s2":"EMUTIMER: timeKillEvent -> %d","tick":"EMUTIMER: tick"})
