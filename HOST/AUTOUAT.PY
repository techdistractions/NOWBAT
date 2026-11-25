#!/usr/bin/env python3
"""NOWBAT native command-matrix UAT, with 37 separately verified commands.

Retains the original AUDIT baseline; native Windows tasks, not host simulation,
are required for PASS. END/PASS/FAIL run in isolated Win16 modules.
"""
import json
import os
import subprocess
import shutil
import sys
import traceback
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import importlib.machinery
import types
import runuat

# AUDIT.PY is deliberately uppercase in this legacy Windows tree. Explicit
# source loading works on both case-sensitive test hosts and Windows.
_loader = importlib.machinery.SourceFileLoader('was_autouat_audit',str(Path(__file__).with_name('AUDIT.PY')))
audit = types.ModuleType(_loader.name)
audit.__file__ = str(Path(__file__).with_name('AUDIT.PY'))
_loader.exec_module(audit)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'AUTOUAT'
RESULTS = OUT/'RESULTS'
ARCHIVE = ROOT/'AUTOUAT_OUTPUT.ZIP'
VALID = ('WIN101','WIN200','WIN300','ALL')


def check_current_build():
    """Don't qualify stale executables or auto-rewrite BUILD/MANIFEST.JSON."""
    audit.check_source()
    hashes={}
    for name,exp_target,exp_version in (('WIN101',0,0),('WIN300',2,0x300)):
        path=ROOT/'DIST'/name/'NOWBAT.EXE'
        b=path.read_bytes()
        if b'NOWBAT_BUILD=W054\0' not in b:
            raise ValueError(name+': stale runtime, run MAKE ALL')
        ne=audit.parse_ne(path)
        if (ne['target'],ne['expected_win_ver'])!=(exp_target,exp_version):
            raise ValueError(name+': wrong NE target/version')
        if set(map(tuple,ne['ordinal_imports']))!=audit.required_native_ordinals(name):
            raise ValueError(name+': wrong imported Win16 API ordinals')
        audit.iconbuild.check_icons(b,name)
        audit.necompact.check_packed(b)
        if audit.missing_binary_commands(b):
            raise ValueError(name+': missing required interpreter commands')
        audit.check_dgroup_budget(name,ne['autodata_minalloc'],audit.BASELINE[name][1])
        if ne['size']>audit.MAX_RELEASE_EXE:
            raise ValueError(name+': executable size ceiling')
        hashes[name]=ne['sha256']
    child=ROOT/'BUILD'/'WCHILD.EXE'
    hashes['WCHILD']=runuat.sha256(child.read_bytes())
    hashes['WWAIT']=runuat.sha256((ROOT/'BUILD'/'WWAIT.EXE').read_bytes())
    for target in ('WIN101','WIN300'):
        for terminal in ('NBTEND','NBTPASS','NBTFAIL'):
            path=ROOT/'BUILD'/'TERMS'/target/(terminal+'.EXE')
            raw=path.read_bytes()
            ne=audit.parse_ne(path)
            audit.necompact.check_packed(raw)
            if (b'NOWBAT_BUILD=W054\0' not in raw or
                set(map(tuple,ne['ordinal_imports']))!=audit.required_native_ordinals(target)):
                raise ValueError('Stale/invalid terminal binary: '+str(path))
            hashes[target+':'+terminal]=ne['sha256']
    manifest=ROOT/'BUILD'/'MANIFEST.JSON'
    if not manifest.is_file():
        raise ValueError('BUILD/MANIFEST.JSON missing; run MAKE ALL')
    recorded=json.loads(manifest.read_text(encoding='utf-8'))
    actual=audit.build_manifest(hashes)
    # Windows paths in a MAKE manifest use backslashes; test hosts may be POSIX.
    for m in (recorded,actual):
        m['sources']={k.replace('\\','/'):v for k,v in m['sources'].items()}
        # The command matrix is a guest TEST SCRIPT, not a compiled binary
        # input. Its actual hash is captured in STAGE.JSON and verified after
        # native execution. Do not require MAKE ALL when only AUTO.WAS changes.
        # Every other source and every Win16 binary hash remains mandatory.
        m['sources'].pop('TESTS/AUTO.WAS',None)
    if recorded!=actual:
        raise ValueError('Built source/binary hashes do not match MAKE ALL; rebuild before AUTOUAT')
    # AutoUAT script is not part of the executable build, but its hash is
    # frozen in each STAGE.JSON/RESULT.JSON for native evidence authenticity.
    script=ROOT/'TESTS'/'AUTO.WAS'
    if not script.is_file():
        raise ValueError('Missing TESTS\\AUTO.WAS')
    return hashes


def package():
    keep=[ROOT/'TESTS'/'AUTO.WAS', *(ROOT/'TESTS'/(kind+'.WAS') for kind in ('TEND','TPASS','TFAIL')), ROOT/'HOST'/'AUTOUAT.PY',
          ROOT/'AUTOUAT.BAT', OUT/'RESULT.JSON', OUT/'RUN.LOG']
    if RESULTS.exists():
        keep+=sorted(p for p in RESULTS.rglob('*') if p.is_file())
    with ZipFile(str(ARCHIVE),'w',ZIP_DEFLATED) as z:
        for f in keep:
            if f.is_file():
                z.write(f,str(f.relative_to(ROOT)).replace('\\','/'))
    print('AUTOUAT evidence:',ARCHIVE.name,ARCHIVE.stat().st_size,'bytes',flush=True)


