; NOWBAT SNAP: full desktop and native BPP unless options override.
; SNAP defaults to FAST; SNAPSAFE uses the original GDI compatibility path.
; Inclusive rectangle X,Y,X1,Y1; optional BPP 1/4/8/24, 0=desktop depth.
; Direct mode requires recognised hardware; other drivers use COMPAT.
.8086
.model small
extrn GetDC:far
extrn ReleaseDC:far
extrn GetDeviceCaps:far
extrn GetPixel:far
extrn Yield:far
extrn Dos3Call:far
extrn wasInput:byte
extrn wasResult:word
extrn wasRect:word
extrn wasBpp:word
extrn wasSnapMode:byte   ; 0=COMPAT 1=FAST 2=AUTO
PUBLIC SnapDo,snapMethod,snapVideoMode

.data
snapHdc      dw 0
snapMethod   db 0        ; 0=COMPAT GetPixel, 2=direct framebuffer
snapVideoMode db 0FFh    ; BIOS video mode or FF for unsupported
snapDirect   db 0        ; 1=direct, 2=Hercules, 3=EGA/VGA planar
snapScreenW  dw 0
snapScreenH  dw 0
snapLineRaw  dw 0        ; hardware scanline bytes (80,90 or 40)
snapCopyN    dw 0        ; byte aligned BMP content per scanline
snapXByte    dw 0
snapVideoSeg dw 0        ; B800/B000/A000, selected only after mode probe
snapGCIndex  db 0
snapGCRead   db 0
snapGCMode   db 0
snapGCPlanes db 0
snapAttrOld  db 0        ; VGA attribute-controller index before palette read
snapAttrMode db 0        ; VGA attribute mode control (P54S)
snapColorSel db 0        ; VGA palette high-bit select
snapPelMask  db 0FFh     ; VGA DAC pixel mask
snapBufUsed   dw 0       ; 4 KiB direct-video rows, flushed in one DOS write
snapFile     dw 0FFFFh
snapW        dw 0
snapH        dw 0
snapX0       dw 0
snapY0       dw 0
snapX1       dw 0
snapY1       dw 0
snapX        dw 0
snapY        dw 0
snapPixel    dw 0
snapStride   dw 0
snapBpp      dw 0
snapPaletteN dw 0
snapPixelLo  dw 0
snapPixelHi  dw 0
snapBF       db 54 dup(0)
; BMP palette reuses snapRow[0..1023] before any scanlines are written.
; The 256-entry RGBQUAD table is streamed to disk before snapRow is
; cleared or filled for pixel data. Saves 1024 DGROUP bytes on XT.
snapRow      db 4096 dup(0)   ; COMPAT row or FAST batch, never a framebuffer
snapPlaneBuf db 400 dup(0)    ; four 100-byte planar slots; 640/800 widths
snapDefault  dw 0

.code
SnapDo proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 mov snapMethod,0
 mov snapDirect,0
 mov snapVideoMode,0FFh
 xor ax,ax
 push ax
 call GetDC
 or ax,ax
 jz snapFail
 mov snapHdc,ax
 ; Query pixel dimensions, not physical display size.
 push snapHdc
 mov ax,8
 push ax
 call GetDeviceCaps
 mov snapW,ax
 push snapHdc
 mov ax,10
 push ax
 call GetDeviceCaps
 mov snapH,ax
 mov snapScreenH,ax
 mov ax,snapW
 mov snapScreenW,ax
 ; desktop bits-per-pixel: BITSPIXEL * PLANES
 push snapHdc
 mov ax,12
 push ax
 call GetDeviceCaps
 mov snapDefault,ax
 push snapHdc
 mov ax,14
 push ax
 call GetDeviceCaps
 mul snapDefault
 ; BMP BI_RGB allows 1,4,8,24, not planar or 2-bpp output.
 cmp ax,1
 jbe snapDepth1
 cmp ax,4
 jbe snapDepth4
 cmp ax,8
 jbe snapDepth8
 mov ax,24
 jmp snapDepthSet
snapDepth1:
 mov ax,1
 jmp snapDepthSet
snapDepth4:
 mov ax,4
 jmp snapDepthSet
snapDepth8:
 mov ax,8
snapDepthSet:
 mov snapBpp,ax
 cmp wasBpp,0
 je snapResolveRect
 mov ax,wasBpp
 cmp ax,1
 je snapSetBpp
 cmp ax,4
 je snapSetBpp
 cmp ax,8
 je snapSetBpp
 cmp ax,24
 jne snapCleanupFail
