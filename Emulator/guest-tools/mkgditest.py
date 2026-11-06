import sys
src=open(sys.argv[0].replace("mkgditest","mkexe")).read().split("asm='''")[0]
m={}; exec(src, m)
# Create a window 1024x600, fill a 16bpp DIB section 480x272 with a gradient, BitBlt it at (100,100) every 500ms for 20s, log results.
asm='''
    push {r4-r11, lr}
    sub sp, sp, #0x300
    @ WNDCLASS at sp+0x100: style, lpfnWndProc, cbClsExtra, cbWndExtra, hInstance, hIcon, hCursor, hbrBackground, lpszMenuName, lpszClassName
    add r4, sp, #0x100
    mov r0, #0
    str r0, [r4]
    ldr r0, =@DefWindowProcW
    ldr r0, [r0]
    str r0, [r4, #4]
    mov r0, #0
    str r0, [r4, #8]
    str r0, [r4, #12]
    str r0, [r4, #16]
    str r0, [r4, #20]
    str r0, [r4, #24]
    str r0, [r4, #28]
    str r0, [r4, #32]
    ldr r0, =$cls
    str r0, [r4, #36]
    mov r0, r4
    ldr r4, =@RegisterClassW
    ldr r4, [r4]
    blx r4
    @ CreateWindowExW(0, cls, title, WS_VISIBLE|WS_POPUP=0x90000000, 0,0,1024,600, 0,0,0,0)
    mov r0, #0
    ldr r1, =$cls
    ldr r2, =$title
    ldr r3, =0x90000000
    mov r4, #0
    str r4, [sp]
    str r4, [sp, #4]
    mov r4, #1024
    str r4, [sp, #8]
    mov r4, #600
    str r4, [sp, #12]
    mov r4, #0
    str r4, [sp, #16]
    str r4, [sp, #20]
    str r4, [sp, #24]
    str r4, [sp, #28]
    ldr r4, =@CreateWindowExW
    ldr r4, [r4]
    blx r4
    mov r5, r0
    mov r2, r5
    ldr r1, =$f_hwnd
    add r0, sp, #0x200
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x200
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    @ BITMAPINFO at sp+0x40: biSize=40, w=480, h=-272, planes=1, bpp=16, compression=BI_BITFIELDS(3), sizeimage, xppm,yppm, clrused, clrimp, then masks F800 07E0 001F
    add r4, sp, #0x40
    mov r0, #40
    str r0, [r4]
    mov r0, #480
    str r0, [r4, #4]
    ldr r0, =-272
    str r0, [r4, #8]
    ldr r0, =0x00100001
    str r0, [r4, #12]
    mov r0, #3
    str r0, [r4, #16]
    mov r0, #0
    str r0, [r4, #20]
    str r0, [r4, #24]
    str r0, [r4, #28]
    str r0, [r4, #32]
    str r0, [r4, #36]
    ldr r0, =0xF800
    str r0, [r4, #40]
    ldr r0, =0x07E0
    str r0, [r4, #44]
    ldr r0, =0x001F
    str r0, [r4, #48]
    @ hdc = GetDC(hwnd)
    mov r0, r5
    ldr r4, =@GetDC
    ldr r4, [r4]
    blx r4
    mov r6, r0
    @ hbm = CreateDIBSection(hdc, bmi, DIB_RGB_COLORS=0, &bits, 0, 0)
    mov r0, r6
    add r1, sp, #0x40
    mov r2, #0
    add r3, sp, #0x30
    mov r4, #0
    str r4, [sp]
    str r4, [sp, #4]
    ldr r4, =@CreateDIBSection
    ldr r4, [r4]
    blx r4
    mov r7, r0
    ldr r8, [sp, #0x30]
    mov r2, r7
    mov r3, r8
    ldr r1, =$f_dib
    add r0, sp, #0x200
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x200
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    @ fill bits: 480*272 halfwords with pattern row<<5 | col
    mov r0, r8
    ldr r1, =130560
    mov r2, #0
fill:
    and r3, r2, #0x3f
    lsl r3, r3, #5
    orr r3, r3, #0x1f
    strh r3, [r0], #2
    add r2, r2, #1
    cmp r2, r1
    bne fill
    @ memdc = CreateCompatibleDC(hdc); SelectObject(memdc, hbm)
    mov r0, r6
    ldr r4, =@CreateCompatibleDC
    ldr r4, [r4]
    blx r4
    mov r9, r0
    mov r0, r9
    mov r1, r7
    ldr r4, =@SelectObject
    ldr r4, [r4]
    blx r4
    mov r10, #20
loop:
    @ BitBlt(hdc, 100,100, 480,272, memdc, 0,0, SRCCOPY)
    mov r0, r6
    mov r1, #100
    mov r2, #100
    mov r3, #480
    mov r4, #272
    str r4, [sp]
    str r9, [sp, #4]
    mov r4, #0
    str r4, [sp, #8]
    str r4, [sp, #12]
    ldr r4, =0x00CC0020
    str r4, [sp, #16]
    ldr r4, =@BitBlt
    ldr r4, [r4]
    blx r4
    mov r2, r0
    ldr r1, =$f_blt
    add r0, sp, #0x200
    ldr r4, =@wsprintfW
    ldr r4, [r4]
    blx r4
    add r0, sp, #0x200
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    @ pump messages: PeekMessage loop briefly
    mov r0, #1000
    ldr r4, =@Sleep
    ldr r4, [r4]
    blx r4
    subs r10, r10, #1
    bne loop
    mov r0, r5
    ldr r4, =@DestroyWindow
    ldr r4, [r4]
    blx r4
    mov r0, #0
    add sp, sp, #0x300
    pop {r4-r11, pc}
'''
m["build"](sys.argv[1], asm, {"COREDLL.dll":["OutputDebugStringW","wsprintfW","Sleep","RegisterClassW","CreateWindowExW","DefWindowProcW","GetDC","CreateDIBSection","CreateCompatibleDC","SelectObject","BitBlt","DestroyWindow"]},
   {"cls":"EmuGdiTest","title":"EmuGdiTest","f_hwnd":"EMUGDI: hwnd=%08x","f_dib":"EMUGDI: dib=%08x bits=%08x","f_blt":"EMUGDI: BitBlt -> %d"})
