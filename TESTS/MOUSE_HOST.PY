#!/usr/bin/env python3
"""W069 focused host contracts and fail-closed evidence protocol (not UAT)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys,runpy,re,io
from contextlib import redirect_stdout
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'HOST'))
import runuat
from types import SimpleNamespace
audit=SimpleNamespace(**runpy.run_path(str(root/'HOST/AUDIT.PY')))
src=(root/'SRC/WAS.ASM').read_text()
script=(root/'TESTS/MOUSE.WAS').read_text()
checks=0
for token in ('extrn SetCursorPos:far','extrn GetCursorPos:far','jc commandMouseMove',
              'call SetCursorPos','call GetCursorPos','cmp ax,wasMouseReqX','cmp ax,wasMouseReqY',
              'mov wasErrorCode,87','sysMOUSEX','sysMOUSEY'):
    assert token in src,token;checks+=1
for marker in ('MOUSEMOVE 40,50','MOUSEMOVE %X%,%Y%', 'IF %MOUSEX% NE 120',
               'IF %MOUSEY% NE 100','MOUSEMOVE 65535,100','IF %RESULT% NE 2',
               'IF %ERRORCODE% NE 87','FIRST=@RUN@ %MOUSEX%,%MOUSEY%',
               'SECOND=@RUN@ %MOUSEX%,%MOUSEY%','MOUSE_PASS=@RUN@'):
    assert marker in script,marker;checks+=1
for target in ('WIN101','WIN300'):
    assert {('USER',17),('USER',70)} <= audit.required_native_ordinals(target);checks+=1
    for f in [root/'LINK'/(target+'.RSP'),*(root/'LINK/TERMS').glob(target+'_*.RSP')]:
        t=f.read_text();assert 'IMPORT SetCursorPos USER.70' in t and 'IMPORT GetCursorPos USER.17' in t;checks+=1
assert 'MOUSEMOVE' in (root/'SCRIPT.TXT').read_text();checks+=1
from audit_modes import OPERATOR_MODES
assert 'MOUSE' in OPERATOR_MODES;checks+=1
assert 'NOWBAT_MOUSE_DEV' in (root/'AUDIT.BAT').read_text();checks+=1
assert 'call WasReadMouse' in src[src.index('wasCheckMouseX:'):src.index('wasCheckDiskFree:')];checks+=1
with TemporaryDirectory() as tmp:
    base=Path(tmp);u=base/'uat';w=base/'win';u.mkdir();w.mkdir();token='W069TEST'
    body=b'SHOWICON=NO\nEND\n';(w/'TEST.WAS').write_bytes(body);(w/'MOUSE.WAS').write_bytes(body)
    st={'uat':u,'staged_win':w,'token':token,'script_sha256':runuat.sha256(body)}
    trace='\n'.join(('WAS_INITTASK',runuat.EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'))+'\n'
    (w/'EARLY.LOG').write_text(trace)
    vals={'MSFIRST.OK':'FIRST='+token+' 40,50','MSSECOND.OK':'SECOND='+token+' 120,100','MSBAD.OK':'INVALID='+token,'MSPASS.OK':'MOUSE_PASS='+token,'DOSBOOT.OK':'DOSBOOT '+token}
    for f,v in vals.items():(u/f).write_text(v+'\n')
    expected={'first':[40,50],'second':[120,100],'invalid':'PASS'}
    assert runuat.validate_mouse(st)['mouse']==expected;checks+=1
    for filename,bad in [('MSFIRST.OK','FIRST='+token+' 41,50'),('MSSECOND.OK','SECOND='+token+' 120,101'),('MSBAD.OK','INVALID=OLD'),('MSPASS.OK','MOUSE_PASS=OLD'),('DOSBOOT.OK','DOSBOOT OLD')]:
        (u/filename).write_text(bad+'\n')
        try:runuat.validate_mouse(st)
        except runuat.GuestError:checks+=1
        else:raise AssertionError('accepted bad witness '+filename)
        (u/filename).write_text(vals[filename]+'\n')
    for path,wrong,original in [(w/'EARLY.LOG',trace.replace('END\n','').encode(),trace.encode()),(w/'MOUSE.WAS',b'tampered',body),(w/'TEST.WAS',b'tampered',body)]:
        path.write_bytes(wrong)
        try:runuat.validate_mouse(st)
        except runuat.GuestError:checks+=1
        else:raise AssertionError('accepted bad '+path.name)
        path.write_bytes(original)
    (u/'MSFAIL.LOG').write_text('FAILED\n')
    try:runuat.validate_mouse(st)
    except runuat.GuestError:checks+=1
    else:raise AssertionError('accepted failure')
    def row(t):return {'target':t,'native':'MOUSE_MOVE','mouse':expected,'result':'PASS'}
    for target in ('WIN101','WIN200','WIN300',''):
        rows=[row(target)] if target else [row(t) for t in ('WIN101','WIN200','WIN300')]
        log=io.StringIO()
        with redirect_stdout(log):audit.report_native('MOUSE',rows,gui_target=target)
        assert 'MOUSE_DIAGNOSTIC_PASS' in log.getvalue();checks+=1
    for rows,target in [([row('WIN200')],'WIN101'),([row('WIN101'),row('WIN101')],'WIN101'),([{'target':'WIN101','result':'PASS'}],'WIN101'),([], '')]:
        try:audit.report_native('MOUSE',rows,gui_target=target)
        except ValueError:checks+=1
        else:raise AssertionError('accepted bad report')
print(f'MOUSE HOST=PASS ({checks} source/protocol checks; native UAT pending)')
