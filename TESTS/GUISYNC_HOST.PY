#!/usr/bin/env python3
"""W065 static guard of the new bounded Win16 GUI synchronization commands.

This checks source shape and witness script; it does not claim native execution.
"""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
src=(root/'SRC/WAS.ASM').read_text(encoding='ascii')
doc=(root/'SCRIPT.TXT').read_text(encoding='ascii')
was=(root/'TESTS/GUISYNC.WAS').read_text(encoding='ascii')
checks=0
for word in ('cmdDOEVENTS','cmdWAITFOR','cmdFILE','cmdTIMEOUT','commandDoEvents:',
             'commandWaitFor:','wasWaitForPoll:','wasWaitForTimeout:',
             'wasWaitForCloseError:','wasWaitForStopped:'):
    assert src.count(word)>=1,word
    checks+=1
assert re.search(r'commandDoEvents:.*?mov uiPumpAny,1.*?call UiPump.*?call Yield.*?mov wasResult,0',src,re.S)
checks+=1
assert re.search(r'commandWaitFor:.*?call FetchArg.*?cmdFILE.*?cmdTIMEOUT.*?cmp ax,59000.*?wasWaitForPoll:',src,re.S)
checks+=1
assert 'cmp ax,2              ; DOS file not found' in src and 'cmp ax,3              ; DOS path not found' in src
checks+=1
assert 'mov wasResult,1' in src[src.index('wasWaitForTimeout:'):src.index('wasWaitForDone:')]
checks+=1
assert 'call WaitMessage' in src[src.index('commandWaitFor:'):src.index('commandSet:')]
checks+=1
assert 'add ax,6000' in src[src.index('commandWaitFor:'):src.index('commandSet:')]
checks+=1
assert 'call WasStopTimer' in src[src.index('commandWaitFor:'):src.index('commandSet:')]
checks+=1
assert src.count('commandDoEvents:')==1 and src.count('commandWaitFor:')==1
checks+=1
for marker in ('COMMAND: DOEVENTS','COMMAND: WAITFOR','TIMEOUT 15000','RESULT=1 means','RESULT=2 means'):
    assert marker in doc,marker
    checks+=1
for marker in ('SHOWICON=NO','DOEVENTS','WAITFOR FILE "C:\\WASUAT\\GSEVENT.OK" TIMEOUT 1000',
               'WAITFOR FILE "C:\\WASUAT\\GSMISS.OK" TIMEOUT 700','GSPASS.OK','SYNC_PASS=@RUN@'):
    assert marker in was,marker
    checks+=1
assert was.count('WAITFOR FILE ')==2
checks+=1
# Do not allow the new commands to link unsupported imports into Win1/Win2.
assert 'extrn SetWindowsHook' not in src and 'extrn SendInput' not in src
checks+=1
# Existing SNAP contract remains intact, W065 never edits the capture engine.
assert 'mov wasSnapMode,1       ; SNAP defaults to strict FAST' in src
checks+=1
print(f'GUISYNC HOST=PASS ({checks} source/script contracts; native build and UAT pending)')