snapSetBpp:
 mov snapBpp,ax
snapResolveRect:
 cmp word ptr wasRect,0FFFFh
 jne snapCustom
 mov word ptr snapX0,0
 mov word ptr snapY0,0
 mov ax,snapW
 dec ax
 mov snapX1,ax
 mov ax,snapH
 dec ax
 mov snapY1,ax
 jmp snapValidate
snapCustom:
 mov ax,wasRect
 mov snapX0,ax
 mov ax,wasRect+2
 mov snapY0,ax
 mov ax,wasRect+4
 mov snapX1,ax
 mov ax,wasRect+6
 mov snapY1,ax
snapValidate:
 mov ax,snapX1
 cmp ax,snapX0
 jb snapCleanupFail
 cmp ax,snapW
 jae snapCleanupFail
 mov ax,snapY1
 cmp ax,snapY0
 jb snapCleanupFail
 cmp ax,snapH
 jae snapCleanupFail
 ; Compute row bytes padded to DWORD alignment.
 mov ax,snapX1
 sub ax,snapX0
 inc ax
 mov snapW,ax
 mov ax,snapY1
 sub ax,snapY0
 inc ax
 mov snapH,ax
 mov ax,snapW
 mul snapBpp              ; DX:AX = bits/row; cap under 65535
 or dx,dx
 jne snapCleanupFail
 add ax,31
 jc snapCleanupFail
 shr ax,1
 shr ax,1
 shr ax,1
 shr ax,1
 shr ax,1
 shl ax,1
 shl ax,1                 ; ((bits+31)/32)*4
 cmp ax,4096
 ja snapCleanupFail
 mov snapStride,ax
 ; BMP file header 14 bytes + 40-byte BITMAPINFOHEADER.
 mov ax,ds
 mov es,ax
 lea di,snapBF
 xor ax,ax
 mov cx,27
 rep stosw
 mov word ptr snapBF,4D42h
 mov word ptr snapBF+14,40
 mov ax,snapW
 mov word ptr snapBF+18,ax
 mov ax,snapH
 mov word ptr snapBF+22,ax
 mov word ptr snapBF+26,1
 mov ax,snapBpp
 mov word ptr snapBF+28,ax
 mov ax,snapStride
 mul snapH
 mov word ptr snapBF+34,ax
 mov word ptr snapBF+36,dx
 xor ax,ax
 cmp snapBpp,24
 je snapPaletteSet
 mov ax,1
 mov cx,snapBpp
 shl ax,cl               ; 8086 variable shift by CL, CL=1,4 or 8
snapPaletteSet:
 mov snapPaletteN,ax
 mov bx,ax
 shl bx,1
 shl bx,1                 ; 4-byte RGBQUAD each
 mov ax,54
 add ax,bx
 mov word ptr snapBF+10,ax
 mov ax,snapStride
 mul snapH
 add ax,word ptr snapBF+10
 adc dx,0
 mov word ptr snapBF+2,ax
 mov word ptr snapBF+4,dx
 ; BuildPalette temporarily fills snapRow; it is written to disk
 ; before the first pixel/FAST strip reuses this storage.
 call BuildPalette
 ; Fixed EGA palette is only a fallback. In 4-bpp direct VGA/SVGA
 ; capture, pixel indices are interpreted through the CURRENT hardware
 ; attribute palette and DAC: static EGA RGB values are not correct.
 ; The palette occupies snapRow until written to the BMP, before video
 ; rows reuse it. This adds no separate 1024-byte allocation.
 ; FAST refuses unknown memory layouts. AUTO may fall back to COMPAT.
 cmp wasSnapMode,0
 je snapCreateFile
 call SnapDirectProbe
 jnc snapUseDirect
 cmp wasSnapMode,1
 je snapFastUnsupported
 jmp snapCreateFile
snapUseDirect:
 mov snapMethod,2
 mov snapBufUsed,0
 cmp snapDirect,3
 jne snapCreateFile
 cmp snapBpp,4
 jne snapCreateFile
 call SnapVgaPalette      ; read active VGA palette before capturing rows
