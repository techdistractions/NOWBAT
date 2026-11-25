#!/usr/bin/env python3
"""WAS host-only NE and runtime-evidence gate. Python 3.9+. No compiler semantics."""
import hashlib
import os
import json
import re
import struct
import iconbuild
import necompact
from audit_modes import NATIVE_MODES
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [('WIN101', 'WIN101', 0, 0x0000), ('WIN300', 'WIN300', 2, 0x0300)]
REQUIRED = {'KERNEL', 'USER', 'GDI'}
# Source of immediate wave deltas: the actual 0.0.26 linked binaries in
# OUTPUT(20261115-110341).ZIP (19462/18568 bytes, 10656 minimum DGROUP).
# That native audit FAILED SHELLWAIT; these values are size baselines only.
# Preserve the 1 KiB EXE growth ceiling; allow up to 10% more DGROUP
# than the qualified size baseline, with an equally expanded release ceiling.
BASELINE = {'WIN101': (19462, 10656), 'WIN300': (18568, 10656)}
MAX_EXE_GROWTH = 1024
# Diagnostic STARTSHOT qualification temporarily permits W054's larger
# binaries, WITHOUT weakening the 20 KiB / +1 KiB PUBLIC RELEASE gate.
# These bounded allowances are for MAKE/targeted native diagnostics only.
MAX_DIAGNOSTIC_EXE = 21 * 1024
MAX_DIAGNOSTIC_GROWTH = 1536
# W081: reserve bounded +9 KiB for composite keyboard development only.
# for explicitly flagged development builds only; release limits unchanged.
MAX_GUI_DEV_GROWTH = 9216
MAX_DGROUP_GROWTH_PERCENT = 10
MAX_RELEASE_EXE = 20 * 1024  # linked NE bytes; validated icon resources are separate
# The previous absolute 11 KiB guard must not negate the 10% allowance.
MAX_RELEASE_DGROUP = (11 * 1024 * (100 + MAX_DGROUP_GROWTH_PERCENT)) // 100

def check_release_image_size(name, file_bytes, linked_size):
    """Enforce 20 KiB linked NE plus the exact validated icon overhead.

    The icon resource and NE alignment must not be mistaken for linked code.
    iconbuild.check_icons and iconbuild.code_size independently verify them.
    """
    if linked_size > MAX_RELEASE_EXE:
        raise ValueError('%s: linked NE exceeds 20 KiB release ceiling (%d > %d)' %
                         (name, linked_size, MAX_RELEASE_EXE))
    expected = linked_size + iconbuild.expected_overhead(name, linked_size)
    if len(file_bytes) != expected:
        raise ValueError('%s: unexpected extra bytes outside validated NE icon (%d != %d)' %
                         (name, len(file_bytes), expected))
    return expected - linked_size


def check_diagnostic_image_size(name, file_bytes, linked_size):
    """Nonrelease gate for MAKE and STARTSHOT. Public release remains strict."""
    # SNAPFAST is a one-time explicitly diagnostic development run. Public
    # release limits and ordinary MAKE2/STARTSHOT limits are unchanged.
    trial = (os.environ.get('NOWBAT_SNAPFAST_DEV') == '1' or
                     os.environ.get('NOWBAT_GUISYNC_DEV') == '1')
    ceiling = 28 * 1024 if trial else MAX_DIAGNOSTIC_EXE
    if linked_size > ceiling:
        raise ValueError('%s: diagnostic linked NE ceiling exceeded (%d > %d bytes)' %
                         (name, linked_size, ceiling))
    expected = linked_size + iconbuild.expected_overhead(name, linked_size)
    if len(file_bytes) != expected:
        raise ValueError('%s: unexpected extra bytes outside validated NE icon (%d != %d)' %
                         (name, len(file_bytes), expected))
    return expected - linked_size


def check_diagnostic_growth(name, linked_size, base_size):
    trial = (os.environ.get('NOWBAT_SNAPFAST_DEV') == '1' or
             os.environ.get('NOWBAT_GUISYNC_DEV') == '1')
    growth_cap = MAX_GUI_DEV_GROWTH if trial else MAX_DIAGNOSTIC_GROWTH
    if linked_size > base_size + growth_cap:
        raise ValueError('%s: DIAGNOSTIC code/link budget exceeded (+%d, cap +%d bytes)' %
                         (name, linked_size-base_size, growth_cap))


def check_terminal_link_parity():
    """Source preflight: three terminal NE modules must import exactly what the
    main NE imports for the same target. A missing RSP import previously
    allowed primary WIN300 linking then failed at NBTEND (E2028).
    """
    for target in ('WIN101', 'WIN300'):
        main_rsp = (ROOT/'LINK'/(target+'.RSP')).read_text(encoding='ascii')
        imports = {line.strip().upper() for line in main_rsp.splitlines()
                   if line.strip().upper().startswith('IMPORT ')}
        if not imports:
            raise ValueError('%s: empty import list' % target)
        for term in ('NBTEND', 'NBTPASS', 'NBTFAIL'):
            path = ROOT/'LINK'/'TERMS'/(target+'_'+term+'.RSP')
            if not path.is_file():
                raise ValueError('Missing terminal link response: '+str(path))
            rsp = path.read_text(encoding='ascii')
            actual = {line.strip().upper() for line in rsp.splitlines()
                      if line.strip().upper().startswith('IMPORT ')}
            if actual != imports:
                missing = sorted(imports-actual)
                extra = sorted(actual-imports)
                raise ValueError('%s %s import mismatch; missing=%r extra=%r' %
                                 (target, term, missing, extra))


def dgroup_growth_limit(baseline_bytes):
    """Integer arithmetic only; never permit >10% growth by rounding up."""
    return (baseline_bytes * MAX_DGROUP_GROWTH_PERCENT) // 100

def check_dgroup_budget(name, allocation, base_data):
    """Enforce both the 10% baseline budget and proportional release ceiling."""
    if allocation > MAX_RELEASE_DGROUP:
        raise ValueError('%s: release DGROUP ceiling exceeded (%d > %d bytes)' %
                         (name, allocation, MAX_RELEASE_DGROUP))
    allowance = dgroup_growth_limit(base_data)
    if allocation > base_data + allowance:
        raise ValueError('%s: DGROUP budget exceeded (+%d, cap +%d bytes / %d%%)' %
                         (name, allocation - base_data,
                          allowance, MAX_DGROUP_GROWTH_PERCENT))
    return allowance
