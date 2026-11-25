#!/usr/bin/env python3
"""WAS root OUTPUT.ZIP: sources and current build/UAT evidence; not Windows installations."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from root_cleanup import archive_notes

ROOT=Path(__file__).resolve().parents[1]
INCLUDE=['SRC/*.ASM','LINK/*.RSP','LINK/TERMS/*.RSP','HOST/*.PY','HOST/*.py','TESTS/*.WAS','TESTS/*.ASM','TESTS/*.PY',
         'TESTS/*.INI','ASSETS/**/*','LICENSE','.gitignore','.gitattributes','.editorconfig','README.md',
         'VERSION.TXT','SCRIPT.TXT','DEVELOPMENT.TXT','MAKE.BAT','MAKE2.BAT','AUDIT.BAT','AUTOUAT.BAT',
         'BUILD/RESULT.JSON','BUILD/MANIFEST.JSON','DOCS/*.TXT','DOCS/HISTORY/*.TXT','VERIFY.BAT','WASVERIFY.BAT',
         'DIST/WIN101/NOWBAT.EXE','DIST/WIN300/NOWBAT.EXE',
         'BUILD/BUILD.LOG','BUILD/AUDIT.LOG','BUILD/AUDIT.RESULT',
         'UAT/RESULTS/*/RESULT.JSON', 'UAT/RESULTS/*/DOSBOX_DOS.LOG', 'UAT/RESULTS/*/DOSBOX_BOOT.LOG',
         'UAT/RESULTS/*/DOSBOX_UAT.LOG', 'UAT/RESULTS/*/BOOT.LOG',
         'UAT/RESULTS/*/DOSBOX.CONF','UAT/RESULTS/*/RUNUAT.BAT','UAT/RESULTS/*/DOSPROBE.CONF',
         'UAT/RESULTS/*/DOSREADY.OK','UAT/RESULTS/*/DOSBOOT.OK',
         'UAT/RESULTS/*/WINRETURN.OK','UAT/RESULTS/*/WAS.LOG',
         'UAT/RESULTS/**/*','UAT/REGRESSION/**/*']
archive_notes(ROOT)
P=ROOT/'OUTPUT.ZIP'
items=sorted({f for g in INCLUDE for f in ROOT.glob(g) if f.is_file()})
with ZipFile(P,'w',ZIP_DEFLATED) as z:
    for f in items:
        z.write(f, f.relative_to(ROOT))
print('OUTPUT.ZIP', len(items), 'files', P.stat().st_size, 'bytes')
