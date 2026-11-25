#!/usr/bin/env python3
"""Validate the exact two-package public distribution against this source tree.

Runs after MAKE on any host with Python 3; requires no DOSBox-X or Windows.
Native runtime qualification remains a separate developer audit.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from importlib.machinery import SourceFileLoader
import types

_loader = SourceFileLoader('nowbat_dist_release', str(Path(__file__).with_name('RELEASE.PY')))
RELEASE = types.ModuleType(_loader.name)
RELEASE.__file__ = str(Path(__file__).with_name('RELEASE.PY'))
_loader.exec_module(RELEASE)

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'DIST'


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def entries(archive: Path) -> dict[str, bytes]:
    require(archive.is_file() and archive.stat().st_size > 0, 'missing or empty ' + str(archive))
    with ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), 'duplicate members in ' + archive.name)
        for name in names:
            p = PurePosixPath(name)
            require(not p.is_absolute() and '..' not in p.parts and name.startswith('NOWBAT/'),
                    'unsafe member path ' + name)
            require(not name.endswith('/'), 'unexpected directory entry ' + name)
        return {name: z.read(name) for name in names}


def ne_image(data: bytes, target: str) -> None:
    require(len(data) > 0x50 and data[:2] == b'MZ', target + ' is not MZ')
    ne = int.from_bytes(data[0x3c:0x40], 'little')
    require(0x40 <= ne < len(data) - 0x40 and data[ne:ne+2] == b'NE', target + ' has no valid NE header')
    # The WIN101 linker produces legacy target type 0; WIN300 is Windows 2.
    expect = 0 if target == 'WIN101' else 2
    require(data[ne + 0x36] == expect, target + ' NE target is unexpected')


def run() -> None:
    src = entries(DIST / 'NOWBAT_SOURCE.ZIP')
    bins = entries(DIST / 'NOWBAT_BINARIES.ZIP')
    expected_src = {'NOWBAT/' + p.relative_to(ROOT).as_posix(): p.read_bytes()
                    for p in RELEASE.source_paths()}
    expected_bins = {
        'NOWBAT/README.TXT': (DIST / 'README.TXT').read_bytes(),
        'NOWBAT/SCRIPT.TXT': (ROOT / 'SCRIPT.TXT').read_bytes(),
        'NOWBAT/HISTORY.TXT': (ROOT / 'HISTORY.TXT').read_bytes(),
        'NOWBAT/LICENSE': (ROOT / 'LICENSE').read_bytes(),
        **{'NOWBAT/EXAMPLES/' + f.name: f.read_bytes() for f in (ROOT / 'EXAMPLES').glob('*.WAS')},
        **{'NOWBAT/' + t + '/NOWBAT.EXE': RELEASE.BIN[t].read_bytes() for t in ('WIN101','WIN300')},
    }
    status = DIST / 'BUILD_STATUS.TXT'
    if status.is_file():
        expected_bins['NOWBAT/BUILD_STATUS.TXT'] = status.read_bytes()
    require(src == expected_src, 'source ZIP differs from source files or contains extras')
    require(bins == expected_bins, 'binary ZIP differs from build files or contains extras')
    require('NOWBAT/MAKE.BAT' in src and 'NOWBAT/MAKE2.BAT' in src, 'source build entrypoints missing')
    public_make = src['NOWBAT/MAKE.BAT'].decode('utf-8', 'replace').upper()
    for forbidden in (r'C:\RETRO', 'WHERE /R', '..\\..\\', 'NOWBAT_TOOLROOT'):
        require(forbidden not in public_make, 'public MAKE has non-portable discovery: ' + forbidden)
    for target in ('WIN101','WIN300'):
        ne_image(bins['NOWBAT/' + target + '/NOWBAT.EXE'], target)
    require(b'This is free and unencumbered software' in bins['NOWBAT/LICENSE'],
            'Unlicense text missing from binary archive')
    require('NOWBAT/LICENSE' in src, 'Unlicense text missing from source archive')
    checkfile = DIST / 'SHA256SUMS.TXT'
    require(checkfile.is_file(), 'missing SHA256SUMS.TXT')
    hashes: dict[str, str] = {}
    for line in checkfile.read_text(encoding='ascii').splitlines():
        if not line or line.startswith('#'):
            continue
        parts = line.split('  ', 1)
        require(len(parts) == 2 and len(parts[0]) == 64, 'bad SHA256SUMS.TXT line')
        hashes[parts[1]] = parts[0]
    assets = {
        'NOWBAT_SOURCE.ZIP': (DIST / 'NOWBAT_SOURCE.ZIP').read_bytes(),
        'NOWBAT_BINARIES.ZIP': (DIST / 'NOWBAT_BINARIES.ZIP').read_bytes(),
        'README.TXT': (DIST / 'README.TXT').read_bytes(),
        'LICENSE': (ROOT / 'LICENSE').read_bytes(),
        **{t + '/NOWBAT.EXE': RELEASE.BIN[t].read_bytes() for t in ('WIN101','WIN300')},
    }
    require(set(hashes) == set(assets), 'checksums do not cover the six expected outputs')
    for name, blob in assets.items():
        require(hashes[name] == digest(blob), 'SHA256 mismatch ' + name)
    print('DIST_CHECK=PASS: portable MAKE, both Windows NE images, exact ZIP contents and SHA256')
    print('DIST_CHECK=PASS: source %d files; binary %d files' % (len(src), len(bins)))


def main() -> int:
    try:
        run()
        return 0
    except (OSError, ValueError, KeyError) as ex:
        print('DIST_CHECK=FAIL: ' + str(ex), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
