#!/usr/bin/env python3
"""Independent NE layout and zero-arena tests. Not a native loader test."""
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'HOST'))
import necompact as nc
import iconbuild


def fixture(shift, pad):
    # Minimal synthetic NE with ordinary code, automatic DGROUP, name
    # tables ahead of both segments, and two realistic internal fixups.
    ne, align = 0x70, 1<<shift
    code_off = 0x200
    off = 0x500
    data = bytearray(256)
    data[16:24] = b'KEEPDATA'
    struct.pack_into('<H', data, 30, 42)
    struct.pack_into('<H', data, 42, 0xffff)
    struct.pack_into('<H', data, 70, 0xffff)
    data.extend(nc.MARKER)
    cut = len(data)
    data.extend(bytes(nc.ZERO_BYTES+pad))
    alloc = (len(data)+15)&~15
    # Linker data length may differ from paragraph allocation.
    raw = bytearray(off)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 60, ne)
    raw[ne:ne+2] = b'NE'
    def w(a,v): struct.pack_into('<H',raw,ne+a,v)
    w(0xe,2); w(0x12,2048); w(0x16,1); w(0x1a,2)
    w(0x1c,2); w(0x20,0); w(0x22,0x40); w(0x24,0x50)
    w(0x26,0x54 if shift==4 else 0x50)
    w(0x28,0x60); w(0x2a,0x62); w(0x04,0x64); w(0x32,shift)
    struct.pack_into('<I',raw,ne+0x2c,0x180)
    if shift==4:
        struct.pack_into('<HH',raw,ne+0x50,shift,0)
    struct.pack_into('<4H',raw,ne+0x40,code_off//align,128,0x0d00,128)
    struct.pack_into('<4H',raw,ne+0x48,off//align,len(data),0x0d51 if shift==4 else 0x0d41,alloc)
    raw[code_off:code_off+128] = bytes(range(128))
    struct.pack_into('<H',raw,code_off+128,0)
    reloc = struct.pack('<HBBHHHBBHHH',2,2,0,30,1,0,2,0,70,2,0)
    raw.extend(data); raw.extend(reloc)
    return bytes(raw),off,cut,alloc


def rejects(raw):
    try: nc.compact(raw)
    except (ValueError,struct.error): return
    raise AssertionError('unsafe NE accepted')


for shift,target in ((4,'WIN101'),(1,'WIN300')):
    for pad in (0,1,7,15):
        raw,off,cut,alloc=fixture(shift,pad)
        out=nc.compact(raw)
        assert len(raw)-len(out)==nc.ZERO_BYTES+pad
        assert nc.check_packed(out)==alloc-cut
        assert out[off:off+cut]==raw[off:off+cut]
        assert out[-18:]==raw[-18:]
        assert nc.layout(raw)[4]==nc.layout(out)[4]
        with_icon=iconbuild.embed(out,target)
        assert iconbuild.check_icons(with_icon,target)
        assert iconbuild.code_size(with_icon,target)==len(out)
        assert nc.check_packed(with_icon)==alloc-cut
        rejects(with_icon)
        rejects(raw+b'extra')
        rejects(out)
        bad=bytearray(raw); bad[off+cut+7]=1; rejects(bad)
        bad=bytearray(raw); struct.pack_into('<H',bad,off+42,cut); rejects(bad)
        bad=bytearray(raw); struct.pack_into('<H',bad,off+42,30); rejects(bad)
        bad=bytearray(raw); bad[-16]=5; rejects(bad)
        bad=bytearray(raw); bad[off+cut-len(nc.MARKER)]=0; rejects(bad)
        bad=bytearray(raw); struct.pack_into('<H',bad,nc.layout(raw)[1]+6,cut); rejects(bad)

# Source/link layout contract: verify every moved declaration, exact size,
# no change in ordering of the initialized prefix, and final object in all
# 8 link response files (production plus terminal modules).
ui=(ROOT/'SRC'/'WASUI.ASM').read_text()
core=(ROOT/'SRC'/'WAS.ASM').read_text()
arena=ui.split('WasZeroStart LABEL BYTE\n',1)[1].split('WasZeroEnd LABEL BYTE',1)[0]
entries=re.findall(r'^(\w+)\s+db\s+(\d+) dup\(0\)',arena,re.M|re.I)
assert len(entries)==26 and sum(int(n) for _,n in entries)==nc.ZERO_BYTES
for sym,n in entries:
    assert 'PUBLIC '+sym+'\n' in arena
    owners=[p for p in (ROOT/'SRC').glob('*.ASM') if p.name!='WASUI.ASM' and re.search(r'^extrn '+sym+r':byte\b',p.read_text(),re.M|re.I)]
    assert owners, sym
assert re.search(r'WasZeroEnd LABEL BYTE\s+\.code',ui)
assert core.index('call InitTask') < core.index('mov di,offset WasZeroStart') < core.index('rep stosb') < core.index('call InitApp')
assert 'mov cx,offset WasZeroEnd\n sub cx,di\n xor ax,ax\n cld\n rep stosb\n pop es' in core
assert ' dw 0,0,5,0,0,0,0,0' in core
for p in [ROOT/'LINK'/'WIN101.RSP',ROOT/'LINK'/'WIN300.RSP',*(ROOT/'LINK'/'TERMS').glob('*.RSP')]:
    line=next(l for l in p.read_text().splitlines() if l.startswith('FILE '))
    assert line.endswith('BUILD/WASUI.OBJ'),p
print('NECOMPACT HOST=PASS (8 NE layouts, icon round-trips, unsafe input rejection, source/link arena contract)')
