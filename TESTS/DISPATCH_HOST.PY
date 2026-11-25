"""Exercise actual stream subprocess dispatch without launching a Windows guest."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'HOST'))
from audit_modes import OPERATOR_MODES
from root_cleanup import archive_notes, LEGACY_NOTES

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    host = root / 'HOST'
    host.mkdir()
    for name in ('STREAM.PY', 'audit_modes.py'):
        shutil.copy2(ROOT / 'HOST' / name, host / name)
    (host / 'AUDIT.PY').write_text(
        'import sys\nprint("DISPATCH=" + sys.argv[1])\n'
        'sys.exit(7 if sys.argv[1] == "INPUT" else 0)\n')
    expected = ('FULL','WIN101','WIN200','WIN300','STARTSHOT','GUISYNC',
                'MOUSE','WINDOW','INPUT','KEYBOARD','INPUTABI')
    assert set(OPERATOR_MODES) == set(expected) | {'REGRESSION'}
    for mode in (*expected, 'UNKNOWN'):
        proc = subprocess.run([sys.executable, '-B', str(host/'STREAM.PY'), mode],
                              cwd=root, capture_output=True, text=True, timeout=10)
        log = (root/'BUILD'/'AUDIT.LOG').read_text()
        assert log == proc.stdout, (mode, log, proc.stdout)
        if mode == 'UNKNOWN':
            assert proc.returncode == 2 and 'invalid native target' in log
        else:
            assert proc.returncode == (7 if mode == 'INPUT' else 0), (mode, proc)
            assert log.strip() == 'DISPATCH=' + mode
    for name in LEGACY_NOTES:
        (root/name).write_text(name)
    for name in ('MAKE.LOCAL.BAT','AUDIT.LOCAL.BAT','README.md','W999_README.TXT'):
        (root/name).write_text('keep')
    history = root/'DOCS'/'HISTORY'
    history.mkdir(parents=True)
    (history/LEGACY_NOTES[0]).write_text('previous different content')
    (root/'DOCS'/'W072_INPUT.TXT').write_text('old wave')
    (root/'DOCS'/'W074_INPUT_FIX.TXT').write_text('previous wave')
    (root/'DOCS'/'W075_INPUT_THUNKS.TXT').write_text('previous wave 75')
    (root/'DOCS'/'W076_DRAG_PRECISION.TXT').write_text('previous wave 76')
    (root/'DOCS'/'W077_WINDOW_WAIT.TXT').write_text('previous wave')
    (root/'DOCS'/'W078_KEYBOARD.TXT').write_text('previous keyboard wave')
    (root/'DOCS'/'W079_KEYBOARD_ENABLE.TXT').write_text('previous keyboard fix')
    (root/'DOCS'/'W080_BUILD_GATE.TXT').write_text('previous wave')
    (root/'DOCS'/'W081_KEYCOMBO_TYPE.TXT').write_text('previous wave')
    (root/'DOCS'/'W082_SIZE.TXT').write_text('current wave')
    archive_notes(root)
    assert (history/'W072_INPUT.TXT').read_text() == 'old wave'
    assert (history/'W074_INPUT_FIX.TXT').read_text() == 'previous wave'
    assert (history/'W075_INPUT_THUNKS.TXT').read_text() == 'previous wave 75'
    assert (history/'W076_DRAG_PRECISION.TXT').read_text() == 'previous wave 76'
    assert (history/'W077_WINDOW_WAIT.TXT').is_file()
    assert (history/'W079_KEYBOARD_ENABLE.TXT').is_file()
    assert (history/'W080_BUILD_GATE.TXT').is_file()
    assert (history/'W081_KEYCOMBO_TYPE.TXT').is_file()
    assert (history/'W082_SIZE.TXT').is_file()
    archive_notes(root)  # idempotent
    assert (history/LEGACY_NOTES[0]).read_text() == 'previous different content'
    assert (history/'START_HERE_1.TXT').read_text() == LEGACY_NOTES[0]
    assert all(not (root/n).exists() for n in LEGACY_NOTES)
    assert all((root/n).read_text() == 'keep' for n in
               ('MAKE.LOCAL.BAT','AUDIT.LOCAL.BAT','README.md','W999_README.TXT'))
print('DISPATCH HOST=PASS (all modes, return codes, log retention, safe cleanup)')
