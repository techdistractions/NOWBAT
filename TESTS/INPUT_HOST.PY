from pathlib import Path
import sys,runpy,struct,tempfile
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root/'HOST'))
import runuat
from types import SimpleNamespace
A=SimpleNamespace(**runpy.run_path(str(root/'HOST/AUDIT.PY')))
A.check_import_contract(); A.check_terminal_link_parity()
s=(root/'SRC/WAS.ASM').read_text(); f=(root/'TESTS/WGEOM.ASM').read_text()
for x in ('WasResolveMouse','WasFindStore','WasFindCall','call dword ptr wasInputProc','call WasReleaseMouse','GetMouseEventProc','commandMouseClick','commandMouseDblClick','commandWindowFocus'):
    assert x in s,x
assert 'PostMessage' not in '\n'.join(line.split(';')[0] for line in s.splitlines())
assert 'fixtureEventRecord:' in f and 'WEVENT.DAT' in f
# Native input must not move via SetCursorPos while a button is held.
motion=s[s.index('wasMouseAbsolute:'):s.index('wasMouseMoveOK:')]
assert motion.index('call WasDragToPoint') < motion.index('call SetCursorPos')
assert 'mov ax,1' not in motion
resolver=s[s.index('WasResolveMouse proc near'):s.index('WasInputProbe proc near')]
for x in ('call WasFindDriverData','mov wasStoragePrefix,2Eh','mov wasStoragePrefix,0',
          'call WasScanMouseStores','call WasFindStore','call WasFindCall','wasResolveConflict:'):
    assert x in resolver,x
# W075: assert all three legacy ordinal paths resolve export thunks before
# inspecting code. The synthetic image reproduces the observed stub shape.
follow=s[s.index('WasFollowEntry proc near'):s.index('WasFollowEntry endp')]
for x in ('cmp word ptr es:[si],0D02Eh','cmp byte ptr es:[si+2],3Eh',
          'cmp byte ptr es:[si+5],0EAh','mov bx,es:[si+1]',
          'mov dx,es:[si+3]','dec cx','jnz wasFollowNext'):
    assert x in follow,x
assert resolver.count('call WasFollowEntry') == 3
assert 'cmp ax,wasUserExportSeg' in resolver
assert resolver.index('call WasFollowEntry') < resolver.index('mov wasUserCode,dx')
assert resolver.index('mov wasDriverExport,ax') < resolver.index('mov wasDriverEntry,ax')
# Reference model for the same bounded entry resolution algorithm.
def follow_entry(memory,seg,off):
    for _ in range(8):
        if not seg or off > 0xfff6 or seg not in memory:
            return None
        b=memory[seg][off:off+10]
        if len(b)<10:return None
        j=0 if b[0]==0xea else 5 if b[:3]==bytes((0x2e,0xd0,0x3e)) and b[5]==0xea else -1
        if j<0:return seg,off
        off,seg=struct.unpack_from('<HH',b,j+1)
    return None
mem={0x1111:bytearray(256),0x2222:bytearray(256),0x3333:bytearray(256)}
mem[0x1111][16:26]=bytes((0x2e,0xd0,0x3e,0x5d,0,0xea))+struct.pack('<HH',0x35,0x2222)
mem[0x2222][0x35:0x3a]=bytes((0xea,))+struct.pack('<HH',0x40,0x3333)
mem[0x3333][0x40]=0x55
assert follow_entry(mem,0x1111,16)==(0x3333,0x40)
assert follow_entry(mem,0x3333,0x40)==(0x3333,0x40)
mem[0x3333][0x40:0x45]=bytes((0xea,))+struct.pack('<HH',16,0x1111)
assert follow_entry(mem,0x1111,16) is None
assert follow_entry(mem,0,0) is None
assert follow_entry(mem,0x1111,0xffff) is None
move=s[s.index('WasDragToPoint proc near'):s.index('WasDragToPoint endp')]
for x in ('call WasReadMouse','call WasDragClamp','call WasMouseEvent','call WasInputYield',
          'dec wasDragBudget','cmp ax,wasMouseReqX','cmp ax,wasMouseReqY'):
    assert x in move,x
# W076 regression: USER may double mickeys. The old clamp oscillated
# at Y=31/39 on native WIN300. Preserve the exact endpoint requirement.
clamp=s[s.index('WasDragClamp proc near'):s.index('WasDragClamp endp')]
for x in ('xor dx,bx','shr bx,1','mov cx,bx','wasDragClampImpossible:'):
    assert x in clamp,x
