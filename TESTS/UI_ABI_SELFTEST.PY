#!/usr/bin/env python3
"""Win16 NOWBAT UiPump register/ABI and 8086 size-optimisation regression.

Checks source invariants only. MAKE ALL still determines the linked EXE size,
and AUTOUAT ALL is required for native Win1/2/3 qualification.
"""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
src=(root/'SRC'/'WASUI.ASM').read_text(encoding='latin-1')
batch=(root/'AUTOUAT.BAT').read_text(encoding='latin-1')
start=src.index('UiPump proc near')
end=src.index('UiPump endp',start)
pump=src[start:end]
ops='\n'.join(line.split(';',1)[0].rstrip() for line in pump.splitlines() if line.split(';',1)[0].strip())+'\n'
assert ops.count(' push ds\n')==3, 'UiPump must preserve caller DS and push own MSG segment to both calls'
assert ops.count(' pop ds\n')==1, 'UiPump must restore caller DS on all exits'
assert ' cmp wasIconWnd,0\n je uiPumpDone\n' in ops, 'fast no-window return must remain'
assert (' call PeekMessage\n push ax\n mov ax,@data\n mov ds,ax\n mov es,ax\n cld\n'
        ' pop ax\n pop cx\n or ax,ax\n jz uiPumpDone\n push cx\n') in ops, 'PeekMessage value or DGROUP/loop counter lost'
assert (' call DispatchMessage\n mov ax,@data\n mov ds,ax\n mov es,ax\n cld\n'
        ' pop cx\n cmp wasStop,0\n jne uiPumpDone\n loop uiNextMessage\n') in ops, 'DispatchMessage result breaks data or bounded loop'
assert 'uiPumpDone:\n pop ds\n pop es\n' in ops, 'Stack restore order wrong'
assert ' mov ax,ds\n push ax' not in ops, 'Use compact 8086 PUSH DS for MSG segment'
assert ' xor ax,ax\n push ax' in ops and ' inc ax\n push ax' in ops, 'Compact PM_REMOVE=1 setup missing'
assert ('UiClose proc near\n push ax\n xor ax,ax\n xchg ax,wasIconWnd\n'
        ' or ax,ax\n jz uiCloseDone\n') in '\n'.join(x.split(';',1)[0].rstrip() for x in src.splitlines())+'\n', 'UiClose atomic HWND detach missing'
assert 'call MAKE2.BAT ALL' in batch, 'AUTOUAT must build current runtime'
assert batch.index('call MAKE2.BAT ALL') < batch.index('HOST\\AUTOUAT_STREAM.PY'), 'AutoUAT launched native guests before build'
print('UI ABI + 8086 COMPACTION SOURCE REGRESSION PASS (not native qualification)')
