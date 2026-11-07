import sys
src=open(sys.argv[0].replace("mklaunch","mkexe")).read().split("asm='''")[0]
m={}; exec(src, m)
out=sys.argv[1]; procs=sys.argv[2:]   # pairs: exe|args
launch=""
strings={"fmt":"EMUWIN: hwnd=%08x class='%s' title='%s' vis=%d rect=%d,%d,%d,%d","end":"EMUWIN: ---","start":"EMUWIN: launching"}
for i,p in enumerate(procs):
    exe,_,args=p.partition("|")
    if exe=="hidetaskbar":
        # the Explorer taskbar covers the bottom 26 px of the 480x272 screen,
        # where the VW apps and Navigon put their button bars
        strings["taskbar"]="HHTaskBar"
        launch+=f'''
    ldr r0, =$taskbar
    mov r1, #0
    ldr r4, =@FindWindowW
    ldr r4, [r4]
    blx r4
    cmp r0, #0
    movne r1, #0
    ldrne r4, =@ShowWindow
    ldrne r4, [r4]
    blxne r4
'''
        continue
    if exe=="mkdir":
        strings[f"dir{i}"]=args
        launch+=f'''
    ldr r0, =$dir{i}
    mov r1, #0
    ldr r4, =@CreateDirectoryW
    ldr r4, [r4]
    blx r4
'''
        continue
    strings[f"exe{i}"]=exe; strings[f"arg{i}"]=args
    launch+=f'''
    ldr r0, =$exe{i}
    ldr r1, =$arg{i}
    mov r2, #0
    mov r3, #0
    mov r4, #0
    str r4, [sp]
    str r4, [sp, #4]
    str r4, [sp, #8]
    str r4, [sp, #12]
    str r4, [sp, #16]
    add r4, sp, #0x380
    str r4, [sp, #20]
    ldr r4, =@CreateProcessW
    ldr r4, [r4]
    blx r4
    ldr r0, =$start
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #1500
    ldr r4, =@Sleep
    ldr r4, [r4]
    blx r4
'''
asm=f'''
    push {{r4-r8, lr}}
    sub sp, sp, #0x400
    {launch}
    mov r8, #12
outer:
    mov r0, #10000
    ldr r4, =@Sleep
    ldr r4, [r4]
    blx r4
    ldr r0, =cb
    mov r1, #0
    ldr r4, =@EnumWindows
    ldr r4, [r4]
    blx r4
    b done
cb:
    push {{r4-r6, lr}}
    sub sp, sp, #0x400
    mov r5, r0
    mov r0, r5
    add r1, sp, #0x100
    mov r2, #64
    ldr r4, =@GetClassNameW
    ldr r4, [r4]
    blx r4
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
    add r0, sp, #0x20
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x20
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #1
    add sp, sp, #0x400
    pop {{r4-r6, pc}}
done:
    ldr r0, =$end
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    subs r8, r8, #1
    bne outer
    mov r0, #0
    add sp, sp, #0x400
    pop {{r4-r8, pc}}
'''
m["build"](out, asm, {"COREDLL.dll":["CreateProcessW","CreateDirectoryW","FindWindowW","ShowWindow","Sleep","EnumWindows","GetClassNameW","GetWindowTextW","IsWindowVisible","GetWindowRect","wsprintfW","OutputDebugStringW"]}, strings)