UAT_SUITES = {'COMMAND_TAIL_TEST.WAS', 'SHUTDOWN_DOS_RETURN'}

# The interpreter compares case-insensitively. Older labels deliberately use
# mixed case in their literal storage (e.g. LOGClose), so the static build gate
# must not demand a different, never-linked spelling such as LOGCLOSE. Keep this
# small positive signature gate in addition to the full NE/header/import checks.
REQUIRED_BINARY_COMMANDS = (
    b'SHUTDOWN\0', b'LOGCLOSE\0', b'WAIT\0', b'MKDIR\0',
    b'COPY\0', b'DIR\0', b'SHOWICON=YES\0', b'SHOWICON=NO\0',
    b'SHELLWAIT\0', b'SHELL\0', b'DOEVENTS\0', b'WAITFOR\0', b'MOUSEMOVE\0', b'WINDOWSELECT\0', b'WINDOWFOCUS\0', b'MOUSECLICK\0', b'MOUSEDOWN\0', b'MOUSEUP\0', b'MOUSEDBLCLICK\0', b'RELEASEINPUT\0', b'KEYDOWN\0', b'KEYUP\0', b'KEYPRESS\0',
)

# Win1/2 and Win3 deliberately share the early Win16 USER imports. Keeping
# these exact prevents a build with missing or accidental additional APIs from
# receiving a false STATIC PASS. Only the shutdown ordinal differs by target.
UI_ORDINALS = frozenset({
    ('USER', 1),   # MessageBox
    ('USER', 41),  # CreateWindow
    ('USER', 42),  # ShowWindow
    ('USER', 53),  # DestroyWindow
    ('USER', 57),  # RegisterClass
    ('USER', 107), # DefWindowProc
    ('USER', 109), # PeekMessage
    ('USER', 114), # DispatchMessage
    ('USER', 153), # ChangeMenu
    ('USER', 156), # GetSystemMenu
    ('USER', 174), # LoadIcon
})


def missing_binary_commands(exe_bytes):
    """Reject genuinely absent interpreter tokens, not mixed-case literals."""
    upper = exe_bytes.upper()
    return [token[:-1].decode('ascii') for token in REQUIRED_BINARY_COMMANDS
            if token not in upper]


def required_native_ordinals(target):
    """Exact Win16 NE import footprint: original runtime plus optional UI."""
    ordinals = {('KERNEL', 91), ('KERNEL', 30), ('KERNEL', 29), ('KERNEL',45), ('KERNEL',48),
                ('KERNEL', 3), ('USER', 5), ('USER', 66), ('USER', 68), ('USER', 17), ('USER', 70),
                ('GDI', 80), ('GDI', 83), ('USER', 54), ('USER', 36), ('USER', 47), ('USER', 33), ('USER', 28), ('KERNEL', 51), ('KERNEL', 52), ('KERNEL',47), ('KERNEL',50), ('USER',59), ('USER',60)} | UI_ORDINALS
    # Direct frame-buffer SNAP calls BIOS and I/O ports, not GDI bulk APIs.
    # COMPAT relies on the legacy GDI.83 GetPixel import.
    ordinals |= ({('USER', 7), ('KERNEL', 132), ('USER', 10), ('USER', 12), ('USER', 112), ('USER',337)} if target == 'WIN300'
                 else {('USER', 2)})
    return ordinals

def check_import_contract():
    """Reject stale native import expectations BEFORE assembling either target.

    Keep the independent fixed ordinal whitelist in required_native_ordinals,
    but verify it matches the actual two production linker response files.
    This catches stale GDI ordinal mappings at SOURCE stage, rather than
    producing a MAKE failure after compiling and linking every executable.
    """
    for target in ('WIN101', 'WIN300'):
        rsp = ROOT / 'LINK' / (target + '.RSP')
        actual = set()
        for row in rsp.read_text(encoding='ascii').splitlines():
            line = row.split(';', 1)[0].strip()
            if not line.upper().startswith('IMPORT '):
                continue
            match = re.fullmatch(r'IMPORT\s+[A-Z_][A-Z0-9_]*\s+([A-Z_][A-Z0-9_]*)\.(\d+)', line, re.I)
            if match is None:
                raise ValueError(target + ': malformed native import: ' + line)
            item = (match.group(1).upper(), int(match.group(2)))
            if item in actual:
                raise ValueError(target + ': duplicate native import: ' + line)
            actual.add(item)
        expected = required_native_ordinals(target)
        if actual != expected:
            raise ValueError('%s: linker/native ordinal mismatch; missing=%r extra=%r' %
                             (target, sorted(expected - actual), sorted(actual - expected)))


def u16(data, off):
    return struct.unpack_from('<H', data, off)[0]

def parse_ne(p):
    b = p.read_bytes()
    if len(b) < 128 or b[:2] != b'MZ':
        raise ValueError('missing MZ header')
    ne = struct.unpack_from('<I', b, 0x3c)[0]
    if ne + 64 > len(b) or b[ne:ne + 2] != b'NE':
        raise ValueError('missing NE header')
    t = b[ne + 0x36]
    expver = u16(b, ne + 0x3e)
    flags = u16(b, ne + 0xc)
    segments = u16(b, ne + 0x1c)
    adseg = u16(b, ne + 0xe)
    segtbl = ne + u16(b, ne + 0x22)
    seg_shift = u16(b, ne + 0x32)
    names = ne + u16(b, ne + 0x2a)
    modcnt = u16(b, ne + 0x1e)
    modtab = ne + u16(b, ne + 0x28)
    if not (1 <= segments <= 64 and 1 <= adseg <= segments and 1 <= modcnt <= 16):
        raise ValueError('implausible NE segment/module tables')
    imports = []
    for i in range(modcnt):
        pos = names + u16(b, modtab + i * 2)
        n = b[pos]
        imports.append(b[pos + 1:pos + 1 + n].decode('ascii').upper())
    segs = []
    for i in range(segments):
        off, length, info, minalloc = struct.unpack_from('<HHHH', b, segtbl + i * 8)
        disk_len = length if length else 65536
        segs.append({'offset': off << seg_shift, 'length': disk_len,
                     'minalloc': minalloc or 65536, 'flags': info})
    ordinal_imports = set()
    for seg in segs:
        if not seg['flags'] & 0x100:
            continue
        reloc = seg['offset'] + seg['length']
        for i in range(u16(b, reloc)):
            at = reloc + 2 + i * 8
            kind = b[at+1] & 3
            if kind == 1:
                ordinal_imports.add((imports[u16(b,at+4)-1],u16(b,at+6)))
            elif kind == 2:
                raise ValueError('named imports are not permitted in this ordinal-only Win1 gate')
    return {'size': len(b), 'target': t, 'expected_win_ver': expver,
            'flags': flags, 'imports': imports, 'segments': segs,
            'autodata_minalloc': segs[adseg-1]['minalloc'],
            'entry_ip': u16(b, ne+0x14), 'entry_seg': u16(b, ne+0x16),
            'ordinal_imports': sorted(ordinal_imports),
            'sha256': hashlib.sha256(b).hexdigest()}




