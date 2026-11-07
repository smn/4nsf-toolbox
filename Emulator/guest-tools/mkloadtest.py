"""loadtest.exe PATH: LoadLibraryW(PATH) and report handle + GetLastError
in a message box and on the debug serial line (EMULOAD: ...)."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
import importlib.util
spec=importlib.util.spec_from_file_location("mkexe", sys.argv[0].replace("mkloadtest","mkexe")); m=importlib.util.module_from_spec(spec)
src=open(sys.argv[0].replace("mkloadtest","mkexe")).read().split("asm='''")[0]
exec(src, m.__dict__)
asm='''
    push {r4-r8, lr}
    sub sp, sp, #0x400
    ldr r4, =@GetCommandLineW
    ldr r4, [r4]
    blx r4
    mov r5, r0              @ r5 = path (command line as given by the .lnk)
    @ skip leading quote and spaces
skip:
    ldrh r1, [r5]
    cmp r1, #0x22
    cmpne r1, #0x20
    addeq r5, r5, #2
    beq skip
    @ strip a trailing quote
    mov r6, r5
find_end:
    ldrh r1, [r6]
    cmp r1, #0
    addne r6, r6, #2
    bne find_end
    sub r6, r6, #2
    ldrh r1, [r6]
    cmp r1, #0x22
    moveq r1, #0
    strheq r1, [r6]
    mov r0, r5
    ldr r4, =@LoadLibraryW
    ldr r4, [r4]
    blx r4
    mov r7, r0
    ldr r4, =@GetLastError
    ldr r4, [r4]
    blx r4
    mov r8, r0
    mov r2, r5              @ %s = path
    mov r3, r7              @ %08x = handle
    ldr r1, =$fmt
    add r0, sp, #0x20
    @ wsprintfW(buf, fmt, path, h, err): 5th arg on the stack
    str r8, [sp]
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x20
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r3, #0
    ldr r2, =$title
    add r1, sp, #0x20
    mov r0, #0
    ldr r4, =@MessageBoxW
    ldr r4, [r4]
    blx r4
    mov r0, #0
    add sp, sp, #0x400
    pop {r4-r8, pc}
'''
m.build(sys.argv[1], asm, {"COREDLL.dll":["GetCommandLineW","LoadLibraryW","GetLastError","wsprintfW","OutputDebugStringW","MessageBoxW"]},
        {"fmt":"EMULOAD: '%s' -> h=%08x err=%d","title":"loadtest"})
