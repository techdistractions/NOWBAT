"""Actual hidden guest fault injections; a rejected guest is never a guest PASS."""
import json
import runuat as u


def run(cfg,dosbox):
    reports=[]
    cases=[('DROP_ARGUMENT','WIN101','NARG'),('FALLBACK_USED','WIN101','NFALL'),
           ('ONLY_EXIT','WIN200','NEXIT'),('NO_SHUTDOWN','WIN300','NEND')]
    for case,target,slot in cases:
        st=None;out=u.ROOT/'UAT'/'RESULTS'/'NEGATIVE'/case
        out.mkdir(parents=True,exist_ok=True)
        row={'test':case,'target':target,'test_result':'FAIL','guest_result':'FAIL'}
        old=u.launch_dosbox
        try:
            st=u.stage(target,cfg,slot=slot)
            if case in ('DROP_ARGUMENT','FALLBACK_USED'):
                p=st['batch'];p.write_bytes(p.read_bytes().replace(b' NOWBAT.EXE TEST.WAS',b' NOWBAT.EXE'))
                st['bootline']=st['bootline'].replace(' TEST.WAS','')
            else:
                p=st['staged_win']/'TEST.WAS'
                p.write_bytes(p.read_bytes().replace(b'\nSHUTDOWN',b'\n'+(b'EXIT' if case=='ONLY_EXIT' else b'END')))
                st['script_sha256']=u.sha256(p.read_bytes())
            if case=='FALLBACK_USED':
                # Inject after the normal preflight rejection of WAS.WAS to
                # exercise the actual fallback path and the runtime verifier.
                def launch(*args,**kwargs):
                    (st['staged_win']/'WAS.WAS').write_bytes((st['staged_win']/'TEST.WAS').read_bytes())
                    return old(*args,**kwargs)
                u.launch_dosbox=launch
            try:
                u.run_phase(target,'FOUNDATION',st,dosbox,6,out)
            except u.GuestError as exc:
                row['rejection']=str(exc)
            else:
                raise AssertionError('Fault injection falsely passed')
            trace=u.read_trace(st)
            assert 'WAS_INITAPP' in trace,'The faulted guest never initialized WAS'
            if case=='DROP_ARGUMENT':
                assert 'WAS_TAIL=' in trace and 'WAS_OPEN=TEST.WAS' not in trace
            elif case=='FALLBACK_USED':
                assert 'WAS_OPEN=WAS.WAS' in trace and 'WAS_SHUTDOWN_REQUESTED' in trace
            else:
                assert 'WAS_OPEN=TEST.WAS' in trace and 'WAS_SHUTDOWN_REQUESTED' not in trace
            process=st['process']
            assert process['exited'] and process['windows_remaining']==0 and process['handles_closed']
            row.update(test_result='PASS',trace=trace)
        except (OSError,ValueError,AssertionError,u.GuestError) as exc:
            row['error']=str(exc)
        finally:
            u.launch_dosbox=old
            if st:
                row['process']=st.get('process',{})
                u.collect(st,out)
                if (st['staged_win']/'WAS.WAS').exists():
                    (out/'WAS.WAS').write_bytes((st['staged_win']/'WAS.WAS').read_bytes())
            (out/'RESULT.JSON').write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
        reports.append(row)
        print('NATIVE REJECTION',row['test_result'],case,row.get('error',row.get('rejection','')),flush=True)
    report={'test_result':'PASS' if all(r['test_result']=='PASS' for r in reports) else 'FAIL','cases':reports}
    (u.ROOT/'UAT'/'RESULTS'/'NEGATIVE'/'RESULT.JSON').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
