import sys,struct,pefile
from capstone import *
def load(path):
    p=pefile.PE(path); p.parse_data_directories()
    img=p.get_memory_mapped_image(); base=p.OPTIONAL_HEADER.ImageBase
    imports={}
    for e in getattr(p,'DIRECTORY_ENTRY_IMPORT',[]):
        for i in e.imports: imports[i.address]=(e.dll.decode(), i.name.decode() if i.name else f"ord{i.ordinal}")
    exports={}
    for s in getattr(getattr(p,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[]): exports[base+s.address]=s.name.decode() if s.name else f"ord{s.ordinal}"
    return p,img,base,imports,exports
def find_wstr(img,base,s):
    w=s.encode('utf-16le'); i=img.find(w); return base+i if i>=0 else None
def xrefs(img,base,va):
    # literal pool references (4-byte aligned words equal to va) and also any occurrence
    out=[]; i=0; b=struct.pack('<I',va)
    while True:
        i=img.find(b,i)
        if i<0: break
        out.append(base+i); i+=1
    return out
def disas(img,base,va,n,imports,exports,thumb=True):
    md=Cs(CS_ARCH_ARM, CS_MODE_THUMB if thumb else CS_MODE_ARM); md.detail=False
    code=img[va-base:va-base+n]
    for ins in md.disasm(code,va):
        note=""
        if ins.mnemonic.startswith('ldr') and 'pc' in ins.op_str:
            # resolve literal
            try:
                imm=int(ins.op_str.split('#')[1].rstrip(']'),0); addr=(((ins.address+4)&~3)+imm) if thumb else (ins.address+8+imm)
                val=struct.unpack_from('<I',img,addr-base)[0]
                note=f"; lit=0x{val:x}"
                if val in imports: note+=f" -> IMPORT {imports[val]}"
                elif val in exports: note+=f" -> {exports[val]}"
                else:
                    try:
                        t=img[val-base:val-base+64]
                        if all(32<=c<127 or c==0 for c in t[:16]) and t[1]==0: note+=" "+repr(t.decode('utf-16le',errors='replace').split('\0')[0])
                    except Exception: pass
            except Exception: pass
        if ins.mnemonic in ('bl','blx','b','bx') and ins.op_str.startswith('#'):
            t=int(ins.op_str[1:],0)
            if t in exports: note+=f" -> {exports[t]}"
        print(f"{ins.address:08x}  {ins.mnemonic:8s} {ins.op_str:30s} {note}")
if __name__=="__main__":
    path=sys.argv[1]; p,img,base,imports,exports=load(path)
    cmd=sys.argv[2]
    if cmd=="xref":
        va=find_wstr(img,base,sys.argv[3]); print("string at",hex(va) if va else None)
        for x in xrefs(img,base,va): print("  ref word at",hex(x))
    elif cmd=="dis":
        va=int(sys.argv[3],0); n=int(sys.argv[4],0); disas(img,base,va,n,imports,exports,thumb=(len(sys.argv)<6 or sys.argv[5]!="arm"))
    elif cmd=="exports":
        for a,n in sorted(exports.items()): print(hex(a),n)
    elif cmd=="imports":
        for a,n in sorted(imports.items()): print(hex(a),n)

def pdata(p,base):
    sec=[s for s in p.sections if s.Name.startswith(b'.pdata')]
    if not sec: return []
    d=sec[0].get_data(); out=[]
    for i in range(0,len(d)-7,8):
        a,b=struct.unpack_from('<II',d,i)
        if not a: continue
        prolog=b&0xff; flen=(b>>8)&0x3fffff; is32=(b>>30)&1
        out.append((a, a+flen*(4 if is32 else 2), is32))
    return out
def func_of(funcs,va):
    for a,e,is32 in funcs:
        if a<=va<e: return (a,e,is32)
    return None
if __name__=="__main__" and sys.argv[2] in ("func","funcs"):
    path=sys.argv[1]; p,img,base,imports,exports=load(path); funcs=pdata(p,base)
    if sys.argv[2]=="funcs":
        print(len(funcs),"functions");
        for a,e,is32 in funcs[:int(sys.argv[3]) if len(sys.argv)>3 else 20]: print(hex(a),hex(e),"arm" if is32 else "thumb")
    else:
        va=int(sys.argv[3],0); f=func_of(funcs,va); print("function",[hex(x) if isinstance(x,int) else x for x in f] if f else None)
        if f: disas(img,base,f[0],f[1]-f[0],imports,exports,thumb=not f[2])
