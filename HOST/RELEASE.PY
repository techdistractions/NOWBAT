#!/usr/bin/env python3
"""Reproducible NOWBAT public DIST generator (host only).

Strict mode permits release packaging only when the current executable bytes
match the recorded SHA-256 values of a successful three-target native AutoUAT.
No external dependencies or network access required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'DIST'
BIN = {'WIN101': DIST / 'WIN101' / 'NOWBAT.EXE', 'WIN300': DIST / 'WIN300' / 'NOWBAT.EXE'}
SRC_TOP = (
    '.editorconfig', '.gitattributes', '.gitignore',
    'README.md', 'README.TXT', 'DEVELOPMENT.TXT', 'SCRIPT.TXT', 'HISTORY.TXT',
    'VERSION.TXT', 'MAKE.BAT', 'MAKE2.BAT', 'AUDIT.BAT', 'AUTOUAT.BAT',
    'VERIFY.BAT', 'NOWBATVERIFY.BAT', 'WASVERIFY.BAT', 'DISTMAKE.BAT',
)
SRC_ROOTS = {'SRC', 'LINK', 'HOST', 'TESTS', 'EXAMPLES'}
SRC_DOCS = ('DOCS/ENDUSER_README.TXT', 'DOCS/SNAP_MODES.TXT',
            'DOCS/REGRESSION_QUALIFIED.TXT')
SRC_ASSETS = ('ASSETS/WIN101.ICO', 'ASSETS/WIN300.ICO')
SRC_CI = ('.github/workflows/host-checks.yml',)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def qualified_from_evidence() -> tuple[str, str]:
    report_path = ROOT / 'OUTPUT.ZIP'
    if not report_path.is_file():
        raise ValueError('OUTPUT.ZIP missing; run AUTOUAT ALL before DISTMAKE')
    try:
        with zipfile.ZipFile(report_path) as z:
            report = json.loads(z.read('AUTOUAT/RESULT.JSON'))
    except (KeyError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as ex:
        raise ValueError('OUTPUT.ZIP has no valid AutoUAT result: ' + str(ex)) from ex
    if report.get('mode') != 'ALL' or report.get('result') != 'MATRIX_PASS':
        raise ValueError('AutoUAT report is not an ALL-target MATRIX_PASS')
    if report.get('pending_isolated_terminal_tests'):
        raise ValueError('terminal-command qualification incomplete')
    guests = report.get('guests', [])
    by_target = {x.get('target'): x for x in guests}
    if len(guests) != 3 or set(by_target) != {'WIN101','WIN200','WIN300'}:
        raise ValueError('expected exactly WIN101, WIN200 and WIN300 guest results')
    for target, g in by_target.items():
        if g.get('result') != 'PASS':
            raise ValueError(target + ' did not pass native AutoUAT')
        commands = g.get('verified_commands', [])
        terminal = g.get('terminal_commands', {})
        if len(commands) != 34 or set(terminal) != {'END','PASS','FAIL'} or any(terminal[k].get('result') != 'PASS' for k in terminal):
            raise ValueError(target + ' has incomplete 37-command coverage')
        proc = g.get('process',{})
        if proc.get('forced_termination') or not proc.get('natural_exit') or proc.get('exit_code') != 0:
            raise ValueError(target + ' did not exit DOSBox naturally')
    if by_target['WIN101']['exe_sha256'] != by_target['WIN200']['exe_sha256']:
        raise ValueError('WIN101 and WIN200 did not use the same target executable')
    for target in ('WIN101', 'WIN300'):
        p = BIN[target]
        if not p.is_file():
            raise ValueError(f'missing binary {p}')
        if sha(p.read_bytes()) != by_target[target]['exe_sha256']:
            raise ValueError(f'{target} binary hash does not match the passing AutoUAT: rebuild and rerun')
    enforce_release_code_budget()
    return sha(report_path.read_bytes()), 'Native AutoUAT PASS: 37/37 on WIN101, WIN200 and WIN300'



def enforce_release_code_budget() -> None:
    """Reapply the exact audited release budget; an AutoUAT result cannot
    silently turn a diagnostic-size executable into a public release.
    """
    from importlib.machinery import SourceFileLoader
    import types
    loader = SourceFileLoader('nowbat_public_size_audit', str(ROOT / 'HOST' / 'AUDIT.PY'))
    audit = types.ModuleType(loader.name)
    audit.__file__ = str(ROOT / 'HOST' / 'AUDIT.PY')
    loader.exec_module(audit)
    for target, path in BIN.items():
        binary = path.read_bytes()
        audit.iconbuild.check_icons(binary, target)
        linked_size = audit.iconbuild.code_size(binary, target)
        audit.check_release_image_size(target, binary, linked_size)
        base_size, base_data = audit.BASELINE[target]
        if linked_size > base_size + audit.MAX_EXE_GROWTH:
            raise ValueError('%s linked growth +%d exceeds release limit +%d' %
                             (target, linked_size - base_size, audit.MAX_EXE_GROWTH))
        ne = audit.parse_ne(path)
        audit.check_dgroup_budget(target, ne['autodata_minalloc'], base_data)


def build_binary_zip(readme: bytes, licence: bytes, build_status: bytes | None = None) -> bytes:
    """Public end-user archive; no Windows installation or compiler binaries."""
    from io import BytesIO
    out = BytesIO()
    files = {
        'NOWBAT/README.TXT': readme,
        'NOWBAT/SCRIPT.TXT': (ROOT / 'SCRIPT.TXT').read_bytes(),
        'NOWBAT/HISTORY.TXT': (ROOT / 'HISTORY.TXT').read_bytes(),
        'NOWBAT/LICENSE': licence,
        'NOWBAT/EXAMPLES/HELLO.WAS': (ROOT / 'EXAMPLES/HELLO.WAS').read_bytes(),
        'NOWBAT/EXAMPLES/CAPTURE.WAS': (ROOT / 'EXAMPLES/CAPTURE.WAS').read_bytes(),
        'NOWBAT/EXAMPLES/FILECOPY.WAS': (ROOT / 'EXAMPLES/FILECOPY.WAS').read_bytes(),
        'NOWBAT/WIN101/NOWBAT.EXE': BIN['WIN101'].read_bytes(),
        'NOWBAT/WIN300/NOWBAT.EXE': BIN['WIN300'].read_bytes(),
    }
    if build_status is not None:
        files['NOWBAT/BUILD_STATUS.TXT'] = build_status
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, data in sorted(files.items()):
            info = zipfile.ZipInfo(rel, date_time=(2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return out.getvalue()


def source_paths() -> list[Path]:
    paths: list[Path] = []
    if (ROOT / 'LICENSE').is_file():
        paths.append(ROOT / 'LICENSE')
    for name in SRC_TOP + SRC_DOCS + SRC_ASSETS + SRC_CI:
        p = ROOT / name
        if not p.is_file():
            raise ValueError('missing source distribution file ' + name)
        paths.append(p)
    extensions = {'SRC': {'.asm'}, 'LINK': {'.rsp'}, 'HOST': {'.py'},
                  'TESTS': {'.was','.asm','.py','.ini'}, 'EXAMPLES': {'.was'}}
    for d in sorted(SRC_ROOTS):
        for p in sorted((ROOT / d).rglob('*')):
            if not p.is_file():
                continue
            if any(x.upper().endswith('.LOCAL') or x.upper().endswith('.LOCAL.BAT')
                   or x.upper().endswith('.LOCAL.CMD') for x in p.parts):
                continue
            if '__pycache__' in p.parts or p.suffix.lower() not in extensions[d]:
                continue
            paths.append(p)
    names = [p.relative_to(ROOT).as_posix() for p in paths]
    if len(names) != len(set(names)):
        raise ValueError('duplicate source ZIP path')
    return sorted(paths, key=lambda p:p.relative_to(ROOT).as_posix())


def build_source_zip() -> bytes:
    from io import BytesIO
    out = BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in source_paths():
            rel = 'NOWBAT/' + p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(2026, 11, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description='Build NOWBAT DIST, verifying three native guests')
    parser.add_argument('--preview', action='store_true', help='create a clearly unqualified local packaging preview only')
    parser.add_argument('--source-only', action='store_true', help='package a source candidate without claiming release qualification')
    parser.add_argument('--local-build', action='store_true', help='package a fresh local MAKE build without claiming native qualification')
    args = parser.parse_args()
    if args.source_only:
        try:
            DIST.mkdir(exist_ok=True)
            out = DIST / 'NOWBAT_SOURCE_CANDIDATE.ZIP'
            out.write_bytes(build_source_zip())
            print('SOURCE_CANDIDATE=' + str(out))
            print('SOURCE_ONLY=PASS')
            return 0
        except (OSError, ValueError) as ex:
            print('SOURCE_CANDIDATE=FAIL: ' + str(ex), file=sys.stderr)
            return 1
    licence_file = ROOT / 'LICENSE'
    if not licence_file.is_file():
        print('DIST=FAIL: LICENSE missing; select a source licence first', file=sys.stderr)
        return 1
    licence_text = licence_file.read_text(encoding='utf-8', errors='replace')
    if ('[COPYRIGHT HOLDER' in licence_text or 'UNSELECTED TEMPLATE' in licence_text or
            'NOT LICENSED' in licence_text.upper()):
        print('DIST=FAIL: unapproved or placeholder LICENSE', file=sys.stderr)
        return 1
    if args.local_build and args.preview:
        print('DIST=FAIL: choose --local-build OR --preview', file=sys.stderr)
        return 2
    if args.preview:
        status = ('UNQUALIFIED PREVIEW ONLY. These snapshot EXEs were NOT established\n'
                  'to match full current native AutoUAT. DO NOT PUBLISH the binaries.\n'
                  'Run DISTMAKE on the Windows development host to rebuild and qualify.\n')
        report_hash = None
    elif args.local_build:
        status = ('LOCAL BUILD: not native-AutoUAT qualified. Test on each Windows version\r\n'
                  'before publishing binaries. The dev qualification uses MAKE2 / AUTOUAT.\r\n')
        report_hash = None
    else:
        try:
            report_hash, status = qualified_from_evidence()
        except ValueError as ex:
            print('DIST=FAIL: ' + str(ex), file=sys.stderr)
            return 1
    try:
        payload = build_source_zip()
        base_doc = (ROOT / 'DOCS' / 'ENDUSER_README.TXT').read_bytes()
        # Strip an existing auto-generated preview header (idempotent preview runs).
        hdr = b'NOWBAT DISTRIBUTION STATUS\r\n'
        if base_doc.startswith(hdr):
            cut = base_doc.find(b'NOWBAT - WINDOWS ADMIN SCRIPT')
            if cut < 0: raise ValueError('release readme header could not be recovered')
            base_doc = base_doc[cut:]
        # Qualified public README is a clean DOS-era plain-text manual.
        # Native qualification remains recorded by RESULT.JSON, checksums,
        # and the DISTMAKE console; it is not a banner in the user manual.
        doc = base_doc
        hashes = []
        for target in ('WIN101','WIN300'):
            p = BIN[target]
            if not p.is_file(): raise ValueError('missing ' + str(p))
            hashes.append(f'{sha(p.read_bytes())}  {target}/NOWBAT.EXE')
        hashes.append(f'{sha(payload)}  NOWBAT_SOURCE.ZIP')
        hashes.append(f'{sha(doc)}  README.TXT')
        licence = (ROOT / 'LICENSE').read_bytes()
        hashes.append(f'{sha(licence)}  LICENSE')
        build_status = status.encode('ascii') if (args.local_build or args.preview) else None
        binary_zip = build_binary_zip(doc, licence, build_status)
        hashes.append(f'{sha(binary_zip)}  NOWBAT_BINARIES.ZIP')
        if report_hash: hashes.append('# AUTO_UAT_OUTPUT_SHA256=' + report_hash)
        (DIST / 'NOWBAT_SOURCE.ZIP').write_bytes(payload)
        (DIST / 'README.TXT').write_bytes(doc)
        (DIST / 'LICENSE').write_bytes(licence)
        (DIST / 'NOWBAT_BINARIES.ZIP').write_bytes(binary_zip)
        if build_status is not None:
            (DIST / 'BUILD_STATUS.TXT').write_bytes(build_status)
        elif (DIST / 'BUILD_STATUS.TXT').exists():
            (DIST / 'BUILD_STATUS.TXT').unlink()
        (DIST / 'SHA256SUMS.TXT').write_bytes(('\r\n'.join(hashes) + '\r\n').encode('ascii'))
        print('DIST=' + ('LOCAL_BUILD' if args.local_build else ('PREVIEW_ONLY' if args.preview else 'QUALIFIED_PASS')))
        print('SOURCE=' + str(DIST / 'NOWBAT_SOURCE.ZIP'))
        print('BINARIES=' + str(DIST / 'NOWBAT_BINARIES.ZIP'))
        for target in ('WIN101', 'WIN300'):
            print(target + ' SHA256=' + sha(BIN[target].read_bytes()))
        return 0
    except (OSError, ValueError) as ex:
        print('DIST=FAIL: ' + str(ex), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
