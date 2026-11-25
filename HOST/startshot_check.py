#!/usr/bin/env python3
"""NOWBAT STARTSHOT proof: decode actual BMP pixels, verify independent TAR.

A valid BMP header alone is NOT evidence that GetPixel captured the desktop.
All pixel rows are decoded; palette entries and row padding are not counted.
"""
import collections
import hashlib
from pathlib import Path
import struct
import tarfile


def inspect_bmp(path, expected_bpp=4):
    path=Path(path)
    if not path.is_file():
        raise ValueError('STARTSHOT missing captured SCREEN.BMP')
    raw=path.read_bytes()
    if len(raw)<62 or raw[:2]!=b'BM':
        raise ValueError('STARTSHOT invalid BMP signature/header')
    size,=struct.unpack_from('<I',raw,2)
    offset,=struct.unpack_from('<I',raw,10)
    header,w,h,planes,bpp,compression,pixel_len=struct.unpack_from('<IiiHHII',raw,14)
    if header!=40 or planes!=1 or bpp!=expected_bpp or bpp not in (1,4) or compression!=0:
        raise ValueError('STARTSHOT requires uncompressed Windows BMP, %d-bpp'%expected_bpp)
    if not (320<=w<=4096 and 200<=h<=4096):
        raise ValueError('STARTSHOT invalid full desktop dimensions: %sx%s'%(w,h))
    stride=((w*bpp+31)//32)*4
    colors=1<<bpp
    expected_offset=54+4*colors
    if size!=len(raw) or offset!=expected_offset or pixel_len!=stride*h or len(raw)!=offset+pixel_len:
        raise ValueError('STARTSHOT BMP truncated, padded incorrectly, or header size wrong')
    palette=[tuple(raw[54+i*4:54+i*4+3][::-1]) for i in range(colors)]
    pixels=collections.Counter()
    unique_rows=set()
    for y in range(h):
        row=raw[offset+y*stride:offset+y*stride+stride]
        counts=collections.Counter()
        for x in range(w):
            if bpp==4:
                b=row[x//2]
                idx=(b>>4) if x%2==0 else (b&15)
            else:
                idx=(row[x//8]>>(7-(x%8)))&1
            counts[idx]+=1
        pixels.update(counts)
        # Check real pixel rows; disregard stride/palette differences.
        unique_rows.add(bytes(row[:(w*bpp+7)//8]))
    if len(pixels)<2:
        raise ValueError('STARTSHOT BLANK: every desktop pixel has the same colour (index %d)'%next(iter(pixels)))
    dominant,n=pixels.most_common(1)[0]
    other=w*h-n
    if other<max(100,w*h//400):
        raise ValueError('STARTSHOT NEAR-BLANK: %d contrasting pixels of %d (%.3f%%)'%
                         (other,w*h,100*other/(w*h)))
    if len(unique_rows)<2:
        raise ValueError('STARTSHOT BLANK: desktop has only one distinct pixel row')
    return {'width':w,'height':h,'bpp':bpp,'pixels':w*h,
            'unique_colours':len(pixels),'distinct_rows':len(unique_rows),
            'dominant_index':dominant,'dominant_rgb':palette[dominant],
            'palette_rgb':palette if bpp==4 else None,
            'contrasting_pixels':other,'contrasting_percent':round(100*other/(w*h),3),
            'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw)}


def verify_win101_palette(bmp):
    """Check the standard WIN101 SVGA 800x600 palette used by SNAPFAST UAT.

    The 0x6A mode desktop displayed in the test guest uses remapped palette
    entries: e.g. index 7 is WHITE, not standard EGA grey. A structurally
    correct BMP with a fixed EGA palette must not pass as colour-correct.
    """
    entries=bmp.get('palette_rgb') or []
    expected={2:(85,255,85),3:(255,255,85),4:(85,85,255),
              6:(85,255,255),7:(255,255,255)}
    if len(entries)!=16:
        raise ValueError('SNAPFAST Win1 palette missing 16 RGB entries')
    for idx,rgb in expected.items():
        got=entries[idx]
        if any(abs(int(g)-want)>5 for g,want in zip(got,rgb)):
            raise ValueError('SNAPFAST Win1 palette incorrect at index %d: got %s, expected near %s'%(
                idx,got,rgb))
    return True

def verify_shot_tar(path, expected):
    path=Path(path)
    if not path.is_file():
        raise ValueError('STARTSHOT missing SCREEN.TAR')
    raw=path.read_bytes()
    if len(raw)<2048 or len(raw)%512!=0 or raw[-1024:]!=bytes(1024):
        raise ValueError('STARTSHOT TAR missing aligned terminal blocks')
    expected={str(name).upper():data for name,data in expected.items()}
    seen={}
    try:
        with tarfile.open(str(path),'r:',errorlevel=2) as tar:
            members=tar.getmembers()
            if len(members)!=len(expected):
                raise ValueError('STARTSHOT TAR has wrong number of entries')
            for member in members:
                name=member.name.upper()
                if name not in expected or name in seen or not member.isfile():
                    raise ValueError('STARTSHOT TAR contains wrong/duplicate entry '+member.name)
                reader=tar.extractfile(member)
                data=reader.read() if reader else b''
                if data!=expected[name]:
                    raise ValueError('STARTSHOT TAR payload differs from real file '+member.name)
                seen[name]=len(data)
    except (tarfile.TarError,OSError,EOFError) as exc:
        raise ValueError('STARTSHOT unreadable TAR: '+str(exc)) from exc
    if set(seen)!=set(expected):
        raise ValueError('STARTSHOT TAR missing expected member(s)')
    return {'members':seen,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def verify_ten_second_wait(begin_path,end_path,begin_time,end_time):
    """Two separately closed markers; validate 10 s via host or file clock."""
    if not Path(begin_path).is_file() or not Path(end_path).is_file():
        raise ValueError('STARTSHOT missing warmup checkpoint')
    host=(end_time-begin_time) if begin_time is not None and end_time is not None else -1.
    try:
        fs=(Path(end_path).stat().st_mtime_ns-Path(begin_path).stat().st_mtime_ns)/1e9
    except OSError:
        fs=-1.
    if max(host,fs)<9.0:
        raise ValueError('STARTSHOT 10s WAIT not observed (host %.2fs, filesystem %.2fs)'%(host,fs))
    return {'seconds':round(max(host,fs),2),'method':'host-monotonic' if host>=9.0 else 'host-file-mtime',
            'script_wait_ms':10000}
