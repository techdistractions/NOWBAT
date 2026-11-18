#!/usr/bin/env python3
"""Embed a tiny, deterministic bat icon in a Win16 NE executable.

No RC.EXE/Windows SDK dependency. Windows 1.x/2.x use a native 1bpp RT_ICON
resource, Windows 3.0 real mode a 4bpp RT_GROUP_ICON + RT_ICON DIB. This tool
changes only NE file offsets/resource metadata and appends icon bytes; it
checks that original code, data, imports, and entry point are unchanged.
"""
from pathlib import Path
import argparse
import struct
import sys

W = H = 32

def u16(b, pos): return struct.unpack_from('<H', b, pos)[0]
def u32(b, pos): return struct.unpack_from('<I', b, pos)[0]
def put16(b, pos, val): struct.pack_into('<H', b, pos, val)
def put32(b, pos, val): struct.pack_into('<I', b, pos, val)

# 32x32 pixel-art bat, deliberately simple at tiny Win1/2 icon sizes.
# . transparent; # silhouette; P EGA purple wing panel; O white eyes.
# Same silhouette for both targets; WIN101 collapses purple into black.
BAT_PIXELS = (
    '................................',
    '................................',
    '................................',
    '................................',
    '................................',
    '................................',
    '................................',
    '.............#....#.............',
    '.............##..##.............',
    '.......#.....######.....#.......',
    '......####...######...####......',
    '......##P##..######..##P##......',
    '...#####PP############PP#####...',
    '..###PPPPPP##########PPPPPP###..',
    '..##PPPPPPP###O##O###PPPPPPP##..',
    '.##PPPPPPPP##########PPPPPPPP##.',
    '.##PPPPPPPP##########PPPPPPPP##.',
    '.##PPP#PPPP##########PPPP#PPP##.',
    '.######P################P######.',
    '...##########################...',
    '...#..###..##########..###..#...',
    '......##...##########...##......',
    '.......#....########....#.......',
    '............########............',
    '.............##..##.............',
    '.............#....#.............',
    '................................',
    '................................',
    '................................',
    '................................',
    '................................',
    '................................',
)

def bitmap():
    palette = {'.': None, '#': 0, 'P': 5, 'O': 15}
    assert len(BAT_PIXELS) == 32 and all(len(r) == 32 for r in BAT_PIXELS)
    return [[palette[c] for c in row] for row in BAT_PIXELS]

def pack_and(pix, reverse=False):
    rows=list(reversed(pix)) if reverse else pix
    return b''.join(bytes(sum((1 << (7-b) if rows[y][x+b] is None else 0)
                              for b in range(8)) for x in range(0,32,8))
                    for y in range(32))

def pack_xor1(pix, reverse=False):
    rows=list(reversed(pix)) if reverse else pix
    # 1-bit monochrome: black silhouette with white eyes.
    return b''.join(bytes(sum((1 << (7-b) if rows[y][x+b] == 15 else 0)
                              for b in range(8)) for x in range(0,32,8))
                    for y in range(32))

def pack_xor4(pix):
    return bytes(( ((row[x] or 0) << 4) | (row[x+1] or 0) )
                 for row in reversed(pix) for x in range(0,32,2))

# Classic EGA palette, B G R reserved, 16 colors.
EGA = [(0,0,0), (0,0,170), (0,170,0), (0,170,170),
       (170,0,0), (170,0,170), (170,85,0), (170,170,170),
       (85,85,85), (85,85,255), (85,255,85), (85,255,255),
       (255,85,85), (255,85,255), (255,255,85), (255,255,255)]

def payloads(target):
    pix=bitmap(); and_top=pack_and(pix)
    if target=='WIN101':
        # Win1/2 icon format: 12-byte hot spot / dimension / scan-stride
        # header, then top-down AND and XOR 1bpp masks. No group resource.
        # Early Windows 1.x/2.x single-image ICONEDIT resource has the
        # 0x0001 type/format word before its 12-byte bitmap header. Without
        # it Win2 can decode the first words as dimensions and paint only
        # a clipped fragment of the minimized icon.
        old = struct.pack('<H',1) + struct.pack('<6H',0,0,32,32,4,0) + and_top + pack_xor1(pix)
        return [(3,1,old)]
    if target=='WIN300':
        dib=struct.pack('<IiiHHIIiiII',40,32,64,1,4,0,640,0,0,16,0)
        pal=b''.join(bytes((b,g,r,0)) for r,g,b in EGA)
        image=dib+pal+pack_xor4(pix)+pack_and(pix,reverse=True)
        group=struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHIH',32,32,16,0,1,4,len(image),2)
        return [(3,2,image),(14,1,group)]
    raise ValueError('unknown target')