def build_files():
    return sorted([p for folder,pattern in [('SRC','*.ASM'),('LINK','*.RSP'),('LINK/TERMS','*.RSP')]
                   for p in (ROOT/folder).glob(pattern)]+[ROOT/'HOST'/'necompact.py', ROOT/'VERSION.TXT',
                   ROOT/'SCRIPT.TXT', ROOT/'DEVELOPMENT.TXT', ROOT/'TESTS'/'TEST.WAS',ROOT/'TESTS'/'WCHILD.ASM', ROOT/'TESTS'/'WGEOM.ASM',
                         *(ROOT/'TESTS'/(kind+'.WAS') for kind in ('AUTO','TEND','TPASS','TFAIL','GUISYNC','MOUSE','WINDOW','INPUT','KEYBOARD'))])


def build_manifest(binary_hashes):
    return {'version':(ROOT/'VERSION.TXT').read_text().strip(),
            'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in build_files()},'binaries':binary_hashes}

def check_proc_structure(name, src):
    """Catch JWASM A2142 unmatched/nested PROC blocks before build."""
    active = None
    for line_number, raw in enumerate(src.splitlines(), 1):
        line = raw.split(';', 1)[0]
        opened = re.match(r'^\s*(\w+)\s+PROC\b', line, re.I)
        closed = re.match(r'^\s*(\w+)\s+ENDP\b', line, re.I)
        if opened:
            if active is not None:
                raise ValueError('%s:%d: nested PROC %s inside %s' %
                                 (name, line_number, opened.group(1), active))
            active = opened.group(1)
        elif closed:
            if active is None or active.upper() != closed.group(1).upper():
                raise ValueError('%s:%d: unmatched ENDP %s (open=%r)' %
                                 (name, line_number, closed.group(1), active))
            active = None
    if active is not None:
        raise ValueError(name + ': PROC not closed: ' + active)


def check_short_loop_reach(name, src):
    """Catch obviously overlong 8086 LOOP/JCXZ backward branches.

    LOOP-family opcodes are ALWAYS rel8; JWASM cannot promote these to near.
    This is a conservative instruction-count gate, not a replacement for JWASM.
    """
    lines = src.splitlines()
    labels = {}
    for i, raw in enumerate(lines):
        code = raw.split(';', 1)[0].strip()
        m = re.match(r'^([A-Za-z_][A-Za-z_0-9]*):(?:\s*.*)?$', code)
        if m:
            labels[m.group(1).upper()] = i
    for i, raw in enumerate(lines):
        code = raw.split(';', 1)[0].strip()
        m = re.match(r'^(LOOP|LOOPE|LOOPNE|LOOPZ|LOOPNZ|JCXZ)\s+([A-Za-z_][A-Za-z_0-9]*)\b', code, re.I)
        if not m or m.group(2).upper() not in labels:
            continue
        dest = labels[m.group(2).upper()]
        lo, hi = sorted((dest, i))
        instr = sum(1 for l in lines[lo+1:hi]
                    if (c := l.split(';', 1)[0].strip())
                    and not c.endswith(':') and not c.lower().startswith(('db ', 'dw ', 'dd ')))
        if instr > 35:
            raise ValueError('%s:%d: potentially out-of-range 8086 %s to %s (%d intervening instructions); use DEC CX + JZ + JMP' %
                             (name, i+1, m.group(1).upper(), m.group(2), instr))


def check_source():
    names = ['WAS.ASM','WASTAR.ASM','WASSNAP.ASM','WASFS.ASM','WASUI.ASM']
    joined = ''
    for name in names:
        src = (ROOT / 'SRC' / name).read_text(encoding='ascii')
        if name == 'WAS.ASM' and not all(term in src for term in
             ("cmdSHUTDOWN  db 'SHUTDOWN',0", 'commandShutdown:', 'wasHasScriptArg:', 'wasOpenScript:')):
            raise ValueError('WAS.ASM missing explicit command-line or SHUTDOWN support')
        if not re.search(r'^\s*\.8086\b', src, re.I | re.M):
            raise ValueError(name + ' missing explicit .8086')
        for lineno, line in enumerate(src.splitlines(), 1):
            line = line.split(';', 1)[0]
            if re.search(r'\b(?:PUSHA|POPA|ENTER|LEAVE|MOVZX|MOVSX|BSWAP|PUSHAD|POPAD|EAX|EBX|ECX|EDX|ESI|EDI|FS|GS)\b', line, re.I):
                raise ValueError('%s:%d: non-8086 feature: %s' % (name, lineno, line))
        check_proc_structure(name, src)
        check_short_loop_reach(name, src)
        # Byte-register comparisons accept a single-character literal only.
        # MASM does not use C escape rules: '\\' is TWO characters and
        # yields JWASM A2048 (byte-versus-word size mismatch).
        for lineno, line in enumerate(src.splitlines(), 1):
            clean = line.split(';', 1)[0]
            if re.search(r"\bcmp\s+(?:al|ah|bl|bh|cl|ch|dl|dh)\s*,\s*'[^']{2,}'", clean, re.I):
                raise ValueError('%s:%d: multi-character immediate in 8-bit comparison' % (name, lineno))
        joined += src
    core=(ROOT/'SRC'/'WAS.ASM').read_text(encoding='ascii')
    if "traceBuild     db 'NOWBAT_BUILD=W054'" not in core:
        raise ValueError('WAS.ASM missing W054 startup identity')
    for token in ('extrn GetModuleUsage:far','call LoadModule','call GetModuleUsage',
                  'commandShellNoWait:', 'commandShellWait:', 'wasWindowsWait:', 'commandEnd:', 'commandPass:', 'commandFail:'):
        if token not in core:
            raise ValueError('WAS.ASM missing Windows-only SHELL contract: '+token)
    if 'WASRUN.COM' in core or 'INCBIN <BUILD/WASRUN.BIN>' in core or (ROOT/'SRC'/'WASRUN.ASM').exists():
        raise ValueError('Obsolete DOS EXEC bridge must not be in WAS runtime')
    fixture=(ROOT/'TESTS'/'WCHILD.ASM').read_text(encoding='ascii')
    if not all(x in fixture for x in ('InitTask','InitApp','Yield','WCHILD.OK','int 21h','.8086')):
        raise ValueError('Independent Win16 child fixture incomplete')
    check_proc_structure('WCHILD.ASM',fixture)
    check_short_loop_reach('WCHILD.ASM',fixture)
    geometry=(ROOT/'TESTS'/'WGEOM.ASM').read_text(encoding='ascii')
    if not all(x in geometry for x in ('.8086','CreateWindow','GetClientRect','ClientToScreen','WGEOM.DAT','GetMessage','int 21h')):
        raise ValueError('Independent window geometry fixture incomplete')
    check_proc_structure('WGEOM.ASM',geometry)
    check_short_loop_reach('WGEOM.ASM',geometry)
    if re.search(r'wasIfMatch:\s*cmp bl,1\s*cmp bl,1', joined, re.I):
        raise ValueError('IF EQ compares a constant against itself, making EQ always true')
    for label in ('TarCreate proc', 'TarAdd proc', 'TarClose proc', 'SnapDo proc',
                  'cmdEXISTS', 'cmdASSERT', 'commandExists:', 'commandAssert:', 'FsCopy proc', 'FsDir proc', 'FsBinary proc', 'start:'):
        if label.lower() not in joined.lower():
            raise ValueError('missing handler: ' + label)
    # Mandatory opt-in UI: test static Win16 API contracts without a GUI
    # fixture. Native menu interaction remains a separate UAT qualification.
    ui = (ROOT/'SRC'/'WASUI.ASM').read_text(encoding='ascii').upper()
    core = (ROOT/'SRC'/'WAS.ASM').read_text(encoding='ascii').upper()
    expected_about_version = 'VERSION: ' + (ROOT/'VERSION.TXT').read_text(encoding='ascii').strip().upper()
    for token in ('UIOPEN PROC', 'UICLOSE PROC', 'UIPUMP PROC',
                  'UIWNDPROC PROC FAR', 'CALL MESSAGEBOX',
                  'CALL GETSYSTEMMENU', 'CALL CHANGEMENU',
                  'NOWBAT - WINDOWS ADMIN SCRIPT', expected_about_version):
        if token not in ui:
            raise ValueError('WASUI missing UI contract: '+token)
    for token in ('CMDSHOWICONYES', 'CMDSHOWICONNO', 'CALL UIOPEN', 'CALL UICLOSE'):
        if token not in core:
            raise ValueError('WAS missing ShowIcon command: '+token)
    # The source tree, not memory of a conversation, owns the rules. A new
    # command is not delivered without its reference and engineering policy.
    script = (ROOT/'SCRIPT.TXT').read_text(encoding='ascii').upper()
    rules = (ROOT/'DEVELOPMENT.TXT').read_text(encoding='ascii').upper()
    for cmd in ('COPY','MOVE','REN','DEL','MKDIR','RMDIR','CHDIR','DIR','PWD',
                'EXISTS','ASSERT','WAIT','SNAP','TARCREATE','SHUTDOWN','SHOWICON','SHELL','SHELLWAIT','DOEVENTS','WAITFOR','MOUSEMOVE','WINDOWSELECT','WINDOWFOCUS','MOUSECLICK','MOUSEDOWN','MOUSEUP','MOUSEDBLCLICK','RELEASEINPUT','KEYDOWN','KEYUP','KEYPRESS'):
        if ('COMMAND: '+cmd) not in script:
            raise ValueError('SCRIPT.TXT missing command reference: '+cmd)
    for req in ('8088', 'DGROUP', 'SCRIPT.TXT', 'JWASM', 'NBJWLINK'):
        if req not in rules:
            raise ValueError('DEVELOPMENT.TXT missing build rule: '+req)
    check_terminal_link_parity()
    check_import_contract()
    print('PASS SOURCE 8086 / balanced PROC-ENDP / core handlers / native and terminal imports match')

def run_selftest(startshot=False,guisync=False,mouse=False,window=False,input_dev=False,keyboard=False):
    """Run host regressions with isolated mode flags, before guest staging.

    The broad SELFTEST.PY fixture always uses TEST.WAS. STARTSHOT is tested
    separately; its flag must never cause that synthetic tree to request
    SHOT.WAS, which the broad fixture deliberately does not contain.
    """
    print('AUDIT STAGE: HOST SELFTEST', flush=True)
    # The ordinary host self-test asserts the standard 50s startup watchdog.
    # SNAPFAST temporarily uses a 300s native guest budget at 750 cycles,
    # so isolate only the self-test subprocess from that trial override.
    # Do NOT clear the flag from the parent environment: the native runner
    # still needs BPP=1, 750 cycles and the longer boot allowance.
    selftest_env = os.environ.copy()
    for flag in ('WAS_UAT_BOOT_ONLY', 'WAS_UAT_AUTOUAT', 'NOWBAT_STARTSHOT',
                 'NOWBAT_SNAPFAST_DEV', 'NOWBAT_GUISYNC_DEV', 'NOWBAT_MOUSE_DEV','NOWBAT_WINDOW_DEV','NOWBAT_INPUT_DEV','NOWBAT_KEYBOARD_DEV'):
        selftest_env.pop(flag, None)
    suites = [] if guisync or mouse or window or input_dev or keyboard else [('SELFTEST.PY', 'host selftest')]
    if startshot:
        suites.append(('STARTSHOT_HOST.PY', 'STARTSHOT host preflight'))
    if guisync:
        suites.extend([('GUISYNC_HOST.PY', 'GUISYNC source preflight'),
                       ('GUISYNC_AUDIT_HOST.PY', 'GUISYNC audit evidence preflight')])
    if mouse:
        suites.append(('MOUSE_HOST.PY', 'MOUSE source and audit preflight'))
    if input_dev:
        suites.extend([('DISPATCH_HOST.PY','audit dispatch and cleanup regression'),
                       ('INPUT_HOST.PY','INPUT source and evidence preflight')])
    if keyboard:
        suites.extend([('DISPATCH_HOST.PY','audit dispatch and cleanup regression'),
                       ('KEYBOARD_HOST.PY', 'KEYBOARD source and evidence preflight')])
    if window:
        suites.append(('WINDOW_HOST.PY','WINDOW source and audit preflight'))
    for filename, label in suites:
        proc = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'TESTS' / filename)],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors='replace', env=selftest_env)
        if proc.stdout:
            print(proc.stdout.rstrip(), flush=True)
        if proc.returncode:
            raise ValueError('%s failed (exit %d)' % (label, proc.returncode))
    print('AUDIT HOST SELFTEST=PASS', flush=True)


