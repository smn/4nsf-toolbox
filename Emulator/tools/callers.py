import sys,struct,json,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from disas import load,pdata,disas
from capstone import *
path=sys.argv[1]; p,img,base,imports,exports=load(path); funcs=pdata(p,base)
cache=path+'.calls.json'
if os.path.exists(cache): calls=json.load(open(cache))
else:
    calls={}
    mdT=Cs(CS_ARCH_ARM,CS_MODE_THUMB); mdA=Cs(CS_ARCH_ARM,CS_MODE_ARM)
    for a,e,is32 in funcs:
        md=mdA if is32 else mdT
        for ins in md.disasm(img[a-base:e-base],a):
            if ins.mnemonic in('bl','blx','b') and ins.op_str.startswith('#'):
                t=int(ins.op_str[1:],0)
                calls.setdefault(str(t),[]).append([ins.address,a])
    json.dump(calls,open(cache,'w'))
# thunks: ARM thunk literal word == slot VA, thunk start = word addr - 12? pattern: ldr ip,[pc,#4]; ldr ip,[ip]; bx ip; .word
def thunk_for_slot(slot):
    b=struct.pack('<I',slot); i=0; out=[]
    while True:
        i=img.find(b,i)
        if i<0: break
        va=base+i
        if struct.unpack_from('<I',img,i-12)[0]==0xE59FC004: out.append(va-12)
        i+=4
    return out
cmd=sys.argv[2]
if cmd=='callers':
    t=int(sys.argv[3],0)
    for site,fn in calls.get(str(t),[]): print(f"  call at {site:#x} in func {fn:#x}")
elif cmd=='import':
    name=sys.argv[3]
    for slot,(dll,n) in imports.items():
        if name.lower() in n.lower():
            print(dll,n,'slot',hex(slot))
            for th in thunk_for_slot(slot):
                print(' thunk',hex(th))
                for site,fn in calls.get(str(th),[]): print(f"  call at {site:#x} in func {fn:#x}")
