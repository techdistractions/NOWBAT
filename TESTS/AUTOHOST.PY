#!/usr/bin/env python3
"""Host-only AutoUAT verifier regression. Never labels synthetic evidence native."""
import io
import os
import re
import struct
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'HOST'))
import runuat as u


def bmp(n):
    w=h=16; palette=0 if n==24 else 1 << n
    stride=((w*n+31)//32)*4
    offset=54+palette*4
    size=offset+stride*h
    hdr=b'BM'+struct.pack('<IHHI',size,0,0,offset)
    dib=struct.pack('<IiiHHIIiiII',40,w,h,1,n,0,stride*h,0,0,palette,0)
    return hdr+dib+(b'\0'*palette*4)+(b'\0'*(stride*h))


def put_guest_text(path, content):
    """Write exact bytes, without Windows text-mode CRLF conversion.

    Path.write_text(... '\r\n') becomes CRCRLF on Windows and produces
    extra empty records when the strict native-evidence verifier splits lines.
    """
    path.write_bytes(content.encode('ascii'))


def stage_synthetic(root,token='ABC123'):
    guest=root/'GUEST'; win=root/'WIN'; fs=guest/'FS'
    fs.mkdir(parents=True);win.mkdir()
    script=b'# synthetic script, NOT guest evidence\r\n'
    (win/'TEST.WAS').write_bytes(script)
    (fs/'D.TXT').write_bytes(script)
    (guest/'LAUNCH.OK').write_bytes(script)
    (win/'WCHILD.OK').write_bytes(b'2')
    (win/'WWAIT.OK').write_bytes(b'2')
    put_guest_text(win/'WAS.LOG','DEFAULT_LOG='+token+'\r\n')
    trace=['WAS_INITTASK',u.EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP',
           'WAS_VERSION=0302','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS',
           'SHOWICON=YES','SHELL_LAUNCHED','SHELL_LAUNCHED',
           'SHELLWAIT_COMPLETED','SHELL_LAUNCH_ERROR=2','SHELL_LAUNCH_ERROR=2',
           'SHOWICON=NO','WAS_SHUTDOWN_REQUESTED','WAS_SHUTDOWN_API=USER.2']
    put_guest_text(win/'EARLY.LOG','\r\n'.join(trace)+'\r\n')
    for name,val in [('DOSBOOT.OK','DOSBOOT '+token),('DOSEND.OK','DOSEND '+token),
                     ('START.OK','AUTO_START='+token),('DONE.LOG','AUTO_DONE='+token)]:
        put_guest_text(guest/name,val+'\r\n')
    lines=[x+token for x in ('AUTO_BEGIN=','SUB_ONE=','SUB_TWO=','CONTROL_OK=','ENV_OK=')]
    lines+=['SHELL_OK='+token,'\\NBUTIL\\WAS\\FS','D.TXT']
    lines +=[x+token for x in ('FILES_OK=','WAIT_OK=','SNAP_OK=')]
    put_guest_text(guest/'AUTO.LOG','\r\n'.join(lines)+'\r\n')
    put_guest_text(guest/'ENV.LOG','WINVER=2\r\nSCREENW=640\r\nSCREENH=200\r\nBPP=4\r\nDISKFREE(C)=123456\r\n')
    for phase in u.AUTO_PHASE_MARKERS:
        (guest/phase).write_bytes((guest/'ENV.LOG').read_bytes())
    (guest/'ASYNC.OK').write_bytes((guest/'ENV.LOG').read_bytes())
    for bpp in (1,4,8,24): (guest/('R%d.BMP'%bpp)).write_bytes(bmp(bpp))
    with tarfile.open(str(guest/'AUTO.TAR'),'w:',format=tarfile.USTAR_FORMAT) as tar:
        for name,path in [('AUTO.LOG',guest/'AUTO.LOG'),('D.TXT',fs/'D.TXT'),('R4.BMP',guest/'R4.BMP')]:
            content=path.read_bytes()
            info=tarfile.TarInfo(name);info.size=len(content);info.mtime=0
            tar.addfile(info,io.BytesIO(content))
    for kind in ('TEND','TPASS','TFAIL'):
        put_guest_text(guest/(kind+'.BEG'),'TERM_BEGIN_'+kind+'='+token+'\r\n')
        put_guest_text(guest/(kind+'.DON'),'TERM_DONE_'+kind+'='+token+'\r\n')
    terminal_shas={}
    for kind,command in (('TEND','END'),('TPASS','PASS'),('TFAIL','FAIL')):
        directory=guest/kind;directory.mkdir()
        terminal_script=(ROOT/'TESTS'/(kind+'.WAS')).read_bytes().replace(b'@RUN@',token.encode('ascii'))
        (directory/(kind+'.WAS')).write_bytes(terminal_script)
        terminal_shas[kind]=u.sha256(terminal_script)
        put_guest_text(directory/('TERM'+command+'.LOG'),'TERM'+command+'='+token+'\r\n')
        put_guest_text(directory/'EARLY.LOG','\r\n'.join([
            'WAS_INITTASK',u.EXPECTED_BUILD_MARKER,'WAS_TAIL="'+kind+'.WAS"',
            'WAS_INITAPP','WAS_SCRIPT='+kind+'.WAS','WAS_OPEN='+kind+'.WAS',command])+'\r\n')
    return {'uat':guest,'staged_win':win,'token':token,'target':'WIN200',
            'script_sha256':u.sha256(script), 'terminal_scripts':terminal_shas}


def rejects(cb):
    try:cb()
    except u.GuestError:return
    raise AssertionError('Verifier accepted tampered synthetic evidence')


def main():
    checks=0
    script=(ROOT/'TESTS'/'AUTO.WAS').read_text(encoding='ascii').upper()
    for cmd in u.AUTO_COMMANDS:
        # 'SHOWICON=YES' and 'SHOWICON=NO' are not space separated.
        assert re.search(r'(?m)^'+re.escape(cmd)+r'(?:\s|=)',script),cmd
        checks+=1
    assert set(u.AUTO_COMMANDS).isdisjoint(u.AUTO_PENDING)
    assert set(u.AUTO_PENDING)=={'END','PASS','FAIL'}
    # Ensure we test the whole documented language, not an arbitrary subset.
    reference=(ROOT/'SCRIPT.TXT').read_text(encoding='ascii')
    documented=set(re.findall(r'(?m)^COMMAND:\s+([A-Z][A-Z0-9]*)',reference.upper()))
    for alias_line in re.findall(r'(?m)^ALIASES:\s+(.+)$',reference):
        documented.update(x.strip() for x in alias_line.split(','))
    # Fast SNAP is separately qualified by the 750-cycle STARTSHOT audit;
    # the all-platform AutoUAT matrix exercises SNAPSAFE for legacy depths.
    snapshot=(ROOT/'TESTS'/'SHOT.WAS').read_text(encoding='ascii').upper()
    assert re.search(r'(?m)^SNAP\s+',snapshot)
    # New GUI commands have independent native regression fixtures. Keep the
    # original AutoUAT matrix intact and require the documented union.
    gui = {
        'GUISYNC.WAS': {'DOEVENTS', 'WAITFOR'},
        'MOUSE.WAS': {'MOUSEMOVE'},
        'WINDOW.WAS': {'WINDOWSELECT'},
        'INPUT.WAS': {'WINDOWFOCUS', 'MOUSEDOWN', 'MOUSEUP', 'MOUSECLICK', 'MOUSEDBLCLICK', 'RELEASEINPUT'},
        'KEYBOARD.WAS': {'KEYDOWN', 'KEYUP', 'KEYPRESS', 'KEYCOMBO', 'TYPE'},
    }
    for filename, commands in gui.items():
        fixture=(ROOT/'TESTS'/filename).read_text(encoding='ascii').upper()
        for command in commands:
            assert re.search(r'(?m)^'+command+r'(?:\s|$)',fixture), (filename,command)
    covered=set(u.AUTO_COMMANDS)|set(u.AUTO_PENDING)|{'SNAP'}|set().union(*gui.values())
    assert documented == covered, ('Documented commands missing qualification coverage',documented ^ covered)
    checks+=1
    for target in ('WIN101','WIN300'):
        assert ('NAME DIST/'+target+'/NOWBAT.EXE') in (ROOT/'LINK'/(target+'.RSP')).read_text()
        for module in ('NBTEND','NBTPASS','NBTFAIL'):
            rsp=ROOT/'LINK'/'TERMS'/(target+'_'+module+'.RSP')
            assert rsp.is_file() and ('NAME BUILD/TERMS/'+target+'/'+module+'.EXE') in rsp.read_text()
            checks+=1
    assert r'C:\WASUAT' in (ROOT/'TESTS'/'AUTO.WAS').read_text()
    # LOGFILE truncates; reopening AUTO.LOG would discard earlier checkpoints.
    assert script.count(r'LOGFILE "C:\WASUAT\AUTO.LOG"')==1
    assert script.index(':SUB_ONE')<script.index(':AUTO_MAIN')<script.index('SET KEY=ALPHA')
    for phase in u.AUTO_PHASE_MARKERS:
        assert script.count('C:'+chr(92)+'WASUAT'+chr(92)+phase)==1,phase
    # W052 isolated child tests: SHELLWAIT must complete before
    # the asynchronous SHELL starts, removing overlapping Win16 tasks.
    waiter=script.index('SHELLWAIT "WWAIT.EXE"')
    waiter_marker=script.index('EXISTS "WWAIT.OK"')
    sh=script.index('SHELL "WCHILD.EXE"')
    gap=script.index(r'COPY "TEST.WAS" "C:\WASUAT\LAUNCH.OK"')
    child_done=script.index('EXISTS "WCHILD.OK"')
    async_witness=script.index(r'COPY "C:\WASUAT\ENV.LOG" "C:\WASUAT\ASYNC.OK"')
    files=script.index(r'MKDIR "C:\WASUAT\FS"')
    assert waiter < waiter_marker < sh < gap < child_done < async_witness < files
    assert script.index('WAIT 3000',sh)<child_done
    assert script.count('LAUNCH.OK')==1 and script.count('ASYNC.OK')==1
    assert script.index('LOG "SHELL_OK=@RUN@"') < script.index('LOG "FILES_OK=@RUN@"')
    # No additional CHDIR to WIN during terminal tests: the async witness
    # was captured before any directory-changing filesystem work.
    assert r'CHDIR "C:\WASUAT\..\WIN"' not in script

    checks+=len(u.AUTO_PHASE_MARKERS)+1
    assert 'AUTOUAT [WIN101' in (ROOT/'AUTOUAT.BAT').read_text()
    for kind,term in (('TEND','END'),('TPASS','PASS'),('TFAIL','FAIL')):
        source=(ROOT/'TESTS'/(kind+'.WAS')).read_text(encoding='ascii')
        assert '\n'+term+'\n' in source and '\nSHUTDOWN\n' in source
        assert source.index('LOGCLOSE') < source.index('\n'+term+'\n') < source.index('SHUTDOWN')
        assert ('SHELLWAIT \"C:\\WASUAT\\'+kind+'\\NB'+('TEND' if kind=='TEND' else 'TPASS' if kind=='TPASS' else 'TFAIL')+'.EXE\"') in script
        checks+=1
    checks+=5
    for n in (1,4,8,24):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'R.BMP';p.write_bytes(bmp(n))
            assert u.validate_auto_bmp(p,n)['bpp']==n
            rejects(lambda:u.validate_auto_bmp(p,8 if n!=8 else 24))
            p.write_bytes(p.read_bytes()[:-3])
            rejects(lambda:u.validate_auto_bmp(p,n))
            checks+=3
    with tempfile.TemporaryDirectory() as d:
        st=stage_synthetic(Path(d))
        # Guard against the Windows-only CRCRLF regression before validation.
        assert (st['uat']/'DONE.LOG').read_bytes() == b'AUTO_DONE=ABC123\r\n'
        assert b'\r\r\n' not in (st['uat']/'AUTO.LOG').read_bytes()
        assert u.auto_phase_status(st)==len(u.AUTO_PHASE_MARKERS)-1
        async_ok=st['uat']/'ASYNC.OK'
        original_async=async_ok.read_bytes()
        async_ok.write_bytes(b'BOGUS\r\n')
        rejects(lambda:u.validate_auto(st))
        async_ok.write_bytes(original_async)
        launch=st['uat']/'LAUNCH.OK'
        original_launch=launch.read_bytes()
        launch.write_bytes(b'STALE')
        rejects(lambda:u.validate_auto(st))
        launch.write_bytes(original_launch)
        good=u.validate_auto(st)
        assert good['status']=='PASS' and good['auto_suite']
        assert set(good['verified_commands'])==set(u.AUTO_COMMANDS)
        for child_name in ('WCHILD.OK','WWAIT.OK'):
            marker=st['staged_win']/child_name
            marker.write_bytes(b'1')
            rejects(lambda:u.validate_auto(st));checks+=1
            marker.write_bytes(b'2')
        assert good['pending_isolated_terminal_tests']==[]
        assert set(good['terminal_commands'])=={'END','PASS','FAIL'}
        # The evidence packager must preserve the actual surviving file,
        # not the obsolete MOVED.TXT name from the foundation audit.
        st['work']=Path(d)/'WORK'
        st['work'].mkdir()
        st['auto_suite']=True
        evidence=Path(d)/'PACKED'
        evidence.mkdir()
        u.collect(st,evidence)
        assert (evidence/'FS'/'D.TXT').read_bytes() == (st['uat']/'FS'/'D.TXT').read_bytes()
        assert (evidence/'LAUNCH.OK').read_bytes() == (st['staged_win']/'TEST.WAS').read_bytes()
        assert (evidence/'ASYNC.OK').read_bytes() == (st['uat']/'ENV.LOG').read_bytes()
        checks+=5
        for phase in u.AUTO_PHASE_MARKERS:
            p=st['uat']/phase
            original=p.read_bytes()
            p.write_bytes(b'BOGUS\r\n')
            rejects(lambda:u.validate_auto(st));checks+=1
            p.write_bytes(original)
        done=st['uat']/'DONE.LOG'
        done.rename(st['uat']/'DONE.SAV')
        rejects(lambda:u.validate_auto(st));checks+=1
        (st['uat']/'DONE.SAV').rename(done)
        env=st['uat']/'ENV.LOG';data=env.read_bytes()
        env.write_bytes(data.replace(b'WINVER=2',b'WINVER=99'))
        rejects(lambda:u.validate_auto(st));checks+=1
        env.write_bytes(data)
        src=st['uat']/'AUTO.TAR';data=src.read_bytes()
        src.write_bytes(data[:-512])
        # tarfile can tolerate one lost end block; payload mutation cannot.
        rejects_case=False
        src.write_bytes(data[:1024]+b'X'*512+data[1536:])
        rejects(lambda:u.validate_auto(st));checks+=1
        src.write_bytes(data)
        trace=st['staged_win']/'EARLY.LOG';data=trace.read_bytes()
        trace.write_bytes(data.replace(b'SHELLWAIT_COMPLETED',b'SHELLWAIT_BROKEN'))
        rejects(lambda:u.validate_auto(st));checks+=1
        trace.write_bytes(data)
        for kind in ('TEND','TPASS','TFAIL'):
            done=st['uat']/(kind+'.DON');data=done.read_bytes()
            done.write_bytes(b'FALSE\r\n')
            rejects(lambda:u.validate_auto(st));checks+=1
            done.write_bytes(data)
        for kind,term in (('TEND','END'),('TPASS','PASS'),('TFAIL','FAIL')):
            trace=st['uat']/kind/'EARLY.LOG';original=trace.read_bytes()
            trace.write_bytes(original.replace(term.encode()+b'\r\n',b'BROKEN\r\n'))
            rejects(lambda:u.validate_auto(st));checks+=1
            trace.write_bytes(original)
            marker=st['uat']/kind/('TERM'+term+'.LOG');data=marker.read_bytes()
            marker.write_bytes(b'FAKE\r\n')
            rejects(lambda:u.validate_auto(st));checks+=1
            marker.write_bytes(data)
        # Win16 accepts a single quoted or unquoted command tail. Both
        # must be verified, but malformed/duplicate tails must fail closed.
        for kind in ('TEND','TPASS','TFAIL'):
            trace=st['uat']/kind/'EARLY.LOG'
            original=trace.read_bytes()
            quoted=b'WAS_TAIL="'+kind.encode('ascii')+b'.WAS"'
            bare=b'WAS_TAIL='+kind.encode('ascii')+b'.WAS'
            assert quoted in original
            trace.write_bytes(original.replace(quoted,bare))
            assert u.validate_auto(st)['status']=='PASS';checks+=1
            trace.write_bytes(original.replace(quoted,quoted+b'\r\n'+bare))
            rejects(lambda:u.validate_auto(st));checks+=1
            trace.write_bytes(original.replace(quoted,b'WAS_TAIL="OTHER.WAS"'))
            rejects(lambda:u.validate_auto(st));checks+=1
            trace.write_bytes(original)
        (st['uat']/'ERROR.LOG').write_text('AUTO_ERROR=ABC123')
        rejects(lambda:u.validate_auto(st));checks+=1
    if os.name=='nt':
        import subprocess
        env=os.environ.copy();env['WAS_AUTO_DRYRUN']='1'
        cases=[([],0,'MODE=ALL'),(['WIN101'],0,'MODE=WIN101'),
               (['WIN200'],0,'MODE=WIN200'),(['WIN300'],0,'MODE=WIN300'),
               (['ALL'],0,'MODE=ALL'),(['BOGUS'],2,'Usage: AUTOUAT'),
               (['WIN101','EXTRA'],2,'Usage: AUTOUAT')]
        for args,code,marker in cases:
            proc=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c','AUTOUAT.BAT']+args,
                    cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,timeout=20,errors='replace')
            assert proc.returncode==code and marker in proc.stdout, (args,proc.stdout)
            checks+=1
    print('AUTOHOST_SELFTEST=PASS (%d host-only checks; no guest launched)'%checks)


if __name__=='__main__':main()