def report_native(mode, reports, gui_target="", fast_target="", fast_trial=False):
    """Finalize one native audit mode after common status/hash validation."""
    # Full qualification requires all three real guest launches.
    # A targeted pass must be prominently labelled as a diagnostic.
    if mode == 'KEYBOARD':
        requested = {gui_target} if gui_target else {'WIN101','WIN200','WIN300'}
        if {r['target'] for r in reports} != requested or len(reports)!=len(requested): raise ValueError('KEYBOARD missing or duplicate guest')
        for r in reports:
            if r.get('native')!='NATIVE_KEYBOARD_INPUT' or any(r.get('keyboard',{}).get(k)!='PASS' for k in ('recovery','combo','type')): raise ValueError('KEYBOARD missing native witness')
            print('KEYBOARD_NATIVE %s: %s'%(r['target'],r['keyboard']),flush=True)
    elif mode == 'INPUT':
        requested = {gui_target} if gui_target else {'WIN101','WIN200','WIN300'}
        if {r['target'] for r in reports} != requested or len(reports)!=len(requested): raise ValueError('INPUT missing or duplicate guest')
        for r in reports:
            if r.get('native')!='NATIVE_MOUSE_INPUT' or r.get('input',{}).get('drag')!='PASS': raise ValueError('INPUT missing native input witness')
            print('INPUT_NATIVE %s: %s'%(r['target'],r['input']),flush=True)
        print('INPUT_MOUSE_PASS: %d native guest(s)'%len(reports),flush=True)
    elif mode == 'WINDOW':
        requested = {gui_target} if gui_target else {'WIN101','WIN200','WIN300'}
        if {r['target'] for r in reports} != requested or len(reports) != len(requested):
            raise ValueError('WINDOW missing or unexpected native guest')
        for r in reports:
            if r.get('native')!='WINDOW_GEOMETRY' or not r.get('window') or r['window'].get('invalid')!='PASS' or r['window'].get('missing')!='PASS' or r['window'].get('waitfor_found')!='PASS' or r['window'].get('waitfor_timeout')!='PASS':
                raise ValueError('WINDOW missing native geometry witness: '+r['target'])
            print('WINDOW_NATIVE %s: %s'%(r['target'],r['window']),flush=True)
        print('WINDOW_DIAGNOSTIC_PASS: %d native guest(s); no button/keyboard input claimed'%len(reports),flush=True)
    elif mode == 'MOUSE':
        requested = {gui_target} if gui_target else {'WIN101','WIN200','WIN300'}
        if {r['target'] for r in reports} != requested or len(reports) != len(requested):
            raise ValueError('MOUSE missing or unexpected native guest')
        for r in reports:
            if r.get('native') != 'MOUSE_MOVE' or r.get('mouse') != {'first':[40,50],'second':[120,100],'invalid':'PASS'}:
                raise ValueError('MOUSE missing native cursor witness: '+r['target'])
            print('MOUSE_NATIVE %s: 40,50 -> 120,100; invalid argument PASS'%r['target'],flush=True)
        print('MOUSE_DIAGNOSTIC_PASS: %d native guest(s); cursor positioning only'%len(reports),flush=True)
    elif mode == 'GUISYNC':
        requested = {gui_target} if gui_target else {'WIN101','WIN200','WIN300'}
        if {r['target'] for r in reports} != requested or len(reports) != len(requested):
            raise ValueError('GUISYNC missing or unexpected native guest: '+repr(reports))
        for r in reports:
            if r.get('native') != 'GUI_SYNC' or not r.get('guisync'):
                raise ValueError('GUISYNC missing closed native witness: '+r['target'])
            print('GUISYNC_NATIVE %s: DOEVENTS=PASS WAITFOR_FOUND=PASS WAITFOR_TIMEOUT=PASS timeout_seconds=%s' %
                  (r['target'], r['guisync'].get('timeout_seconds')),flush=True)
        print('GUISYNC_DIAGNOSTIC_PASS: %d native guest(s); no GUI input injection claimed' % len(reports),flush=True)
    elif mode == 'STARTSHOT':
        if fast_target:
            if len(reports)!=1 or reports[0]['target'] != fast_target:
                raise ValueError('SNAPFAST targeted diagnostic requires the selected guest')
        elif len(reports)!=3 or {r['target'] for r in reports}!={'WIN101','WIN200','WIN300'}:
            raise ValueError('STARTSHOT requires all three distinct Windows guests')
        for r in reports:
            if fast_trial and r['result']=='UNSUPPORTED':
                if (r.get('native')!='STARTSHOT_UNSUPPORTED' or
                    r.get('reason')!='BIOS_MODE_UNSUPPORTED' or
                    not r.get('bios_mode') or not r.get('compat_crop_bytes') or
                    not r.get('warmup')):
                    raise ValueError('SNAPFAST unsupported result lacks complete evidence for '+r['target'])
                continue
            if r.get('native')!='STARTSHOT' or not r.get('snapshot') or not r.get('warmup'):
                raise ValueError('STARTSHOT missing native pixel/warmup evidence for '+r['target'])
        if os.environ.get('NOWBAT_SNAPFAST_DEV') == '1':
            supported=0
            unsupported=0
            for r in reports:
                target=r['target']
                if r['result']=='UNSUPPORTED':
                    unsupported+=1
                    print('SNAPFAST_NATIVE %s method=UNSUPPORTED bios_mode=0x%s cycles=750 COMPAT_CROP=YES' %
                          (target,r['bios_mode']),flush=True)
                    print('SNAPFAST_BENCH %s safe_crop_guest_seconds=%s fast_guest_seconds=%s (1s clock precision)' %
                          (target,r.get('snap_safe_guest_seconds'),r.get('snap_fast_guest_seconds')),flush=True)
                    continue
                supported+=1
                trace_file=ROOT/'UAT'/'RESULTS'/target/'EARLY.LOG'
                if not trace_file.is_file():
                    raise ValueError('SNAPFAST missing native method witness: '+target)
                evidence=trace_file.read_text(encoding='ascii',errors='replace')
                expected='SNAP_METHOD=VIDEO_DIRECT'
                if expected not in evidence:
                    raise ValueError('SNAPFAST did not use the direct frame-buffer path on '+target+'; trace='+repr(evidence[-400:]))
                if r.get('snapshot',{}).get('bpp') not in (1,4):
                    raise ValueError('SNAPFAST did not preserve native desktop 1/4-bpp output: '+target)
                print('SNAPFAST_NATIVE %s method=VIDEO_DIRECT cycles=750 capture_seconds=%s nonblank=YES TAR=YES' %
                      (target,r.get('capture_seconds','not-recorded')),flush=True)
                print('SNAPFAST_BENCH %s safe_crop_guest_seconds=%s fast_guest_seconds=%s (1s clock precision)' %
                      (target,r.get('snap_safe_guest_seconds'),r.get('snap_fast_guest_seconds')),flush=True)
            if not supported:
                raise ValueError('SNAPFAST no supported FAST captures; all targets unsupported')
            if unsupported:
                print('SNAPFAST_DIAGNOSTIC_PARTIAL: %d direct captures, %d explicitly unsupported BIOS modes; unsupported targets NOT qualified' %
                      (supported,unsupported),flush=True)
            else:
                print('SNAPFAST_NATIVE_PASS: video-direct capture on all three Windows guests',flush=True)
        if not any(r['result']=='UNSUPPORTED' for r in reports):
            print('STARTSHOT_DIAGNOSTIC_PASS: real full-desktop BMPs on all three targets',flush=True)
        else:
            print('STARTSHOT_DIAGNOSTIC_PARTIAL: unsupported targets did not produce full-screen BMPs',flush=True)
    elif mode == 'FULL':
        if any(r.get('boot_only') for r in reports):
            raise ValueError('BOOT diagnostic cannot qualify FULL audit')
        if len(reports) != 3 or {r['target'] for r in reports} != {'WIN101', 'WIN200', 'WIN300'}:
            raise ValueError('FULL audit requires all three distinct Windows guests')
        print('AUDIT NATIVE=PASS (WIN300, WIN200, WIN101)', flush=True)
    else:
        if len(reports) != 1 or reports[0]['target'] != mode:
            raise ValueError('Targeted audit requires exactly one report for '+mode)
        print('AUDIT NATIVE=DIAGNOSTIC_PASS (%s %s; full qualification pending)' %
              (mode,'BOOT-ONLY' if reports[0].get('boot_only') else 'ONLY'),flush=True)


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else 'FULL').upper()
    if mode == 'INPUTABI':
        # No build, emulator, or stale native results in this inventory.
        results = ROOT / 'UAT' / 'RESULTS'
        if results.exists():
            shutil.rmtree(str(results))
        import inputabi
        inputabi.run(ROOT)
        return
    # SOURCE and STATIC are internal MAKE stages, not separate operator steps.
    native_modes = NATIVE_MODES
    if mode not in ('SOURCE', 'STATIC') + native_modes:
        raise ValueError('Use AUDIT [WIN300|WIN200|WIN101|ALL|STARTSHOT|GUISYNC|MOUSE|WINDOW|INPUT|KEYBOARD]; internal stages: SOURCE/STATIC')
    if mode in native_modes:
        # Fail closed: never leave a previous invocation's guest PASS report.
        results = ROOT / 'UAT' / 'RESULTS'
        if results.exists():
            shutil.rmtree(str(results))
    print('AUDIT STAGE: SOURCE', flush=True)
    check_source()
    if mode == 'SOURCE':
        for test in ('NECOMPACT_HOST.PY','REGRESSION_HOST.PY'):
            subprocess.run([sys.executable, '-B', str(ROOT/'TESTS'/test)], check=True)
        print('AUDIT_SOURCE=PASS')
        return
    if mode in native_modes:
        run_selftest(startshot=(mode == 'STARTSHOT'),guisync=(mode == 'GUISYNC'),mouse=(mode == 'MOUSE'),window=(mode=='WINDOW'),input_dev=(mode=='INPUT'),keyboard=(mode=='KEYBOARD'))
    print('AUDIT STAGE: STATIC NE', flush=True)
    target_filter = os.environ.get('WAS_AUDIT_TARGET', 'ALL').upper()
    selected = TARGETS if mode in native_modes or target_filter == 'ALL' else [
        x for x in TARGETS if x[0] == target_filter]
    if not selected:
        raise ValueError('invalid WAS_AUDIT_TARGET: ' + target_filter)
    binary_hashes = {}
    for name, path, target, expver in selected:
        exe_path = ROOT / 'DIST' / path / 'NOWBAT.EXE'
        if not exe_path.is_file():
            raise ValueError(name + ': missing binary: ' + str(exe_path))
        missing = missing_binary_commands(exe_path.read_bytes())
        if missing:
            raise ValueError(name + ': NE missing required interpreter command(s): '
                             + ', '.join(missing) + '; run MAKE ALL')
        # Stale W029/W028 runtime binaries cannot pass a W054 source gate.
        if b'NOWBAT_BUILD=W054\x00' not in exe_path.read_bytes():
            raise ValueError(name + ': missing W054 resident runtime marker; run MAKE ALL from active WAS folder')
        n = parse_ne(exe_path)
        if n['target'] != target or n['expected_win_ver'] != expver:
            raise ValueError('%s: header mismatch target=%02X expver=%04X' %
                             (name, n['target'], n['expected_win_ver']))
        if n['flags'] & 0x0008 or n['flags'] & 0x0060:
            raise ValueError(name + ': protected-mode / 286+ requirement')
        if set(n['imports']) != REQUIRED:
            raise ValueError(name + ': unexpected imports: ' + str(n['imports']))
        # Linking only USER.7 on Win3 avoids unresolved imports on Win1/2.
        # Validate source and link policy; the NE parser verifies module names.
        source_rsp = (ROOT / 'LINK' / (name + '.RSP')).read_text(encoding='ascii')
        required_fn = 'IMPORT ExitWindows USER.7' if name == 'WIN300' else 'IMPORT OldExitWindows USER.2'
        if required_fn not in source_rsp:
            raise ValueError(name + ': incorrect shutdown API import')
        # 0.0.23's opt-in icon needs 11 more USER ordinals. The original
        # headless-only expected list rejected the correctly linked executable.
        if set(map(tuple, n['ordinal_imports'])) != required_native_ordinals(name):
            raise ValueError(name + ': incorrect native ordinal imports: '
                             + repr(n['ordinal_imports']))
        base_size,base_data=BASELINE[name]
        file_bytes = exe_path.read_bytes()
        iconbuild.check_icons(file_bytes, name)
        saved = necompact.check_packed(file_bytes)
        print('PASS DGROUP zero arena %s: %d bytes off disk' % (name, saved), flush=True)
        # Real NE linked bytes exclude the independently validated icon.
        # Release qualification keeps the original 20 KiB / +1 KiB limits.
        # W082 enforces the original strict size gate at MAKE STATIC as well.
        linked_size = iconbuild.code_size(file_bytes, name)
        if mode in ('FULL', 'STATIC'):
            icon_overhead = check_release_image_size(name, file_bytes, linked_size)
            if linked_size>base_size+MAX_EXE_GROWTH:
                raise ValueError('%s: RELEASE EXE code/link budget exceeded (+%d, cap +%d bytes)' %
                                 (name,linked_size-base_size,MAX_EXE_GROWTH))
        else:
            icon_overhead = check_diagnostic_image_size(name, file_bytes, linked_size)
            check_diagnostic_growth(name, linked_size, base_size)
            if linked_size>MAX_RELEASE_EXE or linked_size>base_size+MAX_EXE_GROWTH:
                print('WARN RELEASE_SIZE_PENDING %s linked=%d bytes growth=+%d bytes; release limits: %d / +%d' %
                      (name,linked_size,linked_size-base_size,MAX_RELEASE_EXE,MAX_EXE_GROWTH),flush=True)
        check_dgroup_budget(name, n['autodata_minalloc'], base_data)
        print('SIZE %s: EXE %+d bytes, DGROUP %+d bytes vs qualified 0.0.22' %
              (name,n['size']-base_size,n['autodata_minalloc']-base_data),flush=True)
        binary_hashes[name] = n['sha256']
        print('PASS NE', name, '%d bytes (linked %d + icon %d)' % (n['size'], linked_size, icon_overhead), 'DGROUP=%d' % n['autodata_minalloc'],
              'modules=' + ','.join(n['imports']), 'sha256=' + n['sha256'][:12], flush=True)
    # Independent Windows child fixture is also built fresh by MAKE.
    for kind in ('WCHILD','WWAIT'):
        child=ROOT/'BUILD'/(kind+'.EXE')
        if not child.is_file():raise ValueError('Missing freshly linked '+kind+'.EXE')
        cn=parse_ne(child)
        if cn['target']!=0 or cn['size']>8192 or cn['size']<100 or set(cn['imports'])!={'KERNEL','USER'}:
            raise ValueError('Invalid Windows 1.x-compatible Win16 '+kind+' fixture')
        if set(map(tuple,cn['ordinal_imports']))!={('KERNEL',91),('KERNEL',30),('KERNEL',29),('KERNEL',3),('USER',5)}:
            raise ValueError('Incorrect imports in '+kind+'.EXE')
        binary_hashes[kind]=cn['sha256']
        print('PASS WIN16 CHILD',kind, cn['size'],'bytes',flush=True)
    fixture=ROOT/'BUILD'/'WGEOM.EXE'
    if not fixture.is_file(): raise ValueError('Missing freshly linked WGEOM.EXE')
    fn=parse_ne(fixture)
    fimports={('KERNEL',91),('KERNEL',30),('USER',5),('USER',57),('USER',41),('USER',42),('USER',33),('USER',28),('USER',108),('USER',113),('USER',114),('USER',107),('USER',6),('USER',66),('USER',68),('GDI',33)}
    if fn['target']!=0 or fn['size']>8192 or set(map(tuple,fn['ordinal_imports']))!=fimports:
        raise ValueError('Invalid Windows 1.x native WGEOM fixture')
    binary_hashes['WGEOM']=fn['sha256']
    print('PASS WIN16 CHILD WGEOM',fn['size'],'bytes',flush=True)
    # AutoUAT terminal modules must match this exact 8086 build. They are
    # independent NE modules so Win1 never waits on a reused module handle.
    for target, _, expected_target, expected_version in selected:
        for terminal in ('NBTEND', 'NBTPASS', 'NBTFAIL'):
            path = ROOT/'BUILD'/'TERMS'/target/(terminal+'.EXE')
            if not path.is_file():
                raise ValueError('AutoUAT terminal binary missing: '+str(path))
            ne = parse_ne(path)
            if (ne['target'], ne['expected_win_ver']) != (expected_target, expected_version):
                raise ValueError('Wrong terminal NE target: '+str(path))
            if set(map(tuple,ne['ordinal_imports'])) != required_native_ordinals(target):
                raise ValueError('Wrong terminal import ordinals: '+str(path))
            necompact.check_packed(path.read_bytes())
            if b'NOWBAT_BUILD=W054\x00' not in path.read_bytes():
                raise ValueError('Stale AutoUAT terminal build: '+str(path))
            binary_hashes[target+':'+terminal] = ne['sha256']
            print('PASS TERMINAL MODULE',target,terminal,flush=True)
    print('AUDIT STATIC=PASS', flush=True)
    manifest_path=ROOT/'BUILD'/'MANIFEST.JSON'
    current=build_manifest(binary_hashes)
    if mode=='STATIC':
        manifest_path.write_text(json.dumps(current,indent=2)+'\n',encoding='utf-8')
    if mode in native_modes:
        if not manifest_path.is_file() or json.loads(manifest_path.read_text())!=current:
            raise ValueError('Sources/binaries changed since MAKE ALL; rebuild before AUDIT')
        if mode == 'STARTSHOT':
            os.environ['NOWBAT_STARTSHOT']='1'
            os.environ['WAS_UAT_DESKTOP']='visible'
            print('AUDIT STAGE: STARTSHOT - WIN101/WIN200/WIN300, visible + 10s warmup + END (no SHUTDOWN)',flush=True)
        if mode in ('GUISYNC','MOUSE','WINDOW','INPUT','KEYBOARD'):
            if mode == 'KEYBOARD': os.environ['NOWBAT_KEYBOARD_DEV']='1'
            if mode == 'INPUT': os.environ['NOWBAT_INPUT_DEV']='1'
            if mode == 'WINDOW': os.environ['NOWBAT_WINDOW_DEV']='1'
            if mode == 'MOUSE': os.environ['NOWBAT_MOUSE_DEV']='1'
            os.environ['NOWBAT_GUISYNC_DEV']='1'
            os.environ['WAS_UAT_DESKTOP']='visible'
            print('AUDIT STAGE: KEYBOARD - native keystrokes, chords, TYPE and modifier recovery' if mode=='KEYBOARD' else 'AUDIT STAGE: INPUT - native mouse events and drag witnesses' if mode=='INPUT' else 'AUDIT STAGE: WINDOW - native WAITFOR WINDOW and client-relative geometry on 750 cycles' if mode=='WINDOW' else 'AUDIT STAGE: MOUSE - native cursor positioning and readback on 750 cycles' if mode=='MOUSE' else 'AUDIT STAGE: GUISYNC - native headless DOEVENTS + WAITFOR FILE (pass + timeout) on 750 cycles',flush=True)
        if mode == 'FULL':
            print('AUDIT STAGE: WIN300 / WIN200 / WIN101 WAIT+DESKTOP BMP4+TAR+SHUTDOWN', flush=True)
        elif mode not in ('STARTSHOT','GUISYNC','MOUSE','WINDOW','INPUT','KEYBOARD'):
            print('AUDIT STAGE: %s ONLY - DIAGNOSTIC; not full release qualification' % mode, flush=True)
        import runuat
        try:
            fast_target = os.environ.get('NOWBAT_SNAPFAST_TARGET','').upper() if mode == 'STARTSHOT' else ''
            gui_target = os.environ.get('NOWBAT_GUISYNC_TARGET','').upper() if mode in ('GUISYNC','MOUSE','WINDOW','INPUT','KEYBOARD') else ''
            reports = runuat.run_native(only_target=(gui_target or fast_target or None)
                if mode in ('FULL','STARTSHOT','GUISYNC','MOUSE','WINDOW','INPUT','KEYBOARD') else mode)
        except runuat.GuestError as exc:
            raise ValueError(str(exc))
        fast_trial = mode == 'STARTSHOT' and os.environ.get('NOWBAT_SNAPFAST_DEV') == '1'
        failed = [r for r in reports if r['result'] != 'PASS' and
                  not (fast_trial and r['result'] == 'UNSUPPORTED')]
        if failed:
            raise ValueError('native guest UAT failure: ' + '; '.join(
                r['target'] + ': ' + (r.get('error') or r.get('reason') or 'unknown')
                for r in failed))
        for r in reports:
            binary = 'WIN300' if r['target'] == 'WIN300' else 'WIN101'
            if r.get('exe_sha256') != binary_hashes[binary]:
                raise ValueError(r['target'] + ': guest binary hash not current')
        report_native(mode, reports, gui_target, fast_target, fast_trial)
    print('AUDIT_%s=PASS' % mode, flush=True)

