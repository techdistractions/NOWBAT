#!/usr/bin/env python3
"""Real DOSBox-X Windows 1/2/3 guest UAT. No forged guest-result JSON.

Uses the proven NOWBASIC/BATUAT topology: one DOSBox-X guest per target,
DOS RUNUAT.BAT, and WIN.COM starting a Win16 application from a complete
copy of the proven installed Windows tree. Unlike legacy guest launchers, do NOT run Windows in DOSBox-X's DOS-only -silent mode or launch
Windows twice for BOOT and QUALIFY. Windows video needs a real SDL session,
which the Windows host now launches on the normal, VISIBLE desktop for live
triage (an optional private/hidden mode remains available). Qualify
on actual Win16 NOWBAT file evidence, never by assuming a DOS marker is enough.
Python 3.9+ host orchestration only. Never contributes to NOWBAT.EXE.
"""
import configparser
import datetime
import hashlib
import json
import os
import struct
import tarfile
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
def locate_cdrive_root(root):
    """Find the DOSBox-X mounted CDrive for either supported source layout.

    Accept CDrive/NOWBAT and CDrive/NBUTIL/WAS without guessing levels.
    NOWBAT_CDRIVE is an explicit override for other local layouts.
    """
    override = os.environ.get('NOWBAT_CDRIVE') or os.environ.get('WAS_CDRIVE')
    if override:
        return Path(override).expanduser().resolve()
    for folder in (root, *root.parents):
        if folder.name.casefold() == 'cdrive':
            return folder.resolve()
    # A clean private checkout may sit outside the mounted drive, e.g.
    # <workspace>/test/NOWBAT next to <workspace>/Dosbox-X/CDrive.
    # Search only nearby ancestor levels, never the entire workstation.
    for parent in (root, *root.parents):
        if not parent.is_dir():
            continue
        for direct in (parent / 'CDrive', parent / 'cdrive'):
            if direct.is_dir() and ((direct / 'TOOLS').is_dir() or (direct / 'WIN100').is_dir()):
                return direct.resolve()
        for child in parent.iterdir():
            if child.is_dir() and child.name.casefold() in ('dosbox-x', 'dosboxx'):
                for drive in child.iterdir():
                    if drive.is_dir() and drive.name.casefold() == 'cdrive':
                        return drive.resolve()
    # Keep a deterministic fallback for source-only regressions. Native
    # guest staging will reject a root without actual DOSBox-X installs.
    return root.parent.parent.resolve()


CDRIVE = locate_cdrive_root(ROOT)
TARGETS = {
    'WIN101': {'folders': ('WIN100', 'WIN101', 'WIN1'), 'machine': 'svga_s3', 'win': 'WIN.COM', 'args': ''},
    'WIN200': {'folders': ('WIN200', 'WIN203', 'WIN2'), 'machine': 'svga_s3', 'win': 'WIN.COM', 'args': ''},
    'WIN300': {'folders': ('WIN300', 'WIN30', 'WIN3'), 'machine': 'svga_s3', 'win': 'WIN.COM', 'args': '/r'},
}
# Native guest qualification order: Win3 real-mode first isolates early-Windows startup.
# A diagnostic selection bypasses all other guests without marking them PASS.
AUDIT_ORDER = ('WIN300', 'WIN200', 'WIN101')

DOS_END = 'DOSEND.OK'  # every guest filename must obey DOS 8.3
STARTUP_TRACE_LIMIT_SECONDS = 300 if (os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1') else 50  # 750-cycle boot budget
EXPECTED_BUILD_MARKER = 'NOWBAT_BUILD=W054'
# Closed, token-bearing AutoUAT phase markers. Each is a byte-identical
# copy of the immutable guest ENV.LOG. 8.3 names, no new native commands.
AUTO_PHASE_MARKERS = ('CPBEG.OK','CPCTL.OK','CPENV.OK','CPSHL.OK',
                       'CPFIL.OK','CPWAT.OK','CPSNP.OK','CPTAR.OK')
AUTO_PHASE_LIMIT_SECONDS = 70  # diagnostic progress, not overall timeout
AUTO_TERMINAL_MARKERS = (('TEND.BEG','TERM_BEGIN_TEND'),
                         ('TEND.DON','TERM_DONE_TEND'),
                         ('TPASS.BEG','TERM_BEGIN_TPASS'),
                         ('TPASS.DON','TERM_DONE_TPASS'),
                         ('TFAIL.BEG','TERM_BEGIN_TFAIL'),
                         ('TFAIL.DON','TERM_DONE_TFAIL'),
                         ('DONE.LOG','AUTO_DONE'))


class GuestError(Exception):
    pass


def expected_child_version(target):
    """Win1 and Win2 use the no-Yield fixture; Win3 uses a yielding fixture.

    The completion files contain a one-byte live GetVersion witness. A stale
    or cross-target fixture cannot silently qualify the current guest.
    """
    return {'WIN101':b'1', 'WIN200':b'2', 'WIN300':b'3'}[target]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def find_ci(folder, name):
    """Case-insensitive child lookup on Linux test hosts and Windows hosts."""
    p = Path(folder) / name
    if p.exists():
        return p
    if not Path(folder).is_dir():
        raise GuestError('Directory does not exist: ' + str(folder))
    match = [x for x in Path(folder).iterdir() if x.name.upper() == name.upper()]
    if len(match) != 1:
        raise GuestError('Cannot locate %s in %s' % (name, folder))
    return match[0]


def get_config():
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(str(ROOT / 'UAT' / 'CONFIG.INI'), encoding='utf-8')
    return cfg


def option(cfg, section, key, default=''):
    env_key = 'WAS_' + (section + '_' if section != 'runner' else '') + key.upper()
    # Explicit WAS_DOSBOX, WAS_UAT_TIMEOUT and WAS_UAT_CYCLES are convenient aliases.
    aliases = {'DOSBOX': 'WAS_DOSBOX', 'TIMEOUT': 'WAS_UAT_TIMEOUT', 'CYCLES': 'WAS_UAT_CYCLES'}
    if section == 'runner' and key.upper() in aliases:
        x = os.environ.get(aliases[key.upper()], '').strip()
        if x:
            return x
    env = os.environ.get(env_key, '').strip()
    return env if env else cfg.get(section, key, fallback=default).strip()


def guest_desktop_mode(cfg):
    # Temporary UAT-debugging default: show each DOSBox-X SDL window.
    # WAS_UAT_DESKTOP overrides the INI; hidden mode is still available.
    mode = os.environ.get('WAS_UAT_DESKTOP', option(cfg, 'runner', 'desktop', 'visible')).strip().lower()
    if mode not in ('visible', 'hidden'):
        raise GuestError('Invalid [runner] desktop mode: %r (use visible or hidden)' % mode)
    return mode


def locate_dosbox(cfg):
    specified = option(cfg, 'runner', 'dosbox')
    candidates = ([Path(specified)] if specified else [
        CDRIVE.parent / 'DOSBox-X.exe',
        CDRIVE.parent / 'DOSBox-X' / 'DOSBox-X.exe',
        CDRIVE.parent / 'dosbox-x.exe',
    ])
    found = shutil.which('dosbox-x') or shutil.which('DOSBox-X.exe')
    if found and not specified:
        candidates.append(Path(found))
    for x in candidates:
        if x.is_file():
            return x.resolve()
    raise GuestError('DOSBox-X executable missing; set WAS_DOSBOX or UAT\\CONFIG.INI [runner] dosbox')


def is_win_folder(path):
    """Accept only a plausible DOS/Win16 installation, not a named empty dir."""
    if not path.is_dir():
        return False
    try:
        names = {entry.name.upper() for entry in path.iterdir() if entry.is_file()}
    except OSError:
        return False
    return 'WIN.INI' in names and ('WIN.COM' in names or 'WIN86.COM' in names)


def locate_windows(cfg, target):
    """Resolve guest Windows deterministically without selecting archived copies.

    Priority: explicit configuration, shared CDrive\\TOOLS, CDrive root,
    then a conservative nested search excluding archives/build snapshots. A
    level with more than one plausible installation is ambiguous and fails.
    """
    raw = option(cfg, target, 'windows_dir')
    if raw:
        p = Path(raw).resolve()
        if not is_win_folder(p):
            raise GuestError('%s windows_dir missing WIN.INI/WIN.COM: %s' % (target, p))
        return p

    def at_root(root):
        found = set()
        for name in TARGETS[target]['folders']:
            p = root / name
            for candidate in (p, p / 'WINDOWS'):
                if is_win_folder(candidate):
                    found.add(candidate.resolve())
        return sorted(found)

    # Shared CDrive\\TOOLS is the authoritative active tool suite for NBUTIL.
    # Discover it BEFORE broad search so #Archive copies cannot be mistaken
    # for additional active installations. A direct CDrive install is next.
    for root in (CDRIVE / 'TOOLS', CDRIVE):
        candidates = at_root(root)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise GuestError('%s multiple Windows installations under %s; set [%s] windows_dir in UAT\\CONFIG.INI: %s' %
                             (target, root, target, ', '.join(str(x) for x in candidates)))

    # Fallback for installations such as CDrive\\NOWBASIC\TOOLS\\WIN1.
    # Old archived projects are never chosen implicitly. An archive may still
    # be used intentionally via windows_dir above.
    target_names = {s.upper() for s in TARGETS[target]['folders']}
    skip = {'.GIT', '_LOCAL', 'BUILD', 'DIST', 'NODE_MODULES', '__PYCACHE__',
            '.VENV', 'TEMP', 'TMP', 'OUTPUT', 'RESULTS', '#ARCHIVE',
            'ARCHIVE', 'ARCHIVES', '_ARCHIVE', 'BACKUP', 'BACKUPS'}
    found = set()
    if CDRIVE.is_dir():
        for base, dirs, filenames in os.walk(str(CDRIVE)):
            rel = Path(base).relative_to(CDRIVE)
            if len(rel.parts) > 5:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d.upper() not in skip]
            if set(part.upper() for part in rel.parts).intersection(target_names):
                present = {x.upper() for x in filenames}
                if 'WIN.INI' in present and ('WIN.COM' in present or 'WIN86.COM' in present):
                    found.add(Path(base).resolve())
    if len(found) == 1:
        return next(iter(found))
    if len(found) > 1:
        raise GuestError('%s multiple active Windows candidates; set [%s] windows_dir in UAT\\CONFIG.INI: %s' %
                         (target, target, ', '.join(str(x) for x in sorted(found))))
    raise GuestError('%s Windows directory not found under %s (archives excluded); set [%s] windows_dir in UAT\\CONFIG.INI' %
                     (target, CDRIVE, target))


def check_environment(cfg):
    """Collect all missing prerequisites before spawning any emulator session."""
    failures = []
    dosbox = None
    try:
        dosbox = locate_dosbox(cfg)
    except GuestError as exc:
        failures.append(str(exc))
    found = {}
    for target in TARGETS:
        try:
            found[target] = locate_windows(cfg, target)
        except GuestError as exc:
            failures.append(str(exc))
    if failures:
        raise GuestError('Guest configuration incomplete:\n  - ' + '\n  - '.join(failures))
    return dosbox, found


def print_config():
    cfg = get_config()
    dosbox, found = check_environment(cfg)
    print('PASS DOSBOX', dosbox)
    for target, directory in found.items():
        print('PASS', target, directory)
    print('AUDIT_CONFIG=PASS (prerequisites only; guest not executed)')


def esc_dosbox_path(p):
    s = str(p.resolve())
    if '"' in s or '\n' in s or '\r' in s:
        raise GuestError('Unsupported quote/newline in host mount path')
    return s


def resolve_profile(cfg, target, win_src):
    """Find a target-specific known-working DOSBox-X configuration.

    An explicitly configured profile always wins. Otherwise only target-named
    configs at active installation/tool locations are considered. Never choose
    archive copies or an arbitrary general config for a specific Windows.
    """
    raw = option(cfg, target, 'dosbox_conf')
    if raw:
        profile = Path(raw).resolve()
        if not profile.is_file():
            raise GuestError('%s DOSBox-X profile not found: %s' % (target, profile))
        return profile
    target_names = ('WIN1', 'WIN100', 'WIN101', 'WIN1X') if target == 'WIN101' else (
        ('WIN2', 'WIN200', 'WIN203', 'WIN2X') if target == 'WIN200' else
        ('WIN3', 'WIN300', 'WIN30', 'WIN3X'))
    folders = [win_src, win_src.parent, CDRIVE / 'TOOLS', CDRIVE.parent]
    names = ['DOSBOX-X.CONF', 'DOSBOX.CONF']
    for stem in target_names:
        names.extend((stem + '.CONF', stem + '.INI'))
    # First: a profile directly in the installation folder (but only actual
    # DOSBox configuration names); second: target-named profiles elsewhere.
    direct = [x for x in (win_src / 'DOSBOX-X.CONF', win_src / 'DOSBOX.CONF') if x.is_file()]
    if len(direct) == 1:
        return direct[0].resolve()
    if len(direct) > 1:
        raise GuestError('%s multiple DOSBox-X profiles in %s; set dosbox_conf' % (target, win_src))
    for folder in folders:
        matches = set()
        for stem in target_names:
            for name in (stem + '.CONF', stem + '.INI'):
                x = folder / name
                if x.is_file():
                    matches.add(x.resolve())
        if len(matches) == 1:
            return next(iter(matches))
        if len(matches) > 1:
            raise GuestError('%s multiple target DOSBox-X profiles in %s; set dosbox_conf: %s' %
                             (target, folder, ', '.join(map(str, sorted(matches)))))
    return None


def guest_path(path, drive):
    """Convert an existing native path into a DOS C: path under the true CDrive.

    The guest sees the original CDrive structure, not an incomplete clone. The
    result must be representable as a DOS 8.3 path for Win1/Win2 boot commands.
    """
    try:
        rel = path.resolve().relative_to(drive.resolve())
    except ValueError:
        raise GuestError('Native UAT requires NOWBAT and Windows below mounted CDrive; set NOWBAT_CDRIVE in AUDIT.LOCAL.BAT: %s' % path)
    if any(' ' in part or len(part.split('.')[0]) > 8 or
           ('.' in part and (part.count('.') > 1 or len(part.rsplit('.', 1)[1]) > 3))
           for part in rel.parts):
        raise GuestError('Non-8.3 guest path: %s (put NOWBAT under a DOS 8.3-named folder inside CDrive)' % path)
    return 'C:\\' + str(rel).replace('/', '\\')



