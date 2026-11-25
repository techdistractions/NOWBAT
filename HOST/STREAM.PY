#!/usr/bin/env python3
"""Show the single AUDIT's progress live while retaining the exact BUILD/AUDIT.LOG.

Host-only utility; no extra WAS.EXE memory or NE imports.
"""
from pathlib import Path
import subprocess
import shutil
import sys
from audit_modes import OPERATOR_MODES

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / 'BUILD' / 'AUDIT.LOG'
LOG.parent.mkdir(exist_ok=True)


def run():
    mode = sys.argv[1].upper() if len(sys.argv) > 1 else 'FULL'
    command = [sys.executable, '-B', '-u', str(ROOT / 'HOST' / 'AUDIT.PY'), mode]
    with LOG.open('w', encoding='utf-8', newline='\n') as output:
        if mode not in OPERATOR_MODES:
            msg = 'AUDIT=FAIL: invalid native target ' + mode
            print(msg, flush=True)
            output.write(msg + '\n')
            return 2
        def emit(line):
            sys.stdout.write(line)
            sys.stdout.flush()
            output.write(line)
            output.flush()
        def launch(phase, env=None):
            cmd = command[:-1] + [phase]
            try:
                with subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True,
                                      errors='replace', bufsize=1) as proc:
                    for line in proc.stdout:
                        emit(line)
                    return proc.wait()
            except OSError as exc:
                emit('AUDIT=FAIL: unable to launch host audit: %s\n' % exc)
                return 1
        if mode == 'REGRESSION':
            import regression
            return regression.run(ROOT, launch, emit)
        previous = ROOT/'UAT'/'REGRESSION'
        if previous.exists(): shutil.rmtree(previous)
        return launch(mode)

if __name__ == '__main__':
    sys.exit(run())
