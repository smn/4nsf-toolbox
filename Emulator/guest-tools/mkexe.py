"""Build a minimal Windows CE ARM EXE from assembly + imports (fixed base 0x10000)."""
import struct,sys
from keystone import Ks, KS_ARCH_ARM, KS_MODE_ARM
BASE=0x10000; TEXT=0x1000; IDATA=0x2000; DATA=0x3000
def align(v,a): return (v+a-1)//a*a
def build(out, asm, imports, strings):
    # imports: {dll: [names]} ; strings: {label: text(wide)}
    # layout .idata: descriptors, ILT/IAT per dll, hint/name entries, dll names
    desc=bytearray(); ilt=bytearray(); names=bytearray(); dllnames=bytearray()
    ndesc=len(imports)
    desc_size=20*(ndesc+1)
    # compute thunk area size
    thunk_total=sum(4*(len(n)+1) for n in imports.values())
    ilt_rva=IDATA+desc_size; iat_rva=ilt_rva+thunk_total; names_rva=iat_rva+thunk_total
    # names blob
    name_off={}
    for dll,ns in imports.items():
        for n in ns:
            name_off[(dll,n)]=len(names); names+=struct.pack("<H",0)+n.encode()+b"\0"
            if len(names)%2: names+=b"\0"
    dll_off={}
    for dll in imports:
        dll_off[dll]=len(dllnames); dllnames+=dll.encode()+b"\0"
    dllnames_rva=names_rva+len(names)
    iat_addr={}
    toff=0
    for dll,ns in imports.items():
        desc+=struct.pack("<IIIII", ilt_rva+toff,0,0,dllnames_rva+dll_off[dll], iat_rva+toff)
        for n in ns:
            ilt+=struct.pack("<I", names_rva+name_off[(dll,n)]); iat_addr[n]=BASE+iat_rva+toff; toff+=4
        ilt+=b"\0\0\0\0"; toff+=4
    desc+=b"\0"*20
    idata=bytes(desc)+bytes(ilt)+bytes(ilt)+bytes(names)+bytes(dllnames)
    # strings in .data
    data=bytearray(); str_addr={}
    for k,t in strings.items():
        str_addr[k]=BASE+DATA+len(data); data+=t.encode("utf-16le")+b"\0\0"
        while len(data)%4: data+=b"\0"
    # assemble with symbol substitution
    for n in sorted(iat_addr, key=len, reverse=True): asm=asm.replace(f"@{n}", hex(iat_addr[n]))
    for k,a in str_addr.items(): asm=asm.replace(f"${k}", hex(a))
    ks=Ks(KS_ARCH_ARM,KS_MODE_ARM); enc,_=ks.asm(asm, BASE+TEXT); code=bytes(enc)
    fa=0x200; hdr=0x400
    secs=[(b".text",TEXT,code,0x60000020),(b".idata",IDATA,idata,0xC0000040),(b".data",DATA,bytes(data),0xC0000040)]
    pe=bytearray(b"MZ"+b"\0"*0x3a+struct.pack("<I",0x40)+b"PE\0\0")
    pe+=struct.pack("<HHIIIHH",0x1C2,len(secs),0,0,0,0xE0,0x0102)
    pe+=struct.pack("<HBBIIIIIII",0x10B,8,0,align(len(code),fa),align(len(idata),fa)+align(len(data),fa),0,TEXT,TEXT,IDATA,BASE)
    pe+=struct.pack("<IIHHHHHHIIIIHHIIIIII",0x1000,fa,4,0,0,0,5,0,0,DATA+align(len(data),0x1000),hdr,0,9,0,0x10000,0x1000,0x100000,0x1000,0,16)
    dirs=[(0,0)]*16; dirs[1]=(IDATA,desc_size); dirs[12]=(iat_rva,thunk_total)
    for r,s in dirs: pe+=struct.pack("<II",r,s)
    ptr=hdr; bodies=[]
    for name,rva,body,ch in secs:
        raw=align(len(body),fa); pe+=name.ljust(8,b"\0")+struct.pack("<IIIIIIHHI",len(body),rva,raw,ptr,0,0,0,0,ch); bodies.append((ptr,raw,body)); ptr+=raw
    pe+=b"\0"*(hdr-len(pe))
    for p,raw,body in bodies: pe+=body+b"\0"*(raw-len(body))
    open(out,"wb").write(pe); print("wrote",out,len(pe))
asm='''
    push {r4-r7, lr}
    sub sp, sp, #0x200
    ldr r0, =$s_start
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #0x202
    mov r1, sp
    ldr r4, =@WSAStartup
    ldr r4, [r4]
    blx r4
    cmp r0, #0
    ldreq r0, =$s_wsa_ok
    ldrne r0, =$s_wsa_fail
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #2
    mov r1, #1
    mov r2, #6
    ldr r4, =@socket
    ldr r4, [r4]
    blx r4
    mov r5, r0
    cmn r0, #1
    ldreq r0, =$s_sock_fail
    ldrne r0, =$s_sock_ok
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    cmn r5, #1
    beq done
    @ sockaddr_in: family=2, port=27011 (0x6983) big endian, addr 127.0.0.1
    mov r1, sp
    mov r2, #0
    str r2, [sp, #8]
    str r2, [sp, #12]
    ldr r2, =0x0100007f
    str r2, [sp, #4]
    ldr r2, =0x83690002
    str r2, [sp]
    mov r0, r5
    mov r2, #16
    ldr r4, =@bind
    ldr r4, [r4]
    blx r4
    cmp r0, #0
    ldreq r0, =$s_bind_ok
    ldrne r0, =$s_bind_fail
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, r5
    mov r1, #5
    ldr r4, =@listen
    ldr r4, [r4]
    blx r4
    cmp r0, #0
    ldreq r0, =$s_listen_ok
    ldrne r0, =$s_listen_fail
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, r5
    ldr r4, =@closesocket
    ldr r4, [r4]
    blx r4
done:
    ldr r4, =@WSAGetLastError
    ldr r4, [r4]
    blx r4
    @ print last error as 4 hex digits appended to a buffer: simple loop
    mov r5, r0
    ldr r6, =$s_err
    add r7, r6, #28
    mov r2, #4
hexloop:
    and r1, r5, #0xf
    cmp r1, #10
    addlt r1, r1, #48
    addge r1, r1, #55
    strh r1, [r7], #2
    lsr r5, r5, #4
    subs r2, r2, #1
    bne hexloop
    mov r1, #0
    strh r1, [r7]
    mov r0, r6
    ldr r4, =@OutputDebugStringW
    ldr r4, [r4]
    blx r4
    mov r0, #0
    add sp, sp, #0x200
    pop {r4-r7, pc}
'''
strings={"s_start":"EMUTEST: start","s_wsa_ok":"EMUTEST: WSAStartup ok","s_wsa_fail":"EMUTEST: WSAStartup FAILED",
 "s_sock_ok":"EMUTEST: socket(AF_INET,SOCK_STREAM) ok","s_sock_fail":"EMUTEST: socket FAILED",
 "s_bind_ok":"EMUTEST: bind 127.0.0.1:27011 ok","s_bind_fail":"EMUTEST: bind FAILED","s_listen_ok":"EMUTEST: listen ok","s_listen_fail":"EMUTEST: listen FAILED",
 "s_err":"EMUTEST: lasterr=0x"+"\0"*4}
build(sys.argv[1], asm, {"COREDLL.dll":["OutputDebugStringW"],"WS2.dll":["WSAStartup","socket","bind","listen","closesocket","WSAGetLastError"]}, strings)