def generate_guest_conf(work, drive, staged_win, guest, target, cfg, profile, token):
    if profile:
        profile_text = profile.read_text(encoding='latin-1')
        config = re.split(r'(?im)^\s*\[autoexec\]\s*$', profile_text)[0]
    else:
        # Matches the current NOWBASIC BATCHPATH142 surface/S3 fixture model.
        # Keep the established MAX audit speed and 4 MiB guest RAM budget.
        config = ('[sdl]\noutput=surface\nfullscreen=false\nshowmenu=false\n'
                  'autolock=false\nwaitonerror=false\npriority=normal,normal\n'
                  '[dosbox]\nmachine=%s\nmemsize=4\nworking directory option=noprompt\n'
                  '[cpu]\ncore=normal\ncputype=auto\ncycles=%s\n'
                  '[serial]\nserial1=serialmouse\n[dos]\nver=3.30\n') % (
                      option(cfg, target, 'machine', TARGETS[target]['machine']),
                      ('750' if os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1' else option(cfg, 'runner', 'cycles', 'max')))
    if (os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1') and profile:
        # Profile configs must not silently reset SNAPFAST to cycles=max.
        # Replace only the [cpu] section to avoid duplicate CPU settings.
        match=re.search(r'(?im)^\s*\[cpu\]\s*$',config)
        if match:
            next_head=re.search(r'(?m)^\s*\[[^\]\r\n]+\]',config[match.end():])
            stop=match.end()+next_head.start() if next_head else len(config)
            cpu=config[match.end():stop]
            if re.search(r'(?im)^\s*cycles\s*=',cpu):
                cpu=re.sub(r'(?im)^\s*cycles\s*=.*$', 'cycles=750', cpu, count=1)
            else: cpu='\ncycles=750\n'+cpu
            config=config[:match.end()]+cpu+config[stop:]
        else:config+='\n[cpu]\ncycles=750\n'
    win_name = option(cfg, target, 'win', 'WIN.COM')
    try:
        win_exe = find_ci(staged_win, win_name)
    except GuestError:
        if target != 'WIN200' or win_name.upper() != 'WIN.COM':
            raise
        win_exe = find_ci(staged_win, 'WIN86.COM')
    switches = option(cfg, target, 'args', TARGETS[target]['args'])
    if (target == 'WIN300' and switches.lower() != '/r') or (target != 'WIN300' and switches):
        raise GuestError('The foundation gate requires Win3 /r and no Win1/Win2 switches')
    boot = win_exe.name.upper() + ((' ' + switches) if switches else '') + ' NOWBAT.EXE TEST.WAS'
    win_dir, guest_dir = guest_path(staged_win, drive), guest_path(guest, drive)
    batch = ('@echo off\r\nver set 3 30\r\npath %s;%s\r\ncd %s\r\n'
             'echo DOSBOOT %s > %s\\DOSBOOT.OK\r\n'
             '%s > %s\\WINBOOT.LOG\r\n'
             'echo DOSEND %s > %s\\DOSEND.OK\r\n') % (
                 win_dir, guest_dir, win_dir, token, guest_dir,
                 boot, guest_dir, token, guest_dir)
    (work / 'RUNUAT.BAT').write_bytes(batch.encode('ascii'))
    conf = work / 'DOSBOX.CONF'
    autoexec = ('[autoexec]\n@echo off\nmount c "%s"\nc:\ncall %s\nexit\n') % (
        esc_dosbox_path(drive), guest_path(work/'RUNUAT.BAT', drive))
    # Both launch modes require a real SDL display (never DOS-only -silent).
    # Visibility is chosen by the host launcher; this file never hides a guest.
    config += '\n[log]\nlogfile=%s\n' % (work/'DOSBOX.LOG')
    conf.write_bytes((config+'\n'+autoexec).encode('latin-1'))
    return conf, boot



def stage(target, cfg, slot=None):
    win_src = locate_windows(cfg, target)
    drive = CDRIVE.resolve()
    guest_path(win_src, drive)
    slot=slot or target
    if not re.fullmatch(r'[A-Z0-9_]{1,8}',slot):
        raise GuestError('Invalid DOS 8.3 staging slot')
    # Source checkout may be outside the mounted CDrive (e.g. C:\Retro\test\nowbat).
    # DOSBox-X can only address files under its mounted guest drive.
    # Keep all disposable guest staging under an 8.3 directory on that drive.
    # Preserve original staging path for a checkout already on CDrive.
    try:
        ROOT.resolve().relative_to(drive)
        stage_parent = ROOT/'BUILD'/'UAT'
    except ValueError:
        stage_parent = drive/'NBTUAT'
    work = stage_parent/slot
    if work.exists():
        # Only delete this audit-owned target slot, never the Windows install.
        if work.resolve().parent != stage_parent.resolve():
            raise GuestError('Unsafe staging path')
        shutil.rmtree(str(work))
    work.mkdir(parents=True)
    staged_win = work/'WIN'
    shutil.copytree(str(win_src), str(staged_win), copy_function=shutil.copy2)
    guest = work/'GUEST'
    guest.mkdir()
    binary = ROOT/'DIST'/('WIN300' if target=='WIN300' else 'WIN101')/'NOWBAT.EXE'
    if not binary.is_file():
        raise GuestError('Missing freshly built binary: '+str(binary))
    shutil.copy2(str(binary), str(staged_win/'NOWBAT.EXE'))
    for name in ('WAS.WAS','EARLY.LOG','WAS.LOG','SHUTFAIL.LOG','WCHILD.OK','WWAIT.OK','SWWAIT.DAT'):
        (staged_win/name).unlink(missing_ok=True)
    token = uuid.uuid4().hex.upper()
    script_name = ('KEYBOARD.WAS' if os.environ.get('NOWBAT_KEYBOARD_DEV')=='1' else 'INPUT.WAS' if os.environ.get('NOWBAT_INPUT_DEV')=='1' else 'WINDOW.WAS' if os.environ.get('NOWBAT_WINDOW_DEV')=='1' else 'MOUSE.WAS' if os.environ.get('NOWBAT_MOUSE_DEV')=='1' else 'GUISYNC.WAS' if os.environ.get('NOWBAT_GUISYNC_DEV')=='1' else
                   'SHOT.WAS' if os.environ.get('NOWBAT_STARTSHOT')=='1'
                   else 'BOOT.WAS' if os.environ.get('WAS_UAT_BOOT_ONLY')=='1' and target=='WIN200'
                   else 'AUTO.WAS' if os.environ.get('WAS_UAT_AUTOUAT')=='1'
                   else 'TEST.WAS')
    script = (ROOT/'TESTS'/script_name).read_bytes().replace(
        b'C:\\WASUAT', guest_path(guest, drive).encode('ascii')).replace(b'@RUN@',token.encode('ascii'))
    if script_name=='SHOT.WAS' and os.environ.get('NOWBAT_SNAPFAST_DEV')=='1':
        if b'SCREEN.BMP"' not in script or b'SCREEN.BMP" MODE=' in script: raise GuestError('SNAPFAST expected default-mode, native-depth full-desktop SNAP without MODE or BPP override')
        if b'SNAPSAFE "' not in script: raise GuestError('SNAPFAST must exercise the explicit SNAPSAFE GDI fallback')
    (staged_win/'TEST.WAS').write_bytes(script)
    # Archive an independent copy, not the currently executing script handle.
    # The guest's current directory is the staged Windows directory.
    if script_name in ('SHOT.WAS', 'GUISYNC.WAS', 'MOUSE.WAS','WINDOW.WAS','INPUT.WAS','KEYBOARD.WAS'):
        (staged_win/script_name).write_bytes(script)
    # Independent native Windows child, built by MAKE from TESTS/WCHILD.ASM.
    # Both children report the actual Windows major version in their marker.
    # Win1: immediate exit; Win2/3: two seconds of cooperative Yield.
    child=ROOT/'BUILD'/'WCHILD.EXE'
    if not child.is_file():
        raise GuestError('MAKE did not build independent SHELL fixture WCHILD.EXE')
    shutil.copy2(str(child),str(staged_win/'WCHILD.EXE'))
    waiter=ROOT/'BUILD'/'WWAIT.EXE'
    if not waiter.is_file():
        raise GuestError('MAKE did not build independent WWAIT.EXE')
    shutil.copy2(str(waiter),str(staged_win/'WWAIT.EXE'))
    if script_name in ('WINDOW.WAS','INPUT.WAS','KEYBOARD.WAS'):
        fixture=ROOT/'BUILD'/'WGEOM.EXE'
        if not fixture.is_file(): raise GuestError('MAKE did not build WGEOM.EXE')
        shutil.copy2(str(fixture),str(staged_win/'WGEOM.EXE'))
        (staged_win/'WGEOM.DAT').unlink(missing_ok=True)
        (staged_win/'WEVENT.DAT').unlink(missing_ok=True)
        (staged_win/'INABI.DAT').unlink(missing_ok=True)
    terminal_scripts = {}
    if script_name == 'AUTO.WAS':
        # Three different NE module names avoid Win1's re-used-module trap.
        # Each child runs in its own directory, keeping EARLY.LOG isolated.
        build_target = 'WIN300' if target == 'WIN300' else 'WIN101'
        for kind, exe in (('TEND','NBTEND'),('TPASS','NBTPASS'),('TFAIL','NBTFAIL')):
            source = ROOT/'BUILD'/'TERMS'/build_target/(exe+'.EXE')
            if not source.is_file():
                raise GuestError('AutoUAT terminal binary not built: '+str(source))
            child_dir = guest/kind
            child_dir.mkdir()
            shutil.copy2(str(source), str(child_dir/(exe+'.EXE')))
            content = (ROOT/'TESTS'/(kind+'.WAS')).read_bytes().replace(
                b'@RUN@',token.encode('ascii'))
            (child_dir/(kind+'.WAS')).write_bytes(content)
            terminal_scripts[kind] = sha256(content)
    profile = resolve_profile(cfg, target, win_src)
    conf, boot = generate_guest_conf(work, drive, staged_win, guest, target, cfg, profile, token)
    return dict(target=target,boot_only=(os.environ.get('WAS_UAT_BOOT_ONLY')=='1' and target=='WIN200'),
                shot_suite=(script_name=='SHOT.WAS'),guisync_suite=(script_name in ('GUISYNC.WAS','MOUSE.WAS','WINDOW.WAS','INPUT.WAS','KEYBOARD.WAS')),window_suite=(script_name=='WINDOW.WAS'),input_suite=(script_name=='INPUT.WAS'),keyboard_suite=(script_name=='KEYBOARD.WAS'),mouse_suite=(script_name=='MOUSE.WAS'),
                auto_suite=(script_name=='AUTO.WAS'),work=work,drive=drive,uat=guest,conf=conf,binary=binary,
                win_src=win_src,staged_win=staged_win,profile=profile,bootline=boot,
                batch=work/'RUNUAT.BAT',token=token,script_sha256=sha256(script),
                terminal_scripts=terminal_scripts)


def write_stage_manifest(st):
    records = {'source':str(st['win_src']),'stage':str(st['staged_win']),
               'boot':st['bootline'],'token':st['token'],
               'child_fixture': ('WIN3_YIELD_2S' if st['target']=='WIN300'
                                 else 'WIN1_2_IMMEDIATE_EXIT'),
               'terminal_scripts':st.get('terminal_scripts',{}),'files':{}}
    for filename in ('WIN.COM','WIN86.COM','WIN.INI','SYSTEM.INI','WIN100.BIN',
                     'WIN200.BIN','SYSTEM/KERNEL.EXE','NOWBAT.EXE','WCHILD.EXE','WWAIT.EXE','WGEOM.EXE','TEST.WAS'):
        file=st['staged_win']/filename
        if file.is_file():
            records['files'][filename]={'bytes':file.stat().st_size,'sha256':sha256(file.read_bytes())}
    (st['work']/'STAGE.JSON').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')


def prepare_phase(st, phase):
    if phase != 'FOUNDATION':
        raise GuestError('Unsupported native phase: '+phase)
    for folder,names in ((st['uat'],('BEFORE.OK','AFTER.OK','WSTART.OK','WEND.OK','DESKTOP.LOG','DESKTOP.BMP','EVIDENCE.TAR','FS.LOG','CONTROL.LOG','BOOT.LOG','START.OK',*AUTO_PHASE_MARKERS,'AUTO.LOG','DONE.LOG','ENV.LOG','ERROR.LOG','LAUNCH.OK','ASYNC.OK',
                                         'TEND.BEG','TEND.DON','TPASS.BEG','TPASS.DON','TFAIL.BEG','TFAIL.DON','R1.BMP','R4.BMP','R8.BMP','R24.BMP','AUTO.TAR','GSEVENT.OK','GSFOUND.OK','GSMBEG.OK','GSMDON.OK','GSPASS.OK','GSFAIL.LOG','GSTIME.LOG','MSFIRST.OK','MSSECOND.OK','MSBAD.OK','MSPASS.OK','MSFAIL.LOG','WFIND.OK','WFBEG.OK','WFDONE.OK','WINGEO.OK','WINBAD.OK','WINMISS.OK','WINPASS.OK','WINFAIL.LOG','GSMISS.OK','DOSBOOT.OK',DOS_END,'WINBOOT.LOG')),
                         (st['staged_win'],('EARLY.LOG','WAS.LOG','SHUTFAIL.LOG','WCHILD.OK','WWAIT.OK'))):
        for name in names:
            (folder/name).unlink(missing_ok=True)
    if (st['uat']/'FS').exists():shutil.rmtree(str(st['uat']/'FS'))
    if (st['staged_win']/'WAS.WAS').exists():
        raise GuestError('Forbidden no-argument fallback WAS.WAS')
    if sha256((st['staged_win']/'TEST.WAS').read_bytes())!=st['script_sha256']:
        raise GuestError('TEST.WAS changed after staging')


def read_trace(st):
    p=st['staged_win']/'EARLY.LOG'
    return p.read_bytes().decode('ascii',errors='replace').splitlines() if p.is_file() else []


def startup_timed_out(elapsed, trace, closed_guest_witness=False):
    """50s applies to launch only, not an interpreter that is already running.

    DOSBox-X may not expose the contents of an open DOS handle on the host
    filesystem until the handle closes. An authenticated, closed WSTART.OK or
    WEND.OK file proves that WAS opened TEST.WAS and reached WAIT, even when
    EARLY.LOG remains zero bytes. Do not confuse an unflushed trace with a
    non-starting Win16 program.
    """
    return elapsed >= STARTUP_TRACE_LIMIT_SECONDS and not (
        closed_guest_witness or
        (EXPECTED_BUILD_MARKER in trace and 'WAS_OPEN=TEST.WAS' in trace))


def closed_script_checkpoint(st, name):
    """Accept only a closed, byte-identical copy of the current staged script."""
    if name not in ('BEFORE.OK', 'AFTER.OK'):
        return False
    p = st['uat'] / name
    return p.is_file() and sha256(p.read_bytes()) == st['script_sha256']


def closed_env_witness(st):
    """A validated closed ENV.LOG proves interpreter activity after Win16 startup."""
    p = st['uat'] / 'ENV.LOG'
    if not p.is_file():
        return False
    try:
        rows = p.read_text(encoding='ascii').splitlines()
        names = ('WINVER','SCREENW','SCREENH','BPP','DISKFREE(C)')
        if len(rows) != len(names):
            return False
        vals = {}
        for name, row in zip(names, rows):
            if not row.startswith(name + '=') or not row[len(name)+1:].isdecimal():
                return False
            vals[name] = int(row[len(name)+1:])
        return vals['WINVER'] == {'WIN101':1,'WIN200':2,'WIN300':3}[st['target']] and all(
            vals[k] > 0 for k in names)
    except (OSError, UnicodeError, ValueError):
        return False


def native_startup_witness(st):
    """Fresh closed guest proof; EARLY.LOG may be zero while its handle is open."""
    return ((st.get('shot_suite') and (
                 read_wait_marker(st,'SHOTBEG.OK','SHOT_BEGIN') or
                 read_wait_marker(st,'SHOTWAT.OK','SHOT_WAIT_DONE') or
                 read_wait_marker(st,'SNAPOK.OK','SNAP_DONE'))) or
            closed_env_witness(st) or
            closed_script_checkpoint(st,'BEFORE.OK') or
            closed_script_checkpoint(st,'AFTER.OK') or
            (st.get('auto_suite') and read_wait_marker(st,'START.OK','AUTO_START')) or
            read_wait_marker(st,'WSTART.OK','WAIT_BEGIN') or
            read_wait_marker(st,'WEND.OK','WAIT_DONE'))



def snap_timing_witness(folder, unsupported=False):
    """Read separate guest-clock intervals for SNAPSAFE and default SNAP.

    DOS time resolution is whole seconds; times exclude initial WAIT and TAR.
    Never report the compatibility crop as part of FAST's duration.
    """
    stamps=folder/'TIMES.LOG'
    if not stamps.is_file():
        raise GuestError('SNAPFAST missing DATE/TIME witness TIMES.LOG')
    lines=stamps.read_text(encoding='ascii', errors='replace').splitlines()
    labels=('SNAPSAFE_START','SNAPSAFE_END','COMPAT_CROP_OK',
            'SNAPFAST_START','SNAPFAST_END')
    expected=len(labels)+(1 if unsupported else 0)
    if len(lines)!=expected:
        raise GuestError('SNAPFAST incorrect time log entries: '+repr(lines))
    observations={}
    for label, row in zip(labels,lines):
        if label=='COMPAT_CROP_OK':
            if row!='COMPAT_CROP_OK=YES':
                raise GuestError('SNAPFAST safe path did not complete: '+repr(row))
            continue
        value=row.removeprefix(label+'=')
        if not row.startswith(label+'=') or re.fullmatch(
                r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', value) is None:
            raise GuestError('SNAPFAST malformed time entry: '+repr(row))
        try:
            observations[label]=datetime.datetime.fromisoformat(value)
        except ValueError as exc:
            raise GuestError('SNAPFAST invalid guest date/time: '+repr(row)) from exc
    if unsupported and lines[-1]!='FAST_UNSUPPORTED=YES':
        raise GuestError('SNAPFAST missing unsupported witness: '+repr(lines))
    safe=(observations['SNAPSAFE_END']-observations['SNAPSAFE_START']).total_seconds()
    fast=(observations['SNAPFAST_END']-observations['SNAPFAST_START']).total_seconds()
    if safe < 0 or fast < 0:
        raise GuestError('SNAPFAST timestamp order reversed: '+repr(lines))
    return {'snap_safe_guest_seconds':safe,'snap_fast_guest_seconds':fast,
            'snap_time_resolution_seconds':1}


def keyboard_failure(st):
    """Only a complete current-run marker is failure evidence, not open/empty files."""
    try:
        text=(st['uat']/'KBFAIL.LOG').read_text(encoding='ascii').strip()
    except (OSError,UnicodeError):
        return None
    prefix='KEYBOARD_FAIL='+st['token']+' '
    if not text.startswith(prefix): return None
    import re
    if not re.fullmatch(r'STAGE=[A-Z_]+ RESULT=\d+ ERRORCODE=\d+',text[len(prefix):]): return None
    return text[len(prefix):]


def validate_keyboard(st):
    uat=st['uat']; win=st['staged_win']; token=st['token']
    failure=keyboard_failure(st)
    if failure: raise GuestError('KEYBOARD guest failed: '+failure)
    if not read_wait_marker(st,'KBPASS.OK','KEYBOARD_PASS'): raise GuestError('KEYBOARD missing token-matched PASS')
    trace=read_trace(st)
    for v in ('WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'):
        if v not in trace: raise GuestError('KEYBOARD missing startup/END witness: '+v)
    if 'WAS_FAILURE' in trace or 'KEYBOARD_CALLBACK_UNAVAILABLE' in trace: raise GuestError('KEYBOARD callback failed')
    if (uat/'DOSBOOT.OK').read_bytes().strip()!=b'DOSBOOT '+token.encode('ascii'): raise GuestError('KEYBOARD bad DOS boot token')
    body=(win/'TEST.WAS').read_bytes()
    if sha256(body)!=st['script_sha256'] or body!=(win/'KEYBOARD.WAS').read_bytes(): raise GuestError('KEYBOARD staged script changed')
    raw=(win/'WEVENT.DAT').read_bytes()
    if not raw or len(raw)%8: raise GuestError('KEYBOARD missing or incomplete event witness')
    events=list(struct.iter_unpack('<4H',raw))
    transitions=[(m,v) for m,v,lo,hi in events if m in (0x100,0x101,0x104,0x105)]
    expected=[(256, 65), (257, 65), (256, 16), (256, 66), (257, 66), (257, 16), (256, 67), (257, 67), (256, 17), (257, 17), (256, 16), (256, 68), (257, 68), (257, 16), (256, 17), (256, 16), (256, 113), (257, 113), (257, 16), (257, 17), (256, 16), (256, 65), (257, 65), (257, 16), (256, 66), (257, 66), (256, 32), (257, 32), (256, 49), (257, 49), (256, 57), (257, 57), (256, 16), (256, 49), (257, 49), (257, 16), (256, 16), (256, 191), (257, 191), (257, 16), (256, 190), (257, 190), (256, 90), (257, 90)]
    if transitions!=expected: raise GuestError('KEYBOARD native transitions mismatch: '+repr(transitions))
    chars=[v for m,v,lo,hi in events if m==0x102]
    if chars!=list(map(ord,'aBcDAb 19!?.z')): raise GuestError('KEYBOARD translated characters / shift recovery mismatch: '+repr(chars))
    for m,v,lo,hi in events:
        if m in (0x100,0x101) and bool(hi&0x8000)!=(m==0x101): raise GuestError('KEYBOARD transition flags mismatch')
    return {'keyboard':{'transitions':transitions,'characters':''.join(map(chr,chars)),'recovery':'PASS','combo':'PASS','type':'PASS'},'phase':'KEYBOARD','status':'PASS','script_sha256':st['script_sha256']}

def validate_input(st):
    uat=st['uat']; win=st['staged_win']; token=st['token']
    if (uat/'INFAIL.LOG').exists(): raise GuestError('INPUT guest explicitly failed: '+(uat/'INFAIL.LOG').read_text(errors='replace'))
    if not read_wait_marker(st,'INPASS.OK','INPUT_PASS'): raise GuestError('INPUT missing PASS')
    trace=read_trace(st)
    for v in ('WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'):
        if v not in trace: raise GuestError('INPUT missing startup/END witness: '+v)
    if 'WAS_FAILURE' in trace or 'INPUT_CALLBACK_UNAVAILABLE' in trace: raise GuestError('INPUT callback failed')
    if (uat/'DOSBOOT.OK').read_bytes().strip()!=b'DOSBOOT '+token.encode('ascii'): raise GuestError('INPUT bad DOS boot token')
    staged=win/'TEST.WAS'
    if sha256(staged.read_bytes())!=st['script_sha256'] or staged.read_bytes()!=(win/'INPUT.WAS').read_bytes(): raise GuestError('INPUT staged script changed')
    import struct
    raw=(win/'WEVENT.DAT').read_bytes()
    if not raw or len(raw)%8: raise GuestError('INPUT missing or incomplete native message witness')
    events=list(struct.iter_unpack('<4H',raw))
    # Require actual dispatch at the requested client positions. Ignore extra
    # moves, but never substitute the interpreter's own reported state.
    transitions=[(msg,x,y) for msg,flags,x,y in events if msg!=0x200]
    expected=[(0x201,12,12),(0x202,12,12),(0x204,25,25),(0x205,25,25),
              (0x201,15,15),(0x202,45,35),(0x201,35,15),(0x202,35,15),
              (0x203,35,15),(0x202,35,15),(0x204,35,15),(0x205,35,15)]
    if transitions!=expected: raise GuestError('INPUT native transitions mismatch: '+repr(transitions))
    for msg,flags,x,y in events:
        if msg in (0x201,0x203) and not flags&1 or msg==0x202 and flags&1:
            raise GuestError('INPUT incorrect left button state: '+repr((msg,flags,x,y)))
        if msg in (0x204,0x206) and not flags&2 or msg==0x205 and flags&2:
            raise GuestError('INPUT incorrect right button state: '+repr((msg,flags,x,y)))
    if not any(msg==0x200 and flags&1 and (x,y)==(45,35) for msg,flags,x,y in events):
        raise GuestError('INPUT missing held-button drag movement')
    for name in ('CLICK.BMP','DRAG.BMP'):
        b=(uat/name).read_bytes()
        if len(b)<54 or b[:2]!=b'BM' or struct.unpack_from('<I',b,2)[0]!=len(b): raise GuestError('INPUT invalid BMP '+name)
        off=struct.unpack_from('<I',b,10)[0]
        hs,w,h,planes,bpp,comp=struct.unpack_from('<IiiHHI',b,14)
        if not (hs>=40 and w>0 and h!=0 and planes==1 and bpp in (1,4,8,24) and comp==0 and 54<=off<len(b) and off+((w*bpp+31)//32)*4*abs(h)<=len(b)):
            raise GuestError('INPUT malformed BMP geometry or payload '+name)
    return {'input':{'events':len(events),'transitions':transitions,'drag':'PASS','screenshots':['CLICK.BMP','DRAG.BMP']},'phase':'INPUT','status':'PASS','script_sha256':st['script_sha256']}


def validate_window(st, begin_at=None, end_at=None):
    uat=st['uat']; win=st['staged_win']; token=st['token']
    if (uat/'WINFAIL.LOG').exists(): raise GuestError('WINDOW guest explicitly failed')
    def witness(name,prefix):
        p=uat/name
        if not p.is_file(): raise GuestError('WINDOW missing '+name)
        v=p.read_text(encoding='ascii').strip()
        head=prefix+'='+token
        if not v.startswith(head+' '): raise GuestError('WINDOW stale or bad '+name)
        return v[len(head)+1:]
    try:
        geo,cur=witness('WINGEO.OK','GEOMETRY').split(' ')
        if witness('WFIND.OK','WINDOW_FOUND') != geo:
            raise ValueError('WAITFOR WINDOW selection differs from geometry')
        for name,kind in (('WFBEG.OK','WINDOW_TIMEOUT_BEGIN'),('WFDONE.OK','WINDOW_TIMEOUT_DONE')):
            if not read_wait_marker(st,name,kind): raise ValueError('missing/stale '+name)
        if begin_at is None or end_at is None or not .65 <= end_at-begin_at <= 10.0:
            raise ValueError('WAITFOR WINDOW 1000ms timeout not independently timed')
        x,y,w,h=map(int,geo.split(',')); cx,cy=map(int,cur.split(','))
        if not (0<=x<32767 and 0<=y<32767 and 10<w<=32767 and 10<h<=32767 and (cx,cy)==(x+10,y+10)):
            raise ValueError('incorrect native coordinate translation')
        for name,kind in (('WINBAD.OK','INVALID'),('WINMISS.OK','MISSING')):
            if witness(name,kind)!=cur: raise ValueError('invalid/missing operation moved cursor')
    except (ValueError,UnicodeError) as exc: raise GuestError('WINDOW invalid geometry witness: '+str(exc)) from exc
    import struct
    independent=win/'WGEOM.DAT'
    if not independent.is_file() or len(independent.read_bytes())!=8:
        raise GuestError('WINDOW missing independent native fixture geometry')
    if struct.unpack('<4H',independent.read_bytes())!=(x,y,w,h):
        raise GuestError('WINDOW interpreter geometry differs from independent fixture')
    if not read_wait_marker(st,'WINPASS.OK','WINDOW_PASS'): raise GuestError('WINDOW missing PASS')
    trace=read_trace(st)
    for v in ('WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO','END'):
        if v not in trace: raise GuestError('WINDOW missing startup/END witness: '+v)
    if 'WAS_FAILURE' in trace: raise GuestError('WINDOW native failure')
    boot=uat/'DOSBOOT.OK'
    if not boot.is_file() or boot.read_bytes().strip()!=b'DOSBOOT '+token.encode('ascii'): raise GuestError('WINDOW bad DOS boot token')
    staged=win/'TEST.WAS'; other=win/'WINDOW.WAS'
    if not other.is_file() or not staged.is_file() or sha256(staged.read_bytes())!=st['script_sha256'] or staged.read_bytes()!=other.read_bytes(): raise GuestError('WINDOW staged script changed or missing')
    return {'window':{'origin':[x,y],'client':[w,h],'cursor':[cx,cy],'invalid':'PASS','missing':'PASS','waitfor_found':'PASS','waitfor_timeout':'PASS','timeout_seconds':round(end_at-begin_at,3)},'phase':'WINDOW','status':'PASS','script_sha256':st['script_sha256']}


def validate_mouse(st):
    uat=st['uat']; win=st['staged_win']; token=st['token']
    if (uat/'MSFAIL.LOG').exists(): raise GuestError('MOUSE guest explicitly failed')
    for name,expected in (('MSFIRST.OK','FIRST='+token+' 40,50'),
                          ('MSSECOND.OK','SECOND='+token+' 120,100'),
                          ('MSBAD.OK','INVALID='+token),('MSPASS.OK','MOUSE_PASS='+token)):
        p=uat/name
        if not p.is_file() or p.read_bytes().strip()!=expected.encode('ascii'):
            raise GuestError('MOUSE missing/stale/incorrect cursor witness: '+name)
    trace=read_trace(st)
    if 'WAS_FAILURE' in trace or 'END' not in trace: raise GuestError('MOUSE missing native END')
    for witness in ('WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP',
                    'WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=NO'):
        if witness not in trace: raise GuestError('MOUSE missing startup witness: '+witness)
    boot=uat/'DOSBOOT.OK'
    if not boot.is_file() or boot.read_bytes().strip()!=b'DOSBOOT '+token.encode('ascii'):
        raise GuestError('MOUSE absent or stale DOS boot token')
    staged=win/'TEST.WAS'; other=win/'MOUSE.WAS'
    if not other.is_file() or not staged.is_file() or sha256(staged.read_bytes())!=st['script_sha256'] or staged.read_bytes()!=other.read_bytes():
        raise GuestError('MOUSE staged script changed or missing')
    return {'mouse':{'first':[40,50],'second':[120,100],'invalid':'PASS'},
            'phase':'MOUSE','status':'PASS','script_sha256':st['script_sha256']}


def validate_guisync(st, begin_at=None, end_at=None):
    """Require native Win16 execution, five token-bound closed checkpoints,
    timeout interval, immutable script and authentic END; never mark a
    source-only host preflight as native qualification.
    """
    uat=st['uat']; win=st['staged_win']
    if (uat/'GSFAIL.LOG').is_file():
        raise GuestError('GUISYNC guest explicitly failed')
    if (uat/'GSMISS.OK').exists():
        raise GuestError('GUISYNC intentionally absent marker unexpectedly exists')
    for name,kind in (('GSEVENT.OK','EVENT_OK'),('GSFOUND.OK','FILE_FOUND'),
                      ('GSMBEG.OK','TIMEOUT_BEGIN'),('GSMDON.OK','TIMEOUT_DONE'),
                      ('GSPASS.OK','SYNC_PASS')):
        if not read_wait_marker(st,name,kind):
            raise GuestError('GUISYNC missing/stale/invalid closed marker: '+name)
    trace=read_trace(st)
    if 'WAS_FAILURE' in trace or 'END' not in trace:
        raise GuestError('GUISYNC did not reach native END: '+repr(trace[-15:]))
    for witness in ('WAS_INITTASK', EXPECTED_BUILD_MARKER, 'WAS_TAIL=TEST.WAS',
                    'WAS_INITAPP', 'WAS_SCRIPT=TEST.WAS', 'WAS_OPEN=TEST.WAS',
                    'SHOWICON=NO'):
        if witness not in trace:
            raise GuestError('GUISYNC missing native runtime/startup witness: '+witness)
    boot=uat/'DOSBOOT.OK'
    if not boot.is_file() or boot.read_bytes().strip()!=b'DOSBOOT '+st['token'].encode('ascii'):
        raise GuestError('GUISYNC absent or stale DOS boot token')
    staged=win/'TEST.WAS'
    other=win/'GUISYNC.WAS'
    if (not other.is_file() or not staged.is_file() or
            sha256(staged.read_bytes())!=st['script_sha256'] or
            staged.read_bytes()!=other.read_bytes()):
        raise GuestError('GUISYNC staged Win16 script changed or is missing')
    begin=(uat/'GSMBEG.OK').stat().st_mtime_ns
    end=(uat/'GSMDON.OK').stat().st_mtime_ns
    file_delta=(end-begin)/1e9
    # DOS file mtimes are quantized to TWO seconds. Never use them to
    # accept/reject a sub-second timeout; measure live host observations.
    # Missing/simultaneously observed markers are not timing evidence.
    if begin_at is None or end_at is None:
        raise GuestError('GUISYNC WAITFOR 700ms timeout not independently timed (missing live observation; DOS mtime %.3fs)' % file_delta)
    delta=end_at-begin_at
    # Host loop polls at 100ms; tolerate sampling and DOS clock quantization.
    if not .45 <= delta <= 10.0:
        raise GuestError('GUISYNC WAITFOR 700ms timeout not independently timed (host %.3fs; DOS mtime %.3fs)' % (delta,file_delta))
    guest_time=uat/'GSTIME.LOG'
    if (not guest_time.is_file() or not re.fullmatch(
            rb'GUEST_COMPLETED=\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\r?\n',
            guest_time.read_bytes())):
        raise GuestError('GUISYNC missing/malformed guest time witness')
    return {'guisync': {'doevents':'PASS','waitfor_existing':'PASS',
                        'waitfor_timeout':'PASS','timeout_seconds':round(delta,3),
                        'timer_method':'host-monotonic-closed-markers',
                        'dos_file_mtime_seconds':round(file_delta,3),
                        'dos_file_mtime_resolution_seconds':2,
                        'requested_timeout_ms':700,
                        'timestamp':guest_time.read_text(encoding='ascii').strip()},
            'phase':'GUISYNC','status':'PASS','script_sha256':st['script_sha256']}


def validate_startshot_unsupported(st):
    """A deliberate FAST refusal is not a capture success or a runtime crash."""
    import struct
    folder=st['uat']
    if os.environ.get('NOWBAT_SNAPFAST_DEV')!='1':
        raise GuestError('FAST unsupported outcome outside opt-in SNAPFAST trial')
    for name,prefix in (('DOSBOOT.OK','DOSBOOT'),('SHOTBEG.OK','SHOT_BEGIN'),
                        ('SHOTWAT.OK','SHOT_WAIT_DONE'),('FASTNO.OK','FAST_UNSUPPORTED')):
        if name=='DOSBOOT.OK':
            p=folder/name
            if not p.is_file() or p.read_text(encoding='ascii').strip()!=prefix+' '+st['token']:
                raise GuestError('SNAPFAST unsupported: missing/invalid DOSBOOT.OK')
        elif not read_wait_marker(st,name,prefix):
            raise GuestError('SNAPFAST unsupported: missing/invalid '+name)
    trace=read_trace(st)
    if not {'WAS_OPEN=TEST.WAS','SHOWICON=YES','SNAP_METHOD=UNSUPPORTED','END'}.issubset(set(trace)):
        raise GuestError('SNAPFAST unsupported: incomplete runtime trace '+repr(trace))
    if 'WAS_SHUTDOWN_REQUESTED' in trace or 'WAS_FAILURE' in trace or 'SNAP_METHOD=VIDEO_DIRECT' in trace:
        raise GuestError('SNAPFAST unsupported: invalid runtime branch')
    modes=[row.split('=',1)[1] for row in trace if row.startswith('SNAP_BIOS_MODE=')]
    if not modes or not re.fullmatch(r'[0-9A-F]{4}',modes[-1]):
        raise GuestError('SNAPFAST unsupported: no hardware mode witness')
    if modes[-1] in {'0006','0007','000D','000E','000F','0010','0011','0012','006A'}:
        raise GuestError('SNAPFAST refused a normally supported BIOS mode '+modes[-1])
    if (folder/'SHOTERR.LOG').exists() or (folder/'SCREEN.BMP').exists() or (folder/'SCREEN.TAR').exists():
        raise GuestError('SNAPFAST unsupported: failure log or unexpected full-screen output')
    safe=folder/'SAFE.BMP'
    if not safe.is_file():
        raise GuestError('SNAPFAST unsupported: COMPAT crop missing')
    b=safe.read_bytes()
    stride=((64+31)//32)*4
    if (len(b)!=62+32*stride or b[:2]!=b'BM' or
        struct.unpack_from('<I',b,2)[0]!=len(b) or
        struct.unpack_from('<I',b,10)[0]!=62 or
        struct.unpack_from('<IiiHHI',b,14)!=(40,64,32,1,1,0)):
        raise GuestError('SNAPFAST unsupported: COMPAT crop malformed')
    timings=snap_timing_witness(folder, unsupported=True)
    if (st['staged_win']/'TEST.WAS').read_bytes()!=(st['staged_win']/'SHOT.WAS').read_bytes():
        raise GuestError('SNAPFAST unsupported: staged script changed')
    return {'phase':'STARTSHOT','status':'UNSUPPORTED','reason':'BIOS_MODE_UNSUPPORTED',
            'bios_mode':modes[-1],'compat_crop_bytes':len(b), **timings}


def validate_startshot(st):
    """Proof of a visible, non-uniform real desktop, not merely a valid BMP."""
    from startshot_check import inspect_bmp, verify_shot_tar
    folder=st['uat']
    for name,kind in (('DOSBOOT.OK','DOSBOOT'),
                      ('SHOTBEG.OK','SHOT_BEGIN'),('SHOTWAT.OK','SHOT_WAIT_DONE'),
                      ('SNAPOK.OK','SNAP_DONE'),('TARCRT.OK','TAR_CREATED'),
                      ('TARBMP.OK','TAR_BMP_ADDED'),('TARSCR.OK','TAR_SCRIPT_ADDED'),
                      ('TAROK.OK','TAR_DONE')):
        if name == 'DOSBOOT.OK':
            marker=folder/name
            if not marker.is_file() or marker.read_text(encoding='ascii').strip()!=kind+' '+st['token']:
                raise GuestError('STARTSHOT missing/invalid DOS marker '+name)
        elif not read_wait_marker(st,name,kind):
            raise GuestError('STARTSHOT missing/invalid closed checkpoint '+name)
    if (folder/'SHOTERR.LOG').exists():
        raise GuestError('STARTSHOT script reported a UI/capture/TAR error')
    # The probe explicitly requests the native iconic UI before its first
    # closed checkpoint. A background-only NOWBAT task is not sufficient for
    # this visual proof, even if it produced valid BMP bytes.
    trace = read_trace(st)
    if 'WAS_OPEN=TEST.WAS' not in trace or 'SHOWICON=YES' not in trace:
        raise GuestError('STARTSHOT did not prove NOWBAT loaded TEST.WAS and created its icon; trace=' + repr(trace[-12:]))
    if 'END' not in trace or 'WAS_SHUTDOWN_REQUESTED' in trace:
        raise GuestError('STARTSHOT must terminate NOWBAT with END, without Windows SHUTDOWN')
    # This performance audit must NEVER pass silently through 480,000 GetPixel
    # calls when the bulk Win16 GDI path is unsupported or fails.
    if os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' and 'SNAP_METHOD=VIDEO_DIRECT' not in trace:
        raise GuestError('SNAPFAST did not use VIDEO_DIRECT: per-pixel fallback is unacceptable at 750 cycles')
    timings=snap_timing_witness(folder) if os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' else {}
    if (st['staged_win']/'SHUTFAIL.LOG').exists():
        raise GuestError('STARTSHOT unexpectedly attempted Windows SHUTDOWN')
    if (st['staged_win']/'TEST.WAS').read_bytes() != (st['staged_win']/'SHOT.WAS').read_bytes():
        raise GuestError('STARTSHOT staged script/archive copy differs')
    if sha256((st['staged_win']/'TEST.WAS').read_bytes()) != st['script_sha256']:
        raise GuestError('STARTSHOT executed script changed')
    try:
        if os.environ.get('NOWBAT_SNAPFAST_DEV')=='1':
            # The script omits BPP: verify the native GDI desktop depth
            # matches the recognised BIOS hardware mode, not an imposed 1bpp.
            modes=[row.split('=',1)[1] for row in trace if row.startswith('SNAP_BIOS_MODE=')]
            if not modes: raise GuestError('SNAPFAST missing BIOS mode for depth verification')
            bios_mode=int(modes[-1],16)
            expected_bpp=4 if bios_mode in (0x0D,0x0E,0x10,0x12,0x6A) else 1
        else:
            expected_bpp=4
        bmp=inspect_bmp(folder/'SCREEN.BMP',expected_bpp=expected_bpp)
        if os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' and bios_mode==0x6A:
            if (bmp['width'],bmp['height'],bmp['bpp']) != (800,600,4):
                raise GuestError('WIN101 0x6A FAST requires a complete 800x600x4 BMP')
            from startshot_check import verify_win101_palette
            verify_win101_palette(bmp)
    except ValueError as exc:
        raise GuestError(str(exc)) from exc
    try:
        tar=verify_shot_tar(folder/'SCREEN.TAR',
                            {'SCREEN.BMP':(folder/'SCREEN.BMP').read_bytes(),
                             'SHOT.WAS':(st['staged_win']/'SHOT.WAS').read_bytes()})
    except ValueError as exc:
        raise GuestError(str(exc)) from exc
    return {'phase':'STARTSHOT','status':'PASS','snapshot':bmp,'tar':tar,
            'script_sha256':st['script_sha256'], **timings}


def validate_boot(st):
    """BOOT-only: prove interpreter entry + iconic Win16 UI + DOS return."""
    for name,pre in (('DOSBOOT.OK','DOSBOOT'),(DOS_END,'DOSEND')):
        file=st['uat']/name
        if not file.is_file() or file.read_text(encoding='ascii').strip()!=pre+' '+st['token']:
            raise GuestError('BOOT-only missing DOS marker '+name)
    trace=read_trace(st)
    expected=('WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS',
              'WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS',
              'SHOWICON=YES','SHOWICON=NO','WAS_SHUTDOWN_REQUESTED')
    for event in expected:
        if event not in trace:
            raise GuestError('BOOT-only missing native event: '+event+'; trace='+repr(trace))
    log=st['uat']/'BOOT.LOG'
    if not log.is_file() or 'WAS_BOOT_OK='+st['token'] not in log.read_text(encoding='latin-1'):
        raise GuestError('BOOT-only missing native BOOT.LOG')
    return {'phase':'BOOT_ONLY','status':'PASS','boot_only':True,
            'suites':['WIN200_STARTUP','ICON_UI','SHUTDOWN_DOS_RETURN']}


def validate_session(st):
    folder=st['uat']
    for name,prefix in (('DOSBOOT.OK','DOSBOOT'),(DOS_END,'DOSEND')):
        p=folder/name
        if not p.is_file() or p.read_text(encoding='ascii').strip()!=prefix+' '+st['token']:
            raise GuestError('Missing or stale DOS marker '+name)
    if (st['staged_win']/'WAS.WAS').exists():
        raise GuestError('Forbidden no-argument fallback WAS.WAS')
    raw_trace=read_trace(st)
    # Native diagnostics are *additional* trace lines, not script events.
    # Keep the strict PASS sequence and its length; never accept an
    # unexpected event by silently dropping any other kind of line.
    trace=[line for line in raw_trace if not line.startswith((
        'SHELL_NEXT=', 'SHELL_LOAD_AX=', 'SHELL_ES_RESTORED'))]
    api='USER.7' if st['target']=='WIN300' else 'USER.2'
    version=[x for x in trace if x.startswith('WAS_VERSION=')]
    if len(version)!=1 or not re.fullmatch(r'WAS_VERSION=[0-9A-F]{4}',version[0]):
        raise GuestError('Windows GetVersion evidence absent or malformed')
    ver=int(version[0].split('=')[1],16)
    major={'WIN101':1,'WIN200':2,'WIN300':3}[st['target']]
    if ver & 0xff != major:
        raise GuestError('Wrong Windows runtime version: '+version[0])
    expected=['WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS','WAS_INITAPP',version[0]]
    flags=None
    if st['target']=='WIN300':
        fs=[x for x in trace if x.startswith('WAS_WINFLAGS=')]
        if len(fs)!=1 or not re.fullmatch(r'WAS_WINFLAGS=[0-9A-F]{4}',fs[0]):
            raise GuestError('GetWinFlags evidence missing')
        flags=int(fs[0].split('=')[1],16)
        if flags & 0x31:
            raise GuestError('Windows 3 is not running in real mode: '+fs[0])
        expected+=fs
    expected+=['WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS','SHOWICON=YES',
               'SHELL_LAUNCHED','SHELL_LAUNCHED','SHELLWAIT_COMPLETED']
    # A deliberately missing Windows program must produce a loader error,
    # never an invented DOS application exit code.
    if len(trace) < len(expected)+4 or trace[:len(expected)]!=expected:
        # Native ENV.LOG, not host-computed values, explains early IF exits.
        env_path=folder/'ENV.LOG'
        env_values=(env_path.read_text(encoding='ascii',errors='replace').splitlines()
                    if env_path.is_file() else ['ENV.LOG ABSENT'])
        raise GuestError('Invalid Win16 launch/control trace; ENV.LOG='+repr(env_values)+'; TRACE='+repr(trace))
    trailer=trace[len(expected):]
    if not trailer or not re.fullmatch(r'SHELL_LAUNCH_ERROR=[1-9][0-9]*',trailer[0]):
        raise GuestError('Win16 negative launch error missing: '+repr(trailer))
    # TEST.WAS performs exactly one SNAPSAFE, which bypasses the direct
    # video probe. The resident runtime emits its mode and method in order.
    # Require the exact compatibility pair; do not hide arbitrary SNAP rows.
    if trailer[1:3]!=['SNAP_BIOS_MODE=00FF','SNAP_METHOD=GETPIXEL']:
        raise GuestError('Foundation SNAPSAFE diagnostic missing or invalid: '+repr(trailer))
    if trailer[3:]!=['SHOWICON=NO','WAS_SHUTDOWN_REQUESTED','WAS_SHUTDOWN_API='+api]:
        raise GuestError('Invalid interpreter command-tail/open/shutdown evidence: '+repr(trailer))
    if (st['staged_win']/'SHUTFAIL.LOG').exists():
        raise GuestError('Windows shutdown API returned (veto/failure)')
    if sha256((st['staged_win']/'TEST.WAS').read_bytes())!=st['script_sha256']:
        raise GuestError('TEST.WAS changed during execution')
    return {'phase':'FOUNDATION','status':'PASS',
            'suites':['COMMAND_TAIL_TEST.WAS','SHUTDOWN_DOS_RETURN'],
            'windows_version_hex':'%04X'%ver,'winflags_hex':None if flags is None else '%04X'%flags,
            'trace_sha256':sha256((st['staged_win']/'EARLY.LOG').read_bytes()),
            'script_sha256':st['script_sha256']}



# The interactive/terminating PASS, FAIL and END statements require isolated
# child-task qualification. They are deliberately NOT credited by this matrix.
AUTO_COMMANDS = (
    'SHOWICON', 'COPY', 'MOVE', 'REN', 'RENAME', 'DEL', 'DELETE', 'ERASE',
    'MKDIR', 'MD', 'RMDIR', 'RD', 'CHDIR', 'CD', 'DIR', 'PWD', 'EXISTS',
    'LOG', 'LOGFILE', 'LOGCLOSE', 'SET', 'IF', 'ASSERT', 'GOTO', 'GOSUB',
    'RETURN', 'WAIT', 'SHELL', 'SHELLWAIT', 'SNAPSAFE', 'TARCREATE', 'TARADD',
    'TARCLOSE', 'SHUTDOWN',
)
AUTO_PENDING = ('END', 'PASS', 'FAIL')  # separately staged, now verified below


def validate_auto_bmp(path, expected_bpp):
    if not path.is_file():
        raise GuestError('AutoUAT missing BMP: ' + path.name)
    b = path.read_bytes()
    if len(b) < 62 or b[:2] != b'BM':
        raise GuestError('AutoUAT invalid BMP signature: ' + path.name)
    actual_size, offset = struct.unpack_from('<IxxxxI', b, 2)
    hsize, w, h, planes, bpp, comp = struct.unpack_from('<IiiHHI', b, 14)
    if not (actual_size == len(b) and 40 <= hsize <= 124 and
            w == 16 and abs(h) == 16 and planes == 1 and
            bpp == expected_bpp and comp == 0 and 54 <= offset < len(b)):
        raise GuestError('AutoUAT malformed %s BMP: %r' % (path.name,
                         (len(b), w, h, planes, bpp, comp, offset)))
    stride = ((w * bpp + 31) // 32) * 4
    if len(b) < offset + stride * abs(h):
        raise GuestError('AutoUAT truncated BMP: ' + path.name)
    return {'bpp': bpp, 'width': w, 'height': h, 'bytes': len(b),
            'sha256': sha256(b)}


def auto_phase_status(st):
    """Return the last *consecutive* closed phase, verified against ENV.LOG."""
    env = st['uat']/'ENV.LOG'
    if not env.is_file() or not closed_env_witness(st):
        return -1
    expected = env.read_bytes()
    latest = -1
    for index,name in enumerate(AUTO_PHASE_MARKERS):
        marker = st['uat']/name
        if not marker.is_file() or marker.read_bytes()!=expected:
            break
        latest=index
    return latest


def validate_auto(st):
    """Strict, independent host verification of real guest AutoUAT evidence."""
    directory = st['uat']
    token = st['token']
    for name, prefix in (('DOSBOOT.OK', 'DOSBOOT'), (DOS_END, 'DOSEND'),
                         ('START.OK', 'AUTO_START')):
        p = directory / name
        want = prefix + (' ' if name in ('DOSBOOT.OK', DOS_END) else '=') + token
        if not p.is_file() or p.read_text(encoding='ascii', errors='replace').strip() != want:
            raise GuestError('AutoUAT missing/stale guest marker ' + name)
    if auto_phase_status(st) != len(AUTO_PHASE_MARKERS)-1:
        missing = AUTO_PHASE_MARKERS[auto_phase_status(st)+1]
        raise GuestError('AutoUAT missing/invalid closed phase '+missing)
    # W054: the first SHELL must resume into a real file operation before
    # SHELLWAIT. Verify its closed copy against the actual staged script,
    # never merely trust a self-reported PASS line.
    launch_copy = directory/'LAUNCH.OK'
    if not launch_copy.is_file() or launch_copy.read_bytes() != (st['staged_win']/'TEST.WAS').read_bytes():
        raise GuestError('AutoUAT missing/invalid post-SHELL source copy LAUNCH.OK')
    # The asynchronous SHELL is not complete merely because LoadModule succeeded.
    # Require an independently closed native checkpoint after the child marker.
    async_marker = directory/'ASYNC.OK'
    env_path = directory/'ENV.LOG'
    if not async_marker.is_file() or async_marker.read_bytes() != env_path.read_bytes():
        raise GuestError('AutoUAT missing/invalid async-child checkpoint ASYNC.OK')
    if (directory/'ERROR.LOG').exists():
        raise GuestError('AutoUAT script reached ERROR: '+
                         (directory/'ERROR.LOG').read_text(encoding='latin-1', errors='replace'))
    done = directory/'DONE.LOG'
    if not done.is_file() or done.read_text(encoding='latin-1').splitlines() != ['AUTO_DONE='+token]:
        raise GuestError('AutoUAT lacks terminal AUTO_DONE marker')
    if sha256((st['staged_win']/'TEST.WAS').read_bytes()) != st['script_sha256']:
        raise GuestError('AutoUAT staged script was changed')
    trace = read_trace(st)
    for needle in ('WAS_INITTASK',EXPECTED_BUILD_MARKER,'WAS_TAIL=TEST.WAS',
                   'WAS_INITAPP','WAS_SCRIPT=TEST.WAS','WAS_OPEN=TEST.WAS',
                   'SHOWICON=YES','SHOWICON=NO','SHELLWAIT_COMPLETED',
                   'WAS_SHUTDOWN_REQUESTED',
                   'WAS_SHUTDOWN_API='+('USER.7' if st['target']=='WIN300' else 'USER.2')):
        if needle not in trace:
            raise GuestError('AutoUAT trace missing '+needle+': '+repr(trace[-20:]))
    if 'WAS_FAILURE' in trace or (st['staged_win']/'SHUTFAIL.LOG').exists():
        raise GuestError('AutoUAT runtime failure or shutdown veto')
    versions = [v for v in trace if v.startswith('WAS_VERSION=')]
    expect_major = {'WIN101':1, 'WIN200':2, 'WIN300':3}[st['target']]
    if len(versions)!=1 or int(versions[0].split('=',1)[1],16)&0xff != expect_major:
        raise GuestError('AutoUAT wrong native Windows version: '+repr(versions))
    if trace.count('SHELL_LAUNCHED') < 2 or len([v for v in trace if v.startswith('SHELL_LAUNCH_ERROR=')]) < 2:
        raise GuestError('AutoUAT SHELL / SHELLWAIT positive and negative evidence incomplete')
    for name in ('WCHILD.OK','WWAIT.OK'):
        marker=st['staged_win']/name
        if not marker.is_file() or marker.read_bytes()!=expected_child_version(st['target']):
            raise GuestError('AutoUAT Win16 child did not finish on the correct Windows version: '+name)
    defaultlog = st['staged_win']/'WAS.LOG'
    if not defaultlog.is_file() or 'DEFAULT_LOG='+token not in defaultlog.read_text(encoding='latin-1'):
        raise GuestError('AutoUAT default LOG missing')
    log = directory/'AUTO.LOG'
    if not log.is_file():
        raise GuestError('AutoUAT AUTO.LOG missing')
    lines = log.read_text(encoding='latin-1',errors='replace').splitlines()
    ordered = ['AUTO_BEGIN=', 'SUB_ONE=', 'SUB_TWO=', 'CONTROL_OK=', 'ENV_OK=',
               'SHELL_OK=', 'FILES_OK=', 'WAIT_OK=', 'SNAP_OK=']
    positions = []
    for item in ordered:
        matches = [i for i, line in enumerate(lines) if line == item+token]
        if len(matches)!=1:
            raise GuestError('AutoUAT log marker '+item+' missing/duplicated: '+repr(lines))
        positions.append(matches[0])
    if positions != sorted(positions):
        raise GuestError('AutoUAT checkpoints out of execution order')
    between = lines[positions[5]+1:positions[6]]
    if not any('\\' in line and line.upper().endswith('\\FS') for line in between):
        raise GuestError('AutoUAT PWD output is absent/invalid: '+repr(between))
    if 'D.TXT' not in [line.upper() for line in between]:
        raise GuestError('AutoUAT DIR wildcard did not list expected D.TXT')
    fs = directory/'FS'
    surviving = fs/'D.TXT'
    if not surviving.is_file() or surviving.read_bytes() != (st['staged_win']/'TEST.WAS').read_bytes():
        raise GuestError('AutoUAT COPY/REN/MOVE corrupted D.TXT')
    for name in ('A.TXT','B.TXT','C.TXT','E.TXT','F.TXT','G.TXT','BAD.TXT'):
        if (fs/name).exists():
            raise GuestError('AutoUAT deleted/moved file unexpectedly survived: '+name)
    if any((fs/x).exists() for x in ('ONE','TWO')):
        raise GuestError('AutoUAT RD/RMDIR did not remove empty subfolder')
    envlog = directory/'ENV.LOG'
    if not envlog.is_file():
        raise GuestError('AutoUAT ENV.LOG missing')
    values = {}
    for line in envlog.read_text(encoding='ascii',errors='replace').splitlines():
        if '=' not in line: raise GuestError('AutoUAT malformed environment line '+repr(line))
        key, val = line.split('=',1)
        if key in values or not val.isdecimal():
            raise GuestError('AutoUAT duplicate/non-numeric environment value '+repr(line))
        values[key]=int(val)
    expected = ('WINVER','SCREENW','SCREENH','BPP','DISKFREE(C)')
    if set(values) != set(expected) or values['WINVER'] != expect_major or \
            any(values[k] <= 0 for k in expected):
        raise GuestError('AutoUAT invalid live environment values: '+repr(values))
    bmp = {p:validate_auto_bmp(directory/('R%d.BMP'%p),p) for p in (1,4,8,24)}
    tarpath = directory/'AUTO.TAR'
    if not tarpath.is_file():
        raise GuestError('AutoUAT TAR missing')
    expected_members = {'AUTO.LOG':log.read_bytes(), 'D.TXT':surviving.read_bytes(),
                        'R4.BMP':(directory/'R4.BMP').read_bytes()}
    with tarfile.open(str(tarpath),'r:') as tar:
        members = tar.getmembers()
        if [m.name.upper() for m in members] != list(expected_members):
            raise GuestError('AutoUAT TAR members wrong: '+repr([m.name for m in members]))
        for m in members:
            if not m.isfile() or m.size != len(expected_members[m.name.upper()]):
                raise GuestError('AutoUAT TAR member size/type invalid: '+m.name)
            if tar.extractfile(m).read() != expected_members[m.name.upper()]:
                raise GuestError('AutoUAT TAR payload mismatch: '+m.name)
    # END/PASS/FAIL must each actually execute in a separate Win16 task.
    # The parent's own script reaches DONE only after each child unloads.
    for kind in ('TEND','TPASS','TFAIL'):
        if (not read_wait_marker(st,kind+'.BEG','TERM_BEGIN_'+kind) or
            not read_wait_marker(st,kind+'.DON','TERM_DONE_'+kind)):
            raise GuestError('AutoUAT missing/invalid closed terminal boundaries for '+kind)
    terminals = {}
    for kind, exe, terminal in (('TEND','NBTEND','END'),
                                ('TPASS','NBTPASS','PASS'),
                                ('TFAIL','NBTFAIL','FAIL')):
        d = directory/kind
        source = d/(kind+'.WAS')
        expected_sha = st.get('terminal_scripts',{}).get(kind)
        if not source.is_file() or not expected_sha or sha256(source.read_bytes()) != expected_sha:
            raise GuestError('AutoUAT missing/tampered terminal script '+kind)
        path = d/('TERM'+terminal+'.LOG')
        if not path.is_file() or path.read_text(encoding='latin-1').splitlines() != [
                'TERM'+terminal+'='+token]:
            raise GuestError('AutoUAT terminal marker missing/invalid: '+kind)
        native = d/'EARLY.LOG'
        if not native.is_file():
            raise GuestError('AutoUAT terminal native trace missing: '+kind)
        lines = native.read_text(encoding='ascii',errors='replace').splitlines()
        # Win16 command tails preserve the caller's quotes.  SHELLWAIT in
        # AUTO.WAS deliberately passes "TEND.WAS" (etc.); both quoted and
        # unquoted single-filename tails select the same script.  Require
        # exactly one tail and reject malformed/duplicate values.
        tails = [line for line in lines if line.startswith('WAS_TAIL=')]
        allowed = ('WAS_TAIL='+kind+'.WAS', 'WAS_TAIL="'+kind+'.WAS"')
        if len(tails) != 1 or tails[0] not in allowed:
            raise GuestError('AutoUAT terminal trace invalid WAS_TAIL: '+kind+
                             ' '+repr(tails))
        for marker in ('WAS_INITTASK', EXPECTED_BUILD_MARKER,
                       'WAS_INITAPP', 'WAS_SCRIPT='+kind+'.WAS',
                       'WAS_OPEN='+kind+'.WAS',terminal):
            if lines.count(marker) != 1:
                raise GuestError('AutoUAT terminal trace missing/duplicate '+marker+': '+kind)
        if 'WAS_FAILURE' in lines or 'WAS_SHUTDOWN_REQUESTED' in lines or (d/'SHUTFAIL.LOG').exists():
            raise GuestError('AutoUAT terminal child failed or shut down session: '+kind)
        if terminal != lines[-1]:
            raise GuestError('AutoUAT unexpected execution after terminal '+kind+': '+repr(lines))
        terminals[terminal] = {'result':'PASS','exe':exe+'.EXE',
                               'script_sha256':expected_sha,'trace_sha256':sha256(native.read_bytes())}
    return {'phase':'AUTO_COMMANDS', 'status':'PASS', 'auto_suite':True,
            'suites':['CONTROL','ENV','DOS_FILES','WIN16_SHELL','BMP_1_4_8_24',
                      'USTAR_WILDCARD','ICON','WIN_SHUTDOWN'],
            'verified_commands':list(AUTO_COMMANDS),
            'pending_isolated_terminal_tests':[],
            'terminal_commands':terminals,
            'environment':values,'bmp':bmp,'tar_bytes':tarpath.stat().st_size,
            'script_sha256':st['script_sha256']}

def validate_bmp4(path):
    """Full desktop, Windows BMP v3, 4bpp BI_RGB, exact size/palette/stride."""
    if not path.is_file():raise GuestError('Missing DESKTOP.BMP')
    raw=path.read_bytes()
    if len(raw)<118 or raw[:2]!=b'BM':raise GuestError('Invalid BMP signature/length')
    size=struct.unpack_from('<I',raw,2)[0]
    offset=struct.unpack_from('<I',raw,10)[0]
    head,w,h,planes,bpp,compression,imagebytes=struct.unpack_from('<IiiHHII',raw,14)
    if head!=40 or planes!=1 or bpp!=4 or compression!=0 or w<320 or h<200 or w>4096 or h>4096:
        raise GuestError('Not an uncompressed full-desktop 4-bpp BMP: %sx%s bpp=%s'%(w,h,bpp))
    stride=((w*4+31)//32)*4
    if size!=len(raw) or offset!=118 or imagebytes!=stride*h or size!=offset+imagebytes:
        raise GuestError('BMP file, palette or stride mismatch')
    # A single-colour screenshot is suspicious, but black desktops are legal;
    # retain bytewise pixel hash for human review rather than inventing UI pixels.
    return {'width':w,'height':h,'bpp':4,'bytes':len(raw),'pixel_bytes':imagebytes,
            'sha256':sha256(raw)}


def validate_tar(path, expected):
    if not path.is_file():raise GuestError('Missing EVIDENCE.TAR')
    raw=path.read_bytes()
    if len(raw)<2048 or len(raw)%512 or raw[-1024:]!=bytes(1024):
        raise GuestError('TAR missing aligned two-block end marker')
    result={}
    try:
        with tarfile.open(str(path),'r:',errorlevel=2) as arc:
            members=arc.getmembers()
            if len(members)!=2 or set(x.name.upper() for x in members)!=set(expected):
                raise GuestError('TAR must contain exactly DESKTOP.LOG and DESKTOP.BMP')
            for member in members:
                if not member.isfile() or member.pax_headers:
                    raise GuestError('Unexpected TAR entry type')
                contents=arc.extractfile(member)
                if contents is None or contents.read()!=expected[member.name.upper()]:
                    raise GuestError('TAR payload mismatches independent original: '+member.name)
                result[member.name.upper()]=member.size
    except (tarfile.TarError,OSError,EOFError) as exc:
        raise GuestError('Unreadable USTAR archive: '+str(exc))
    return {'members':result,'bytes':len(raw),'sha256':sha256(raw)}


def read_wait_marker(st, name, kind):
    """Closed, separate 8.3 guest file. The content proves its run token.

    DESKTOP.LOG is intentionally not a timing witness: DOSBox-X may expose
    the two lines together when the log finally closes after SNAP.
    """
    path=st['uat']/name
    if not path.is_file():
        return False
    try:
        return path.read_bytes().splitlines()==[(kind+'='+st['token']).encode('ascii')]
    except OSError:
        return False


def verify_wait_interval(st, begin, end):
    """Verify elapsed time between *separate closed files*, never buffered log lines.

    The preferred measure is the host's monotonic first-observed time. If
    the host happens to wake only after both events, the independent host
    filesystem modification times of those separately closed files provide
    a second witness. Neither method uses emulator startup time as a proxy.
    """
    if not read_wait_marker(st,'WSTART.OK','WAIT_BEGIN'):
        raise GuestError('Missing or invalid pre-WAIT closed marker WSTART.OK')
    if not read_wait_marker(st,'WEND.OK','WAIT_DONE'):
        raise GuestError('Missing or invalid post-WAIT closed marker WEND.OK')
    observed = (end-begin) if begin is not None and end is not None else -1
    if observed >= 4.6:
        return {'seconds':round(observed,3),'method':'host-monotonic'}
    try:
        stamps=(st['uat']/'WEND.OK').stat().st_mtime_ns-(st['uat']/'WSTART.OK').stat().st_mtime_ns
        filesystem=stamps/1_000_000_000
    except OSError:
        filesystem=-1
    if filesystem>=4.6:
        return {'seconds':round(filesystem,3),'method':'host-file-mtime'}
    raise GuestError('Five-second WAIT not independently verified (host=%.3fs, files=%.3fs)'%(
        observed,filesystem))


def validate_filesystem(st):
    """Native, byte-for-byte DOS file operations proof; no script-only claims.

    The script must move a byte-identical copy of its own source and delete
    intermediate files, report an expected DOS open error, enumerate the
    surviving 8.3 filename, and change/read the current directory.
    """
    work=st['uat']; directory=work/'FS'; token=st['token']
    log=work/'FS.LOG'
    if not log.is_file():raise GuestError('Missing filesystem test log FS.LOG')
    lines=log.read_bytes().decode('ascii',errors='replace').splitlines()
    if len(lines)!=4 or lines[0].upper()!='MOVED.TXT' or lines[1]!='FS_DIR_OK='+token or not lines[2].upper().endswith('\\FS') or lines[3]!='FS_ALL_OK='+token:
        raise GuestError('DOS filesystem command sequence incorrect: '+repr(lines))
    surviving=directory/'MOVED.TXT'
    if not surviving.is_file() or surviving.read_bytes()!=(st['staged_win']/'TEST.WAS').read_bytes():
        raise GuestError('COPY/REN/MOVE lost or changed script bytes')
    for name in ('ORIG.TXT','REN.TXT','DEL.TXT','BAD.TXT'):
        if (directory/name).exists():raise GuestError('DOS filesystem operation left forbidden '+name)
    if (directory/'EMPTY').exists():raise GuestError('RMDIR failed to remove EMPTY')
    return {'log_sha256':sha256(log.read_bytes()),
            'moved_file_sha256':sha256(surviving.read_bytes()),
            'moved_file_bytes':surviving.stat().st_size}


def validate_control(st):
    """Verify actual Win16 child launch, wait and negative launch handling.

    The witness comes from independent Windows NE executables, never
    from DOS .COM files. WCHILD.OK and WWAIT.OK mark independent Win16 children.
    It must be absent before this run and is collected as native evidence.
    """
    env_path=st['uat']/'ENV.LOG'
    if not env_path.is_file():raise GuestError('Missing native ENV.LOG')
    env_lines=env_path.read_text(encoding='ascii',errors='replace').splitlines()
    names=('WINVER','SCREENW','SCREENH','BPP','DISKFREE(C)')
    if len(env_lines)!=len(names):
        raise GuestError('Invalid native environment value count: '+repr(env_lines))
    values={}
    for name,line in zip(names,env_lines):
        if not line.startswith(name+'=') or not line[len(name)+1:].isdigit():
            raise GuestError('Invalid native environment value: '+repr(line))
        values[name]=int(line[len(name)+1:])
    if values['WINVER']!={'WIN101':1,'WIN200':2,'WIN300':3}[st['target']] or any(
        values[n]<=0 for n in ('SCREENW','SCREENH','BPP','DISKFREE(C)')):
        raise GuestError('Native environment values unavailable or overwritten: '+repr(values))
    path=st['uat']/'CONTROL.LOG'
    if not path.is_file():raise GuestError('Missing CONTROL.LOG')
    token=st['token']
    expect=['IF_EQ_NE_OK='+token,'ENV_IF_OK='+token,'GOSUB_RETURN_OK='+token,
            'SHELL_LAUNCH_OK='+token,'SHELLWAIT_WIN16_OK='+token,
            'SHELL_ERROR_OK='+token]
    if path.read_bytes().decode('ascii',errors='replace').splitlines()!=expect:
        raise GuestError('Control flow or Win16 SHELL evidence invalid')
    built=ROOT/'BUILD'/'WCHILD.EXE'
    installed=st['staged_win']/'WCHILD.EXE'
    if not built.is_file() or not installed.is_file() or sha256(installed.read_bytes())!=sha256(built.read_bytes()):
        raise GuestError('Independent Win16 shell child is missing or modified')
    for child_name, marker_name in (('WCHILD','WCHILD.OK'),('WWAIT','WWAIT.OK')):
        built=ROOT/'BUILD'/(child_name+'.EXE')
        installed=st['staged_win']/(child_name+'.EXE')
        if not built.is_file() or not installed.is_file() or sha256(installed.read_bytes())!=sha256(built.read_bytes()):
            raise GuestError('Win16 '+child_name+' fixture missing or modified')
        marker=st['staged_win']/marker_name
        if not marker.is_file() or marker.read_bytes()!=expected_child_version(st['target']):
            raise GuestError('Win16 '+child_name+' completion marker missing or wrong target/version')
    for checkpoint in ('BEFORE.OK','AFTER.OK'):
        if not closed_script_checkpoint(st,checkpoint):
            raise GuestError('Missing or corrupt native Win16 checkpoint: ' + checkpoint)
    return {'log_sha256':sha256(path.read_bytes()),'win16_child_sha256':sha256(built.read_bytes())}


def validate_desktop(st):
    base=validate_session(st)
    folder=st['uat'];token=st['token']
    for marker,kind in (('WSTART.OK','WAIT_BEGIN'),('WEND.OK','WAIT_DONE')):
        if not read_wait_marker(st,marker,kind):
            raise GuestError('Missing or invalid closed WAIT marker: '+marker)
    log=folder/'DESKTOP.LOG'
    if not log.is_file():raise GuestError('Missing DESKTOP.LOG')
    data=log.read_bytes()
    rows=data.decode('ascii',errors='replace').splitlines()
    expected=['WAS_RUN='+token,'WAIT_BEGIN='+token,'WAIT_DONE='+token,
              'CHECKS_OK='+token,'SNAP_OK_4BPP='+token,'EVIDENCE_READY='+token]
    if rows!=expected:raise GuestError('WAS log out of order or incomplete: '+repr(rows))
    filesystem=validate_filesystem(st)
    control=validate_control(st)
    bmp=validate_bmp4(folder/'DESKTOP.BMP')
    tar=validate_tar(folder/'EVIDENCE.TAR',{'DESKTOP.LOG':data,
                                           'DESKTOP.BMP':(folder/'DESKTOP.BMP').read_bytes()})
    base.update(suites=['COMMAND_TAIL_TEST.WAS','WAIT_5000','SNAP_FULL_DESKTOP_BPP4',
                        'LOG','EXISTS_ASSERT','DOS_FILE_DIRECTORY','CONTROL_FLOW','SHELL_WAIT_WIN16',
                        'SHOWICON_TOGGLE','TAR_TWO_MEMBERS','SHUTDOWN_DOS_RETURN'],
                bmp=bmp,tar=tar,filesystem=filesystem,control=control,log_sha256=sha256(data))
    return base


def dosbox_command(dosbox,conf,max_seconds=None):
    args=[str(dosbox),'-defaultconf','-conf',str(conf),'-fastlaunch','-noconsole','-nopromptfolder']
    if max_seconds is not None:args+=['-time-limit',str(int(max_seconds)+5)]
    return args


def launch_dosbox(dosbox,conf,stream,max_seconds=None,desktop_mode='visible'):
    args=dosbox_command(dosbox,conf,max_seconds=max_seconds)
    if desktop_mode=='visible':
        from winvisible import VisibleProcess
        return VisibleProcess(args,ROOT,stream)
    if desktop_mode=='hidden':
        from winhidden import HiddenProcess
        return HiddenProcess(args,ROOT,stream)
    raise GuestError('Unsupported desktop mode: '+str(desktop_mode))


def win1_wait_snapshot(st):
    """Inspect the eight bytes written/closed by WAS, not by the host."""
    f=st['staged_win']/'SWWAIT.DAT'
    if not f.is_file():
        return 'SWWAIT.DAT absent'
    raw=f.read_bytes()
    if len(raw)!=8:
        return 'SWWAIT.DAT invalid size='+str(len(raw))
    handle,baseline,observed,phase=struct.unpack('<4H',raw)
    if phase not in (1,2,3):
        return 'SWWAIT.DAT invalid phase='+str(phase)
    return ('Win1 GetModuleUsage handle=%04X baseline=%u observed=%u phase=%u' %
            (handle,baseline,observed,phase))


def diagnostic(st,phase='FOUNDATION'):
    if not st:return 'Guest staging did not finish'
    if not (st['uat']/'DOSBOOT.OK').exists():return 'DOS autoexec did not start'
    if st.get('keyboard_suite'):
        failure=keyboard_failure(st)
        if failure: return 'KEYBOARD native script: '+failure
    trace=read_trace(st)
    boot=st['uat']/'WINBOOT.LOG'
    if not trace:
        if st.get('shot_suite'):
            for name,kind in (('SHOTBEG.OK','SHOT_BEGIN'),('SHOTWAT.OK','SHOT_WAIT_DONE'),
                              ('SNAPOK.OK','SNAP_DONE'),('TARCRT.OK','TAR_CREATED'),
                              ('TARBMP.OK','TAR_BMP_ADDED'),('TARSCR.OK','TAR_SCRIPT_ADDED'),
                              ('TAROK.OK','TAR_DONE')):
                if not read_wait_marker(st,name,kind):
                    return 'STARTSHOT awaiting '+name+' (script trace may be buffered)'
            return 'STARTSHOT captured BMP and TAR; awaiting native END'
        # EARLY.LOG and WAS.LOG are often zero-sized until DOS closes their
        # handles. Do not report "no startup" after token-checked script output.
        if read_wait_marker(st,'WEND.OK','WAIT_DONE'):
            return 'WAS executed through WAIT_DONE; EARLY.LOG still open/unflushed; '+(
                'BMP captured; awaiting remaining script/shutdown' if (st['uat']/'DESKTOP.BMP').is_file()
                else 'awaiting screenshot/remaining script')
        if read_wait_marker(st,'WSTART.OK','WAIT_BEGIN'):
            return 'WAS executed through WAIT_BEGIN; EARLY.LOG still open/unflushed'
        if closed_script_checkpoint(st,'AFTER.OK'):
            return 'WAS passed SHELLWAIT and assertions; later command blocked; EARLY.LOG unflushed'
        if closed_script_checkpoint(st,'BEFORE.OK'):
            return 'WAS passed SHELL; SHELLWAIT or its assertions not completed; EARLY.LOG unflushed'
        if closed_env_witness(st):
            if st.get('auto_suite'):
                idx=auto_phase_status(st)
                last='ENV.LOG' if idx<0 else AUTO_PHASE_MARKERS[idx]
                upcoming=AUTO_PHASE_MARKERS[idx+1] if idx+1<len(AUTO_PHASE_MARKERS) else 'terminal tests'
                return 'NOWBAT AutoUAT last closed='+last+'; next='+upcoming+'; EARLY.LOG buffered'
            return 'WAS started and closed ENV.LOG; awaiting child/control-flow checkpoint; EARLY.LOG unflushed'
        # Diagnose the observed Win1 DOSBox-X INT 6 storm using a bounded
        # tail read; the previous 180-second run grew this log to ~59 MiB.
        doslog=st['work']/'DOSBOX.LOG'
        if doslog.is_file():
            with doslog.open('rb') as stream:
                stream.seek(max(0,doslog.stat().st_size-8192))
                tail=stream.read(8192)
            if b'Illegal Unhandled Interrupt Called 6' in tail:
                return 'Win1 CPU invalid-opcode/INT 6 loop before WAS trace; check staged Windows boot and executable startup'
        return 'No WAS startup trace; '+(boot.read_text(encoding='latin-1')[-1000:] if boot.exists() else 'no loader output')
    if EXPECTED_BUILD_MARKER not in trace:return 'NOWBAT binary is not build W054; '+repr(trace)
    if 'WAS_INITAPP' not in trace:return 'WAS InitApp failed; '+repr(trace)
    if st.get('shot_suite'):
        for name in ('SHOTBEG.OK','SHOTWAT.OK','SNAPOK.OK','TARCRT.OK','TARBMP.OK','TARSCR.OK','TAROK.OK'):
            if not (st['uat']/name).exists():
                return ('STARTSHOT awaiting '+name+'; NOWBAT must create its bat icon before SHOTBEG.OK' if name=='SHOTBEG.OK' else 'STARTSHOT awaiting '+name)+ ('; EARLY.LOG may be buffered' if not trace else '')
        return 'STARTSHOT capture complete; awaiting native END'
    if 'WAS_TAIL=TEST.WAS' not in trace:return 'Command-line argument lost or changed; '+repr(trace)
    if 'WAS_OPEN=TEST.WAS' not in trace:return 'WAS could not open requested script; '+repr(trace)
    if 'WAS_SHUTDOWN_REQUESTED' not in trace:
        # Never label a failing Win16 launch/wait as a snapshot/TAR failure.
        shell=[v for v in trace if v.startswith(('SHELL_','SHELLWAIT_'))]
        if shell:
            executed=(st['staged_win']/'WWAIT.OK').is_file() and (st['staged_win']/'WWAIT.OK').read_bytes()==expected_child_version(st['target'])
            return ('Win16 wait child marker=%s, shell trace=%s; '%
                    ('YES' if executed else 'NO',repr(shell)))+repr(trace[-7:])
        log=st['uat']/'DESKTOP.LOG'
        return 'Script stopped before evidence capture; '+(log.read_text(encoding='ascii',errors='replace')[-500:] if log.is_file() else repr(trace))
    if (st['staged_win']/'SHUTFAIL.LOG').exists():return 'Shutdown API returned (veto/failure)'
    if not (st['uat']/DOS_END).exists():return 'SHUTDOWN requested but Windows did not return to DOS'
    return 'DOS return present; checking natural emulator exit and evidence'


def stop_dosbox(proc):
    if proc is None:return False
    forced=proc.poll() is None
    if forced:
        proc.terminate()
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill();proc.wait(timeout=3)
    return forced


def run_phase(target,phase,st,dosbox,timeout,output_dir,desktop_mode='visible'):
    prepare_phase(st,phase)
    write_stage_manifest(st)
    proc=None; started=time.monotonic(); dos_end_at=None
    wait_begin_at=None;wait_end_at=None;child_wait_begin_at=None
    auto_stage_index=-2;auto_stage_at=started
    shot_wait_begin_at=None;shot_wait_end_at=None;shot_capture_done_at=None
    gui_wait_begin_at=None;gui_wait_end_at=None
    keyboard_fail_at=None
    st['process']={'started':False,'forced_termination':False,'exited':False,
                   'desktop_mode':desktop_mode}
    print('UAT %s desktop=%s (DOSBox-X guest window %s)' % (
        target, desktop_mode, 'VISIBLE' if desktop_mode=='visible' else 'HIDDEN'), flush=True)
    print('UAT %s startup deadline=%ss; build=W054; full-suite timeout=%ss' % (
        target, STARTUP_TRACE_LIMIT_SECONDS, timeout), flush=True)
    with (output_dir/'DOSBOX_STARTUP.LOG').open('wb') as stream:
        try:
            proc=launch_dosbox(dosbox,st['conf'],stream,timeout,desktop_mode=desktop_mode)
            st['process'].update(started=True,pid=proc.pid,private_desktop=proc.desktop_name)
            auto_term_started={kind:None for kind in ('TEND','TPASS','TFAIL')}
            next_status=started+10
            while time.monotonic()-started<timeout:
                # The guest closes WSTART.OK before WAIT and WEND.OK after it.
                # Seeing two lines in one buffered DESKTOP.LOG proves no interval.
                if st.get('shot_suite'):
                    if shot_wait_begin_at is None and read_wait_marker(st,'SHOTBEG.OK','SHOT_BEGIN'):
                        shot_wait_begin_at=time.monotonic()
                        print('STARTSHOT %s: NOWBAT icon initialized; 10-SECOND WINDOW OPEN - manually open an app NOW'%target,flush=True)
                    if shot_wait_end_at is None and read_wait_marker(st,'SHOTWAT.OK','SHOT_WAIT_DONE'):
                        shot_wait_end_at=time.monotonic()
                        print('STARTSHOT %s: 10-second warmup complete; full-desktop capture started'%target,flush=True)
                    if shot_capture_done_at is None and read_wait_marker(st,'SNAPOK.OK','SNAP_DONE'):
                        shot_capture_done_at=time.monotonic()
                        if shot_wait_end_at is not None:
                            print('SNAPFAST %s: capture checkpoint observed after %.2fs' % (target,shot_capture_done_at-shot_wait_end_at),flush=True)
                    if (st['uat']/'SHOTERR.LOG').exists():
                        raise GuestError('STARTSHOT script reported failure; '+diagnostic(st))
                    if (os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' and
                            shot_wait_end_at is not None and shot_capture_done_at is None and
                            time.monotonic()-shot_wait_end_at > 90):
                        raise GuestError('SNAPFAST capture exceeded 90s at 750 cycles; '
                                         'terminating stalled guest; '+diagnostic(st))
                if wait_begin_at is None and read_wait_marker(st,'WSTART.OK','WAIT_BEGIN'):
                    wait_begin_at=time.monotonic()
                if wait_end_at is None and read_wait_marker(st,'WEND.OK','WAIT_DONE'):
                    wait_end_at=time.monotonic()
                if not st.get('shot_suite') and not st.get('auto_suite') and not st.get('boot_only') and child_wait_begin_at is None and closed_script_checkpoint(st,'BEFORE.OK'):
                    child_wait_begin_at=time.monotonic()
                if st.get('auto_suite'):
                    # The 50s startup watchdog remains independent. Once a
                    # closed START.OK exists, prevent a silent 300s stall even
                    # if EARLY.LOG is buffered by the guest Windows runtime.
                    if read_wait_marker(st,'START.OK','AUTO_START'):
                        phase_index=auto_phase_status(st)
                        # After TAR, track each terminal child and final
                        # DONE without allowing a new 300s unobserved gap.
                        progress_index=phase_index
                        if phase_index==len(AUTO_PHASE_MARKERS)-1:
                            for item,(name,prefix) in enumerate(AUTO_TERMINAL_MARKERS):
                                if not read_wait_marker(st,name,prefix):
                                    break
                                progress_index=len(AUTO_PHASE_MARKERS)+item
                        if progress_index!=auto_stage_index:
                            auto_stage_index=progress_index
                            auto_stage_at=time.monotonic()
                            label=('ENV.LOG' if progress_index<0 else
                                   AUTO_PHASE_MARKERS[progress_index] if progress_index<len(AUTO_PHASE_MARKERS) else
                                   AUTO_TERMINAL_MARKERS[progress_index-len(AUTO_PHASE_MARKERS)][0])
                            print('AUTOUAT %s closed checkpoint: %s'%(target,label),flush=True)
                        final_index=len(AUTO_PHASE_MARKERS)+len(AUTO_TERMINAL_MARKERS)-1
                        if progress_index<final_index and time.monotonic()-auto_stage_at>=AUTO_PHASE_LIMIT_SECONDS:
                            next_idx=progress_index+1
                            next_name=(AUTO_PHASE_MARKERS[next_idx] if next_idx<len(AUTO_PHASE_MARKERS)
                                       else AUTO_TERMINAL_MARKERS[next_idx-len(AUTO_PHASE_MARKERS)][0])
                            raise GuestError('AutoUAT stalled before closed '+next_name+
                                ' (%ds without phase progress); '%AUTO_PHASE_LIMIT_SECONDS+diagnostic(st))
                    # Bounded native child waits, independent of 300-second
                    # total suite budget. Each marker is a closed DOS file.
                    now_probe=time.monotonic()
                    for kind in ('TEND','TPASS','TFAIL'):
                        if auto_term_started[kind] is None and read_wait_marker(
                                st,kind+'.BEG','TERM_BEGIN_'+kind):
                            auto_term_started[kind]=now_probe
                        if (auto_term_started[kind] is not None and
                            not read_wait_marker(st,kind+'.DON','TERM_DONE_'+kind) and
                            now_probe-auto_term_started[kind]>=50):
                            raise GuestError('AutoUAT '+kind+' native SHELLWAIT exceeded 50s; '+diagnostic(st))
                # An unsupported BIOS mode is a correctly rejected FAST request,
                # not a successful capture. The guest proves it with a closed marker
                # and exits through END without attempting a slow GDI fallback.
                if st.get('shot_suite') and read_wait_marker(st,'FASTNO.OK','FAST_UNSUPPORTED'):
                    if 'END' in read_trace(st):
                        result=validate_startshot_unsupported(st)
                        from startshot_check import verify_ten_second_wait
                        try:
                            result['warmup']=verify_ten_second_wait(
                                st['uat']/'SHOTBEG.OK',st['uat']/'SHOTWAT.OK',
                                shot_wait_begin_at,shot_wait_end_at)
                        except ValueError as exc:
                            raise GuestError(str(exc)) from exc
                        st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                        result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                        return result
                # STARTSHOT is an isolated capture check, never a shutdown
                # test. Require closed TAR and native interpreter END first;
                # the host then closes only its dedicated DOSBox instance.
                if st.get('shot_suite') and read_wait_marker(st,'TAROK.OK','TAR_DONE'):
                    trace=read_trace(st)
                    if 'END' in trace and 'WAS_FAILURE' not in trace:
                        result=validate_startshot(st)
                        from startshot_check import verify_ten_second_wait
                        try:
                            result['warmup']=verify_ten_second_wait(
                                st['uat']/'SHOTBEG.OK',st['uat']/'SHOTWAT.OK',
                                shot_wait_begin_at,shot_wait_end_at)
                        except ValueError as exc:
                            raise GuestError(str(exc)) from exc
                        if shot_capture_done_at is not None and shot_wait_end_at is not None:
                            result['capture_seconds']=round(shot_capture_done_at-shot_wait_end_at,3)
                        st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                        result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                        return result
                if st.get('keyboard_suite'):
                    failure=keyboard_failure(st)
                    if failure:
                        # DOSBox may expose marker creation before any writes.
                        # Give FAIL a bounded opportunity to close EARLY.LOG.
                        if keyboard_fail_at is None: keyboard_fail_at=time.monotonic()
                        if 'WAS_FAILURE' in read_trace(st) or time.monotonic()-keyboard_fail_at>=2:
                            raise GuestError('KEYBOARD guest failed: '+failure)
                    if read_wait_marker(st,'KBPASS.OK','KEYBOARD_PASS') and 'END' in read_trace(st):
                        result=validate_keyboard(st)
                        st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                        result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                        return result
                elif st.get('input_suite'):
                    if (st['uat']/'INFAIL.LOG').exists():
                        raise GuestError('INPUT guest failed: '+(st['uat']/'INFAIL.LOG').read_text(errors='replace')+'; '+diagnostic(st))
                    if read_wait_marker(st,'INPASS.OK','INPUT_PASS') and 'END' in read_trace(st):
                        result=validate_input(st)
                        st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                        result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                        return result
                elif st.get('window_suite'):
                    observed_at=time.monotonic()
                    if gui_wait_begin_at is None and read_wait_marker(st,'WFBEG.OK','WINDOW_TIMEOUT_BEGIN'):
                        gui_wait_begin_at=observed_at
                    if gui_wait_end_at is None and read_wait_marker(st,'WFDONE.OK','WINDOW_TIMEOUT_DONE'):
                        gui_wait_end_at=observed_at
                    if (st['uat']/'WINFAIL.LOG').exists():
                        raise GuestError('WINDOW guest script entered FAIL branch; '+diagnostic(st))
                    if read_wait_marker(st,'WINPASS.OK','WINDOW_PASS') and 'END' in read_trace(st):
                        result=validate_window(st,gui_wait_begin_at,gui_wait_end_at)
                        st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                        result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                        return result
                elif st.get('mouse_suite'):
                    if (st['uat']/'MSFAIL.LOG').exists():
                        raise GuestError('MOUSE guest script entered FAIL branch; '+diagnostic(st))
                    if read_wait_marker(st,'MSPASS.OK','MOUSE_PASS') and 'END' in read_trace(st):
                        result=validate_mouse(st)
                        st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                        result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                        return result
                elif st.get('guisync_suite'):
                    # Observe separate token-matched markers live, before
                    # checking END. Same-poll observations cannot prove delay.
                    observed_at=time.monotonic()
                    if gui_wait_begin_at is None and read_wait_marker(st,'GSMBEG.OK','TIMEOUT_BEGIN'):
                        gui_wait_begin_at=observed_at
                    if gui_wait_end_at is None and read_wait_marker(st,'GSMDON.OK','TIMEOUT_DONE'):
                        gui_wait_end_at=observed_at
                    if (st['uat']/'GSFAIL.LOG').exists():
                        raise GuestError('GUISYNC guest script entered FAIL branch; '+diagnostic(st))
                    if read_wait_marker(st,'GSPASS.OK','SYNC_PASS'):
                        trace=read_trace(st)
                        if 'END' in trace and 'WAS_FAILURE' not in trace:
                            result=validate_guisync(st,gui_wait_begin_at,gui_wait_end_at)
                            st['process']['suite_exit']='HOST_CLOSED_AFTER_NATIVE_END'
                            result['termination']='NOWBAT_END_WINDOWS_LEFT_RUNNING'
                            return result
                rc=proc.poll()
                if rc is not None:
                    st['process'].update(exited=True,exit_code=rc,natural_exit=True)
                    if rc!=0:raise GuestError('Emulator exited with code '+str(rc)+'; '+diagnostic(st))
                    if 'WAS_FAILURE' in read_trace(st):
                        raise GuestError(diagnostic(st))
                    if st.get('keyboard_suite'):
                        return validate_keyboard(st)
                    if st.get('input_suite'):
                        return validate_input(st)
                    if st.get('window_suite'):
                        return validate_window(st,gui_wait_begin_at,gui_wait_end_at)
                    if st.get('mouse_suite'):
                        return validate_mouse(st)
                    if st.get('guisync_suite'):
                        return validate_guisync(st,gui_wait_begin_at,gui_wait_end_at)
                    if st.get('shot_suite'):
                        result=validate_startshot(st)
                        from startshot_check import verify_ten_second_wait
                        try:
                            result['warmup']=verify_ten_second_wait(
                                st['uat']/'SHOTBEG.OK',st['uat']/'SHOTWAT.OK',
                                shot_wait_begin_at,shot_wait_end_at)
                        except ValueError as exc:
                            raise GuestError(str(exc)) from exc
                        return result
                    if st.get('boot_only'):
                        return validate_boot(st)
                    if st.get('auto_suite'):
                        return validate_auto(st)
                    result=validate_desktop(st)
                    witness=verify_wait_interval(st,wait_begin_at,wait_end_at)
                    result['observed_wait_seconds']=witness['seconds']
                    result['wait_witness_method']=witness['method']
                    return result
                if (st['uat']/DOS_END).exists():
                    if dos_end_at is None:dos_end_at=time.monotonic()
                    elif time.monotonic()-dos_end_at>3:
                        raise GuestError('DOS returned but emulator did not exit naturally')
                trace=read_trace(st)
                if 'WAS_FAILURE' in trace:
                    raise GuestError(diagnostic(st))
                now=time.monotonic()
                # A stuck Win1/Win2 loader is independent of the full native
                # suite timeout (WAIT, BMP, TAR and shutdown take longer).
                # Fail FAST when no completed interpreter startup is seen.
                if startup_timed_out(now-started,trace,native_startup_witness(st)):
                    raise GuestError('WAS startup lacked both trace and closed guest witness after 50s; '+diagnostic(st))
                # A separately bounded 2-second Win16 child test: do not
                # confuse a blocked SHELLWAIT with startup and wait 180 s.
                if child_wait_begin_at is not None and not closed_script_checkpoint(st,'AFTER.OK') and now-child_wait_begin_at >= 50:
                    raise GuestError('Win16 SHELLWAIT/checkpoint exceeded 50s; '+win1_wait_snapshot(st)+'; '+diagnostic(st))
                if now>=next_status:
                    print('UAT %s %ds: %s'%(target,int(now-started),diagnostic(st)),flush=True)
                    next_status=now+10
                time.sleep(.1)
            raise GuestError('Bounded guest timeout (%ss); %s'%(timeout,diagnostic(st)))
        finally:
            if proc is not None:
                st['process']['forced_termination']=stop_dosbox(proc)
                st['process'].update(exited=proc.poll() is not None,exit_code=proc.returncode,
                                     elapsed_seconds=round(time.monotonic()-started,3))
                try:
                    st['process']['windows_remaining']=proc.window_count()
                finally:
                    proc.close()
                    st['process']['handles_closed']=True


def collect(st,out):
    if not st:return
    for folder,names in ((st['uat'],('DOSBOOT.OK',DOS_END,'SHOTBEG.OK','SHOTWAT.OK',
                                        'SNAPOK.OK','FASTNO.OK','SAFE.BMP','TIMES.LOG','GSEVENT.OK','GSFOUND.OK','GSMBEG.OK','GSMDON.OK','GSPASS.OK','GSFAIL.LOG','GSTIME.LOG','MSFIRST.OK','MSSECOND.OK','MSBAD.OK','MSPASS.OK','MSFAIL.LOG','WFIND.OK','WFBEG.OK','WFDONE.OK','WINGEO.OK','WINBAD.OK','WINMISS.OK','WINPASS.OK','WINFAIL.LOG','KEYBOARD.LOG','KBFAIL.LOG','KBPASS.OK','INPUT.LOG','INFAIL.LOG','INPASS.OK','CLICK.BMP','DRAG.BMP','TARCRT.OK','TARBMP.OK','TARSCR.OK','TAROK.OK','SHOTERR.LOG','SCREEN.BMP','SCREEN.TAR',
                                        'BEFORE.OK','AFTER.OK','WSTART.OK','WEND.OK','DESKTOP.LOG','DESKTOP.BMP','EVIDENCE.TAR','FS.LOG','CONTROL.LOG','BOOT.LOG','START.OK',*AUTO_PHASE_MARKERS,'AUTO.LOG','DONE.LOG','ENV.LOG','ERROR.LOG','LAUNCH.OK','ASYNC.OK',
                                         'TEND.BEG','TEND.DON','TPASS.BEG','TPASS.DON','TFAIL.BEG','TFAIL.DON','R1.BMP','R4.BMP','R8.BMP','R24.BMP','AUTO.TAR','WINBOOT.LOG')),
                         (st['staged_win'],('EARLY.LOG','WAS.LOG','SHUTFAIL.LOG','TEST.WAS','SHOT.WAS','GUISYNC.WAS','MOUSE.WAS','WINDOW.WAS','INPUT.WAS','KEYBOARD.WAS','WGEOM.EXE','WGEOM.DAT','WEVENT.DAT','INABI.DAT','WCHILD.EXE','WWAIT.EXE','WCHILD.OK','WWAIT.OK','SWWAIT.DAT')),
                         (st['work'],('DOSBOX.CONF','RUNUAT.BAT','STAGE.JSON','DOSBOX.LOG'))):
        for name in names:
            p=folder/name
            if p.is_file():shutil.copy2(str(p),str(out/name))
    if st.get('auto_suite'):
        for kind in ('TEND','TPASS','TFAIL'):
            d=st['uat']/kind
            if d.is_dir():
                dst=out/'TERMINALS'/kind
                dst.mkdir(parents=True,exist_ok=True)
                for file in d.iterdir():
                    if file.is_file():
                        shutil.copy2(str(file),str(dst/file.name))
    # Include independent copy/move byte evidence, not just WAS's FS.LOG.
    # Foundation uses MOVED.TXT; AutoUAT uses D.TXT. Retain both when present.
    for name in ('MOVED.TXT','D.TXT'):
        surviving=st['uat']/'FS'/name
        if surviving.is_file():
            dest=out/'FS'/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(str(surviving),str(dest))


def run_target(target,cfg,dosbox,timeout,results_root=None):
    report={'target':target,'started_utc':utcnow(),'result':'FAIL','native':'NOT_STARTED'}
    st=None; out=(Path(results_root) if results_root else ROOT/'UAT'/'RESULTS')/target
    out.mkdir(parents=True,exist_ok=True)
    try:
        desktop_mode=('visible' if os.environ.get('NOWBAT_STARTSHOT')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1'
                      else guest_desktop_mode(cfg))
        st=stage(target,cfg)
        report.update(exe_sha256=sha256(st['binary'].read_bytes()),
                      windows_source=str(st['win_src']),windows_stage=str(st['staged_win']),
                      dosbox=str(dosbox),bootline=st['bootline'],token=st['token'],
                      launch_command=dosbox_command(dosbox,st['conf'],max_seconds=timeout),
                      desktop_mode=desktop_mode,hidden_requested=(desktop_mode=='hidden'),
                      cpu_cycles=('750' if os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1' else 'profile'),
                      child_fixture_policy=('WIN3_YIELD_2S' if target=='WIN300' else 'WIN1_2_IMMEDIATE_EXIT'),
                      ui_policy=('ICON_ONLY_NO_ABOUT' if target=='WIN101' else 'ICON_WITH_SYSTEM_MENU_ABOUT'))
        original_ini=sha256((st['win_src']/'WIN.INI').read_bytes())
        report['native']='STARTED'
        report.update(run_phase(target,'FOUNDATION',st,dosbox,timeout,out,desktop_mode=desktop_mode))
        process=st['process']
        if st.get('shot_suite') or st.get('guisync_suite'):
            # The deliberate test-guest teardown is not a Windows SHUTDOWN.
            if (process.get('suite_exit')!='HOST_CLOSED_AFTER_NATIVE_END' or
                    not process.get('exited') or process.get('windows_remaining')!=0 or
                    not process.get('handles_closed')):
                raise GuestError('Capture/sync guest was not closed after native END')
        elif (not process.get('exited') or process.get('forced_termination') or
                process.get('exit_code')!=0 or process.get('windows_remaining')!=0 or
                not process.get('handles_closed')):
            raise GuestError('Emulator did not exit naturally with all process handles closed')
        if sha256((st['win_src']/'WIN.INI').read_bytes())!=original_ini:
            raise GuestError('Original WIN.INI changed')
        unsupported = st.get('shot_suite') and report.get('status')=='UNSUPPORTED'
        report.update(result=('UNSUPPORTED' if unsupported else 'PASS'),
                      native=('STARTSHOT_UNSUPPORTED' if unsupported else
                              'STARTSHOT' if st.get('shot_suite') else
                              'NATIVE_KEYBOARD_INPUT' if st.get('keyboard_suite') else
                              'NATIVE_MOUSE_INPUT' if st.get('input_suite') else
                              'WINDOW_GEOMETRY' if st.get('window_suite') else
                              'MOUSE_MOVE' if st.get('mouse_suite') else
                              'GUI_SYNC' if st.get('guisync_suite') else
                              'AUTO_SUITE' if st.get('auto_suite') else
                              'BOOT_DIAGNOSTIC' if st.get('boot_only') else 'COMPLETE'),
                      boot_only=st.get('boot_only'),auto_suite=st.get('auto_suite'),original_win_ini_sha256=original_ini)
    except (GuestError,OSError,ValueError,subprocess.SubprocessError) as exc:
        report.update(error=str(exc),diagnostic=diagnostic(st),failed_phase='KEYBOARD' if st and st.get('keyboard_suite') and keyboard_failure(st) else 'FOUNDATION')
    finally:
        if st:report['process']=st.get('process',{'started':False})
        collect(st,out)
        report['completed_utc']=utcnow()
        (out/'RESULT.JSON').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def run_native(only_target=None, results_root=None):
    if only_target is not None and only_target not in TARGETS:
        raise GuestError('Invalid native target: '+str(only_target))
    selected = ((only_target,) if only_target else
                ('WIN101','WIN200','WIN300') if os.environ.get('NOWBAT_GUISYNC_DEV')=='1' else
                ('WIN101','WIN200','WIN300') if os.environ.get('NOWBAT_STARTSHOT')=='1' else
                ('WIN101','WIN200','WIN300') if os.environ.get('WAS_UAT_AUTOUAT')=='1'
                else AUDIT_ORDER)
    cfg=get_config()
    desktop_mode=('visible' if os.environ.get('NOWBAT_STARTSHOT')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1'
                  else guest_desktop_mode(cfg))
    try:
        trial=os.environ.get('NOWBAT_SNAPFAST_DEV')=='1' or os.environ.get('NOWBAT_GUISYNC_DEV')=='1'
        timeout=int(option(cfg,'runner','timeout','900' if trial else '240' if os.environ.get('NOWBAT_STARTSHOT')=='1' else '180'))
        if not 30<=timeout<=(1800 if trial else 600):raise ValueError()
    except ValueError:raise GuestError('Invalid timeout (30..1800 seconds for SNAPFAST)')
    results=Path(results_root) if results_root else ROOT/'UAT'/'RESULTS'
    if results.exists():shutil.rmtree(str(results))
    reports=[]
    # Keep one per-target report even when a prerequisite is missing.
    try:dosbox=locate_dosbox(cfg)
    except GuestError as exc:
        for target in selected:
            out=results/target;out.mkdir(parents=True)
            row={'target':target,'result':'FAIL','native':'NOT_STARTED','error':str(exc)}
            (out/'RESULT.JSON').write_text(json.dumps(row,indent=2)+'\n')
            reports.append(row)
        return reports
    first_failure=None
    for target in selected:
        if first_failure is not None:
            # These targets were NOT run. Do not misreport them as native FAIL
            # or PASS, but include a complete report so OUTPUT.ZIP explains
            # precisely why there is no evidence for them.
            reason=('AutoUAT' if os.environ.get('WAS_UAT_AUTOUAT')=='1' else 'AUDIT')+' stopped after first native failure: '+first_failure
            row={'target':target,'result':'SKIPPED','native':'NOT_STARTED',
                 'reason':reason,'failed_phase':'NOT_RUN'}
            out=results/target
            out.mkdir(parents=True,exist_ok=True)
            (out/'RESULT.JSON').write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
            print('UAT SKIP',target,reason,flush=True)
            reports.append(row)
            continue
        print('UAT START',target,'(%s desktop, %s staged as TEST.WAS)'%(desktop_mode,'SHOT.WAS' if os.environ.get('NOWBAT_STARTSHOT')=='1' else 'AUTO.WAS' if os.environ.get('WAS_UAT_AUTOUAT')=='1' else 'BOOT.WAS' if os.environ.get('WAS_UAT_BOOT_ONLY')=='1' and target=='WIN200' else 'KEYBOARD.WAS' if os.environ.get('NOWBAT_KEYBOARD_DEV')=='1' else 'INPUT.WAS' if os.environ.get('NOWBAT_INPUT_DEV')=='1' else 'WINDOW.WAS' if os.environ.get('NOWBAT_WINDOW_DEV')=='1' else 'MOUSE.WAS' if os.environ.get('NOWBAT_MOUSE_DEV')=='1' else 'GUISYNC.WAS' if os.environ.get('NOWBAT_GUISYNC_DEV')=='1' else 'TEST.WAS'),flush=True)
        if os.environ.get('NOWBAT_KEYBOARD_DEV')=='1':
            print('KEYBOARD %s: native key transitions and translated characters'%target,flush=True)
        elif os.environ.get('NOWBAT_WINDOW_DEV')=='1':
            print('WINDOW %s: unique fixture caption and client-relative cursor readback'%target,flush=True)
        elif os.environ.get('NOWBAT_MOUSE_DEV')=='1':
            print('MOUSE %s: real USER cursor move and readback'%target,flush=True)
        elif os.environ.get('NOWBAT_GUISYNC_DEV')=='1':
            print(('INPUT %s: native click, drag, double-click and release' if os.environ.get('NOWBAT_INPUT_DEV')=='1' else 'GUISYNC %s: DOEVENTS + WAITFOR existing file + WAITFOR missing timeout + END')%target,flush=True)
        if os.environ.get('NOWBAT_STARTSHOT')=='1':
            print('STARTSHOT %s: WAIT + SNAP + TAR + END (no Windows shutdown)'%target,flush=True)
        elif os.environ.get('NOWBAT_GUISYNC_DEV')!='1':
            print('UAT',target,'Win16 child fixture:', 'YIELD 2s (Win3.0 /r)' if target=='WIN300' else 'NO-YIELD (Win1.01/Win2.03)',flush=True)
        row=(run_target(target,cfg,dosbox,timeout,results_root=results)
             if results_root is not None else run_target(target,cfg,dosbox,timeout))
        if os.environ.get('NOWBAT_KEYBOARD_DEV')=='1':
            print('KEYBOARD %s %s: %s'%(target,row['result'],row.get('error',row.get('keyboard',{}))),flush=True)
        elif os.environ.get('NOWBAT_WINDOW_DEV')=='1':
            print('WINDOW %s %s: %s'%(target,row['result'],row.get('error',row.get('window',{}))),flush=True)
        elif os.environ.get('NOWBAT_MOUSE_DEV')=='1':
            print('MOUSE %s %s: %s'%(target,row['result'],row.get('error',row.get('mouse',{}))),flush=True)
        elif os.environ.get('NOWBAT_GUISYNC_DEV')=='1':
            print('%s %s %s: %s'%('INPUT' if os.environ.get('NOWBAT_INPUT_DEV')=='1' else 'GUISYNC',target,row['result'],row.get('error',row.get('input',row.get('guisync',{})))),flush=True)
        if os.environ.get('NOWBAT_STARTSHOT')=='1':
            bmp=row.get('snapshot',{})
            if row['result']=='UNSUPPORTED':
                print('STARTSHOT %s FAST UNSUPPORTED: BIOS mode 0x%s (COMPAT crop verified, no fallback)'%
                      (target,row.get('bios_mode','unknown')),flush=True)
            elif row['result']=='PASS':
                print('STARTSHOT %s PASS: %sx%s, %s colours, %.2f%% contrasting pixels'%
                      (target,bmp.get('width'),bmp.get('height'),bmp.get('unique_colours'),
                       bmp.get('contrasting_percent',0.0)),flush=True)
            else:
                print('STARTSHOT %s FAIL: %s'%(target,row.get('error','unknown failure')),flush=True)
        elif os.environ.get('NOWBAT_GUISYNC_DEV')!='1':
            print('UAT',row['result'],target,row.get('error','DOS files + WAIT 5000 + desktop BMP4 + TAR + shutdown'),flush=True)
        reports.append(row)
        if row['result']=='UNSUPPORTED' and os.environ.get('NOWBAT_STARTSHOT')=='1':
            print('STARTSHOT continuing remaining targets; unsupported mode recorded',flush=True)
        elif row['result']!='PASS':
            first_failure=(None if os.environ.get('NOWBAT_STARTSHOT') == '1' else target)
            if os.environ.get('NOWBAT_STARTSHOT') == '1':
                print('STARTSHOT continuing remaining targets; failure evidence preserved',flush=True)
            elif os.environ.get('WAS_UAT_AUTOUAT') == '1':
                print('AUTOUAT GUEST FAIL',target,'; stopping native matrix (remaining targets SKIPPED)',flush=True)
            else:
                print('AUDIT NATIVE FAIL-FAST at',target,'; later targets SKIPPED',flush=True)
    return reports
