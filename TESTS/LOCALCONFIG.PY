#!/usr/bin/env python3
"""Host regression: relocatable checkout and private local configuration.

No Win16 execution or local Windows installation is required.
"""
import importlib.util
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    loader = SourceFileLoader(name, str(file))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cdrive_detection():
    u = load('nowbat_runuat_local', ROOT / 'HOST' / 'runuat.py')
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / 'CDrive'
        flat = d / 'NOWBAT'
        nested = d / 'NBUTIL' / 'WAS'
        for folder in (flat, nested):
            assert u.locate_cdrive_root(folder) == d.resolve()
        external = Path(t) / 'test' / 'NOWBAT'
        external.mkdir(parents=True)
        emulator = Path(t) / 'Dosbox-X' / 'CDrive'
        emulator.mkdir(parents=True)
        assert u.locate_cdrive_root(external) == emulator.resolve()
        other = Path(t) / 'ANOTHER'
        old = os.environ.get('NOWBAT_CDRIVE')
        try:
            os.environ['NOWBAT_CDRIVE'] = str(other)
            assert u.locate_cdrive_root(flat) == other.resolve()
        finally:
            if old is None: os.environ.pop('NOWBAT_CDRIVE', None)
            else: os.environ['NOWBAT_CDRIVE'] = old


def test_release_excludes_local_files():
    release = load('nowbat_release_local', ROOT / 'HOST' / 'RELEASE.PY')
    with tempfile.TemporaryDirectory() as t:
        clone = Path(t) / 'NOWBAT'
        clone.mkdir()
        needed = list(release.SRC_TOP) + list(release.SRC_DOCS) + list(release.SRC_ASSETS) + list(release.SRC_CI)
        for name in needed:
            dest = clone / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        for d in release.SRC_ROOTS:
            shutil.copytree(ROOT / d, clone / d,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        secret = uuid.uuid4().hex
        for name in ('MAKE.LOCAL.BAT', 'AUDIT.LOCAL.BAT', 'DISTMAKE.LOCAL.BAT',
                     'TESTS/PRIVATE.LOCAL', 'HOST/SECRET.LOCAL.CMD'):
            p = clone / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('set "PRIVATE=' + secret + '"\n')
        oldroot = release.ROOT
        try:
            release.ROOT = clone
            archive = release.build_source_zip()
        finally:
            release.ROOT = oldroot
        with zipfile.ZipFile(__import__('io').BytesIO(archive)) as z:
            names = z.namelist()
            assert 'NOWBAT/MAKE.BAT' in names
            assert 'NOWBAT/DEVELOPMENT.TXT' in names
            assert all('.LOCAL' not in name.upper() for name in names)
            assert not any(secret.encode('ascii') in z.read(name) for name in names)


def test_batch_hooks():
    hooks = {'MAKE2.BAT': 'MAKE.LOCAL.BAT',
             'AUDIT.BAT': 'AUDIT.LOCAL.BAT',
             'AUTOUAT.BAT': 'AUDIT.LOCAL.BAT',
             'DISTMAKE.BAT': 'DISTMAKE.LOCAL.BAT'}
    for script, config in hooks.items():
        text = (ROOT / script).read_text().upper()
        assert 'IF EXIST "%~DP0' + config.upper() + '" CALL' in text
    make = (ROOT / 'MAKE2.BAT').read_text().upper()
    assert '%~DP0..\\TOOLS' in make and '%~DP0..\\..\\TOOLS' in make
    assert 'JWASM_EXE' in make and 'NBJWLINK_EXE' in make
    public = (ROOT / 'MAKE.BAT').read_text().upper()
    assert '%~DP0..\\' not in public and 'WHERE /R' not in public
    ignored = (ROOT / '.gitignore').read_text().upper()
    assert '*.LOCAL.BAT' in ignored and '*.LOCAL.CMD' in ignored


if __name__ == '__main__':
    test_cdrive_detection()
    test_release_excludes_local_files()
    test_batch_hooks()
    print('NOWBAT LOCALCONFIG=PASS (two source layouts, 4 hooks, no private configs in source ZIP)')
