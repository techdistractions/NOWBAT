#!/usr/bin/env python3
"""W068 host-only protocol tests; simulated files NEVER count as native UAT."""
from pathlib import Path
import tempfile,sys,io
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'HOST'))
import runuat
import runpy
from types import SimpleNamespace
root=Path(__file__).resolve().parents[1]
audit=SimpleNamespace(**runpy.run_path(str(root/'HOST/AUDIT.PY')))
from audit_modes import OPERATOR_MODES
assert 'GUISYNC' in OPERATOR_MODES
assert 'NOWBAT_GUISYNC_DEV' in (root/'AUDIT.BAT').read_text()
assert 'validate_guisync(st,gui_wait_begin_at,gui_wait_end_at)' in (root/'HOST/runuat.py').read_text()
assert 'GUISYNC_DIAGNOSTIC_PASS' in (root/'HOST/AUDIT.PY').read_text()
assert "'GUISYNC'" in (root/'HOST/AUDIT.PY').read_text()
assert not any('LOGFILE' in line and 'GSMISS.OK' in line for line in (root/'TESTS/GUISYNC.WAS').read_text().splitlines())
checks=6
with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);u=base/'uat';w=base/'win';u.mkdir();w.mkdir()
    source=b'SHOWICON=NO\nEND\n'
    (w/'TEST.WAS').write_bytes(source);(w/'GUISYNC.WAS').write_bytes(source)
    token='B64B5D761'; st={'uat':u,'staged_win':w,'script_sha256':runuat.sha256(source),'token':token}
    for filename,kind in (('GSEVENT.OK','EVENT_OK'),('GSFOUND.OK','FILE_FOUND'),
                          ('GSMBEG.OK','TIMEOUT_BEGIN'),('GSMDON.OK','TIMEOUT_DONE'),
                          ('GSPASS.OK','SYNC_PASS')):
        (u/filename).write_text(kind+'='+token+'\n')
    trace='\n'.join(('WAS_INITTASK','NOWBAT_BUILD=W054','WAS_TAIL=TEST.WAS',
                 'WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS',
                 'SHOWICON=NO','END'))+'\n'
    (w/'EARLY.LOG').write_text(trace)
    (u/'DOSBOOT.OK').write_text('DOSBOOT '+token+'\n')
    (u/'GSTIME.LOG').write_text('GUEST_COMPLETED=2026-11-24 08:30:01\n')
    def should_reject(reason,begin=100.0,end=100.7):
        global checks
        try: runuat.validate_guisync(st,begin,end)
        except runuat.GuestError as err:
            assert reason in str(err),str(err)
            checks+=1
        else: raise AssertionError('GUISYNC accepted bad evidence for '+reason)
    import os,time
    # Reproduce WIN200: identical FAT mtimes, but valid observed interval.
    stamp=int(time.time())//2*2
    for marker in ('GSMBEG.OK','GSMDON.OK'):
        os.utime(u/marker,(stamp,stamp))
    result=runuat.validate_guisync(st,100.0,100.7)
    assert result['guisync']['waitfor_timeout']=='PASS'
    assert result['guisync']['timer_method']=='host-monotonic-closed-markers'
    assert result['guisync']['timeout_seconds']==0.7
    assert result['guisync']['dos_file_mtime_seconds']==0.0
    checks+=4
    # Reproduce WIN300's two-second mtime boundary: not proof by itself.
    os.utime(u/'GSMDON.OK',(stamp+2,stamp+2))
    result=runuat.validate_guisync(st,100.0,100.8)
    assert result['guisync']['dos_file_mtime_seconds']==2.0
    checks+=1
    for begin,end in ((None,None),(100.0,None),(None,100.7),
                      (100.0,100.0),(100.0,100.2),(100.0,99.0),(100.0,111.0)):
        should_reject('not independently timed',begin,end)
    (u/'GSPASS.OK').write_text('SYNC_PASS=OLD_RUN\n')
    should_reject('GSPASS.OK')
    (u/'GSPASS.OK').write_text('SYNC_PASS='+token+'\n')
    (w/'EARLY.LOG').write_text(trace.replace('END\n',''))
    should_reject('native END')
    (w/'EARLY.LOG').write_text(trace)
    (u/'GSFAIL.LOG').write_text('SYNC_FAIL='+token+'\n')
    should_reject('guest explicitly failed')
    (u/'GSFAIL.LOG').unlink()
    (u/'GSTIME.LOG').write_text('NOT_A_GUEST_CLOCK\n')
    should_reject('guest time')
# Execute the actual final-report dispatch with simulated guest reports.
# W066 fell through after GUISYNC_DIAGNOSTIC_PASS to the generic target
# assertion, making real successful runs fail. Test both entry shapes.
def guest(target):
    return {'target':target,'result':'PASS','native':'GUI_SYNC',
            'guisync':{'doevents':'PASS','waitfor_existing':'PASS',
                       'waitfor_timeout':'PASS','timeout_seconds':2.0}}
all_targets=('WIN101','WIN200','WIN300')
for target in (*all_targets, ''):
    rows=[guest(target)] if target else [guest(t) for t in all_targets]
    log=io.StringIO()
    with redirect_stdout(log):
        audit.report_native('GUISYNC',rows,gui_target=target)
    assert 'GUISYNC_DIAGNOSTIC_PASS: %d native guest(s)'%len(rows) in log.getvalue()
    assert log.getvalue().count('GUISYNC_NATIVE ')==len(rows)
    assert 'AUDIT NATIVE=DIAGNOSTIC_PASS' not in log.getvalue()
    checks+=1
for rows,target in (([guest('WIN200')],'WIN300'),
                    ([guest('WIN300'),guest('WIN300')],'WIN300'),
                    ([guest('WIN101'),guest('WIN200')],''),
                    ([guest('WIN101'),guest('WIN200'),guest('WIN200')],''),
                    ([],'')):
    try:
        audit.report_native('GUISYNC',rows,gui_target=target)
    except ValueError as err:
        assert 'missing or unexpected native guest' in str(err)
        checks+=1
    else:
        raise AssertionError('GUISYNC finalizer accepted wrong target set')
row=guest('WIN300');row.pop('guisync')
try:
    audit.report_native('GUISYNC',[row],gui_target='WIN300')
except ValueError as err:
    assert 'missing closed native witness' in str(err)
    checks+=1
else:
    raise AssertionError('GUISYNC finalizer accepted missing evidence')
# Other native report modes still dispatch normally (no guest launches).
for mode,rows,marker in (
    ('WIN300',[guest('WIN300')],'AUDIT NATIVE=DIAGNOSTIC_PASS'),
    ('FULL',[guest(t) for t in all_targets],'AUDIT NATIVE=PASS')):
    log=io.StringIO()
    with redirect_stdout(log):
        audit.report_native(mode,rows)
    assert marker in log.getvalue()
    checks+=1
try:
    audit.report_native('WIN300',[guest('WIN200')])
except ValueError:
    checks+=1
else:
    raise AssertionError('Single target finalizer accepted wrong target')
print('GUISYNC AUDIT HOST=PASS (%d isolated protocol assertions; native guest pending)'%checks)