snapCreateFile:
 mov ah,3Ch
 xor cx,cx
 mov dx,offset wasInput
 call Dos3Call
 jc snapCleanupFail
 mov snapFile,ax
 mov bx,ax
 mov ah,40h
 mov cx,54
 mov dx,offset snapBF
 call Dos3Call
 jc snapCloseFail
 cmp ax,54
 jne snapCloseFail
 mov cx,snapPaletteN
 jcxz snapRowFirst
 shl cx,1
 shl cx,1
 mov bx,snapFile
 mov ah,40h
 mov dx,offset snapRow
 call Dos3Call
 jc snapCloseFail
 cmp ax,cx
 jne snapCloseFail
snapRowFirst:
 mov ax,snapY1
 mov snapY,ax
snapRowLoop:
 cmp snapDirect,0
 jne snapDirectBufferRow
 ; Original GDI GetPixel compatibility path, one BMP row at a time.
 mov ax,ds
 mov es,ax
 lea di,snapRow
 mov cx,snapStride
 shr cx,1
 xor ax,ax
 rep stosw
 jmp snapLegacyPixelStart
snapDirectBufferRow:
 ; Use all 4096 bytes of snapRow as a bottom-up BMP scanline batch.
 mov ax,ds
 mov es,ax
 mov di,offset snapRow
 add di,snapBufUsed
 mov cx,snapStride
 shr cx,1
 xor ax,ax
 cld
 rep stosw
 call SnapDirectRow
 jc snapCloseFail
 mov ax,snapBufUsed
 add ax,snapStride
 mov snapBufUsed,ax
 mov bx,snapY
 cmp bx,snapY0
 je snapDirectFlush
 add ax,snapStride
 cmp ax,4096
 ja snapDirectFlush
 jmp snapDirectNext
snapDirectFlush:
 mov bx,snapFile
 mov ah,40h
 mov cx,snapBufUsed
 mov dx,offset snapRow
 call Dos3Call
 jc snapCloseFail
 cmp ax,cx
 jne snapCloseFail
 mov snapBufUsed,0
 call Yield
snapDirectNext:
 mov ax,snapY
 cmp ax,snapY0
 je snapSuccess
 dec snapY
 jmp snapRowLoop
snapLegacyPixelStart:
 mov ax,snapX0
 mov snapX,ax
 mov snapPixel,0
snapPixelLoop:
 push snapHdc
 push snapX
 push snapY
 call GetPixel
 mov snapPixelLo,ax
 mov snapPixelHi,dx
 mov ax,snapBpp
 cmp ax,24
 je snapPixel24
 cmp ax,8
 je snapPixel8
 cmp ax,4
 je snapPixel4
 call MapMono
 or al,al
 jnz snapMonoOn
 jmp snapPixelNext
snapMonoOn:
 mov bx,snapPixel
 mov dx,bx
 shr bx,1
 shr bx,1
 shr bx,1                ; byte offset = pixel/8
 and dl,7
 mov cl,7
 sub cl,dl
 mov al,1
 shl al,cl
 or snapRow[bx],al
 jmp snapPixelNext
snapPixel4:
 call MapEGA              ; index in AL, 0..15
 mov bx,snapPixel
 mov dl,bl
 shr bx,1
 test dl,1
 jnz snapLowNibble
 shl al,1
 shl al,1
 shl al,1
 shl al,1
 or snapRow[bx],al
 jmp snapPixelNext
snapLowNibble:
 or snapRow[bx],al
 jmp snapPixelNext
snapPixel8:
 call Map332              ; index in AL
 mov bx,snapPixel
 mov snapRow[bx],al
 jmp snapPixelNext
snapPixel24:
 mov bx,snapPixel
 mov ax,bx
 shl bx,1
 add bx,ax                ; 3 bytes per pixel
 mov ax,snapPixelLo
 mov dx,snapPixelHi
 mov snapRow[bx],dl        ; B
 mov snapRow[bx+1],ah     ; G
 mov snapRow[bx+2],al     ; R
snapPixelNext:
 inc snapPixel
 inc snapX
 mov ax,snapX
 cmp ax,snapX1
 jbe snapPixelLoop
snapWriteRow:
 mov bx,snapFile
 mov ah,40h
 mov cx,snapStride
 mov dx,offset snapRow
 call Dos3Call
 jc snapCloseFail
 cmp ax,cx
 jne snapCloseFail
 call Yield
 mov ax,snapY
 cmp ax,snapY0
 je snapSuccess
 dec snapY
 jmp snapRowLoop
