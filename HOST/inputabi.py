#!/usr/bin/env python3
"""W070 read-only NE export inventory for genuine Win16 input pathways.
No calls into USER, no driver modification, no code bytes in report.
A named export/ordinal is a candidate, NOT a qualified calling convention.
"""
import hashlib
import json
import struct
from pathlib import Path
import runuat

MODULES = {'USER', 'KERNEL', 'MOUSE', 'KEYBOARD', 'SYSTEM'}
USER_CANDIDATES = (17, 70, 289, 299)
INTEREST = ('MOUSE','KEYBD','KEYBOARD','KEYSTATE','HOOK','JOURNAL','EVENT',
            'CURSOR','GETPROCADDRESS','GETMODULEHANDLE','INPUT')

def u16(data, pos):
    return struct.unpack_from('<H', data, pos)[0]

def u32(data, pos):
    return struct.unpack_from('<I', data, pos)[0]

def names(data, pos, end):
    result = []
    if not 0 <= pos < end <= len(data):
        raise ValueError('invalid name table range')
    while pos < end:
        n = data[pos]; pos += 1
        if n == 0:
            return result
        if pos + n + 2 > end:
            raise ValueError('truncated name table')
        raw = data[pos:pos+n]
        if any(c < 32 or c >= 127 for c in raw):
            raise ValueError('non-ASCII export name')
        result.append((raw.decode('ascii'), u16(data,pos+n)))
        pos += n+2
    raise ValueError('name table missing terminator')

def entry_table(data, pos, end, nseg):
    result = {}; ordinal = 1
    if not 0 <= pos < end <= len(data):
        raise ValueError('invalid entry table range')
    while pos < end:
        n = data[pos]; pos += 1
        if not n:
            return result
        if pos >= end:
            raise ValueError('truncated entry bundle')
        seg = data[pos]; pos += 1
        if seg == 0:
            ordinal += n
            continue
        if seg != 255 and seg > nseg:
            raise ValueError('invalid fixed segment')
        size = 6 if seg == 255 else 3
        if pos+n*size > end:
            raise ValueError('truncated entry bundle')
        for _ in range(n):
            flags = data[pos]
            if seg == 255:
                actual_seg = data[pos+3]; offset = u16(data,pos+4)
                if not 1 <= actual_seg <= nseg:
                    raise ValueError('invalid movable segment')
            else:
                actual_seg = seg; offset = u16(data,pos+1)
            result[ordinal] = {'segment':actual_seg, 'offset':offset,
                               'flags':flags}
            ordinal += 1; pos += size
    raise ValueError('entry table missing terminator')

def parse_header(data, h, standalone):
    if h < 0 or h+0x40 > len(data) or data[h:h+2] != b'NE':
        return None
    er, es = u16(data,h+4), u16(data,h+6)
    nseg = u16(data,h+0x1c)
    rr, mr = u16(data,h+0x26), u16(data,h+0x28)
    if not (0 < nseg <= 1024 and 0x40 <= rr < mr and h+mr <= len(data)):
        return None
    try:
        resident = names(data,h+rr,h+mr)
    except ValueError:
        return None
    if not resident or resident[0][1] != 0 or resident[0][0].upper() not in MODULES:
        return None
    module = resident[0][0].upper()
    issues = []
    try:
        if er < 0x40 or not es:
            raise ValueError('missing entry table')
        entries = entry_table(data,h+er,h+er+es,nseg)
        entry_status = 'PARSED'
    except ValueError as e:
        entries = {}; entry_status = 'UNRESOLVED'; issues.append(str(e))
    nonresident = []
    nrlen, nro = u16(data,h+0x20), u32(data,h+0x2c)
    nrstatus = 'NONE' if not nrlen else 'UNRESOLVED_PACKED_OFFSET'
    # For aggregated WIN100/200.BIN, absolute nonresident table offsets
    # cannot be assumed to be file-relative. Never guess or use them.
    if nrlen and standalone:
        try:
            nonresident = names(data,nro,nro+nrlen)
            nrstatus = 'PARSED'
        except ValueError as e:
            nrstatus = 'UNRESOLVED'; issues.append(str(e))
    exports = {}
    for name, ordinal in resident[1:]+nonresident:
        if ordinal:
            exports.setdefault(ordinal,set()).add(name)
    candidates = []
    for ordinal in sorted(set(exports) | (set(USER_CANDIDATES) if module=='USER' else set())):
        enames = sorted(exports.get(ordinal,()))
        if (module=='USER' and ordinal in USER_CANDIDATES) or any(
                k in name.upper() for name in enames for k in INTEREST):
            candidates.append({'ordinal':ordinal,'names':enames,
                'entry':entries.get(ordinal),
                'state': ('ENTRY_PRESENT' if ordinal in entries else
                          'ENTRY_NOT_PRESENT' if entry_status=='PARSED' else 'UNKNOWN')})
    return {'module':module,'ne_offset':h,'standalone_mz':standalone,
            'entry_status':entry_status,'nonresident_status':nrstatus,
            'resident_names':len(resident)-1,'entries':len(entries),
            'named_exports':[{'ordinal':o,'names':sorted(v)} for o,v in sorted(exports.items())],
            'candidates':candidates,'issues':issues}

