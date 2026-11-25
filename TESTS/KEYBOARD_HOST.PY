"""Source/protocol tests; native Windows qualification is a separate gate."""
from pathlib import Path
import sys, struct, tempfile, runpy
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'HOST'))
import runuat as u
A=runpy.run_path(str(root/'HOST/AUDIT.PY'))
s=(root/'SRC/WAS.ASM').read_text(); f=(root/'TESTS/WGEOM.ASM').read_text()
for x in ('WasResolveKey proc near','call dword ptr wasKeyProc','mov bx,289','mov wasDriverName,offset inputKeyName','call WasReleaseAll','wasKeysHeld[bx]','cmp al,cs:[di]','mov ax,cs:[bx]'):
    assert x in s,x
assert 'PostMessage' not in '\n'.join(l.split(';')[0] for l in s.splitlines())
assert 'cmp ax,0102h' in f and 'jbe fixtureEventRecord' in f
# W078 WIN101 observed Enable argument/store sequence at entry+0Ch.
# Independently exercise the structural constraints of the new resolver.
assert 'call WasKeyEnableSlot' in s
assert 'cmp word ptr es:[si],5EC4h' in s and 'cmp word ptr es:[si+9],068Ch' in s
assert 'cmp ax,es:[si+11]' in s and 'cmp dx,wasUserCode' in s
assert 'mov es,wasDriverData' in s

def slot(code, data, user_segments):
    for i in range(32):
        if code[i:i+7]!=bytes.fromhex('c4 5e 0a 8c c0 89 1e') or code[i+9:i+11]!=bytes.fromhex('8c 06'):
            continue
        off=struct.unpack_from('<H',code,i+7)[0]
        if off>0xfffc or struct.unpack_from('<H',code,i+11)[0]!=off+2 or off+4>len(data): return None
        p=struct.unpack_from('<HH',data,off)
        return p if p[0] and p[1] in user_segments else None
    return None
code=bytes.fromhex('b8 61 11 45 55 8b ec 1e 8e d8 56 57 c4 5e 0a 8c c0 89 1e 81 01 8c 06 83 01')+bytes(32)
data=bytearray(1024); struct.pack_into('<HH',data,0x181,0x1234,0x1bd7)
assert slot(code,data,(0x1bd7,))==(0x1234,0x1bd7)
assert slot(code,data,(0x1234,)) is None
assert slot(code[:23]+b'\x84'+code[24:],data,(0x1bd7,)) is None
assert slot(code[:14]+b'\x06'+code[15:],data,(0x1bd7,)) is None
# Verify table stride and key encodings independently.
import re
records={}
for row in s.split('keyNameTable label byte\n')[1].split('keyNameCount equ')[0].splitlines():
    if not row.strip(): continue
    vals=[]
    for val in row.strip()[3:].split(','):
        if val.startswith("'"): vals.extend(val[1:-1].encode('ascii'))
        else: vals.append(int(val))
    assert vals[-1]==0 and 0 not in vals[2:-1],row
    name=bytes(vals[2:-1]).decode(); assert name not in records
    records[name]=tuple(vals[:2])
assert len(records)==64 and records['A']==(65,30) and records['SHIFT']==(16,42) and records['ENTER']==(13,28)
assert len(set(v[0] for v in records.values()))==64 and len(set(v[1] for v in records.values()))==64
assert all(0<v[0]<128 and 0<v[1]<128 for v in records.values())
rows=s.split('typeMap label byte\n')[1].split('; Keyboard events')[0]
mp={chr(int(i)):(int(v),int(k)) for v,k,i in re.findall(r'db (\d+),(\d+) ; ASCII (\d+)',rows)}
assert set(mp)==set(map(chr,range(32,127)))
for c in 'abcdefghijklmnopqrstuvwxyz':
    v,k=records[c.upper()]; assert mp[c]==(v,k) and mp[c.upper()]==(v,k|128)
for c in '0123456789': assert mp[c]==records[c]
assert mp[' ']==records['SPACE'] and mp['!']==(49,130) and mp['?']==(191,181) and mp['.']==(190,52)
# Validate uniqueness of scan->VK (needed for exact recovery of OEM keys).
by_scan={}
for v,k in mp.values():
    k &= 127
    assert k not in by_scan or by_scan[k]==v
    by_scan[k]=v
