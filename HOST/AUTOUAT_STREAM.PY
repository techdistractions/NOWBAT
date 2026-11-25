#!/usr/bin/env python3
"""Stream NOWBAT AutoUAT console output and make one current OUTPUT.ZIP.

This is host-only. It does not modify the native executables, guest staging,
command matrix, or Win1/2/3 execution. Even an early Python exception remains
visible in the evidence instead of leaving a stale MAKE-only OUTPUT.ZIP.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT/'BUILD'/'AUTOUAT.RUN.LOG'
ARCHIVE = ROOT/'AUTOUAT_OUTPUT.ZIP'
LATEST = ROOT/'OUTPUT.ZIP'


def publish(root, returncode, console, archive, latest):
    """Package a single authoritative latest output without manufacturing PASS."""
    console = Path(console)
    archive = Path(archive)
    latest = Path(latest)
    if not console.is_file():
        raise OSError('AutoUAT console log missing')
    report = root/'AUTOUAT'/'RESULT.JSON'
    if archive.is_file():
        # AutoUAT already wrote the native results; append the closed log.
        with zipfile.ZipFile(str(archive), 'a', zipfile.ZIP_DEFLATED) as z:
            if 'AUTOUAT/RUN.LOG' not in z.namelist():
                z.write(str(console), 'AUTOUAT/RUN.LOG')
            if report.is_file() and 'AUTOUAT/RESULT.JSON' not in z.namelist():
                z.write(str(report), 'AUTOUAT/RESULT.JSON')
    else:
        # Even syntax errors or interrupted prerequisites must leave evidence.
        with zipfile.ZipFile(str(archive), 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(str(console), 'AUTOUAT/RUN.LOG')
            if report.is_file():
                z.write(str(report), 'AUTOUAT/RESULT.JSON')
            manifest = root/'BUILD'/'MANIFEST.JSON'
            if manifest.is_file():
                z.write(str(manifest), 'BUILD/MANIFEST.JSON')
    # A completed result is copied only after the archive closes successfully.
    # This replaces MAKE's static-only OUTPUT.ZIP so users can always upload it.
    shutil.copyfile(str(archive),str(latest))
    with zipfile.ZipFile(str(latest)) as z:
        if 'AUTOUAT/RUN.LOG' not in z.namelist():
            raise OSError('Final OUTPUT.ZIP missing AUTOUAT/RUN.LOG')
    return latest


def main(mode):
    (ROOT/'BUILD').mkdir(exist_ok=True)
    for p in (ARCHIVE,LATEST):
        if p.exists():p.unlink()
    command = [sys.executable,'-B','-u',str(ROOT/'HOST'/'AUTOUAT.PY'),mode]
    with CONSOLE.open('w',encoding='utf-8',newline='\n') as output:
        with subprocess.Popen(command,cwd=str(ROOT),stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,text=True,errors='replace',
                              bufsize=1) as child:
            try:
                for line in child.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    output.write(line)
                    output.flush()
                rc=child.wait()
            except KeyboardInterrupt:
                child.terminate()
                child.wait()
                rc=130
                line='AUTOUAT INTERRUPTED - user cancelled\n'
                output.write(line)
                sys.stdout.write(line)
    # Exit status alone is not qualification: native report must exist and say
    # MATRIX_PASS. Fail closed even if a wrapper returned success accidentally.
    if rc == 0:
        report = ROOT/'AUTOUAT'/'RESULT.JSON'
        try:
            if report.is_file():
                result = json.loads(report.read_text(encoding='utf-8'))
            elif ARCHIVE.is_file():
                with zipfile.ZipFile(str(ARCHIVE)) as z:
                    result = json.loads(z.read('AUTOUAT/RESULT.JSON').decode('utf-8'))
            else:
                result = {}
            if result.get('result') != 'MATRIX_PASS':
                raise ValueError('missing MATRIX_PASS report')
        except (OSError,KeyError,ValueError,zipfile.BadZipFile) as exc:
            rc = 1
            line='AUTOUAT FAIL: exit 0 without qualified native result: %s\n' % exc
            print(line,end='',flush=True)
            with CONSOLE.open('a',encoding='utf-8') as output:output.write(line)
    try:
        latest=publish(ROOT,rc,CONSOLE,ARCHIVE,LATEST)
    except (OSError,zipfile.BadZipFile) as exc:
        print('AUTOUAT EVIDENCE PACKAGING FAILED:',exc,flush=True)
        return 1
    print('=================================================',flush=True)
    print(' NOWBAT AUTOUAT : '+('PASS' if rc==0 else 'FAIL'),flush=True)
    print(' EXITCODE: '+str(rc),flush=True)
    print(' EVIDENCE: '+str(latest.name)+' (also AUTOUAT_OUTPUT.ZIP)',flush=True)
    print(' FAILURE DETAIL: AUTOUAT/RUN.LOG',flush=True)
    print('=================================================',flush=True)
    return rc


if __name__ == '__main__':
    sys.exit(main((sys.argv[1] if len(sys.argv)>1 else 'ALL').upper()))
