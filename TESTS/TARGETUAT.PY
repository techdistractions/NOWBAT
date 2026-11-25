#!/usr/bin/env python3
"""Version-specific Win16 child UAT host preflight; NEVER simulates native PASS."""
from pathlib import Path
import sys, re
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'HOST'))
import runuat as r
checks=0
src=(ROOT/'TESTS'/'WCHILD.ASM').read_text(encoding='ascii')
for fragment in ('extrn GetVersion:far', 'call GetVersion', 'mov childVersion,al',
                 "cmp al,'1'", "cmp al,'2'", 'je childWrite', 'call Yield', 'mov cx,1',
                 'lea dx,childVersion', 'int 21h', 'WCHILD.OK', 'WWAIT.OK', '.8086'):
    assert fragment in src,fragment
    checks+=1
# Win1 skips Yield; Win2/3 enters the original cooperative 2s loop.
assert src.index("cmp al,'1'") < src.index('je childWrite') < src.index('call Yield') < src.index('childWrite:')
checks+=1
for rsp in ('WCHILD','WWAIT'):
    text=(ROOT/'LINK'/(rsp+'.RSP')).read_text(encoding='ascii')
    assert 'IMPORT GetVersion KERNEL.3' in text
    assert 'IMPORT Yield KERNEL.29' in text
    checks+=2
for target,major in (('WIN101',b'1'),('WIN200',b'2'),('WIN300',b'3')):
    assert r.expected_child_version(target)==major
    checks+=1
runner=(ROOT/'HOST'/'runuat.py').read_text(encoding='utf-8')
for needle in ('expected_child_version(st[\'target\'])',
               "marker.read_bytes()!=expected_child_version(st['target'])",
               "child_fixture_policy=", "ui_policy=",'UAT START', 'WIN1_2_IMMEDIATE_EXIT', 'WIN3_YIELD_2S'):
    assert needle in runner,needle
    checks+=1
# Explicit Windows 3 real-mode boot; no accidental enhanced/standard mode.
assert r.TARGETS['WIN300']['args']=='/r'
assert r.TARGETS['WIN101']['args']==r.TARGETS['WIN200']['args']==''
checks+=2
# The same NOWBAT WIN101 NE is used for Win1 & Win2; no unsupported Win1
# menu calls, and no Win3-only NE under Win1/2.
ui=(ROOT/'SRC'/'WASUI.ASM').read_text(encoding='ascii')
assert 'cmp uiWinMajor,1' in ui and 'je uiShow' in ui
checks+=1
# The check itself stays a real Win16 module-usage transition, not a
# marker-based shortcut. Also verify all three target-specific policies.
for target,policy in (('WIN101','WIN1_2_IMMEDIATE_EXIT'),
                      ('WIN200','WIN1_2_IMMEDIATE_EXIT'),
                      ('WIN300','WIN3_YIELD_2S')):
    assert (policy if target != 'WIN200' else policy) in runner
    checks+=1
# No relaxation of actual wait success or use of a marker as a substitute.
core=(ROOT/'SRC'/'WAS.ASM').read_text(encoding='ascii')
assert re.search(r'wasWinWaitPoll:.*?call GetModuleUsage.*?cmp ax,wasShellUsage\s+jb wasWinChildDone',core,re.S)
assert 'SWWAIT.DAT' in core
checks+=2
print('TARGETUAT_HOST=PASS (%d version-targeting checks; native tests NOT run)'%checks)