snapSuccess:
 mov bx,snapFile
 mov ah,3Eh
 call Dos3Call
 mov snapFile,0FFFFh
 xor ax,ax
 mov wasResult,ax
 clc
 jmp snapCleanup
snapCloseFail:
 mov bx,snapFile
 mov ah,3Eh
 call Dos3Call
 mov snapFile,0FFFFh
 jmp snapCleanupFail
snapFastUnsupported:
 mov snapMethod,3 ; unsupported means no capture was attempted
 mov wasResult,2  ; unsupported FAST mode or non-byte-aligned region
 stc
 jmp snapCleanup
snapCleanupFail:
 mov wasResult,1
 stc
snapCleanup:
 pushf
 xor ax,ax
 push ax
 push snapHdc
 call ReleaseDC
 popf
 jmp snapDone
snapFail:
 mov wasResult,1
 stc
snapDone:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
SnapDo endp


; FAST hardware probe. Runs only on explicit MODE=FAST/AUTO.
; Never infer the framebuffer from Windows GDI dimensions alone:
; standard BIOS mode AND exact resolution must agree. Region accesses
; require byte alignment. Unknown SVGA/banked modes never access video RAM.
; For EGA/VGA, 1-bpp capture means any non-black indexed pixel -> white.
SnapDirectProbe proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 mov snapDirect,0
 mov snapVideoMode,0FFh
 cmp snapBpp,1
 je snapProbeDepthOK
 cmp snapBpp,4
 jne snapProbeFail
snapProbeDepthOK:
 mov ax,snapX0
 test ax,7
 jnz snapProbeFail
 mov ax,snapW
 test ax,7
 jnz snapProbeFail
 mov ax,snapX0
 shr ax,1
 shr ax,1
 shr ax,1
 mov snapXByte,ax
 mov ax,snapW
 shr ax,1
 shr ax,1
 shr ax,1
 mov snapCopyN,ax
 ; Windows 1.x/2.x/3.0 in real mode permit BIOS mode inquiry.
 ; DOS/BIOS may alter the extra segments, so save them around INT 10h.
 push ds
 mov ah,0Fh
 int 10h
 pop ds
 and al,7Fh
 mov snapVideoMode,al
 cmp al,06h
 je snapProbeCga
 cmp al,07h
 je snapProbeHerc
 cmp al,0Dh
 je snapProbeEga320
 cmp al,0Eh
 je snapProbeEga200
 cmp al,0Fh
 je snapProbeEga350Mono
 cmp al,10h
 je snapProbeEga350
 cmp al,11h
 je snapProbeVgaMono
 cmp al,12h
 je snapProbeVgaColor
 ; DOSBox-X 06Ah is 800x600 16-colour planar mode (M_LIN4).
 ; Confirm exact GDI geometry before touching A000 graphics memory.
 cmp al,6Ah
 je snapProbeSvga800
 jmp snapProbeFail
snapProbeCga:
 cmp snapScreenW,640
 jne snapProbeFail
 cmp snapScreenH,200
 jne snapProbeFail
 mov snapDirect,1
 mov snapVideoSeg,0B800h
 mov snapLineRaw,80
 jmp snapProbeOK
snapProbeHerc:
 ; Only the standard 720x348 four-bank memory arrangement is supported.
 cmp snapScreenW,720
 jne snapProbeFail
 cmp snapScreenH,348
 jne snapProbeFail
 mov snapDirect,2
 ; Page 1 is selected by HGC mode control bit 7.
 mov dx,03B8h
 in al,dx
 mov bx,0B000h
 test al,80h
 jz snapHercPageReady
 mov bx,0B800h
snapHercPageReady:
 mov snapVideoSeg,bx
 mov snapLineRaw,90
 jmp snapProbeOK
snapProbeEga320:
 cmp snapScreenW,320
 jne snapProbeFail
 cmp snapScreenH,200
 jne snapProbeFail
 mov snapLineRaw,40
 mov snapGCPlanes,4
 jmp snapProbeEgaOK
snapProbeEga200:
 cmp snapScreenW,640
 jne snapProbeFail
 cmp snapScreenH,200
 jne snapProbeFail
 mov snapLineRaw,80
 mov snapGCPlanes,4
 jmp snapProbeEgaOK
snapProbeEga350Mono:
 cmp snapScreenW,640
 jne snapProbeFail
 cmp snapScreenH,350
 jne snapProbeFail
 mov snapLineRaw,80
 mov snapGCPlanes,1
 jmp snapProbeEgaOK
