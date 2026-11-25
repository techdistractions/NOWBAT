#!/usr/bin/env python3
"""Host-only STARTSHOT protocol regression. Does not claim a native pass."""
import configparser
import io
import os
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'HOST'))
from startshot_check import inspect_bmp, verify_shot_tar, verify_ten_second_wait
import runuat


def bmp4(width=640,height=480,nonuniform=False):
    stride=((width*4+31)//32)*4
    palette=bytearray()
    for i in range(16):
        palette+=bytes((i*17,i*17,i*17,0))
    data=bytearray([0xff])*(stride*height)
    if nonuniform:
        # A visible 120x100 window with a dark border and title bar.
        for y in range(100,200):
            for x in range(120,240):
                idx=y*stride+x//2
                data[idx] &= (0x0f if x%2==0 else 0xf0)
    size=118+len(data)
    head=bytearray(54)
    struct.pack_into('<2sI',head,0,b'BM',size)
    struct.pack_into('<I',head,10,118)
    struct.pack_into('<IiiHHII',head,14,40,width,height,1,4,0,len(data))
    return bytes(head)+bytes(palette)+bytes(data)


def bmp1(width=640,height=480,nonuniform=False):
    stride=((width+31)//32)*4
    palette=bytes((0,0,0,0,255,255,255,0))
    data=bytearray([0xff])*(stride*height)
    if nonuniform:
        for y in range(100,200):
            for x in range(120,240):
                data[y*stride+x//8] &= ~(1<<(7-x%8))
    size=62+len(data)
    head=bytearray(54)
    struct.pack_into('<2sI',head,0,b'BM',size)
    struct.pack_into('<I',head,10,62)
    struct.pack_into('<IiiHHII',head,14,40,width,height,1,1,0,len(data))
    return bytes(head)+palette+bytes(data)


def reject(fn, phrase):
    try:
        fn()
    except ValueError as ex:
        assert phrase in str(ex),str(ex)
    else:
        raise AssertionError('STARTSHOT rejected no malformed input: '+phrase)


def main():
    checks=0
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        shot=root/'SCREEN.BMP';shot.write_bytes(bmp4(nonuniform=True))
        info=inspect_bmp(shot)
        assert info['width']==640 and info['height']==480
        assert info['unique_colours']>=2 and info['contrasting_pixels']>10000
        checks+=3
        shot.write_bytes(bmp1(nonuniform=True))
        mono=inspect_bmp(shot,expected_bpp=1)
        assert mono['bpp']==1 and mono['contrasting_pixels']>10000
        reject(lambda:inspect_bmp(shot,expected_bpp=4),'4-bpp')
        checks+=3
        shot.write_bytes(bmp4(nonuniform=False))
        reject(lambda:inspect_bmp(shot),'BLANK')
        checks+=1
        shot.write_bytes(bmp4(nonuniform=True)[:6000])
        reject(lambda:inspect_bmp(shot),'truncated')
        checks+=1
        shot.write_bytes(bmp4(nonuniform=True))
        scr=b'; one-time startup test\r\nWAIT 10000\r\nSNAP "C:\\X\\SCREEN.BMP" BPP=4\r\n'
        tarpath=root/'SCREEN.TAR'
        with tarfile.open(tarpath,'w') as tar:
            for name,data in (('SCREEN.BMP',shot.read_bytes()),('SHOT.WAS',scr)):
                item=tarfile.TarInfo(name)
                item.size=len(data)
                tar.addfile(item,io.BytesIO(data))
        result=verify_shot_tar(tarpath,{'SCREEN.BMP':shot.read_bytes(),'SHOT.WAS':scr})
        assert result['members']['SCREEN.BMP']==len(shot.read_bytes())
        checks+=1
        reject(lambda:verify_shot_tar(tarpath,{'SCREEN.BMP':b'damaged','SHOT.WAS':scr}),'differs')
        checks+=1
        before=root/'SHOTBEG.OK';after=root/'SHOTWAT.OK'
        # These are DOS guest marker bytes. Never use write_text() with an
        # explicit CRLF here: on Windows text mode adds another CR (\r\r\n)
        # and the real marker parser correctly rejects the malformed fixture.
        before.write_bytes(b'SHOT_BEGIN=ABC\r\n')
        after.write_bytes(b'SHOT_WAIT_DONE=ABC\r\n')
        assert before.read_bytes()==b'SHOT_BEGIN=ABC\r\n'
        assert after.read_bytes()==b'SHOT_WAIT_DONE=ABC\r\n'
        assert runuat.read_wait_marker({'uat':root,'token':'ABC'},'SHOTBEG.OK','SHOT_BEGIN')
        assert runuat.read_wait_marker({'uat':root,'token':'ABC'},'SHOTWAT.OK','SHOT_WAIT_DONE')
        checks+=4
        # Regression: a double-translated Windows newline is NOT a valid
        # closed guest marker, even though splitlines can hide this in logs.
        before.write_bytes(b'SHOT_BEGIN=ABC\r\r\n')
        assert not runuat.read_wait_marker({'uat':root,'token':'ABC'},'SHOTBEG.OK','SHOT_BEGIN')
        before.write_bytes(b'SHOT_BEGIN=ABC\r\n')
        checks+=1
        evidence=verify_ten_second_wait(before,after,10.0,20.01)
        assert evidence['script_wait_ms']==10000
        checks+=1
        reject(lambda:verify_ten_second_wait(before,after,10.0,10.5),'not observed')
        checks+=1
        # Check that the actual staged test commands keep user interaction
        # before capture and package an independent nonexecuting script copy.
        script=(Path(__file__).parent/'SHOT.WAS').read_text(encoding='ascii')
        assert 'SHOWICON=YES' in script and 'WAIT 10000' in script and 'SNAP ' in script
        assert script.index('SHOWICON=YES') < script.index('SHOTBEG.OK') < script.index('WAIT 10000') < script.index('SNAP ')
        assert 'IF %RESULT% NE 0 THEN GOTO SHOT_FAIL' in script
        checks+=3
        assert 'TARADD "SHOT.WAS"' in script and 'TARADD "TEST.WAS"' not in script
        assert 'SHUTDOWN' not in '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith(';')).upper()
        assert '\nEND\n' in script
        checks+=3
        # Guard the explicit visible-desktop dispatcher and separate mode.
        audit=(Path(__file__).resolve().parents[1]/'AUDIT.BAT').read_text(encoding='ascii')
        assert '"NOWBAT_STARTSHOT=1"' in audit
        assert '"WAS_UAT_DESKTOP=visible"' in audit
        assert 'HOST\\STREAM.PY %MODE%' in audit
        checks+=3
        # A valid BMP/TAR is not enough: the guest must have executed the
        # SHOWICON=YES instruction before the screenshot checkpoints.
        staged_win=root/'WIN'
        staged_win.mkdir()
        (staged_win/'TEST.WAS').write_bytes(scr)
        (staged_win/'SHOT.WAS').write_bytes(scr)
        for name,contents in (("DOSBOOT.OK",b"DOSBOOT ABC\r\n"),
                              ("SNAPOK.OK",b"SNAP_DONE=ABC\r\n"),
                              ("TARCRT.OK",b"TAR_CREATED=ABC\r\n"),
                              ("TARBMP.OK",b"TAR_BMP_ADDED=ABC\r\n"),
                              ("TARSCR.OK",b"TAR_SCRIPT_ADDED=ABC\r\n"),
                              ("TAROK.OK",b"TAR_DONE=ABC\r\n")):
            (root/name).write_bytes(contents)
        st={'uat':root,'staged_win':staged_win,'token':'ABC',
            'script_sha256':runuat.sha256(scr)}
        (staged_win/'EARLY.LOG').write_bytes(b'WAS_OPEN=TEST.WAS\r\n')
        try:
            runuat.validate_startshot(st)
        except runuat.GuestError as err:
            assert 'created its icon' in str(err),str(err)
            checks+=1
        else:
            raise AssertionError('Missing icon witness qualified as PASS')
        (staged_win/'EARLY.LOG').write_bytes(b'WAS_OPEN=TEST.WAS\r\nSHOWICON=YES\r\nEND\r\n')
        assert runuat.validate_startshot(st)['status']=='PASS'
        checks+=1
        (staged_win/'EARLY.LOG').write_bytes(b'WAS_OPEN=TEST.WAS\r\nSHOWICON=YES\r\n')
        try:
            runuat.validate_startshot(st)
        except runuat.GuestError as err:
            assert 'with END' in str(err),str(err)
            checks+=1
        else:
            raise AssertionError('STARTSHOT incorrectly accepted TAR without native END')
    # Catch the W064 failure before launching DOSBox-X: normal SELFTEST
    # uses TEST.WAS, whereas STARTSHOT stages a separate SHOT.WAS copy.
    # Exercise the actual stager for all three Windows targets using only
    # disposable host files; no fake guest execution or PASS is claimed.
    with tempfile.TemporaryDirectory() as tmp:
        drive=Path(tmp)/'CDRIVE'
        source=drive/'NOWBAT'
        (source/'TESTS').mkdir(parents=True)
        (source/'TESTS'/'SHOT.WAS').write_bytes((Path(__file__).parent/'SHOT.WAS').read_bytes())
        (source/'BUILD').mkdir()
        (source/'BUILD'/'WCHILD.EXE').write_bytes(b'HOST_FIXTURE')
        (source/'BUILD'/'WWAIT.EXE').write_bytes(b'HOST_FIXTURE')
        for name in ('WIN101','WIN300'):
            target=source/'DIST'/name
            target.mkdir(parents=True)
            (target/'NOWBAT.EXE').write_bytes(b'HOST_FIXTURE')
        for dirname in ('WIN1','WIN2','WIN3'):
            win=drive/'TOOLS'/dirname
            win.mkdir(parents=True)
            (win/'WIN.COM').write_bytes(b'HOST_FIXTURE')
            (win/'WIN.INI').write_bytes(b'[windows]\r\nrun=\r\n')
        saved_root,saved_drive=runuat.ROOT,runuat.CDRIVE
        saved_mode=os.environ.get('NOWBAT_STARTSHOT')
        try:
            runuat.ROOT,runuat.CDRIVE=source,drive
            os.environ['NOWBAT_STARTSHOT']='1'
            cfg=configparser.ConfigParser(interpolation=None)
            for target in ('WIN101','WIN200','WIN300'):
                staged=runuat.stage(target,cfg)
                win=staged['staged_win']
                expected=(source/'TESTS'/'SHOT.WAS').read_bytes().replace(
                    b'C:\\WASUAT',runuat.guest_path(staged['uat'],drive).encode('ascii')).replace(
                    b'@RUN@',staged['token'].encode('ascii'))
                assert staged['shot_suite'] and staged['target']==target
                assert (win/'TEST.WAS').read_bytes()==expected
                assert (win/'SHOT.WAS').read_bytes()==expected
                assert b'SHOWICON=YES\r\n' in expected
                assert (staged['work']/'RUNUAT.BAT').is_file()
                assert b'NOWBAT.EXE TEST.WAS' in (staged['work']/'RUNUAT.BAT').read_bytes()
                checks+=6
            # The private source tree can also live outside mounted CDrive.
            # Verify guest staging still lands on an accessible DOS 8.3 path.
            outside=Path(tmp)/'PRIVATE'/'NOWBAT'
            outside.mkdir(parents=True)
            (outside/'TESTS').mkdir()
            (outside/'TESTS'/'SHOT.WAS').write_bytes((source/'TESTS'/'SHOT.WAS').read_bytes())
            (outside/'BUILD').mkdir()
            for fixture in ('WCHILD.EXE','WWAIT.EXE'):
                (outside/'BUILD'/fixture).write_bytes(b'HOST_FIXTURE')
            for name in ('WIN101','WIN300'):
                t=outside/'DIST'/name
                t.mkdir(parents=True)
                (t/'NOWBAT.EXE').write_bytes(b'HOST_FIXTURE')
            runuat.ROOT=outside
            external=runuat.stage('WIN300',cfg)
            assert external['work'].parent==drive/'NBTUAT'
            assert external['work'].is_dir()
            assert (external['work']/'RUNUAT.BAT').is_file()
            assert runuat.guest_path(external['work'],drive).startswith('C:\\NBTUAT')
            checks+=4
        finally:
            runuat.ROOT,runuat.CDRIVE=saved_root,saved_drive
            if saved_mode is None:
                os.environ.pop('NOWBAT_STARTSHOT',None)
            else:
                os.environ['NOWBAT_STARTSHOT']=saved_mode
    print('STARTSHOT_HOST=PASS (%d host checks; native captures not run)'%checks)

if __name__=='__main__':main()
