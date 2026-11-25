"""Test complete and failed orchestration without pretending to run Windows."""
from pathlib import Path
import json, sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'HOST'))
import regression as r
for failing in (None,'WINDOW','STARTSHOT'):
    with tempfile.TemporaryDirectory() as t:
        root=Path(t); (root/'BUILD').mkdir(); (root/'VERSION.TXT').write_text('test')
        calls=[]; lines=[]
        def launch(phase,env):
            calls.append(phase)
            assert env['WAS_UAT_DESKTOP']=='visible'
            assert ('NOWBAT_SNAPFAST_DEV' in env)==(phase=='STARTSHOT')
            for target in sorted(r.TARGETS):
                p=root/'UAT'/'RESULTS'/target; p.mkdir(parents=True)
                result='UNSUPPORTED' if phase==failing=='STARTSHOT' and target=='WIN101' else 'PASS'
                (p/'RESULT.JSON').write_text(json.dumps({'target':target,'result':result}))
            (root/'BUILD'/'RESULT.JSON').write_text('{}')
            return 7 if phase==failing=='WINDOW' else 0
        code=r.run(root,launch,lines.append)
        report=json.loads((root/'BUILD'/'RESULT.JSON').read_text())
        assert bool(code)==bool(failing)
        assert report['full_native_qualification']==(failing is None)
        assert calls==list(r.PHASES if failing is None else r.PHASES[:r.PHASES.index(failing)+1])
        for phase in calls:
            assert (root/'UAT'/'REGRESSION'/phase/'GUESTS'/'WIN101'/'RESULT.JSON').is_file()
        assert not (root/'UAT'/'RESULTS').exists()
print('REGRESSION HOST=PASS (all phases, failure preservation, unsupported SNAP rejection)')