snapProbeEga350:
 cmp snapScreenW,640
 jne snapProbeFail
 cmp snapScreenH,350
 jne snapProbeFail
 mov snapLineRaw,80
 mov snapGCPlanes,4
 jmp snapProbeEgaOK
snapProbeVgaMono:
 cmp snapScreenW,640
 jne snapProbeFail
 cmp snapScreenH,480
 jne snapProbeFail
 mov snapLineRaw,80
 mov snapGCPlanes,1
 jmp snapProbeEgaOK
snapProbeSvga800:
 cmp snapScreenW,800
 jne snapProbeFail
 cmp snapScreenH,600
 jne snapProbeFail
 ; 800 / 8 = 100 bytes per plane row; 600 * 100 = 60000
 ; fits in the 64KiB A000 hardware aperture (no bank switching).
 mov snapLineRaw,100
 mov snapGCPlanes,4
 jmp snapProbeEgaOK
snapProbeVgaColor:
 cmp snapScreenW,640
 jne snapProbeFail
 cmp snapScreenH,480
 jne snapProbeFail
 mov snapLineRaw,80
 mov snapGCPlanes,4
snapProbeEgaOK:
 mov snapDirect,3
 mov snapVideoSeg,0A000h
snapProbeOK:
 ; 4-bpp direct capture requires four readable EGA/VGA planes.
 ; Mono hardware and EGA/VGA one-plane modes remain 1-bpp only.
 cmp snapBpp,4
 jne snapProbeAccepted
 cmp snapDirect,3
 jne snapProbeFail
 cmp snapGCPlanes,4
 jne snapProbeFail
snapProbeAccepted:
 clc
 jmp snapProbeExit
snapProbeFail:
 mov snapDirect,0
 stc
snapProbeExit:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
SnapDirectProbe endp

; Direct monochrome scanline copy. Caller cleared snapRow including BMP
; DWORD padding; CF=0 means a complete row can safely be written.
; No GDI calls, no allocation, and no yielding while graphics registers
; are temporarily changed. Hardware registers are restored before return.
SnapDirectRow proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 mov ax,snapY
 cmp snapDirect,1
 je snapRowCga
 cmp snapDirect,2
 je snapRowHerc
 cmp snapDirect,3
 je snapRowEga
 stc
 jmp snapRowReturn
snapRowCga:
 ; CGA mode 6: 80 bytes per line, odd rows in +2000h bank.
 mov bx,ax
 shr ax,1
 mov cx,80
 mul cx
 test bx,1
 jz snapCgaEven
 add ax,2000h
snapCgaEven:
 add ax,snapXByte
 mov si,ax
 jmp snapRowMonoCopy
snapRowHerc:
 ; Hercules: four 8 KiB banks, 90 bytes/line, y MOD 4.
 mov bx,ax
 shr ax,1
 shr ax,1
 mov cx,90
 mul cx
 and bx,3
 mov cl,13
 shl bx,cl
 add ax,bx
 add ax,snapXByte
 mov si,ax
snapRowMonoCopy:
 mov bx,snapVideoSeg
 push ds
 mov ax,ds
 mov es,ax
 mov ds,bx
 lea di,snapRow
 add di,snapBufUsed
 mov cx,snapCopyN
 cld
 rep movsb
 pop ds
 clc
 jmp snapRowReturn
snapRowEga:
 cmp snapBpp,4
 jne snapRowEgaMono
 call SnapDirectRow4
 jmp snapRowReturn
snapRowEgaMono:
 ; EGA/VGA mode 0Dh..12h: planar 1/4-plane memory at A000:0000.
 ; Read-map register 04h selects each plane. Preserve caller's mode 05h
 ; as its read-mode bit may be 1 (colour compare) before our access.
 mov bx,snapLineRaw
 mul bx
 add ax,snapXByte
 mov si,ax
 mov ax,0A000h
 mov es,ax
 mov dx,03CEh
 in al,dx
 mov snapGCIndex,al
 mov al,05h
 out dx,al
 inc dx
 in al,dx
 mov snapGCMode,al
 and al,0F7h
 out dx,al
 dec dx
 mov al,04h
 out dx,al
 inc dx
 in al,dx
 mov snapGCRead,al
 xor bx,bx
