#!/usr/bin/env python3
"""Window geometry source and evidence contract checks; not native UAT."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from contextlib import redirect_stdout
import sys,runpy,struct,io
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'HOST'))
import runuat
audit=SimpleNamespace(**runpy.run_path(str(root/'HOST/AUDIT.PY')))
checks=0
src=(root/'SRC/WAS.ASM').read_text()
for token in ('EnumWindows','GetWindowText','IsWindow','GetClientRect','ClientToScreen','MakeProcInstance','FreeProcInstance','sysWINX','sysWINY','sysWINW','sysWINH'):
    assert token in src,token;checks+=1
for target in ('WIN101','WIN300'):
    assert {('USER',54),('USER',36),('USER',47),('USER',33),('USER',28),('KERNEL',51),('KERNEL',52)} <= audit.required_native_ordinals(target);checks+=1
    for f in [root/'LINK'/(target+'.RSP'),*(root/'LINK/TERMS').glob(target+'_*.RSP')]:
        t=f.read_text();assert all(x in t for x in ('IMPORT EnumWindows USER.54','IMPORT ClientToScreen USER.28','IMPORT GetClientRect USER.33'));checks+=1
script=(root/'TESTS/WINDOW.WAS').read_text()
for token in ('SHELL "WGEOM.EXE"','WAITFOR FILE "WGEOM.DAT" TIMEOUT 15000','WINDOWSELECT "NOWBAT Geometry Fixture"','MOUSEMOVE REL,10,10','MOUSEMOVE REL,32767,32767','WINDOW_PASS=@RUN@','WAITFOR WINDOW "NOWBAT Geometry Fixture" TIMEOUT 15000','TIMEOUT 1000','TIMEOUT 0'):
    assert token in script;checks+=1
with TemporaryDirectory() as tmp:
    base=Path(tmp);u=base/'uat';w=base/'win';u.mkdir();w.mkdir();token='W071TEST'
    body=b'SHOWICON=NO\nEND\n';(w/'TEST.WAS').write_bytes(body);(w/'WINDOW.WAS').write_bytes(body)
    st={'uat':u,'staged_win':w,'token':token,'script_sha256':runuat.sha256(body)}
    trace='\n'.join(('WAS_INITTASK',runuat.EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'))+'\n'
    (w/'EARLY.LOG').write_text(trace)
    vals={'WFIND.OK':'WINDOW_FOUND='+token+' 20,30,180,100','WFBEG.OK':'WINDOW_TIMEOUT_BEGIN='+token,'WFDONE.OK':'WINDOW_TIMEOUT_DONE='+token,'WINGEO.OK':'GEOMETRY='+token+' 20,30,180,100 30,40','WINBAD.OK':'INVALID='+token+' 30,40','WINMISS.OK':'MISSING='+token+' 30,40','WINPASS.OK':'WINDOW_PASS='+token,'DOSBOOT.OK':'DOSBOOT '+token}
    for f,v in vals.items():(u/f).write_text(v+'\n')
    geo=struct.pack('<4H',20,30,180,100);(w/'WGEOM.DAT').write_bytes(geo)
    expected={'origin':[20,30],'client':[180,100],'cursor':[30,40],'invalid':'PASS','missing':'PASS','waitfor_found':'PASS','waitfor_timeout':'PASS','timeout_seconds':1.0}
    assert runuat.validate_window(st,10.0,11.0)['window']==expected;checks+=1
    for begin,end in [(None,11.0),(10.0,10.0),(10.0,25.0)]:
        try:runuat.validate_window(st,begin,end)
        except runuat.GuestError:checks+=1
        else:raise AssertionError('accepted invalid live timeout')
    for name,bad in [('WFIND.OK','WINDOW_FOUND='+token+' 21,30,180,100'),('WFBEG.OK','WINDOW_TIMEOUT_BEGIN=STALE'),('WFDONE.OK','WINDOW_TIMEOUT_DONE=STALE'),('WINGEO.OK','GEOMETRY='+token+' 20,30,180,100 31,40'),('WINBAD.OK','INVALID='+token+' 31,40'),('WINMISS.OK','MISSING=OLD 30,40'),('WINPASS.OK','WINDOW_PASS=OLD'),('DOSBOOT.OK','DOSBOOT OLD')]:
        (u/name).write_text(bad+'\n')
        try:runuat.validate_window(st,10.0,11.0)
        except runuat.GuestError:checks+=1
        else:raise AssertionError('accepted bad witness '+name)
        (u/name).write_text(vals[name]+'\n')
    for p,bad,original in [(w/'WGEOM.DAT',struct.pack('<4H',21,30,180,100),geo),(w/'WGEOM.DAT',b'bad',geo),(w/'EARLY.LOG',trace.replace('END\n','').encode(),trace.encode()),(w/'TEST.WAS',b'tampered',body)]:
        p.write_bytes(bad)
        try:runuat.validate_window(st,10.0,11.0)
        except runuat.GuestError:checks+=1
        else:raise AssertionError('accepted bad '+p.name)
        p.write_bytes(original)
    (u/'WINFAIL.LOG').write_text('FAILED\n')
    try:runuat.validate_window(st,10.0,11.0)
    except runuat.GuestError:checks+=1
    else:raise AssertionError('accepted explicit failure')
    def row(t):return {'target':t,'native':'WINDOW_GEOMETRY','window':expected,'result':'PASS'}
    for target in ('WIN101','WIN200','WIN300',''):
        rows=[row(target)] if target else [row(t) for t in ('WIN101','WIN200','WIN300')]
        log=io.StringIO()
        with redirect_stdout(log):audit.report_native('WINDOW',rows,gui_target=target)
        assert 'WINDOW_DIAGNOSTIC_PASS' in log.getvalue();checks+=1
    for rows,target in [([row('WIN200')],'WIN101'),([row('WIN101'),row('WIN101')],'WIN101'),([{'target':'WIN101','result':'PASS'}],'WIN101'),([], '')]:
        try:audit.report_native('WINDOW',rows,gui_target=target)
        except ValueError:checks+=1
        else:raise AssertionError('accepted bad report')
print(f'WINDOW HOST=PASS ({checks} source/protocol checks; native UAT pending)')
