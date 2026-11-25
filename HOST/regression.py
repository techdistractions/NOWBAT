"""One explicit final regression, using existing native audit validators."""
from pathlib import Path
import json
import os
import shutil

PHASES = ('FULL', 'STARTSHOT', 'GUISYNC', 'MOUSE', 'WINDOW', 'INPUT', 'KEYBOARD')
TARGETS = {'WIN101','WIN200','WIN300'}
FLAGS = ('NOWBAT_SNAPFAST_DEV','NOWBAT_SNAPFAST_TARGET','NOWBAT_STARTSHOT',
         'NOWBAT_GUISYNC_DEV','NOWBAT_GUISYNC_TARGET','NOWBAT_MOUSE_DEV',
         'NOWBAT_WINDOW_DEV','NOWBAT_INPUT_DEV','NOWBAT_KEYBOARD_DEV',
         'WAS_UAT_BOOT_ONLY','WAS_UAT_AUTOUAT')


def run(root, launch, emit):
    evidence=root/'UAT'/'REGRESSION'
    current=root/'UAT'/'RESULTS'
    result=root/'BUILD'/'RESULT.JSON'
    if evidence.exists(): shutil.rmtree(evidence)
    evidence.mkdir(parents=True)
    phases=[]
    error=None
    for phase in PHASES:
        # Never permit a stale diagnostic flag or a prior guest to count.
        if current.exists(): shutil.rmtree(current)
        if result.exists(): result.unlink()
        env=os.environ.copy()
        for flag in FLAGS: env.pop(flag,None)
        env['WAS_UAT_DESKTOP']='visible'
        if phase=='STARTSHOT':
            env['NOWBAT_STARTSHOT']='1'
            env['NOWBAT_SNAPFAST_DEV']='1'
        emit('REGRESSION PHASE: '+phase+'\n')
        code=launch(phase,env)
        out=evidence/phase
        out.mkdir()
        if current.exists(): shutil.move(str(current),str(out/'GUESTS'))
        if result.exists(): shutil.move(str(result),str(out/'RESULT.JSON'))
        rows=[]
        try:
            for target in sorted(TARGETS):
                p=out/'GUESTS'/target/'RESULT.JSON'
                if p.is_file(): rows.append(json.loads(p.read_text(encoding='utf-8')))
            complete=(len(rows)==3 and {x.get('target') for x in rows}==TARGETS
                      and all(x.get('result')=='PASS' for x in rows))
        except (OSError,ValueError,TypeError,AttributeError):
            complete=False
        status='PASS' if code==0 and complete else 'FAIL'
        phases.append({'phase':phase,'result':status,'exitcode':code,
                       'guests':[{k:r.get(k) for k in ('target','result','native','exe_sha256')} for r in rows if isinstance(r,dict)]})
        emit('REGRESSION %s=%s\n'%(phase,status))
        if status!='PASS':
            error=phase+' failed or lacks three passing native guests'
            break
    passed=error is None and len(phases)==len(PHASES)
    report={'version':(root/'VERSION.TXT').read_text().strip(),'mode':'REGRESSION',
            'result':'PASS' if passed else 'FAIL','full_native_qualification':passed,
            'scope':'Foundation, direct SNAP, synchronization, mouse, window, input and keyboard; not public AutoUAT release certification',
            'phases':phases,'error':error}
    result.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    emit('AUDIT_REGRESSION='+report['result']+'\n')
    return 0 if passed else 1