snapPlaneLoop:
 ; Each source bit represents one pixel. OR planes -> monochrome mask.
 mov al,bl
 out dx,al
 mov di,offset snapRow
 add di,snapBufUsed
 mov cx,snapCopyN
 push si
snapPlaneByte:
 mov al,es:[si]
 or [di],al
 inc si
 inc di
 loop snapPlaneByte
 pop si
 inc bl
 cmp bl,snapGCPlanes
 jb snapPlaneLoop
 ; Restore read-map, read-mode and the GC index even on completion.
 mov al,snapGCRead
 out dx,al
 dec dx
 mov al,05h
 out dx,al
 inc dx
 mov al,snapGCMode
 out dx,al
 dec dx
 mov al,snapGCIndex
 out dx,al
 clc
snapRowReturn:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
SnapDirectRow endp

; Convert four planar EGA/VGA bitplanes to indexed 4-bpp BMP nibbles.
; All plane reads happen while the GC is in read mode 0. The VGA/EGA
; graphics-controller index, read-map, and mode are restored BEFORE
; any CPU-intensive packing or cooperative yielding occurs.
; Output order is left-to-right, two pixels per byte, high nibble first.
SnapDirectRow4 proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 push bp
 mov ax,snapY
 mov bx,snapLineRaw
 mul bx                  ; planar scanline offset under 64 KB
 add ax,snapXByte
 mov si,ax
 mov ax,0A000h
 mov es,ax
 mov dx,03CEh
 in al,dx
 mov snapGCIndex,al
 mov al,05h
 out dx,al
 inc dx
 in al,dx
 mov snapGCMode,al
 and al,0F7h             ; force read mode 0
 out dx,al
 dec dx
 mov al,04h
 out dx,al
 inc dx
 in al,dx
 mov snapGCRead,al
 xor bx,bx               ; plane 0..3
 mov di,offset snapPlaneBuf
snap4ReadPlane:
 mov al,bl
 out dx,al               ; 3CF, read-map select
 mov cx,snapCopyN         ; raw 8-pixel groups per row
 push si
snap4ReadByte:
 mov al,es:[si]
 mov [di],al
 inc si
 inc di
 loop snap4ReadByte
 pop si
 ; Each plane occupies its own fixed 100-byte slot.
 mov ax,100
 sub ax,snapCopyN
 add di,ax
 inc bl
 cmp bl,4
 jb snap4ReadPlane
 ; Restore the previous read-map, read mode and GC register index.
 mov al,snapGCRead
 out dx,al
 dec dx
 mov al,05h
 out dx,al
 inc dx
 mov al,snapGCMode
 out dx,al
 dec dx
 mov al,snapGCIndex
 out dx,al
 ; Expand each group of eight 4-bit indexed pixels into four BMP bytes.
 xor bx,bx
 mov di,offset snapRow
 add di,snapBufUsed
snap4Group:
 mov dl,80h              ; start at leftmost pixel of an 8-pixel group
 mov cx,8
 xor bp,bp               ; 0=high nibble, 1=low nibble
snap4Pixel:
 xor al,al
 test snapPlaneBuf[bx],dl
 jz snap4NoP0
 or al,1
snap4NoP0:
 test snapPlaneBuf[bx+100],dl
 jz snap4NoP1
 or al,2
snap4NoP1:
 test snapPlaneBuf[bx+200],dl
 jz snap4NoP2
 or al,4
snap4NoP2:
 test snapPlaneBuf[bx+300],dl
 jz snap4NoP3
 or al,8
snap4NoP3:
 cmp bp,0
 jne snap4LowNibble
 shl al,1
 shl al,1
 shl al,1
 shl al,1
 mov [di],al
 mov bp,1
 jmp snap4NextPixel
snap4LowNibble:
 or [di],al
 inc di
 xor bp,bp
snap4NextPixel:
 shr dl,1
 loop snap4Pixel
 inc bx
 cmp bx,snapCopyN
 jb snap4Group
 clc
 pop bp
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
SnapDirectRow4 endp