for x in ('WasFindKey proc near','call WasCompositeReady','wasComboLast:','wasComboUp:','wasTypeValidate:', 'mov ax,word ptr cs:typeMap[bx]','mov wasKeyPair,2A10h','mov al,wasKeysHeld[bx]','mov ah,bl'):
    assert x in s,x
assert 'extrn wasKeysHeld:byte' in s
assert 'wasKeysHeld db 128 dup(0)' in (root/'SRC'/'WASUI.ASM').read_text()
with tempfile.TemporaryDirectory() as td:
    d=Path(td); w=d/'w'; g=d/'g'; w.mkdir(); g.mkdir(); token='RUN123'; body=b'SHOWICON=NO\nEND\n'
    for n in ('TEST.WAS','KEYBOARD.WAS'): (w/n).write_bytes(body)
    (g/'DOSBOOT.OK').write_text('DOSBOOT '+token+'\n'); (g/'KBPASS.OK').write_text('KEYBOARD_PASS='+token+'\n')
    (w/'EARLY.LOG').write_text('\n'.join(('WAS_INITTASK',u.EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'))+'\n')
    st={'uat':g,'staged_win':w,'token':token,'script_sha256':u.sha256(body)}
    transitions=[(256, 65), (258, 97), (257, 65), (256, 16), (256, 66), (258, 66), (257, 66), (257, 16), (256, 67), (258, 99), (257, 67), (256, 17), (257, 17), (256, 16), (256, 68), (258, 68), (257, 68), (257, 16), (256, 17), (256, 16), (256, 113), (257, 113), (257, 16), (257, 17), (256, 16), (256, 65), (258, 65), (257, 65), (257, 16), (256, 66), (258, 98), (257, 66), (256, 32), (258, 32), (257, 32), (256, 49), (258, 49), (257, 49), (256, 57), (258, 57), (257, 57), (256, 16), (256, 49), (258, 33), (257, 49), (257, 16), (256, 16), (256, 191), (258, 63), (257, 191), (257, 16), (256, 190), (258, 46), (257, 190), (256, 90), (258, 122), (257, 90)]
    events=[(m,v,1,0xc000 if m==0x101 else 0) for m,v in transitions]; path=w/'WEVENT.DAT'
    def put(rows):path.write_bytes(b''.join(struct.pack('<4H',*r) for r in rows))
    put(events); assert u.validate_keyboard(st)['keyboard']['characters']=='aBcDAb 19!?.z'
    fail=g/'KBFAIL.LOG'
    fail.write_bytes(b''); assert u.keyboard_failure(st) is None
    fail.write_text('KEYBOARD_FAIL=STALE STAGE=KEYPRESS RESULT=2 ERRORCODE=50'); assert u.keyboard_failure(st) is None
    fail.write_text('KEYBOARD_FAIL='+token+' STAGE=KEYPRESS RESULT=2'); assert u.keyboard_failure(st) is None
    fail.write_text('KEYBOARD_FAIL='+token+' STAGE=KEYPRESS RESULT=2 ERRORCODE=50')
    assert u.keyboard_failure(st)=='STAGE=KEYPRESS RESULT=2 ERRORCODE=50'
    fail.unlink()
    def reject():
        try:u.validate_keyboard(st)
        except u.GuestError:return
        raise AssertionError('invalid keyboard evidence accepted')
    put([r for r in events if r[:2]!=(0x101,16)]); reject()
    put([(m,67 if m==0x102 and v==99 else v,lo,hi) for m,v,lo,hi in events]); reject()
    put(events+[(0x100,88,1,0)]); reject()
    put([r for r in events if r[:2]!=(0x101,113)]); reject()
    put([(m,47 if m==0x102 and v==63 else v,lo,hi) for m,v,lo,hi in events]); reject()
    put(events); (g/'KBPASS.OK').write_text('KEYBOARD_PASS=STALE\n'); reject()
    (g/'KBPASS.OK').write_text('KEYBOARD_PASS='+token+'\n'); path.write_bytes(b'bad'); reject()
A['report_native']('KEYBOARD',[{'target':t,'native':'NATIVE_KEYBOARD_INPUT','keyboard':{'recovery':'PASS','combo':'PASS','type':'PASS'}} for t in ('WIN101','WIN200','WIN300')])
print('KEYBOARD HOST=PASS (64 packed key records, 95 TYPE mappings, callback contract and independent event protocol; native UAT pending)')
