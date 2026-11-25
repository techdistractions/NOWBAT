#!/usr/bin/env python3
"""Adversarial verifier/watchdog tests. These never qualify a Windows guest."""
from pathlib import Path
import configparser
import contextlib
import io
import os
import struct
import re
import tarfile
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'HOST'))
import runuat as u
import runpy
static_audit = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'HOST' / 'AUDIT.PY'))


def reject(fn, label):
    try:fn()
    except u.GuestError:return
    raise AssertionError('Accepted invalid evidence: '+label)


def main():
    checks=0
    # W035: the DGROUP budget is 10% of each qualified baseline, not +128B.
    for name, (_exe_bytes, base_data) in static_audit['BASELINE'].items():
        allowance = static_audit['dgroup_growth_limit'](base_data)
        assert allowance == base_data // 10
        assert static_audit['check_dgroup_budget'](name, base_data + 160, base_data) == allowance
        assert static_audit['check_dgroup_budget'](name, base_data + allowance, base_data) == allowance
        try:
            static_audit['check_dgroup_budget'](name, base_data + allowance + 1, base_data)
        except ValueError as exc:
            assert 'DGROUP budget exceeded' in str(exc)
        else:
            raise AssertionError('Accepted >10% DGROUP growth for ' + name)
        assert base_data + allowance <= static_audit['MAX_RELEASE_DGROUP']
        checks += 5
    assert static_audit['MAX_RELEASE_DGROUP'] == (11 * 1024 * 110) // 100
    assert static_audit['MAX_EXE_GROWTH'] == 1024
    try:
        static_audit['check_dgroup_budget']('WIN101', static_audit['MAX_RELEASE_DGROUP'] + 1, 10656)
    except ValueError as exc:
        assert 'release DGROUP ceiling exceeded' in str(exc)
    else:
        raise AssertionError('Accepted DGROUP above absolute release ceiling')
    checks += 3
    # W058: the source reference must remain ASCII for source preflight.
    assert (Path(__file__).resolve().parents[1]/'SCRIPT.TXT').read_bytes().isascii()
    assert static_audit['MAX_RELEASE_EXE'] == 20*1024
    assert static_audit['MAX_DIAGNOSTIC_EXE'] == 21*1024
    assert static_audit['MAX_EXE_GROWTH'] == 1024
    assert static_audit['MAX_DIAGNOSTIC_GROWTH'] == 1536
    # W080: actual W079 linked sizes must fit the explicit development gate,
    # but ordinary diagnostics and public releases must not inherit it.
    keys = ('NOWBAT_SNAPFAST_DEV', 'NOWBAT_GUISYNC_DEV')
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        growth = static_audit['check_diagnostic_growth']
        for flag in keys:
            os.environ[flag] = '1'
            for target, linked in (('WIN101', 27444), ('WIN300', 26878)):
                base = static_audit['BASELINE'][target][0]
                growth(target, linked, base)
                icon = static_audit['iconbuild']
                data = b'0' * (linked + icon.expected_overhead(target, linked))
                static_audit['check_diagnostic_image_size'](target, data, linked)
                try:
                    static_audit['check_release_image_size'](target, data, linked)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Development executable accepted for release')
            try:
                growth('WIN300', 18568 + static_audit['MAX_GUI_DEV_GROWTH'] + 1, 18568)
            except ValueError:
                pass
            else:
                raise AssertionError('Unbounded development growth')
            del os.environ[flag]
        try:
            growth('WIN300', 26878, 18568)
        except ValueError:
            pass
        else:
            raise AssertionError('Unflagged diagnostic inherited development budget')
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    checks += 7
    # W054 regression: all six terminal link response files must carry
    # identical imports to their main image, including USER timer ordinals.
    static_audit['check_terminal_link_parity']()
    # Maintain DATE/TIME builtins and strict selectable direct-video capture.
    runtime=(Path(__file__).resolve().parents[1]/'SRC'/'WAS.ASM').read_text()
    assert 'mov ah,2Ch' in runtime and 'mov ah,2Ah' in runtime
    assert "sysTIME      db 'TIME',0" in runtime and "sysDATE      db 'DATE',0" in runtime
    assert 'WriteTwoDigits proc near' in runtime
    checks+=3
    snap=(Path(__file__).resolve().parents[1]/'SRC'/'WASSNAP.ASM').read_text()
    runtime=(Path(__file__).resolve().parents[1]/'SRC'/'WAS.ASM').read_text()
    for part in ('SnapDirectProbe proc near','SnapDirectRow proc near',
                 'snapProbeCga:','snapProbeHerc:','snapProbeEgaOK:',
                 'mov snapVideoSeg,0B800h','mov snapVideoSeg,0A000h',
                 'snapFastUnsupported:','mov wasResult,2'):
        assert part in snap, part
    for part in ('wasSnapMode','snapModeFastName','snapModeCompatName',
                 'snapModeAutoName','traceSnapDirect','traceSnapPixel'):
        assert part in runtime, part
    checks+=15
    static_audit['check_import_contract']()
    for target in ('WIN101','WIN300'):
        imports = static_audit['required_native_ordinals'](target)
        assert ('GDI',83) in imports
        assert ('GDI',48) not in imports and ('GDI',74) not in imports
    checks+=5
    # No direct-video hardware APIs should be added to the Win16 import table.
    with tempfile.TemporaryDirectory() as td:
        testroot=Path(td)
        (testroot/'LINK').mkdir()
        for target in ('WIN101', 'WIN300'):
            original=(Path(__file__).resolve().parents[1]/'LINK'/(target+'.RSP')).read_text(encoding='ascii')
            if target=='WIN300':
                original += 'IMPORT CreateBitmap GDI.48\n'
            (testroot/'LINK'/(target+'.RSP')).write_text(original,encoding='ascii')
        checker=static_audit['check_import_contract']
        oldroot=checker.__globals__['ROOT']
        try:
            checker.__globals__['ROOT']=testroot
            try:
                checker()
            except ValueError as exc:
                assert 'WIN300: linker/native ordinal mismatch' in str(exc)
            else:
                raise AssertionError('Unexpected GDI dependency accepted by source verifier')
        finally:
            checker.__globals__['ROOT']=oldroot
    checks+=1
    for term in ('NBTEND','NBTPASS','NBTFAIL'):
        rsp=(Path(__file__).resolve().parents[1]/'LINK'/'TERMS'/('WIN300_'+term+'.RSP')).read_text()
        assert 'IMPORT SetTimer USER.10' in rsp
        assert 'IMPORT KillTimer USER.12' in rsp
        assert 'IMPORT WaitMessage USER.112' in rsp
    checks+=7
    # Confirm that source preflight rejects the exact missing SetTimer case.
    with tempfile.TemporaryDirectory() as td:
        import shutil
        testroot=Path(td)
        shutil.copytree(Path(__file__).resolve().parents[1]/'LINK',testroot/'LINK')
        rsp=testroot/'LINK'/'TERMS'/'WIN300_NBTEND.RSP'
        rsp.write_text(rsp.read_text().replace('IMPORT SetTimer USER.10\n',''))
        checker=static_audit['check_terminal_link_parity']
        oldroot=checker.__globals__['ROOT']
        try:
            checker.__globals__['ROOT']=testroot
            try:
                checker()
            except ValueError as exc:
                assert 'WIN300 NBTEND import mismatch' in str(exc)
                assert 'IMPORT SETTIMER USER.10' in str(exc)
            else:
                raise AssertionError('Missing SetTimer import accepted')
        finally:
            checker.__globals__['ROOT']=oldroot
    checks+=2
    icon=static_audit['iconbuild']
    for target, linked in (('WIN101', 20180), ('WIN300', 19264)):
        exact=linked+icon.expected_overhead(target,linked)
        overhead=static_audit['check_release_image_size'](target,b'0'*exact,linked)
        assert overhead==icon.expected_overhead(target,linked)
        try:
            static_audit['check_release_image_size'](target,b'0'*(exact+1),linked)
        except ValueError as exc:
            assert 'unexpected extra bytes' in str(exc)
        else:
            raise AssertionError('Accepted extra non-icon byte for '+target)
        too_big=20*1024+1
        try:
            static_audit['check_release_image_size'](target,b'0'*(too_big+icon.expected_overhead(target,too_big)),too_big)
        except ValueError as exc:
            assert 'linked NE exceeds 20 KiB' in str(exc)
        else:
            raise AssertionError('Accepted >20 KiB linked executable for '+target)
        diag_linked=20678 if target=='WIN101' else 19936
        diag_exact=diag_linked+icon.expected_overhead(target,diag_linked)
        assert static_audit['check_diagnostic_image_size'](target,b'0'*diag_exact,diag_linked) == icon.expected_overhead(target,diag_linked)
        try:
            static_audit['check_release_image_size'](target,b'0'*diag_exact,diag_linked)
        except ValueError as exc:
            if target=='WIN101':
                assert 'linked NE exceeds 20 KiB' in str(exc)
            else:
                raise
        else:
            if target=='WIN101':
                raise AssertionError('Diagnostics silently passed the release cap')
        checks+=5
    checks+=2
    # SHELL / SHELLWAIT must use the native Windows module lifetime.
    core=(Path(__file__).resolve().parents[1]/'SRC'/'WAS.ASM').read_text()
    assert 'call LoadModule' in core and 'call GetModuleUsage' in core
    assert 'commandShellNoWait:' in core and 'commandShellWait:' in core
    assert 'wasWindowsWait:' in core and 'call Yield' in core
    assert 'WASRUN.COM' not in core and 'INCBIN <BUILD/WASRUN.BIN>' not in core
    assert not (Path(__file__).resolve().parents[1]/'SRC'/'WASRUN.ASM').exists()
    checks+=5
    # Match NOWBAT's proven Win1 KERNEL.45 parameter ABI, not DOS PSP FCBs.
    # Keep the independent static checks precise: a placeholder import is
    # not proof that WAS constructs the right runtime call arguments.
    assert re.search(r'wasShow\s+dw\s+2\s*,\s*1', core)
    assert re.search(r'wasExecBlock\s+dw\s+0\s*,\s*offset wasCmdTail\s*,\s*0\s*,\s*offset wasShow\s*,\s*0\s*,\s*0\s*,\s*0', core)
    assert 'wasFcb1' not in core and 'wasFcb2' not in core
    assert 'mov word ptr wasExecBlock+12,ax' not in core
    assert re.search(r'wasShellArgsReady:.*?call CopyString260\s+call ExpandArg', core, re.S)
    assert re.search(r'wasWinTailEnd:\s+mov byte ptr \[di\],0\s+mov byte ptr wasCmdTail,cl', core)
    assert re.search(r'wasWindowsWait:.*?call GetModuleUsage.*?mov wasShellUsage,ax', core, re.S)
    assert re.search(r'wasWinWaitPoll:.*?call GetModuleUsage.*?mov ax,@data\s+mov ds,ax\s+mov es,ax\s+cld\s+mov ax,bx.*?cmp ax,wasShellUsage\s+jb wasWinChildDone', core, re.S)
    checks+=8
    # Regression: post-LoadModule execution must not reuse stale DS:wasLine.
    assert re.search(r'wasLoop:.*?mov ax,@data\s+mov ds,ax\s+mov es,ax\s+cld',core,re.S)
    assert re.search(r'call LoadModule.*?push ax\s+mov ax,@data\s+mov ds,ax\s+mov es,ax\s+cld\s+pop ax',core,re.S)
    assert 'traceShellNext' not in core and 'SHELL_NEXT=' not in core
    assert re.search(r'wasShellLaunchFailed:.*?or ax,ax\s+jnz wasShellErrorNonzero\s+mov ax,1',core,re.S)
    checks+=4
    # Win1 child unload must not strand interpreter DS or conceal an early EOF.
    assert re.search(r'wasLoop:.*?call UiPump.*?mov ax,@data\s+mov ds,ax\s+mov es,ax\s+cld',core,re.S)
    assert 'traceLoopStop' not in core
    assert 'traceLoopEof' not in core
    assert 'traceReadError' not in core
    assert re.search(r'wasWinWaitPoll:.*?call GetModuleUsage.*?mov ax,@data\s+mov ds,ax\s+mov es,ax',core,re.S)
    checks+=5
    # W044: independent NE child modules, no Win1 pre-wait/marker deletion.
    fixture=(Path(__file__).resolve().parent/'TEST.WAS').read_text()
    assert 'WAIT 3000' not in fixture and 'DEL "WCHILD.OK"' not in fixture
    assert fixture.index('SHELL "WCHILD.EXE"') < fixture.index('COPY "TEST.WAS" "C:\\WASUAT\\BEFORE.OK"')
    assert fixture.index('COPY "TEST.WAS" "C:\\WASUAT\\BEFORE.OK"') < fixture.index('SHELLWAIT "WWAIT.EXE"')
    assert 'EXISTS "WWAIT.OK"' in fixture
    assert 'IF %WINVER% NE 3 THEN GOTO CF_WAIT_CHILD\nWAITFOR FILE "WCHILD.OK" TIMEOUT 15000\nASSERT %RESULT% EQ 0\n:CF_WAIT_CHILD' in fixture
    assert 'WWAIT.EXE' in (Path(__file__).resolve().parent.parent/'LINK'/'WWAIT.RSP').read_text()
    assert 'WAS_WAIT_CHILD=1' in (Path(__file__).resolve().parent.parent/'MAKE2.BAT').read_text()
    assert 'SaveWaitInfo proc near' in core and 'wasWaitTrace' in core
    assert 'SWWAIT.DAT' in core and 'SWWAIT.DAT' in u.collect.__code__.co_consts.__str__()
    with tempfile.TemporaryDirectory() as temp:
        import struct
        stage=Path(temp);(stage/'SWWAIT.DAT').write_bytes(struct.pack('<4H',0x1BA,2,2,2))
        t={'staged_win':stage}
        assert 'baseline=2 observed=2 phase=2' in u.win1_wait_snapshot(t)
        (stage/'SWWAIT.DAT').write_bytes(b'bad')
        assert 'invalid size' in u.win1_wait_snapshot(t)
        (stage/'SWWAIT.DAT').unlink()
        assert 'absent' in u.win1_wait_snapshot(t)
    checks+=7
    # No Win2 disk-swap dialog: missing SHELL targets are probed before
    # KERNEL.LoadModule. A scripted nonexistent EXE must be an error result.
    preflight=core.index('wasShellPathOk:')
    shell_call=core.index('call LoadModule',preflight)
    assert 'mov ax,3D00h' in core[preflight:shell_call]
    assert 'call Dos3Call' in core[preflight:shell_call]
    assert 'jmp wasShellLaunchFailed' in core[preflight:shell_call]
    assert 'SHELL "NOAPP.EXE"' in (Path(__file__).resolve().parents[1]/'TESTS'/'TEST.WAS').read_text()
    checks += 4
    # Built-in variables resolve through FindVar, not a hardcoded host value.
    assert all('sys'+x in core for x in ('WINVER','SCREENW','SCREENH','BPP','DISKFREE'))
    assert 'call GetDC' in core and 'call GetDeviceCaps' in core
    assert 'mov ah,36h' in core and 'FormatDword proc near' in core
    assert re.search(r'call FindVar\s+jc wasStoreNewVar\s+.*?cmp bx,offset wasNumResult\s+je wasStoreDone',core,re.S)
    assert 'ENV_IF_OK=@RUN@' in (Path(__file__).resolve().parents[1]/'TESTS'/'TEST.WAS').read_text()
    for label in ('wasCheckResult','wasCheckWinVer','wasCheckScreenW','wasCheckScreenH','wasCheckBpp'):
        assert re.search(r'%s:\s+;[^\n]*\n lea si,wasWord\s+lea di,sys'%label,core),label
    assert 'ENV.LOG' in (Path(__file__).resolve().parents[1]/'TESTS'/'TEST.WAS').read_text()
    assert 'ENV.LOG' in u.validate_control.__code__.co_consts or 'ENV.LOG' in u.validate_control.__code__.co_names
    checks += 8
    # Early Win1/Win2 icon contains the ICONEDIT type word, followed by
    # its 12-byte 1bpp header and two 128-byte bitplanes. A structurally
    # valid NE resource without that word can paint a clipped icon in Win2.
    import importlib.util
    icon_path=Path(__file__).resolve().parents[1]/'HOST'/'iconbuild.py'
    icon_spec=importlib.util.spec_from_file_location('was_icon_build',str(icon_path))
    icon_module=importlib.util.module_from_spec(icon_spec)
    icon_spec.loader.exec_module(icon_module)
    mono=icon_module.payloads('WIN101')[0][2]
    assert mono[:2]==b'\x01\x00'
    assert len(mono)==2+12+128+128
    assert mono[6:12]==b'\x20\x00\x20\x00\x04\x00'
    checks+=3
    # Host-only self-tests must remain on their default 50s startup budget,
    # even when the native SNAPFAST run uses the separate 750-cycle profile.
    # No early-GDI or runtime code should depend on host test isolation.
    audit_src=(Path(__file__).resolve().parents[1]/'HOST'/'AUDIT.PY').read_text()
    isolation_block=audit_src[audit_src.index('def run_selftest('):audit_src.index('def main():')]
    assert "'NOWBAT_SNAPFAST_DEV'" in isolation_block
    checks+=1
    # The early startup cap is independent of WAIT/BMP/TAR guest lifetime.
    assert u.STARTUP_TRACE_LIMIT_SECONDS==50
    assert u.EXPECTED_BUILD_MARKER=='NOWBAT_BUILD=W054'
    assert not u.startup_timed_out(49.999,[])
    assert u.startup_timed_out(50.0,[])
    assert u.startup_timed_out(50.0,['WAS_INITTASK'])
    assert u.startup_timed_out(60.0,['WAS_OPEN=TEST.WAS'])
    assert not u.startup_timed_out(60.0,['NOWBAT_BUILD=W054','WAS_OPEN=TEST.WAS'])
    # A real, closed WAIT witness prevents false no-startup timeouts even
    # while the Win16 interpreter's EARLY.LOG handle is still open.
    assert not u.startup_timed_out(60.0,[],True)
    assert u.startup_timed_out(60.0,[],False)
    # Native-progress witnesses must match this run's exact token. A stale
    # marker from a previous guest must not bypass the 50s startup watchdog.
    with tempfile.TemporaryDirectory() as td:
        st={'uat':Path(td),'token':'ABC123'}
        assert not u.native_startup_witness(st)
        (Path(td)/'WSTART.OK').write_bytes(b'WAIT_BEGIN=WRONG\r\n')
        assert not u.native_startup_witness(st)
        (Path(td)/'WSTART.OK').write_bytes(b'WAIT_BEGIN=ABC123\r\n')
        assert u.native_startup_witness(st)
        (Path(td)/'WSTART.OK').unlink()
        (Path(td)/'WEND.OK').write_bytes(b'WAIT_DONE=ABC123\r\n')
        assert u.native_startup_witness(st)
    checks+=11
    make=(Path(__file__).resolve().parents[1]/'MAKE2.BAT').read_text()
    assert r'TESTS\WCHILD.ASM' in make and ' -FoBUILD\\WASRUN.BIN' not in make
    assert r'LINK\WCHILD.RSP' in make and r'LINK\WWAIT.RSP' in make
    checks+=2
    # Two independent operator commands: MAKE builds; AUDIT only tests.
    make_bat=(Path(__file__).resolve().parents[1]/'MAKE.BAT').read_text()
    audit_bat=(Path(__file__).resolve().parents[1]/'AUDIT.BAT').read_text()
    stream=(Path(__file__).resolve().parents[1]/'HOST'/'STREAM.PY').read_text()
    assert re.search(r'NOWBAT W[0-9]+ MAKE', make_bat)
    assert 'call "%~dp0MAKE2.BAT" ALL' in make_bat
    assert 'BUILD\\SNAPFAST.READY' in make_bat
    assert re.search(r'NOWBAT W[0-9]+ AUDIT', audit_bat)
    assert r'HOST\STREAM.PY %MODE%' in audit_bat
    assert 'if not exist BUILD\\SNAPFAST.READY goto no_build' in audit_bat
    assert 'call "%~dp0MAKE2.BAT"' not in audit_bat
    assert 'call "%~dp0VERIFY.BAT"' not in audit_bat
    assert 'call "%~dp0MAKE.BAT"' not in audit_bat
    assert 'WAS_AUDIT_DRYRUN' in audit_bat
    assert '"NOWBAT_STARTSHOT=1"' in audit_bat
    assert '"WAS_UAT_DESKTOP=visible"' in audit_bat
    assert 'if /I "%MODE%"=="ALL" set "MODE=FULL"' in audit_bat
    assert "sys.argv[1].upper()" in stream and "mode]" in stream
    assert u.AUDIT_ORDER == ('WIN300','WIN200','WIN101')
    checks+=15
    # The developer MAKE must avoid Windows CMD builtin VERIFY.
    # AUDIT must not perform pre-build checking.
    verify_bat=(Path(__file__).resolve().parents[1]/'VERIFY.BAT').read_text()
    verify_alias=(Path(__file__).resolve().parents[1]/'WASVERIFY.BAT').read_text()
    assert 'call "%~dp0VERIFY.BAT"' in verify_alias
    assert 'SOURCE VERIFIED' in verify_bat
    assert 'call "%~dp0VERIFY.BAT"' not in make
    assert "'VERIFY.BAT','WASVERIFY.BAT'" in (Path(__file__).resolve().parents[1]/'HOST'/'PACK.PY').read_text()
    checks+=4
    # On Windows, test dispatcher parsing without building or starting DOSBox.
    if os.name=='nt':
        import subprocess
        root=Path(__file__).resolve().parents[1]
        env=os.environ.copy()
        env['WAS_AUDIT_DRYRUN']='1'
        cmd=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c']
        cases=[
            ([],0,'MODE=STARTSHOT'),
            (['SNAPFAST'],0,'MODE=STARTSHOT'),
            (['SNAPFAST','WIN300'],0,'MODE=STARTSHOT'),
            (['SNAPFAST','WIN101'],0,'MODE=STARTSHOT'),
            (['STARTSHOT'],0,'MODE=STARTSHOT'),
            (['ALL'],0,'MODE=FULL'),
            (['WIN300'],0,'MODE=WIN300'),
            (['WIN200'],0,'MODE=WIN200'),
            (['WIN101'],0,'MODE=WIN101'),
            (['WIN200','BOOT'],0,'MODE=WIN200'),
            (['INPUT'],0,'MODE=INPUT'),
            (['INPUT','WIN101'],0,'MODE=INPUT'),
            (['INPUT','WIN200'],0,'MODE=INPUT'),
            (['INPUT','WIN300'],0,'MODE=INPUT'),
            (['INPUT','INVALID'],2,'Usage: AUDIT'),
            (['UNKNOWN'],2,'Usage: AUDIT'),
        ]
        for args,expected,marker in cases:
            outcome=subprocess.run(cmd+['AUDIT.BAT']+args,cwd=root,env=env,
                                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   timeout=15,text=True,errors='replace')
            assert outcome.returncode == expected, (args,outcome.returncode,outcome.stdout)
            assert marker in outcome.stdout, (args,outcome.stdout)
            checks+=1
    # The default UAT launch MUST be visible to inspect SDL guest windows.
    # An explicitly selected private desktop remains a deliberate opt-in.
    cfg_mode=configparser.ConfigParser()
    prior={k:os.environ.pop(k) for k in ('WAS_UAT_DESKTOP','WAS_DESKTOP') if k in os.environ}
    try:
        assert u.guest_desktop_mode(cfg_mode)=='visible'
        cfg_mode['runner']={'desktop':'hidden'}
        assert u.guest_desktop_mode(cfg_mode)=='hidden'
        cfg_mode['runner']={'desktop':'invalid'}
        reject(lambda:u.guest_desktop_mode(cfg_mode),'invalid guest desktop')
        cfg_mode['runner']={'desktop':'hidden'}
        os.environ['WAS_UAT_DESKTOP']='visible'
        assert u.guest_desktop_mode(cfg_mode)=='visible'
        checks+=4
    finally:
        os.environ.pop('WAS_UAT_DESKTOP',None)
        os.environ.update(prior)
    from winvisible import VisibleProcess
    with tempfile.TemporaryDirectory() as tmp:
        with (Path(tmp)/'VISIBLE.LOG').open('wb') as stream:
            proc=VisibleProcess([sys.executable,'-c','import time;time.sleep(30)'],tmp,stream)
            try:
                assert proc.desktop_name is None and proc.pid>0
                assert proc.poll() is None and proc.window_count()==1
                checks+=2
            finally:
                if proc.poll() is None:proc.terminate()
                proc.wait(timeout=5)
                assert proc.window_count()==0
                proc.close()
                assert proc.process is None
                checks+=2
    for target in ('WIN101','WIN300'):
        rsp=(Path(__file__).resolve().parents[1]/'LINK'/(target+'.RSP')).read_text()
        assert 'IMPORT LoadModule KERNEL.45' in rsp
        assert 'IMPORT GetModuleUsage KERNEL.48' in rsp
        wanted=static_audit['required_native_ordinals'](target)
        assert ('KERNEL',45) in wanted and ('KERNEL',48) in wanted
        checks+=2
    # The auxiliary fixture is a separate Win16 program, not a DOS child.
    child=(Path(__file__).resolve().parents[1]/'TESTS'/'WCHILD.ASM').read_text()
    assert 'WCHILD.OK' in child and 'WWAIT.OK' in child and 'call InitTask' in child
    assert re.search(r'call Yield\s+mov ax,@data\s+mov ds,ax\s+mov es,ax\s+cld',child)
    checks+=1
    # Both standard AUDIT and AutoUAT are fail-fast; the remaining targets
    # are explicitly SKIPPED, never reported as native PASS or FAIL.
    runner=(Path(__file__).resolve().parents[1]/'HOST'/'runuat.py').read_text()
    for piece in ("first_failure=None", "if first_failure is not None:",
                  "'result':'SKIPPED'", "AUDIT NATIVE FAIL-FAST at",
                  "AUTOUAT GUEST FAIL"):
        assert piece in runner, 'missing fail-fast contract: '+piece
        checks+=1
    # Win16 USER APIs are FAR PASCAL, with LEFT-TO-RIGHT arguments.
    # Catch the actual 0.0.23 regression (reverse-ordered parameters and
    # WNDPROC offsets) before a new emulator session is spent debugging it.
    ui = (Path(__file__).resolve().parents[1]/'SRC'/'WASUI.ASM').read_text()
    uncommented = '\n'.join(line.split(';',1)[0] for line in ui.splitlines())
    def routine(name):
        found = re.search(r'(?ims)^'+name+r'\s+proc\s+(?:near|far)\b(.*?)^'+name+r'\s+endp\b',uncommented)
        assert found is not None, 'missing '+name
        return found.group(1)
    op = routine('UiOpen')
    assert re.search(r'push\s+wasIconWnd\s+xor ax,ax\s+push ax\s+call GetSystemMenu',op)
    assert re.search(r'push\s+wasIconWnd\s+mov ax,2\s+push ax\s+call ShowWindow',op)
    assert re.search(r'push\s+wasInst\s+push ax\s+push ax\s+call CreateWindow',op)
    assert re.search(r'push\s+ax\s+inc ax\s+push ax\s+call LoadIcon',op)
    assert 'uiRemoveItem' not in op
    assert 'jz uiShow' in op
    # Runtime-detected WIN101 disables WS_SYSMENU, skips the menu APIs,
    # and prevents its About callback. WIN200 uses the same NE and keeps UI.
    assert 'call GetVersion' in op and 'mov uiWinMajor,bl' in op
    assert 'mov ax,020C0h' in op and 'cmp uiWinMajor,1' in op
    assert re.search(r'uiWindowOK:\s+mov wasIconWnd,ax\s+cmp uiWinMajor,1\s+je uiShow',op)
    assert 'cmp uiWinMajor,1' in routine('UiWndProc')
    checks += 8
    menu = routine('UiChangeMenu')
    assert re.search(r'push\s+bx\s+xor si,si\s+push si\s+push ds\s+push dx\s+push cx\s+push ax\s+call ChangeMenu',menu)
    checks += 1
    pump = routine('UiPump')
    assert re.search(r'push\s+ax\s+push ax\s+inc ax\s+push ax\s+call PeekMessage',pump)
    checks += 1
    callback = routine('UiWndProc')
    assert re.search(r'mov ax,\[bp\+12\]\s+cmp ax,0112h',callback)
    assert re.search(r'push word ptr \[bp\+14\]\s+push ds',callback)
    assert re.search(r'push word ptr \[bp\+14\]\s+push word ptr \[bp\+12\]\s+push word ptr \[bp\+10\]\s+push word ptr \[bp\+8\]\s+push word ptr \[bp\+6\]\s+call DefWindowProc',callback)
    checks += 3
    assert 'SHOWICON=YES' in ui or 'uiFailStage' in ui
    assert 'uiFailStage' in (Path(__file__).resolve().parents[1]/'SRC'/'WAS.ASM').read_text()
    checks += 1
    # Both bat icons are native resources, not just image previews.
    import iconbuild
    boot_text = (Path(__file__).resolve().parents[1]/'TESTS'/'BOOT.WAS').read_text()
    assert 'ShowIcon=YES' in boot_text and 'ShowIcon=NO' in boot_text
    assert 'SHUTDOWN' in boot_text and 'SHELL' not in boot_text and '%WINVER%' not in boot_text
    assert 'set "WAS_UAT_BOOT_ONLY="' in audit_bat
    assert 'set "WAS_UAT_BOOT_ONLY=1"' in audit_bat
    checks+=3
    for target in ('WIN101','WIN300'):
        ico=iconbuild.create_ico(target)
        assert ico[:4]==b'\x00\x00\x01\x00' and len(ico)<900
        for typ,rid,asset in iconbuild.payloads(target):
            assert typ in (3,14) and rid in (1,2) and asset
        checks+=2
    # A native-qualified interpreter used 'LOGClose' for the command name.
    # The 0.0.23 static gate must not confuse its mixed case with a stale EXE.
    # The actual linked USER ordinals must include the optional icon imports.
    commands = b'\0'.join(token[:-1] for token in static_audit['REQUIRED_BINARY_COMMANDS']) + b'\0'
    mixed_case = commands.replace(b'LOGCLOSE\0', b'LOGClose\0')
    assert static_audit['missing_binary_commands'](mixed_case) == []
    checks += 1
    assert static_audit['missing_binary_commands'](mixed_case.replace(b'LOGClose\0', b'NOLOGCMD\0')) == ['LOGCLOSE']
    checks += 1
    for target in ('WIN101', 'WIN300'):
        wanted = static_audit['required_native_ordinals'](target)
        assert static_audit['UI_ORDINALS'].issubset(wanted)
        assert (('USER', 2) in wanted) == (target == 'WIN101')
        assert (('USER', 7) in wanted) == (target == 'WIN300')
        assert wanted != (wanted - {('USER', 174)})
        checks += 1
    with tempfile.TemporaryDirectory() as directory:
        drive=Path(directory)/'CDRIVE';root=drive/'NBUTIL'/'WAS'
        (root/'TESTS').mkdir(parents=True)
        (root/'TESTS'/'TEST.WAS').write_bytes((Path(__file__).resolve().parent/'TEST.WAS').read_bytes())
        (root/'BUILD').mkdir()
        (root/'BUILD'/'WCHILD.EXE').write_bytes(b'HOST_ONLY_WCHILD_SIMULATION')
        (root/'BUILD'/'WWAIT.EXE').write_bytes(b'HOST_ONLY_WWAIT_SIMULATION')
        for target in ('WIN101','WIN300'):
            p=root/'DIST'/target;p.mkdir(parents=True)
            (p/'NOWBAT.EXE').write_bytes(b'NOT_A_GUEST_BINARY')
        for name in ('WIN1','WIN2','WIN3'):
            p=drive/'TOOLS'/name;p.mkdir(parents=True)
            (p/'WIN.COM').write_bytes(b'NOT_A_GUEST_LOADER')
            (p/'WIN.INI').write_bytes(b'[windows]\r\nrun=ORIGINAL.EXE\r\n')
            (p/'DRIVER.DRV').write_bytes(b'ORIGINAL')
        oldroot,olddrive=u.ROOT,u.CDRIVE
        try:
            u.ROOT,u.CDRIVE=root,drive
            cfg=configparser.ConfigParser(interpolation=None)
            for target in u.TARGETS:
                st=u.stage(target,cfg)
                u.prepare_phase(st,'FOUNDATION')
                token=st['token'];guest=st['uat'];win=st['staged_win']
                # Filesystem UAT deliberately CHDIRs away from WIN, where
                # TEST.WAS lives. A bare EXISTS "TEST.WAS" would therefore
                # fail despite valid DOS file commands and abort before SNAP.
                staged_script=(win/'TEST.WAS').read_text(encoding='ascii')
                assert 'ShowIcon=YES' in staged_script and 'ShowIcon=NO' in staged_script
                assert 'SHELLWAIT "WWAIT.EXE" "ALPHA BETA" GAMMA' in staged_script
                assert 'GOSUB CF_SUB' in staged_script
                assert (win/'WCHILD.EXE').read_bytes()==b'HOST_ONLY_WCHILD_SIMULATION'
                assert (win/'WWAIT.EXE').read_bytes()==b'HOST_ONLY_WWAIT_SIMULATION'
                assert not (win/'WCHILD.OK').exists() and not (win/'WWAIT.OK').exists()
                assert 'LOG "FS_ALL_OK='+token+'"' in staged_script
                after_fs=staged_script.split('LOG "FS_ALL_OK='+token+'"',1)[1]
                assert 'EXISTS "TEST.WAS"' not in after_fs
                assert ('EXISTS "'+u.guest_path(guest,drive)+'\\FS\\MOVED.TXT"') in after_fs
                checks+=1
                def good():
                    (win/'WCHILD.EXE').write_bytes((root/'BUILD'/'WCHILD.EXE').read_bytes())
                    (win/'WWAIT.EXE').write_bytes((root/'BUILD'/'WWAIT.EXE').read_bytes())
                    for name,prefix in (('DOSBOOT.OK','DOSBOOT'),('DOSEND.OK','DOSEND')):
                        (guest/name).write_text(prefix+' '+token+'\n')
                    lines=['WAS_RUN='+token,'WAIT_BEGIN='+token,'WAIT_DONE='+token,
                           'CHECKS_OK='+token,'SNAP_OK_4BPP='+token,'EVIDENCE_READY='+token]
                    (guest/'WSTART.OK').write_bytes(('WAIT_BEGIN='+token+'\r\n').encode('ascii'))
                    (guest/'WEND.OK').write_bytes(('WAIT_DONE='+token+'\r\n').encode('ascii'))
                    (guest/'DESKTOP.LOG').write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))
                    stride=((320*4+31)//32)*4
                    offset=118
                    pixels=b'\x11'*(stride*200)
                    img=bytearray(offset+len(pixels))
                    struct.pack_into('<2sIHHI',img,0,b'BM',len(img),0,0,offset)
                    struct.pack_into('<IiiHHII',img,14,40,320,200,1,4,0,len(pixels))
                    img[offset:]=pixels
                    (guest/'DESKTOP.BMP').write_bytes(bytes(img))
                    tarbuf=io.BytesIO()
                    with tarfile.open(fileobj=tarbuf,mode='w',format=tarfile.USTAR_FORMAT) as archive:
                        for name in ('DESKTOP.LOG','DESKTOP.BMP'):
                            data=(guest/name).read_bytes()
                            info=tarfile.TarInfo(name);info.size=len(data)
                            archive.addfile(info,io.BytesIO(data))
                    (guest/'EVIDENCE.TAR').write_bytes(tarbuf.getvalue())
                    # Independently reconstructed filesystem evidence. The
                    # guest's own assertions are insufficient for acceptance.
                    fsdir=guest/'FS';fsdir.mkdir(exist_ok=True)
                    for item in fsdir.iterdir():
                        if item.is_dir():import shutil;shutil.rmtree(str(item))
                        else:item.unlink()
                    (fsdir/'MOVED.TXT').write_bytes((win/'TEST.WAS').read_bytes())
                    (win/'WCHILD.OK').write_bytes(u.expected_child_version(target))
                    (win/'WWAIT.OK').write_bytes(u.expected_child_version(target))
                    (guest/'BEFORE.OK').write_bytes((win/'TEST.WAS').read_bytes())
                    (guest/'AFTER.OK').write_bytes((win/'TEST.WAS').read_bytes())
                    (guest/'ENV.LOG').write_text(
                        'WINVER='+str({'WIN101':1,'WIN200':2,'WIN300':3}[target])+"\n"+
                        'SCREENW=640\nSCREENH=480\nBPP=4\nDISKFREE(C)=4096\n')
                    (guest/'CONTROL.LOG').write_bytes(('IF_EQ_NE_OK='+token+'\r\nENV_IF_OK='+token+'\r\nGOSUB_RETURN_OK='+token+
                        '\r\nSHELL_LAUNCH_OK='+token+'\r\nSHELLWAIT_WIN16_OK='+token+'\r\nSHELL_ERROR_OK='+token+'\r\n').encode('ascii'))
                    (guest/'FS.LOG').write_bytes(('MOVED.TXT\r\nFS_DIR_OK='+token+
                        '\r\nNBUTIL\\WAS\\BUILD\\UAT\\FS\r\nFS_ALL_OK='+token+'\r\n').encode('ascii'))
                    version={'WIN101':'0001','WIN200':'0302','WIN300':'0003'}[target]
                    trace=['WAS_INITTASK','NOWBAT_BUILD=W054','WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_VERSION='+version]
                    if target=='WIN300':trace+=['WAS_WINFLAGS=0000']
                    trace+=['WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=YES',
                            'SHELL_LAUNCHED','SHELL_LAUNCHED','SHELLWAIT_COMPLETED',
                            'SHELL_LAUNCH_ERROR=2','SNAP_BIOS_MODE=00FF','SNAP_METHOD=GETPIXEL',
                            'SHOWICON=NO','WAS_SHUTDOWN_REQUESTED',
                            'WAS_SHUTDOWN_API='+('USER.7' if target=='WIN300' else 'USER.2')]
                    (win/'EARLY.LOG').write_text('\n'.join(trace)+'\n')
                good()
                assert u.validate_desktop(st)['status']=='PASS'
                assert not u.startup_timed_out(51,[],u.native_startup_witness(st))
                assert u.closed_env_witness(st)
                assert u.closed_script_checkpoint(st,'BEFORE.OK') and u.closed_script_checkpoint(st,'AFTER.OK')
                checks+=3
                good();(guest/'BEFORE.OK').unlink()
                reject(lambda:u.validate_control(st),'missing prechild checkpoint');checks+=1
                good();(guest/'AFTER.OK').write_bytes(b'OLD_SCRIPT')
                reject(lambda:u.validate_control(st),'corrupt postchild checkpoint');checks+=1
                if target=='WIN200':
                    (guest/'BOOT.LOG').write_text('WAS_BOOT_OK='+token+'\n')
                    assert u.validate_boot(st)['status']=='PASS'
                    checks+=1
                    (guest/'BOOT.LOG').write_text('WAS_BOOT_OK=OTHER\n')
                    reject(lambda:u.validate_boot(st),'invalid boot-only result token')
                    checks+=1
                    (guest/'BOOT.LOG').unlink()
                    reject(lambda:u.validate_boot(st),'missing BOOT.LOG')
                    checks+=1
                good();(guest/'ENV.LOG').write_text('WINVER=0\nSCREENW=640\nSCREENH=480\nBPP=4\nDISKFREE(C)=4096\n')
                reject(lambda:u.validate_desktop(st),'incorrect builtin Windows version');checks+=1
                good();(guest/'ENV.LOG').write_text('WINVER=2\nSCREENW=0\nSCREENH=480\nBPP=4\nDISKFREE(C)=4096\n')
                reject(lambda:u.validate_desktop(st),'zero live width');checks+=1
                good();(guest/'ENV.LOG').unlink()
                reject(lambda:u.validate_desktop(st),'missing ENV.LOG');checks+=1
                good();(guest/'CONTROL.LOG').write_text('SHELLWAIT_WIN16_OK=CORRUPT\n')
                reject(lambda:u.validate_desktop(st),'corrupt control-flow output');checks+=1
                good();(win/'WCHILD.EXE').write_bytes(b'INVALID_CHILD_BINARY')
                reject(lambda:u.validate_desktop(st),'tampered Win16 child');checks+=1
                good();(win/'WWAIT.EXE').write_bytes(b'INVALID_WAIT_BINARY')
                reject(lambda:u.validate_desktop(st),'tampered SHELLWAIT child');checks+=1
                good();(win/'WCHILD.OK').unlink()
                reject(lambda:u.validate_desktop(st),'missing Win16 child completion');checks+=1
                good();(win/'WWAIT.OK').unlink()
                reject(lambda:u.validate_desktop(st),'missing SHELLWAIT completion');checks+=1
                # A closed-file timing witness may not be replaced by two
                # buffered log rows seen simultaneously at process exit.
                assert u.verify_wait_interval(st,100.0,105.0)['method']=='host-monotonic'
                reject(lambda:u.verify_wait_interval(st,100.0,100.0),'zero-duration wait');checks+=1
                good();(guest/'WSTART.OK').unlink()
                reject(lambda:u.validate_desktop(st),'missing pre-WAIT marker');checks+=1
                good();(guest/'WEND.OK').write_text('WAIT_DONE=OLD_RUN\n')
                reject(lambda:u.validate_desktop(st),'stale post-WAIT marker');checks+=1
                good();(guest/'WEND.OK').unlink()
                reject(lambda:u.verify_wait_interval(st,100.0,105.0),'missing post-WAIT marker');checks+=1
                good();os.utime(guest/'WSTART.OK',ns=(100_000_000_000,100_000_000_000))
                os.utime(guest/'WEND.OK',ns=(105_000_000_000,105_000_000_000))
                assert u.verify_wait_interval(st,None,None)['method']=='host-file-mtime'
                good()
                # Runtime-only telemetry must not change the exact native
                # event contract, and unrelated trace lines must still fail.
                trace_path=win/'EARLY.LOG'
                trace_base=trace_path.read_text()
                trace_path.write_text(trace_base.replace(
                    'SHELL_LAUNCHED\n',
                    'SHELL_LOAD_AX=4321\nSHELL_ES_RESTORED\nSHELL_NEXT=ASSERT %RESULT% EQ 0\nSHELL_LAUNCHED\n',1))
                assert u.validate_desktop(st)['status']=='PASS'
                checks+=1
                trace_path.write_text(trace_base.replace('SHELL_LAUNCHED\n',
                    'UNKNOWN_DIAGNOSTIC=BAD\nSHELL_LAUNCHED\n',1))
                reject(lambda:u.validate_desktop(st),'unrecognized diagnostic trace')
                checks+=1
                good()
                # W083: exact SNAPSAFE diagnostic pair, not blanket filtering.
                trace_base=trace_path.read_text()
                pair='SNAP_BIOS_MODE=00FF\nSNAP_METHOD=GETPIXEL\n'
                assert pair in trace_base
                for bad in ('', 'SNAP_BIOS_MODE=00FF\n',
                            'SNAP_METHOD=GETPIXEL\nSNAP_BIOS_MODE=00FF\n',
                            pair+pair, pair.replace('GETPIXEL','VIDEO_DIRECT'),
                            pair.replace('00FF','00GG'), pair.replace('00FF','0012'),
                            pair+'UNKNOWN_DIAGNOSTIC=BAD\n'):
                    trace_path.write_text(trace_base.replace(pair,bad))
                    reject(lambda:u.validate_desktop(st),'invalid SNAPSAFE diagnostics')
                    checks+=1
                good()
                # The archived evidence must retain the real foundation file
                # and all mouse marker names (not only the auto fixture name).
                archive=root/'HOST_TEST_COLLECT'/target
                archive.mkdir(parents=True,exist_ok=True)
                for marker in ('MSFIRST.OK','MSSECOND.OK','MSBAD.OK','MSPASS.OK','MSFAIL.LOG'):
                    (guest/marker).write_bytes(b'HOST_ONLY_EVIDENCE')
                u.collect(st,archive)
                assert (archive/'FS'/'MOVED.TXT').read_bytes()==(win/'TEST.WAS').read_bytes()
                for marker in ('MSFIRST.OK','MSSECOND.OK','MSBAD.OK','MSPASS.OK','MSFAIL.LOG'):
                    assert (archive/marker).read_bytes()==b'HOST_ONLY_EVIDENCE'
                    (guest/marker).unlink()
                checks+=6

                assert 'DOSEND.OK' in st['batch'].read_text()
                assert 'WINRETURN.OK' not in st['batch'].read_text()
                assert not (win/'WAS.WAS').exists()
                assert (win/'DRIVER.DRV').read_bytes()==b'ORIGINAL'
                assert (st['win_src']/'WIN.INI').read_bytes()==b'[windows]\r\nrun=ORIGINAL.EXE\r\n'
                # A hardcoded script claim cannot replace interpreter evidence.
                mutations=[('NOWBAT_BUILD=W054','NOWBAT_BUILD=W028'),
                           ('WAS_TAIL=TEST.WAS','WAS_TAIL='),
                           ('WAS_SCRIPT=TEST.WAS','WAS_SCRIPT=WAS.WAS'),
                           ('WAS_OPEN=TEST.WAS','WAS_OPEN=WRONG.WAS'),
                           ('WAS_SHUTDOWN_REQUESTED\n',''),
                           ('SHOWICON=YES\n',''),
                           ('SHOWICON=NO\n',''),
                           ('WAS_INITAPP\n','WAS_INITAPP\nWAS_INITAPP\n'),
                           ('WAS_VERSION='+{'WIN101':'0001','WIN200':'0302','WIN300':'0003'}[target],
                            'WAS_VERSION=0909')]
                for before,after in mutations:
                    good();p=win/'EARLY.LOG';p.write_text(p.read_text().replace(before,after))
                    reject(lambda:u.validate_desktop(st),before);checks+=1
                good();(guest/'DESKTOP.LOG').write_text('WAS_RUN=OLD_RUN\n')
                reject(lambda:u.validate_desktop(st),'stale script');checks+=1
                good();(guest/'DESKTOP.LOG').write_bytes((guest/'DESKTOP.LOG').read_bytes().replace(
                    ('CHECKS_OK='+token).encode('ascii'),b'CHECKS_SKIPPED'))
                reject(lambda:u.validate_desktop(st),'missing EXISTS/ASSERT completion');checks+=1
                good();(guest/'FS.LOG').write_text('FS_ALL_OK=OLD_RUN\n')
                reject(lambda:u.validate_desktop(st),'invalid filesystem log');checks+=1
                good();(guest/'FS'/'MOVED.TXT').write_bytes(b'CORRUPTED')
                reject(lambda:u.validate_desktop(st),'changed moved file');checks+=1
                good();(guest/'FS'/'DEL.TXT').write_text('SHOULD_NOT_EXIST')
                reject(lambda:u.validate_desktop(st),'delete was skipped');checks+=1
                good();(guest/'FS'/'EMPTY').mkdir(exist_ok=True)
                reject(lambda:u.validate_desktop(st),'rmdir was skipped');checks+=1
                good();(guest/'DOSEND.OK').write_text('DOSEND OLD_RUN\n')
                reject(lambda:u.validate_desktop(st),'stale DOS return');checks+=1
                good();(guest/'DOSEND.OK').unlink()
                reject(lambda:u.validate_desktop(st),'Windows did not exit');checks+=1
                good();(win/'SHUTFAIL.LOG').touch()
                reject(lambda:u.validate_desktop(st),'shutdown API returned');checks+=1
                (win/'SHUTFAIL.LOG').unlink()
                good();(win/'WAS.WAS').write_text('SHUTDOWN\n')
                reject(lambda:u.validate_desktop(st),'fallback exists');checks+=1
                (win/'WAS.WAS').unlink()
                good();script=(win/'TEST.WAS').read_bytes()
                (win/'TEST.WAS').write_bytes(script.replace(b'SHUTDOWN',b'EXIT'))
                reject(lambda:u.validate_desktop(st),'script replaced by EXIT');checks+=1
                (win/'TEST.WAS').write_bytes(script)
                if target=='WIN300':
                    good();p=win/'EARLY.LOG';p.write_text(p.read_text().replace('WAS_WINFLAGS=0000','WAS_WINFLAGS=0011'))
                    reject(lambda:u.validate_desktop(st),'protected mode');checks+=1
                good();u.prepare_phase(st,'FOUNDATION')
                assert not (guest/'BEFORE.OK').exists() and not (guest/'AFTER.OK').exists()
                assert not (guest/'DOSEND.OK').exists() and not (win/'EARLY.LOG').exists() and not (guest/'EVIDENCE.TAR').exists()
                assert not (guest/'WSTART.OK').exists() and not (guest/'WEND.OK').exists()
                # Validate independent originals, depth, truncation and TAR tampering.
                good()
                assert u.validate_bmp4(guest/'DESKTOP.BMP')['bpp']==4
                b=bytearray((guest/'DESKTOP.BMP').read_bytes());b[28]=8
                (guest/'DESKTOP.BMP').write_bytes(b)
                reject(lambda:u.validate_desktop(st),'incorrect screenshot depth');checks+=1
                good();(guest/'EVIDENCE.TAR').write_bytes(b'INVALID')
                reject(lambda:u.validate_desktop(st),'invalid evidence TAR');checks+=1
                good();(guest/'DESKTOP.BMP').write_bytes((guest/'DESKTOP.BMP').read_bytes()[:-1])
                reject(lambda:u.validate_desktop(st),'truncated BMP');checks+=1
                good();(guest/'DESKTOP.LOG').write_text('WAS_RUN=OLD_RUN\n')
                reject(lambda:u.validate_desktop(st),'changed loose log');checks+=1
            # Test the real native dispatcher logic with a fake runner, not
            # merely by grepping its source. No emulator or guest is forged.
            previous_dosbox,previous_run=u.locate_dosbox,u.run_target
            try:
                u.locate_dosbox=lambda _: Path('FAKE_DOSBOX_NOT_RUN')
                attempted=[]
                def fail_once(target,cfg,dosbox,timeout):
                    attempted.append(target)
                    row={'target':target,'result':'FAIL','error':'deliberate host test'}
                    d=root/'UAT'/'RESULTS'/target;d.mkdir(parents=True,exist_ok=True)
                    (d/'RESULT.JSON').write_text('FAIL\n')
                    return row
                u.run_target=fail_once
                with contextlib.redirect_stdout(io.StringIO()):
                    results=u.run_native()
                assert attempted==['WIN300']
                assert [r['result'] for r in results]==['FAIL','SKIPPED','SKIPPED']
                for target in ('WIN200','WIN101'):
                    record=__import__('json').loads((root/'UAT'/'RESULTS'/target/'RESULT.JSON').read_text())
                    assert record['native']=='NOT_STARTED'
                checks+=4
                attempted=[]
                def all_pass(target,cfg,dosbox,timeout):
                    attempted.append(target)
                    return {'target':target,'result':'PASS'}
                u.run_target=all_pass
                with contextlib.redirect_stdout(io.StringIO()):
                    results=u.run_native()
                assert attempted==list(u.AUDIT_ORDER)
                assert all(r['result']=='PASS' for r in results)
                checks+=2
                # A targeted Win3 diagnostic must not silently qualify Win1 or Win2.
                attempted=[]
                with contextlib.redirect_stdout(io.StringIO()):
                    results=u.run_native('WIN300')
                assert attempted==['WIN300'] and len(results)==1 and results[0]['result']=='PASS'
                assert not (root/'UAT'/'RESULTS'/'WIN101'/'RESULT.JSON').exists()
                assert not (root/'UAT'/'RESULTS'/'WIN200'/'RESULT.JSON').exists()
                reject(lambda:u.run_native('WIN999'), 'unknown target')
                checks+=3
            finally:
                u.locate_dosbox,u.run_target=previous_dosbox,previous_run
            if os.name=='nt':
                # Exercise the real Win32 hidden launcher and bounded process cleanup
                # using a sleeping Python process, never substitute it for Win16 UAT.
                from winhidden import HiddenProcess
                jobs=[];oldlaunch=u.launch_dosbox
                def hung(exe,conf,stream,max_seconds=None,desktop_mode='visible'):
                    p=HiddenProcess([sys.executable,'-c','import time;time.sleep(60)'],root,stream)
                    jobs.append(p);return p
                u.launch_dosbox=hung
                try:
                    st=u.stage('WIN101',cfg)
                    output=root/'HOST_TEST';output.mkdir()
                    start=time.monotonic()
                    reject(lambda:u.run_phase('WIN101','FOUNDATION',st,Path('UNUSED'),.4,output),'hung process')
                    assert time.monotonic()-start<5
                    assert st['process']['forced_termination'] and st['process']['exited']
                    assert st['process']['windows_remaining']==0 and st['process']['handles_closed']
                    checks+=1
                finally:u.launch_dosbox=oldlaunch
        finally:u.ROOT,u.CDRIVE=oldroot,olddrive
    print('AUDIT_SELFTEST=PASS (%d rejection/watchdog checks; host-only)'%checks)


if __name__=='__main__':main()
