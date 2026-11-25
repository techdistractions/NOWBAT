#!/usr/bin/env python3
"""Omit a known zero-initialized DGROUP tail from a raw NOWBAT NE image.

This is standard NE file-size vs minimum-allocation layout, not an EXE
packer or a new compression format. No loaded address, fixup, import,
entrypoint, stack or minimum allocation is changed. Refuse unexpected layout.
"""
from pathlib import Path
import struct
import sys

MARKER = b'NOWBAT_ZERO_W054\0'
ZERO_BYTES = 9950


def u16(b, at):
    return struct.unpack_from('<H', b, at)[0]


def u32(b, at):
    return struct.unpack_from('<I', b, at)[0]


def layout(b):
    if b[:2] != b'MZ' or len(b) < 128:
        raise ValueError('missing MZ header')
    ne = u32(b, 0x3c)
    if ne+64 > len(b) or b[ne:ne+2] != b'NE':
        raise ValueError('missing NE header')
    if u32(b, ne+8):
        raise ValueError('nonzero NE checksum: refusing rewrite')
    count, data = u16(b, ne+0x1c), u16(b, ne+0xe)
    shift = u16(b, ne+0x32)
    if count != 2 or data != 2 or shift not in (1, 4):
        raise ValueError('unexpected NOWBAT segment layout')
    table = ne+u16(b, ne+0x22)
    base = table+8
    sector, length, flags, alloc = struct.unpack_from('<4H', b, base)
    off = sector << shift
    if not (sector and length and alloc and alloc >= length and off+length <= len(b)):
        raise ValueError('invalid DGROUP bounds')
    if not flags & 1 or flags & 8 or not flags & 0x100:
        raise ValueError('expected ordinary relocated data segment, not iterated data')
    # Header tables and non-resident name table must precede the data.
    nonres, nonlen = u32(b, ne+0x2c), u16(b, ne+0x20)
    if nonres+nonlen > off:
        raise ValueError('nonresident names after data')
    code_sector, code_len, code_flags, _ = struct.unpack_from('<4H', b, table)
    code_off = code_sector << shift
    code_end = code_off+code_len
    if not code_sector or not code_len or code_flags & 1 or code_end > off:
        raise ValueError('unexpected code segment')
    if code_flags & 0x100:
        code_end += 2+8*u16(b, code_end)
    if code_end > off:
        raise ValueError('overlapping code relocation table')
    end = off+length
    rel_end = end+2+8*u16(b, end)
    if rel_end > len(b):
        raise ValueError('truncated DGROUP relocation table')
    return ne, base, off, length, alloc, end, rel_end


def marker_end(data):
    at = data.find(MARKER)
    if at < 0 or data.find(MARKER, at+1) != -1:
        raise ValueError('missing/ambiguous zero arena marker')
    return at+len(MARKER)


def check_chains(data, relocs, cut):
    # The two W081 DGROUP relocations are standard nonadditive internal
    # selector fixups. Walk *all* chain sources; never truncate a fixup.
    count = u16(relocs, 0)
    if count != 2 or len(relocs) != 2+count*8:
        raise ValueError('unexpected DGROUP relocation count')
    seen = set()
    for i in range(count):
        typ, flags, src, _, _ = struct.unpack_from('<BBHHH', relocs, 2+8*i)
        if typ != 2 or flags != 0:
            raise ValueError('unexpected DGROUP relocation type')
        while src != 0xffff:
            if src in seen or src+2 > cut:
                raise ValueError('DGROUP fixup enters zero arena or cycles')
            seen.add(src)
            src = u16(data, src)


def compact(raw):
    ne, base, off, length, alloc, end, rel_end = layout(raw)
    # Only the unadorned linker output is accepted; icon insertion follows.
    rt, names = u16(raw, ne+0x24), u16(raw, ne+0x26)
    if raw[ne+rt:ne+names] not in (b'', struct.pack('<HH', u16(raw, ne+0x32), 0)):
        raise ValueError('resources already present; compact before icon embedding')
    if rel_end != len(raw):
        raise ValueError('unexpected trailing bytes after DGROUP relocations')
    data = raw[off:end]
    cut = marker_end(data)
    tail = data[cut:]
    # Linker may append paragraph padding. All removed bytes must be zero.
    if not ZERO_BYTES <= len(tail) <= ZERO_BYTES+15 or any(tail):
        raise ValueError('zero arena length/content mismatch: %d bytes' % len(tail))
    relocs = raw[end:rel_end]
    check_chains(data, relocs, cut)
    out = bytearray(raw[:off+cut]+relocs)
    struct.pack_into('<H', out, base+2, cut)
    check_packed(out)
    # Compare the complete initialized memory image and relocation bytes.
    assert out[off:off+cut]+bytes(alloc-cut) == data+bytes(alloc-length)
    assert out[off+cut:] == relocs
    assert out[:base+2] == raw[:base+2] and out[base+4:off] == raw[base+4:off]
    return bytes(out)


def check_packed(b):
    """Works on a compacted raw NE or on the icon-embedded runtime."""
    _, _, off, length, alloc, end, rel_end = layout(b)
    data = b[off:end]
    if marker_end(data) != length or not ZERO_BYTES <= alloc-length <= ZERO_BYTES+30:
        raise ValueError('DGROUP zero arena was not compacted / minalloc mismatch')
    check_chains(data, b[end:rel_end], length)
    return alloc-length


def main():
    if len(sys.argv) != 2:
        raise ValueError('usage: necompact.py linked.exe')
    p = Path(sys.argv[1])
    old = p.read_bytes()
    new = compact(old)
    p.write_bytes(new)
    print('NECOMPACT %s: %d -> %d bytes; %d zero bytes omitted, DGROUP minalloc preserved' %
          (p.name, len(old), len(new), len(old)-len(new)), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, struct.error, AssertionError) as e:
        print('NECOMPACT FAIL:', e, file=sys.stderr)
        sys.exit(1)