def inspect_file(path):
    data = path.read_bytes()
    standard = (u32(data,0x3c) if len(data)>=0x40 and data[:2]==b'MZ'
                else 0 if data[:2]==b'NE' and path.suffix.upper()!='.BIN' else -1)
    modules = []
    if standard >= 0:
        row = parse_header(data,standard,True)
        if row: modules.append(row)
    # Early installed Windows often aggregates bare NE images in WIN*.BIN.
    # Check structurally plausible NE signatures, not raw function strings.
    if path.suffix.upper()=='.BIN':
        pos = -1
        while True:
            pos = data.find(b'NE',pos+1)
            if pos < 0: break
            if pos==standard: continue
            row = parse_header(data,pos,False)
            if row: modules.append(row)
    return {'file':path.name,'bytes':len(data),
            'sha256':hashlib.sha256(data).hexdigest(),'modules':modules}

def inventory(folder):
    paths = set()
    for p in list(folder.iterdir()) + [x for s in folder.iterdir()
            if s.is_dir() and s.name.upper()=='SYSTEM' for x in s.iterdir()]:
        if p.is_file() and (p.name.upper() in ('USER.EXE','KERNEL.EXE','KRNL286.EXE','KRNL386.EXE','MOUSE.DRV','KEYBOARD.DRV','SYSTEM.DRV')
                or p.name.upper().startswith('WIN') and p.suffix.upper()=='.BIN'
                or p.suffix.upper()=='.DRV' and ('MOUSE' in p.name.upper() or 'KEY' in p.name.upper())):
            paths.add(p)
    files = []
    for p in sorted(paths):
        row = inspect_file(p); row['file']=str(p.relative_to(folder));files.append(row)
    users = [m for f in files for m in f['modules'] if m['module']=='USER']
    return {'windows_source':str(folder),'files':files,
            'user_table_status':'PARSED' if any(m['entry_status']=='PARSED' for m in users) else 'UNRESOLVED',
            'input_qualified':False}

def run(root):
    cfg=runuat.get_config();rows=[];failed=False
    for target in ('WIN101','WIN200','WIN300'):
        try:
            folder=runuat.locate_windows(cfg,target)
            row=inventory(folder);row['target']=target
            print('INPUTABI %s: USER table %s (%d source files)'%(target,row['user_table_status'],len(row['files'])),flush=True)
            for f in row['files']:
                for m in f['modules']:
                    if m['module']=='USER':
                        for c in m['candidates']:
                            if c['ordinal'] in USER_CANDIDATES:
                                print('  %s USER.%d: %s %s'%(f['file'],c['ordinal'],c['state'],','.join(c['names']) or '(unnamed)'),flush=True)
            if row['user_table_status']!='PARSED':
                print('  Packed or unavailable USER tables: live probe still required.',flush=True)
        except (OSError,ValueError,struct.error,runuat.GuestError) as e:
            row={'target':target,'error':str(e),'input_qualified':False};failed=True
            print('INPUTABI %s ERROR: %s'%(target,e),flush=True)
        rows.append(row)
    report={'mode':'INPUTABI','result':'FAIL' if failed else 'INVENTORY_COMPLETE',
            'input_qualified':False,'scope':'Read-only module/export metadata; no native calls or input qualification','targets':rows}
    (root/'BUILD'/'RESULT.JSON').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if failed: raise ValueError('INPUTABI could not inspect one or more configured Windows installs')
    print('AUDIT_INPUTABI=PASS (inventory only; input NOT qualified)',flush=True)
