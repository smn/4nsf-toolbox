import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
import importlib.util
spec=importlib.util.spec_from_file_location("mkexe", sys.argv[0].replace("mkwintest","mkexe")); m=importlib.util.module_from_spec(spec)
src=open(sys.argv[0].replace("mkwintest","mkexe")).read().split("asm='''")[0]
exec(src, m.__dict__)
asm='''
    push {r4-r8, lr}
    sub sp, sp, #0x400
    ldr r4, =@GetDesktopWindow
    ldr r4, [r4]
    blx r4
    mov r1, #5
    ldr r4, =@GetWindow
    ldr r4, [r4]
    blx r4
    mov r5, r0
loop:
    cmp r5, #0
    beq done
    @ class name -> sp+0x100
    mov r0, r5
    add r1, sp, #0x100
    mov r2, #64
    ldr r4, =@GetClassNameW
    ldr r4, [r4]
    blx r4
    @ title -> sp+0x200
    mov r0, r5
    add r1, sp, #0x200
    mov r2, #64
    ldr r4, =@GetWindowTextW
    ldr r4, [r4]
    blx r4
    mov r0, r5
    ldr r4, =@IsWindowVisible
    ldr r4, [r4]
    blx r4
    mov r6, r0
    mov r0, r5
    add r1, sp, #0x300
    ldr r4, =@GetWindowRect
    ldr r4, [r4]
    blx r4
    @ wsprintfW(sp, fmt, hwnd, class, title, vis, l, t, r, b)
    ldr r0, [sp, #0x30c]
    str r0, [sp, #0x14]
    ldr r0, [sp, #0x308]
    str r0, [sp, #0x10]
    ldr r0, [sp, #0x304]
    str r0, [sp, #0xc]
    ldr r0, [sp, #0x300]
    str r0, [sp, #8]
    str r6, [sp, #4]
    add r0, sp, #0x200
    str r0, [sp]
    add r3, sp, #0x100
    mov r2, r5
    ldr r1, =$fmt
    mov r0, sp
    add r0, r0, #0x20
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x20
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, r5
    mov r1, #2
    ldr r4, =@GetWindow
    ldr r4, [r4]
    blx r4
    mov r5, r0
    b loop
done:
    ldr r0, =$end
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #0
    add sp, sp, #0x400
    pop {r4-r8, pc}
'''
m.build(sys.argv[1], asm, {"COREDLL.dll":["GetDesktopWindow","GetWindow","GetClassNameW","GetWindowTextW","IsWindowVisible","GetWindowRect","wsprintfW","OutputDebugStringW"]},
        {"fmt":"EMUWIN: hwnd=%08x class='%s' title='%s' vis=%d rect=%d,%d,%d,%d","end":"EMUWIN: end"})