for x in ('mov wasDragCapX,8','mov wasDragCapY,8','mov bx,wasDragDX',
          'mov bx,wasDragDY','mov wasDragCapX,cx','mov wasDragCapY,cx'):
    assert x in move,x
def axis_step(error,previous,cap):
    if not error:return 0,cap
    if previous and (error<0)!=(previous<0):
        if abs(previous)==1:raise ValueError('unreachable at one mickey')
        cap=min(cap,abs(previous)//2)
    return max(-cap,min(cap,error)),cap
def drag_model(start,target,gain):
    pos=list(start); prev=[0,0]; caps=[8,8]; path=[]
    for _ in range(512):
        if tuple(pos)==target:return path
        for a in range(2):
            prev[a],caps[a]=axis_step(target[a]-pos[a],prev[a],caps[a])
        for a in range(2):
            pos[a]+=prev[a]*gain[a]
        path.append(tuple(pos))
    raise ValueError('movement budget exhausted')
assert drag_model((15,15),(45,35),(2,2))==[(31,31),(47,39),(43,35),(45,35)]
assert drag_model((15,15),(45,35),(2,1))[-1]==(45,35)
assert drag_model((45,35),(15,15),(2,2))[-1]==(15,15)
assert drag_model((15,15),(45,35),(1,1))[-1]==(45,35)
try:drag_model((15,15),(46,35),(2,2))
except ValueError:pass
else:raise AssertionError('unreachable target accepted')
callback=s[s.index('WasMouseEvent proc near'):s.index('WasMouseEvent endp')]
assert 'pushf' in callback and 'popf' in callback and 'mov bx,wasDragDX' in callback and 'mov cx,wasDragDY' in callback
assert 'STAGE=%STAGE%' in (root/'TESTS/INPUT.WAS').read_text()
with tempfile.TemporaryDirectory() as td:
    b=Path(td); u=b/'u'; w=b/'w';u.mkdir();w.mkdir();token='TESTTOKEN'; body=b'SHOWICON=NO\nEND\n'
    (w/'TEST.WAS').write_bytes(body);(w/'INPUT.WAS').write_bytes(body)
    (u/'DOSBOOT.OK').write_text('DOSBOOT '+token+'\n');(u/'INPASS.OK').write_text('INPUT_PASS='+token+'\n')
    (w/'EARLY.LOG').write_text('\n'.join(('WAS_INITTASK',runuat.EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'))+'\n')
    st={'uat':u,'staged_win':w,'token':token,'script_sha256':runuat.sha256(body)}
    ev=[(0x201,1,12,12),(0x202,0,12,12),(0x204,2,25,25),(0x205,0,25,25),(0x201,1,15,15),(0x200,1,45,35),(0x202,0,45,35),(0x201,1,35,15),(0x202,0,35,15),(0x203,1,35,15),(0x202,0,35,15),(0x204,2,35,15),(0x205,0,35,15)]
    raw=b''.join(struct.pack('<4H',*x) for x in ev); (w/'WEVENT.DAT').write_bytes(raw)
    bmp=struct.pack('<2sIHHI',b'BM',66,0,0,62)+struct.pack('<IiiHHIIiiII',40,1,1,1,1,0,4,0,0,2,0)+bytes(8)+bytes(4)
    for n in ('CLICK.BMP','DRAG.BMP'):(u/n).write_bytes(bmp)
    assert runuat.validate_input(st)['input']['drag']=='PASS'
    (w/'WEVENT.DAT').write_bytes(raw[:40]+raw[48:])
    try:runuat.validate_input(st)
    except runuat.GuestError:pass
    else:raise AssertionError('missing drag accepted')
    # Reject correct message/position with missing button-state evidence.
    bad=list(ev);bad[0]=(0x201,0,12,12)
    (w/'WEVENT.DAT').write_bytes(b''.join(struct.pack('<4H',*x) for x in bad))
    try:runuat.validate_input(st)
    except runuat.GuestError:pass
    else:raise AssertionError('missing button state accepted')
    (w/'WEVENT.DAT').write_bytes(raw)
    (u/'INPASS.OK').write_text('INPUT_PASS=STALE\n')
    try:runuat.validate_input(st)
    except runuat.GuestError:pass
    else:raise AssertionError('stale token accepted')
print('INPUT HOST=PASS (source and protocol only)')