if __name__ == '__main__':
    status=0
    error=None
    try:
        main()
    except (ValueError, OSError, RuntimeError, IndexError, AssertionError, struct.error, subprocess.SubprocessError) as exc:
        print('AUDIT=FAIL:', exc, flush=True)
        status=1
        error=str(exc) or type(exc).__name__
    finally:
        if (sys.argv[1] if len(sys.argv)>1 else 'FULL').upper() in ('FULL', 'WIN101', 'WIN200', 'WIN300', 'GUISYNC', 'MOUSE','WINDOW','INPUT','KEYBOARD'):
            rows=[]
            for target in ('WIN101','WIN200','WIN300'):
                p=ROOT/'UAT'/'RESULTS'/target/'RESULT.JSON'
                if p.is_file():rows.append(json.loads(p.read_text(encoding='utf-8')))
            mode=(sys.argv[1] if len(sys.argv)>1 else 'FULL').upper()
            report={'version':(ROOT/'VERSION.TXT').read_text().strip(),
                    'result':('PASS' if mode=='FULL' else 'DIAGNOSTIC_PASS') if status==0 else 'FAIL',
                    'mode':mode, 'full_native_qualification':bool(status==0 and mode=='FULL'),
                    'error':error,
                    'scope':('Native KEYBOARD events and modifier recovery' if mode=='KEYBOARD' else 'Native INPUT mouse clicks, drag and release' if mode=='INPUT' else 'Native WAITFOR WINDOW, exact caption and relative cursor geometry' if mode=='WINDOW' else 'Native MOUSE absolute cursor readback and invalid argument' if mode=='MOUSE' else 'Native GUISYNC DOEVENTS and WAITFOR FILE with 700ms timeout' if mode=='GUISYNC'
                             else ('ALL 3' if mode=='FULL' else mode+' ONLY')+
                             (' BOOT-only' if os.getenv('WAS_UAT_BOOT_ONLY')=='1'
                              else ' native EXISTS/ASSERT + WAIT 5000 + desktop BMP4 + TAR + SHUTDOWN/DOS return')),
                    'guests':rows}
            (ROOT/'BUILD'/'RESULT.JSON').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    sys.exit(status)
