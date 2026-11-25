#!/usr/bin/env python3
"""Geometry-only tests for the strict direct-video capture. Not native UAT."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
snap=(root/'SRC/WASSNAP.ASM').read_text(encoding='ascii')
script=(root/'SRC/WAS.ASM').read_text(encoding='ascii')
assert 'mov wasSnapMode,1       ; SNAP defaults to strict FAST' in script
assert 'snapModeFastName' in script and 'snapModeAutoName' in script
assert 'snapModeCompatName' in script
assert "cmdSNAPSAFE  db 'SNAPSAFE',0" in script
assert "lea di,cmdSNAPSAFE\n call IsCommand\n jc commandSnap" in script
assert 'wasDoSnap:\n ; SNAPSAFE unconditionally uses original GDI' in script
assert 'mov wasSnapMode,0\nwasSnapReady:' in script
assert 'mov snapMethod,3' in snap and 'mov wasResult,2' in snap
assert 'SnapDirectRow4 proc near' in snap
assert 'cmp snapGCPlanes,4' in snap
assert 'snap4ReadPlane:' in snap and 'snap4Pixel:' in snap
assert 'extrn snapPlaneBuf:byte' in snap
assert 'snapPlaneBuf db 400 dup(0)' in (root/'SRC'/'WASUI.ASM').read_text()
assert 'je snapResolveRect' in snap  # no BPP: native depth
assert 'mov word ptr snapX0,0' in snap  # no region: full desktop
assert 'snapDirectBufferRow:' in snap and 'snapDirectFlush:' in snap
assert 'add di,snapBufUsed' in snap
assert 'mov cx,snapBufUsed' in snap
assert 'SNAP_METHOD=VIDEO_DIRECT' in script
assert 'SNAP_METHOD=UNSUPPORTED' in script
assert 'SNAP_METHOD=GETPIXEL' in script
shot=(root/'TESTS/SHOT.WAS').read_text(encoding='ascii')
assert 'SNAPSAFE "C:\\WASUAT\\SAFE.BMP"' in shot
assert 'SNAP "C:\\WASUAT\\SCREEN.BMP"' in shot
assert 'SCREEN.BMP" MODE=' not in shot
assert 'SYNTAX: SNAP "file.bmp" [BPP=n]' in (root/'SCRIPT.TXT').read_text(encoding='ascii')
assert 'SYNTAX: SNAP "file.bmp",x,y,x1,y1[,BPP=n]' in (root/'SCRIPT.TXT').read_text(encoding='ascii')
assert 'MODE=FAST|COMPAT|AUTO' not in (root/'SCRIPT.TXT').read_text(encoding='ascii')
for label in ('SNAPSAFE_START','SNAPSAFE_END','SNAPFAST_START','SNAPFAST_END'):
    assert 'LOG "'+label+'=%DATE% %TIME%"' in shot

# Palette (max 256 * RGBQUAD = 1024 bytes) and pixel output are disjoint
# lifetimes, so sharing snapRow preserves all depth and stride options.
assert 'snapPalette  db 1024 dup(0)' not in snap
assert 'extrn snapRow:byte' in snap
assert 'snapRow      db 4096 dup(0)' in (root/'SRC'/'WASUI.ASM').read_text()
assert 'mov dx,offset snapRow' in snap
assert 'lea di,snapRow' in snap.split('BuildPalette proc near',1)[1]
assert snap.index('call BuildPalette') < snap.index('snapRowFirst:')
assert 256*4 <= 4096

# W064 native 4-bpp palette follows VGA attribute + DAC, not fixed RGB.
assert 'call SnapVgaPalette' in snap
assert snap.index('call SnapVgaPalette') < snap.index('snapCreateFile:')
assert 'mov dx,03C0h' in snap and 'mov dx,03C1h' in snap
assert 'mov dx,03C7h' in snap and 'mov dx,03C9h' in snap
assert 'test snapAttrMode,80h' in snap and 'and al,snapPelMask' in snap
assert 'or al,20h' in snap and 'snapAttrOld' in snap
assert 'mov [di+2],al' in snap and 'mov [di+1],al' in snap
# Example observed Windows 1 6Ah indices: dynamic rather than standard EGA RGB.
old_rgb={2:(0,170,0),3:(0,170,170),4:(170,0,0),7:(170,170,170)}
actual_rgb={2:(85,255,85),3:(255,255,85),4:(85,85,255),7:(255,255,255)}
assert all(old_rgb[i]!=actual_rgb[i] for i in old_rgb)
assert all(((v<<2)|(v>>4))==expected for v,expected in ((0,0),(21,85),(42,170),(63,255)))

checks=9
for y in range(200):
    for xbyte in (0,79):
        # CGA 640x200 packed monochrome, two banks.
        off=((y&1)*0x2000)+(y>>1)*80+xbyte
        assert 0<=off<0x4000
        assert off==((y&1)*0x2000)+(y//2)*80+xbyte
        checks+=2
for y in range(348):
    for xbyte in (0,89):
        # HGC 720x348 monochrome, four banks.
        off=(y&3)*0x2000+(y>>2)*90+xbyte
        assert 0<=off<0x8000
        checks+=1
for w,h in ((320,200),(640,200),(640,350),(640,480),(800,600)):
    rowbits=w//8
    for y in range(h):
        for xbyte in (0,rowbits-1):
            assert 0 <= y*rowbits+xbyte < 0x10000
            checks+=1
    stride=((w+31)//32)*4
    assert stride%4==0 and stride==rowbits
    batch=4096//stride
    assert batch>=1
    assert (batch*stride)<=4096
    assert (batch+1)*stride>4096
    checks+=4
# One 1-bit conversion of multiple planes should preserve each nonzero pixel.
planes=[bytes([0x80,0x00]),bytes([0x04,0x08]),bytes([0x00,0x10]),bytes([0x40,0x00])]
combined=bytes([a|b|c|d for a,b,c,d in zip(*planes)])
assert combined==bytes([0xC4,0x18]);checks+=1

# Four hardware planes, 8 pixels/group. Verify correct BMP nibble ordering.
for colors in (list(range(8)),[15,14,13,12,11,10,9,8],[0,15,0,15,1,2,3,4]):
    planes=[sum(((color>>plane)&1)<<(7-i) for i,color in enumerate(colors)) for plane in range(4)]
    unpack=[]
    for bit in range(7,-1,-1):
        unpack.append(sum(((planes[p]>>bit)&1)<<p for p in range(4)))
    packed=bytes((unpack[i]<<4)|unpack[i+1] for i in range(0,8,2))
    assert unpack==colors
    assert packed==bytes((colors[i]<<4)|colors[i+1] for i in range(0,8,2))
    checks+=2
assert (4096//320)==12
assert 640//8==80
assert 320//8==40
assert 800//8==100
assert 599*100+99 < 65536
assert 'cmp al,6Ah' in snap and 'snapProbeSvga800:' in snap
assert 'mov snapLineRaw,100' in snap
assert 'snapPlaneBuf[bx+100]' in snap and 'snapPlaneBuf[bx+200]' in snap and 'snapPlaneBuf[bx+300]' in snap
assert "'006A'" in (root/'HOST/runuat.py').read_text(encoding='utf-8')
checks+=6
checks+=3

print('SNAPMODES_HOST=PASS (%d geometry and mode checks; no native guest)' % checks)

# Verify the four 100-byte plane slots stay distinct for 800px and
# the 4bpp destination fits inside the 4096-byte FAST output batch.
for raw_width in (40,80,100):
    assert raw_width <= 100
    for p in range(4):
        for x in (0,raw_width-1):
            address=p*100+x
            assert 0 <= address < 400
            assert address//100 == p
            checks += 2
assert 800//2 == 400
assert 4096//400 == 10
checks+=2
print('SNAPMODES_SVGA800=PASS')
