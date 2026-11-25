#!/usr/bin/env python3
"""Host-only regression for AutoUAT evidence packaging, not native UAT."""
import importlib.util
from importlib.machinery import SourceFileLoader
import tempfile
import zipfile
from pathlib import Path

src=Path(__file__).resolve().parents[1]/'HOST'/'AUTOUAT_STREAM.PY'
spec=importlib.util.spec_from_loader('nb_auto_report',SourceFileLoader('nb_auto_report',str(src)))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    (root/'BUILD').mkdir()
    console=root/'BUILD'/'AUTOUAT.RUN.LOG'
    console.write_text('AUTOUAT FAIL: sample prerequisite\n',encoding='utf-8')
    archive=root/'AUTOUAT_OUTPUT.ZIP';latest=root/'OUTPUT.ZIP'
    m.publish(root,1,console,archive,latest)
    with zipfile.ZipFile(str(latest)) as z:
        assert z.read('AUTOUAT/RUN.LOG')==console.read_bytes()
        assert 'AUTOUAT/RESULT.JSON' not in z.namelist()
    (root/'AUTOUAT').mkdir()
    (root/'AUTOUAT'/'RESULT.JSON').write_text('{"result":"FAIL"}\n',encoding='utf-8')
    archive.unlink()
    with zipfile.ZipFile(str(archive),'w') as z:
        z.writestr('AUTOUAT/SAMPLE.LOG','native evidence placeholder')
    m.publish(root,1,console,archive,latest)
    with zipfile.ZipFile(str(latest)) as z:
        assert 'AUTOUAT/SAMPLE.LOG' in z.namelist()
        assert z.read('AUTOUAT/RUN.LOG')==console.read_bytes()
        assert z.read('AUTOUAT/RESULT.JSON') == (root/'AUTOUAT'/'RESULT.JSON').read_bytes()
    # Ensure evidence is overwritten, not appended to stale success data.
    console.write_text('AUTOUAT FAIL: second run\n',encoding='utf-8')
    archive.unlink()
    m.publish(root,1,console,archive,latest)
    with zipfile.ZipFile(str(latest)) as z:
        assert z.read('AUTOUAT/RUN.LOG') == console.read_bytes()
        assert 'AUTOUAT/SAMPLE.LOG' not in z.namelist()
    assert m.main.__name__=='main'
print('AUTOUAT_REPORT_SELFTEST=PASS (3 host-only packaging scenarios)')