def main(mode):
    if mode not in VALID:
        raise ValueError('Usage: AUTOUAT [WIN101|WIN200|WIN300|ALL]')
    if OUT.exists():
        shutil.rmtree(str(OUT))
    OUT.mkdir()
    hashes=check_current_build()
    # Developer synthetic tests belong to development/CI, not the user's
    # native-run critical path. They have no bearing on native qualification;
    # command output and guest artifacts are still independently verified.
    if os.environ.get('NOWBAT_DEV_CHECKS') == '1':
        for test in ('SELFTEST.PY','AUTOHOST.PY','REPORTSELF.PY'):
            print('AUTOUAT DEVELOPER CHECK:',test,flush=True)
            proc=subprocess.run([sys.executable,'-B',str(ROOT/'TESTS'/test)],
                                cwd=str(ROOT),stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,text=True,errors='replace')
            if proc.stdout: print(proc.stdout.rstrip(),flush=True)
            if proc.returncode: raise ValueError('Developer regression failed: '+test)
    print('AUTOUAT: current W054 native binaries/manifest VERIFIED',flush=True)
    print('AUTOUAT: launching native Windows guest tests',flush=True)
    old_auto=os.environ.get('WAS_UAT_AUTOUAT')
    old_boot=os.environ.get('WAS_UAT_BOOT_ONLY')
    os.environ['WAS_UAT_AUTOUAT']='1'
    os.environ.pop('WAS_UAT_BOOT_ONLY',None)
    try:
        rows=runuat.run_native(only_target=None if mode=='ALL' else mode,
                               results_root=RESULTS)
    finally:
        if old_auto is None: os.environ.pop('WAS_UAT_AUTOUAT',None)
        else: os.environ['WAS_UAT_AUTOUAT']=old_auto
        if old_boot is not None: os.environ['WAS_UAT_BOOT_ONLY']=old_boot
    for row in rows:
        name=row['target']
        if row['result']=='PASS':
            binname='WIN300' if name=='WIN300' else 'WIN101'
            if row.get('exe_sha256')!=hashes[binname] or not row.get('auto_suite'):
                row.update(result='FAIL',error='AutoUAT binary/hash/suite mismatch')
        print('NOWBAT AUTOUAT',name,row['result'],row.get('error','native evidence verified'),flush=True)
        print('  COMMANDS:', ('37/37 native checks' if row['result']=='PASS' else 'NOT QUALIFIED'),flush=True)
    passed=(len(rows)==(3 if mode=='ALL' else 1) and
            all(row['result']=='PASS' for row in rows))
    report={'mode':mode,'result':'MATRIX_PASS' if passed else 'FAIL',
            'fully_qualified_all_commands':(passed and mode=='ALL'),
            'verified_in_matrix':list(runuat.AUTO_COMMANDS+runuat.AUTO_PENDING) if passed else [],
            'test_plan_commands':list(runuat.AUTO_COMMANDS+runuat.AUTO_PENDING),
            'pending_isolated_terminal_tests':[],
            'guests':rows}
    (OUT/'RESULT.JSON').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('=================================================',flush=True)
    print(' NOWBAT AUTOUAT %s : %s' % (mode,'PASS' if passed else 'FAIL'),flush=True)
    print(' TARGETS:', ', '.join('%s=%s'%(r['target'],r['result']) for r in rows),flush=True)
    print(' COMMAND COVERAGE: %s' % ('37 / 37 per selected guest' if passed else 'INCOMPLETE'),flush=True)
    print('=================================================',flush=True)
    if passed:
        print('NOWBAT AUTOUAT MATRIX PASS: %d commands/aliases verified per guest; '
              'terminal commands END/PASS/FAIL independently verified' % (len(runuat.AUTO_COMMANDS)+len(runuat.AUTO_PENDING)),flush=True)
    if not passed:
        print('NOWBAT AUTOUAT MATRIX FAIL - check AUTOUAT_OUTPUT.ZIP / AUTOUAT/RESULT.JSON',flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    mode=(sys.argv[1] if len(sys.argv)>1 else 'ALL').upper()
    rc=1
    try:
        rc=main(mode)
    except (ValueError, OSError, runuat.GuestError, RuntimeError) as exc:
        print('AUTOUAT FAIL:',exc,flush=True)
        OUT.mkdir(exist_ok=True)
        (OUT/'RESULT.JSON').write_text(json.dumps({'mode':mode,'result':'FAIL',
                   'error':str(exc),'fully_qualified_all_commands':False},indent=2)+'\n')
    try:
        package()
    except OSError as exc:
        print('AUTOUAT packaging failed:',exc,flush=True)
        rc=1
    sys.exit(rc)