; In native 4-bpp VGA modes, the four video planes encode logical
; attribute indices, NOT fixed RGB colours. The VGA attribute controller
; remaps each index to a DAC entry and the DAC defines its live colour.
; Read those 16 mappings once into the BMP RGBQUAD palette. This avoids
; per-pixel GDI and preserves Windows palette settings and custom themes.
; Only called for recognised A000 planar modes; a non-VGA adapter keeps
; BuildPalette's legacy fallback. No video writes are performed.
SnapVgaPalette proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push bp
 push ds
 push es
 ; The supported 12h (VGA) and 6Ah (SVGA) modes are known VGA.
 ; On a less common EGA mode, probe the VGA display-combination BIOS
 ; before reading DAC ports. EGA-only cards retain the fixed fallback.
 cmp snapVideoMode,12h
 je snapVgaPalReady
 cmp snapVideoMode,6Ah
 je snapVgaPalReady
 push ds
 push es
 mov ax,1A00h
 int 10h
 pop es
 pop ds
 cmp al,1Ah
 jne snapVgaPalDone
snapVgaPalReady:
 ; Remember attribute index. Reading 3DAh resets the flip-flop.
 mov dx,03C0h
 in al,dx
 mov snapAttrOld,al
 mov al,10h            ; VGA attribute mode control, bit 7=P54S
 call SnapAttrRead
 mov snapAttrMode,al
 mov al,14h            ; VGA colour select register
 call SnapAttrRead
 mov snapColorSel,al
 mov dx,03C6h         ; PEL mask
 in al,dx
 mov snapPelMask,al
 xor bx,bx
 mov di,offset snapRow ; 16 RGBQUADs (B,G,R,0)
snapVgaPalLoop:
 mov al,bl
 call SnapAttrRead     ; logical pixel index -> attribute palette
 and al,3Fh
 test snapAttrMode,80h ; P54S: bits 5-4 from Color Select
 jz snapVgaAttrLowOK
 and al,0Fh
 mov ah,snapColorSel
 and ah,03h
 shl ah,1
 shl ah,1
 shl ah,1
 shl ah,1
 or al,ah
snapVgaAttrLowOK:
 mov ah,snapColorSel
 and ah,0Ch         ; color select bits 2-3 -> DAC bits 6-7
 shl ah,1
 shl ah,1
 shl ah,1
 shl ah,1
 or al,ah
 and al,snapPelMask
 mov dx,03C7h         ; VGA DAC read address
 out dx,al
 mov dx,03C9h         ; subsequent reads R, G, B (6-bit)
 in al,dx
 call SnapDac6
 mov [di+2],al       ; BMP red
 in al,dx
 call SnapDac6
 mov [di+1],al       ; BMP green
 in al,dx
 call SnapDac6
 mov [di],al         ; BMP blue
 mov byte ptr [di+3],0
 add di,4
 inc bl
 cmp bl,16
 jb snapVgaPalLoop
 ; Restore the attribute-controller index, with video enabled.
 mov dx,03DAh
 in al,dx
 mov dx,03C0h
 mov al,snapAttrOld
 or al,20h
 out dx,al
snapVgaPalDone:
 pop es
 pop ds
 pop bp
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
SnapVgaPalette endp

; AL = VGA DAC component 0..63, convert to BMP 0..255.
; Bit replication equals (value*255)/63 for key EGA levels 0,21,42,63.
SnapDac6 proc near
 push bx
 and al,3Fh
 mov bl,al
 shl al,1
 shl al,1
 shr bl,1
 shr bl,1
 shr bl,1
 shr bl,1
 or al,bl
 pop bx
 ret
SnapDac6 endp

; AL = VGA attribute register number, returns AL = current value.
; Index port 3C0h is write-only for data; 3C1h is the read port.
; Keep attribute video-enable bit set in index writes.
SnapAttrRead proc near
 push bx
 push dx
 mov bl,al
 mov dx,03DAh
 in al,dx            ; reset attribute flip-flop
 mov dx,03C0h
 mov al,bl
 or al,20h
 out dx,al           ; address/index phase
 mov dx,03C1h
 in al,dx            ; read attribute data without changing it
 pop dx
 pop bx
 ret
SnapAttrRead endp

; COLORREF 00BBGGRR in DX:AX from GDI GetPixel.
MapMono proc near
 push bx
 xor bx,bx
 mov al,byte ptr snapPixelLo
 xor ah,ah
 add bx,ax
 mov al,byte ptr snapPixelLo+1
 xor ah,ah
 add bx,ax
 mov al,byte ptr snapPixelHi
 xor ah,ah
 add bx,ax
 mov al,0
 cmp bx,384
 jb snapMonoDone
 mov al,1
snapMonoDone:
 pop bx
 ret
MapMono endp