def create_ico(target):
    if target=='WIN300':
        image=payloads(target)[0][2]; planes,bits,palette=1,4,16
    else:
        pix=bitmap()
        hdr=struct.pack('<IiiHHIIiiII',40,32,64,1,1,0,256,0,0,2,0)
        image=hdr + bytes((0,0,0,0,255,255,255,0)) + pack_xor1(pix,True) + pack_and(pix,True)
        planes,bits,palette=1,1,2
    return struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',32,32,palette,0,planes,bits,len(image),22)+image

def details(data):
    if data[:2] != b'MZ': raise ValueError('not MZ executable')
    ne=u32(data,0x3c)
    if data[ne:ne+2] != b'NE': raise ValueError('not NE executable')
    segrel=u16(data,ne+0x22); shift=u16(data,ne+0x32); cnt=u16(data,ne+0x1c)
    entries=[]
    for i in range(cnt):
        base=ne+segrel+8*i; off=u16(data,base)<<shift; size=u16(data,base+2)
        entries.append((base,off,size if size else 65536))
    return ne,shift,entries

def embed(data,target):
    src=bytes(data)
    ne,shift,segments=details(src)
    rt=u16(src,ne+0x24); names=u16(src,ne+0x26)
    old=src[ne+rt:ne+names]
    if old not in (b'',struct.pack('<HH',shift,0)):
        raise ValueError('refusing to overwrite existing resource table')
    resources=payloads(target)
    parts=[]
    for typ in sorted({t for t,_,_ in resources}):
        parts.append(struct.pack('<HHI',0x8000|typ,sum(1 for x in resources if x[0]==typ),0))
        for t,rid,image in resources:
            if t==typ: parts.append(b'\x00'*12) # filled after payload append
    parts.append(b'\x00\x00')
    table_size=2+sum(map(len,parts))
    align=1<<shift
    insert=(-(- (table_size-len(old)) // align))*align
    if insert < table_size-len(old): raise AssertionError('underallocated icon table')
    if (ne+names+insert)>0xffff: raise ValueError('NE header-relative offsets overflow')
    out=bytearray(src[:ne+rt]+b'\x00'*insert+src[ne+rt:])
    # Logical insertion is immediately before the prior resource table. The
    # new table occupies that position; original content shifts by insert.
    # Relocate all following NE-relative pointers and file-offset segment
    # locations, keeping the module-ref table's *internal* name offsets.
    for field in (0x04,0x26,0x28,0x2a):
        v=u16(src,ne+field)
        if v>=names: put16(out,ne+field,v+insert)
    loc=u32(src,ne+0x2c)
    if loc>=ne+names: put32(out,ne+0x2c,loc+insert)
    for base,off,_ in segments:
        if off>=ne+rt:
            if (off+insert)%align: raise ValueError('misaligned segment')
            put16(out,base,(off+insert)>>shift)
    # Payloads are after code, data, and relocation records. Resource values
    # are the *aligned* sizes, as specified by Windows NE resource tables.
    payload_offsets={}
    for typ,rid,image in resources:
        extra=(-len(out)) % align
        out.extend(b'\x00'*extra)
        payload_offsets[(typ,rid)]=(len(out)>>shift,(-(-len(image)//align)),image)
        out.extend(image)
        out.extend(b'\x00'*((-len(image))%align))
    table=bytearray(struct.pack('<H',shift))
    for typ in sorted({t for t,_,_ in resources}):
        items=[(rid,img) for t,rid,img in resources if t==typ]
        table.extend(struct.pack('<HHI',0x8000|typ,len(items),0))
        for rid,img in items:
            off,sz,_=payload_offsets[(typ,rid)]
            table.extend(struct.pack('<HHHHHH',off,sz,0x0030,0x8000|rid,0,0))
    table.extend(b'\x00\x00')
    assert len(table)==table_size
    out[ne+rt:ne+rt+len(table)]=table
    # Check relocations and imports are byte-for-byte preserved. This can
    # also detect accidental link-table corruption at the insertion point.
    _,_,newsegs=details(out)
    assert len(segments)==len(newsegs)
    for (_,start,length),(_,after,newlength) in zip(segments,newsegs):
        assert length==newlength and src[start:start+length]==out[after:after+newlength]
    assert src[ne+names:segments[0][1]] == out[ne+names+insert:newsegs[0][1]]
    return bytes(out)

def check_icons(data,target):
    ne,shift,_=details(data)
    here=ne+u16(data,ne+0x24)
    if u16(data,here)!=shift: raise ValueError('resource alignment mismatch')
    here+=2; actual={}
    while True:
        typ=u16(data,here);here+=2
        if not typ:break
        count=u16(data,here);here+=6
        if not typ&0x8000 or count>4: raise ValueError('invalid type record')
        for i in range(count):
            off,length,flags,rid,_,_=struct.unpack_from('<6H',data,here);here+=12
            if not rid&0x8000:raise ValueError('noninteger resource identifier')
            actual[(typ&0x7fff,rid&0x7fff)] = data[off<<shift:(off+length)<<shift]
    expected=payloads(target)
    if set(actual)!={(t,i) for t,i,_ in expected}:raise ValueError('missing/extra icon resources')
    for typ,rid,img in expected:
        payload=actual[(typ,rid)]
        if not payload.startswith(img) or payload[len(img):].strip(b'\x00'):
            raise ValueError('incorrect icon pixels/group resource')
    return True

def expected_overhead(target,base_length):
    # Resource header growth plus padding and payload lengths. The raw base
    # executable may not be aligned (linkers append relocation tail records).
    shift=4 if target=='WIN101' else 1;align=1<<shift
    old_len=4 if target=='WIN101' else 0
    new_len=2 + sum(8+12*sum(1 for typ,_,_ in payloads(target) if typ==t)
                      for t in {typ for typ,_,_ in payloads(target)})+2
    insert=(-(-(new_len-old_len)//align))*align
    end=base_length+insert
    for typ,rid,image in payloads(target):
        end+=(-end)%align+len(image)+(-len(image))%align
    return end-base_length

def code_size(data, target):
    """Recover the pre-embedding executable byte count from its NE tail.

    Unlike a fixed guessed icon-size deduction, this follows the last linked
    segment and its actual Win16 relocation records. The builder inserts the
    icon table ahead of the metadata and appends icons after this tail.
    """
    ne,shift,segments=details(data)
    last=0
    for base,off,length in segments:
        end=off+length
        flags=u16(data,base+4)
        if flags&0x100:
            count=u16(data,end)
            end+=2+count*8
        last=max(last,end)
    old=4 if target=='WIN101' else 0
    tablebytes=2+sum(8+12*sum(1 for typ,_,_ in payloads(target) if typ==t)
                  for t in {typ for typ,_,_ in payloads(target)})+2
    insert=((tablebytes-old+(1<<shift)-1)//(1<<shift))*(1<<shift)
    result=last-insert
    if result<=0 or result>len(data): raise ValueError('invalid linked NE end')
    if result + expected_overhead(target,result) != len(data):
        raise ValueError('resource tail does not match linked NE size')
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('target',choices=('WIN101','WIN300'))
    ap.add_argument('file',type=Path)
    ap.add_argument('--asset-dir',type=Path,default=None)
    ns=ap.parse_args()
    source=ns.file.read_bytes()
    changed=embed(source,ns.target)
    check_icons(changed,ns.target)
    if len(changed)-len(source)!=expected_overhead(ns.target,len(source)):
        raise AssertionError('incorrect NE icon overhead')
    ns.file.write_bytes(changed)
    if ns.asset_dir:
        ns.asset_dir.mkdir(parents=True,exist_ok=True)
        (ns.asset_dir/(ns.target+'.ICO')).write_bytes(create_ico(ns.target))
    print('ICON %s bat: +%d bytes, NE segments unchanged, resources verified' % (
          ns.target,len(changed)-len(source)))
if __name__=='__main__':
    try:main()
    except (ValueError,AssertionError,struct.error,OSError) as e:
        print('ICON FAIL:',e,file=sys.stderr);sys.exit(1)

