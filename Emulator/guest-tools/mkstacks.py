import sys
src=open(sys.argv[0].replace("mkstacks","mkexe")).read().split("asm='''")[0]
m={}; exec(src, m)
# locals (all relative to sp, frame 0x900 bytes):
#  0x000 call args scratch (0x40)
#  0x040 PROCESSENTRY32 (564 -> reserve 0x240)
#  0x280 THREADENTRY32 (36 -> 0x40)
#  0x2c0 MODULEENTRY32 (1068 -> 0x440)
#  0x700 frames (32*4=0x80)
#  0x780 text buffer (0x180)
asm='''
    push {r4-r11, lr}
    sub sp, sp, #0x900
    mov r11, #6
outer:
    ldr r0, =$hdr
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #2
    mov r1, #0
    ldr r4, =@CreateToolhelp32Snapshot
    ldr r4, [r4]
    blx r4
    mov r5, r0              @ r5 = process snapshot
    mov r0, #564
    add r1, sp, #0x40
    str r0, [r1]
    mov r0, r5
    ldr r4, =@Process32First
    ldr r4, [r4]
    blx r4
ploop:
    cmp r0, #0
    beq pdone
    add r6, sp, #0x40
    ldr r7, [r6, #8]        @ pid
    @ print process
    add r3, r6, #36         @ szExeFile
    mov r2, r7
    ldr r1, =$fproc
    add r0, sp, #0x780
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x780
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    @ modules of this process
    mov r0, #0x40000000
    orr r0, r0, #8
    mov r1, r7
    ldr r4, =@CreateToolhelp32Snapshot
    ldr r4, [r4]
    blx r4
    mov r8, r0
    cmn r8, #1
    beq mdone
    ldr r0, =1068
    add r1, sp, #0x2c0
    str r0, [r1]
    mov r0, r8
    ldr r4, =@Module32First
    ldr r4, [r4]
    blx r4
mloop:
    cmp r0, #0
    beq mclose
    add r6, sp, #0x2c0
    ldr r2, [r6, #20]       @ modBaseAddr
    ldr r3, [r6, #24]       @ modBaseSize
    add r1, r6, #32         @ szModule
    str r1, [sp]
    ldr r1, =$fmod
    add r0, sp, #0x780
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x780
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, r8
    add r1, sp, #0x2c0
    ldr r4, =@Module32Next
    ldr r4, [r4]
    blx r4
    b mloop
mclose:
    mov r0, r8
    ldr r4, =@CloseToolhelp32Snapshot
    ldr r4, [r4]
    blx r4
mdone:
    @ threads: snapshot all threads, filter by owner pid
    mov r0, #4
    mov r1, #0
    ldr r4, =@CreateToolhelp32Snapshot
    ldr r4, [r4]
    blx r4
    mov r8, r0
    cmn r8, #1
    beq tdone
    mov r0, #36
    add r1, sp, #0x280
    str r0, [r1]
    mov r0, r8
    ldr r4, =@Thread32First
    ldr r4, [r4]
    blx r4
tloop:
    cmp r0, #0
    beq tclose
    add r6, sp, #0x280
    ldr r1, [r6, #12]       @ owner pid
    cmp r1, r7
    bne tnext
    ldr r9, [r6, #8]        @ tid
    mov r0, #0
    mov r1, #0
    mov r2, r9
    ldr r4, =@OpenThread
    ldr r4, [r4]
    blx r4
    mov r10, r0
    cmp r10, #0
    beq tnext
    mov r0, r10
    mov r1, #24
    add r2, sp, #0x700
    mov r3, #0
    mov r4, #0
    str r4, [sp]
    ldr r4, =@GetThreadCallStack
    ldr r4, [r4]
    blx r4
    mov r6, r0              @ frame count
    cmp r6, #0
    bne havecs
    @ GetThreadContext(h, ctx at sp+0x600): ContextFlags=0x43
    mov r0, #0x43
    add r1, sp, #0x600
    str r0, [r1]
    mov r0, r10
    ldr r4, =@GetThreadContext
    ldr r4, [r4]
    blx r4
    add r1, sp, #0x600
    ldr r2, [r1, #0x40]     @ Pc
    ldr r3, [r1, #0x3c]     @ Lr
    ldr r0, [r1, #0x38]     @ Sp
    str r0, [sp]
    ldr r1, =$fctx
    add r0, sp, #0x780
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x780
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
havecs:
    @ print "EMUSTK tid=%08x n=%d: " then frames one per line
    mov r3, r6
    mov r2, r9
    ldr r1, =$fthr
    add r0, sp, #0x780
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x780
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r4, #0
floop:
    cmp r4, r6
    bge fdone
    cmp r4, #24
    bge fdone
    add r1, sp, #0x700
    ldr r3, [r1, r4, lsl #2]
    mov r2, r4
    ldr r1, =$fframe
    add r0, sp, #0x780
    str r4, [sp, #0x8fc]
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x780
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    ldr r4, [sp, #0x8fc]
    add r4, r4, #1
    b floop
fdone:
    mov r0, r10
    ldr r4, =@CloseHandle
    ldr r4, [r4]
    blx r4
tnext:
    mov r0, r8
    add r1, sp, #0x280
    ldr r4, =@Thread32Next
    ldr r4, [r4]
    blx r4
    b tloop
tclose:
    mov r0, r8
    ldr r4, =@CloseToolhelp32Snapshot
    ldr r4, [r4]
    blx r4
tdone:
    mov r0, r5
    add r1, sp, #0x40
    ldr r4, =@Process32Next
    ldr r4, [r4]
    blx r4
    b ploop
pdone:
    mov r0, r5
    ldr r4, =@CloseToolhelp32Snapshot
    ldr r4, [r4]
    blx r4
    mov r0, #3000
    ldr r4, =@Sleep
    ldr r4, [r4]
    blx r4
    subs r11, r11, #1
    bne outer
    mov r0, #0
    add sp, sp, #0x900
    pop {r4-r11, pc}
'''
m["build"](sys.argv[1], asm, {"COREDLL.dll":["OutputDebugStringW","wsprintfW","Sleep","OpenThread","GetThreadCallStack","GetThreadContext","CloseHandle"],
   "toolhelp.dll":["CreateToolhelp32Snapshot","Process32First","Process32Next","Module32First","Module32Next","Thread32First","Thread32Next","CloseToolhelp32Snapshot"]},
   {"hdr":"EMUSTK ===== sample","fproc":"EMUSTK proc pid=%08x name=%s","fmod":"EMUSTK   mod base=%08x size=%08x %s","fthr":"EMUSTK   thread tid=%08x frames=%d","fframe":"EMUSTK     f%02d=%08x","fctx":"EMUSTK     ctx pc=%08x lr=%08x sp=%08x"})
