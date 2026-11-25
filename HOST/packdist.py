#!/usr/bin/env python3
"""Package the two freshly linked NOWBAT runtimes and the minimal source.

Only explicitly listed public files are included. Local tool configuration,
build outputs and other files beside the source never enter either archive.
This checks executable structure and size, not native application behaviour.
"""
from pathlib import Path
import hashlib
import re
import struct
import sys
import zipfile
import iconbuild
import necompact

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'DIST'
TARGETS = ('WIN101', 'WIN300')
# Retain the established linked-image and DGROUP ceilings. Icon bytes are
# accounted for separately by iconbuild.code_size, not charged as code.
LINKED_LIMIT = {'WIN101': min(20 * 1024, 19462 + 1024),
                'WIN300': min(20 * 1024, 18568 + 1024)}
DGROUP_LIMIT = min(11 * 1024 * 110 // 100, 10656 * 110 // 100)
USER_FILES = (
    'README.TXT', 'SCRIPT.TXT', 'HISTORY.TXT', 'LICENSE',
    'DOCS/SNAP_MODES.TXT', 'EXAMPLES/HELLO.WAS',
    'EXAMPLES/CAPTURE.WAS', 'EXAMPLES/FILECOPY.WAS',
)
SOURCE_FILES = USER_FILES + (
    '.gitignore', '.gitattributes', 'README.md', 'VERSION.TXT', 'MAKE.BAT',
    'ASSETS/WIN101.ICO', 'ASSETS/WIN300.ICO',
    'LINK/WIN101.RSP', 'LINK/WIN300.RSP',
    'SRC/WAS.ASM', 'SRC/WASFS.ASM', 'SRC/WASSNAP.ASM',
    'SRC/WASTAR.ASM', 'SRC/WASUI.ASM',
    'HOST/iconbuild.py', 'HOST/necompact.py', 'HOST/packdist.py',
)


def validate(target, data):
    """Reject malformed or oversized images before publishing local ZIPs."""
    necompact.check_packed(data)
    iconbuild.check_icons(data, target)
    ne, _, _, _, allocation, _, _ = necompact.layout(data)
    expected = (0, 0) if target == 'WIN101' else (2, 0x0300)
    if (data[ne+0x36], struct.unpack_from('<H', data, ne+0x3e)[0]) != expected:
        raise ValueError(target + ': incorrect NE target/version')
    linked = iconbuild.code_size(data, target)
    if linked > LINKED_LIMIT[target] or allocation > DGROUP_LIMIT:
        raise ValueError(target + ': executable/DGROUP size limit exceeded')
    print('%s: %d bytes, DGROUP %d bytes' % (target, len(data), allocation))


def write_zip(path, entries):
    """Use stable order, dates and permissions; never sweep the filesystem."""
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo('NOWBAT/' + name, (2026, 11, 25, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)


def verify_zip(path, entries):
    """Read back the complete archive; reject extra files or altered bytes."""
    expected = {'NOWBAT/' + name: data for name, data in entries.items()}
    with zipfile.ZipFile(path) as archive:
        if sorted(archive.namelist()) != sorted(expected):
            raise ValueError('unexpected archive contents: ' + path.name)
        for name, data in expected.items():
            if archive.read(name) != data:
                raise ValueError('archive content mismatch: ' + name)


def main():
    version = (ROOT / 'VERSION.TXT').read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('invalid VERSION.TXT')
    source = {name: (ROOT / name).read_bytes() for name in SOURCE_FILES}
    binary = {name: source[name] for name in USER_FILES}
    for target in TARGETS:
        name = target + '/NOWBAT.EXE'
        data = (DIST / name).read_bytes()
        validate(target, data)
        binary[name] = data
    outputs = ((DIST / f'NOWBAT_SOURCE_{version}.ZIP', source),
               (DIST / f'NOWBAT_BINARIES_{version}.ZIP', binary))
    # Stage both packages; a failed build must never leave a stale ZIP.
    try:
        for path, entries in outputs:
            write_zip(path.with_suffix('.tmp'), entries)
            verify_zip(path.with_suffix('.tmp'), entries)
        for path, _ in outputs:
            path.with_suffix('.tmp').replace(path)
    except Exception:
        for path, _ in outputs:
            path.unlink(missing_ok=True)
            path.with_suffix('.tmp').unlink(missing_ok=True)
        raise
    # Print the exact new asset paths, counts and hashes for the operator.
    for path, entries in outputs:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f'PACK PASS: {path} ({len(entries)} files, {path.stat().st_size} bytes)')
        print('SHA256: ' + digest)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, struct.error, AssertionError) as exc:
        print('PACKDIST FAIL:', exc, file=sys.stderr)
        sys.exit(1)