MapEGA proc near
 push bx
 push cx
 push dx
 mov ax,snapPixelLo
 mov dx,snapPixelHi
 xor bl,bl
 cmp dl,96
 jb snapBlueDone
 or bl,1
snapBlueDone:
 cmp ah,96
 jb snapGreenDone
 or bl,2
snapGreenDone:
 cmp al,96
 jb snapRedDone
 or bl,4
snapRedDone:
 cmp dl,192
 jae snapBright
 cmp ah,192
 jae snapBright
 cmp al,192
 jb snapEgaDone
snapBright:
 or bl,8
snapEgaDone:
 mov al,bl
 pop dx
 pop cx
 pop bx
 ret
MapEGA endp

Map332 proc near
 push bx
 push cx
 mov ax,snapPixelLo
 mov dx,snapPixelHi
 mov bl,al
 shr bl,1
 shr bl,1
 shr bl,1
 mov cl,ah
 shr cl,1
 shr cl,1
 shr cl,1
 shl bl,1
 shl bl,1
 shl bl,1
 shl bl,1
 shl bl,1
 shl cl,1
 shl cl,1
 or bl,cl
 mov cl,dl
 shr cl,1
 shr cl,1
 shr cl,1
 shr cl,1
 shr cl,1
 shr cl,1
 or bl,cl
 mov al,bl
 pop cx
 pop bx
 ret
Map332 endp

BuildPalette proc near
 push ax
 push bx
 push cx
 push dx
 push di
 mov ax,snapPaletteN
 or ax,ax
 jz snapPaletteDone
 lea di,snapRow
 cmp snapBpp,1
 jne snapPaletteColor
 mov byte ptr [di],0
 mov byte ptr [di+1],0
 mov byte ptr [di+2],0
 mov byte ptr [di+3],0
 mov byte ptr [di+4],255
 mov byte ptr [di+5],255
 mov byte ptr [di+6],255
 mov byte ptr [di+7],0
 jmp snapPaletteDone
snapPaletteColor:
 ; Generate simple EGA/3-3-2 standard palettes from RGB index.
 xor bx,bx
 mov cx,snapPaletteN
snapPaletteIndex:
 cmp snapBpp,4
 jne snapPal332
 mov al,bl
 test al,1
 jz snapPalBlue0
 mov byte ptr [di],170
 jmp snapPalGreen
snapPalBlue0:
 mov byte ptr [di],0
snapPalGreen:
 mov al,bl
 test al,2
 jz snapPalGreen0
 mov byte ptr [di+1],170
 jmp snapPalRed
snapPalGreen0:
 mov byte ptr [di+1],0
snapPalRed:
 mov al,bl
 test al,4
 jz snapPalRed0
 mov byte ptr [di+2],170
 jmp snapPalBright
snapPalRed0:
 mov byte ptr [di+2],0
snapPalBright:
 mov al,bl
 test al,8
 jz snapPalNext
 mov ax,di
 ; brighten existing 170 to 255; dark 0 to 85 (except 8=gray)
 cmp byte ptr [di],0
 jne snapPB1
 mov byte ptr [di],85
 jmp snapPG1
snapPB1:
 mov byte ptr [di],255
snapPG1:
 cmp byte ptr [di+1],0
 jne snapPG2
 mov byte ptr [di+1],85
 jmp snapPR1
snapPG2:
 mov byte ptr [di+1],255
snapPR1:
 cmp byte ptr [di+2],0
 jne snapPR2
 mov byte ptr [di+2],85
 jmp snapPalNext
snapPR2:
 mov byte ptr [di+2],255
 jmp snapPalNext
snapPal332:
 ; B2 * 85 ; G3/R3 approximately 36 * level
 mov al,bl
 and al,3
 mov dl,85
 mul dl
 mov [di],al
 mov al,bl
 shr al,1
 shr al,1
 and al,7
 mov dl,36
 mul dl
 mov [di+1],al
 mov al,bl
 shr al,1
 shr al,1
 shr al,1
 shr al,1
 shr al,1
 mov dl,36
 mul dl
 mov [di+2],al
snapPalNext:
 mov byte ptr [di+3],0
 add di,4
 inc bx
 dec cx
 jz snapPaletteDone
 jmp snapPaletteIndex
snapPaletteDone:
 pop di
 pop dx
 pop cx
 pop bx
 pop ax
 ret
BuildPalette endp
end
