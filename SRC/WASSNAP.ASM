; WAS screenshot: 8086-safe, Win1 GDI GetPixel API, disk-streamed BMP rows.
; Inclusive rectangle X,Y,X1,Y1; optional BPP 1/4/8/24, 0=desktop depth.
; Optimisation deliberately postponed until baseline image UAT has passed.
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
PUBLIC SnapDo

.data
snapHdc      dw 0
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
snapPalette  db 1024 dup(0)
snapRow      db 4096 dup(0)   ; scanline only, not a framebuffer
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
 call BuildPalette
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
 mov dx,offset snapPalette
 call Dos3Call
 jc snapCloseFail
 cmp ax,cx
 jne snapCloseFail
snapRowFirst:
 mov ax,snapY1
 mov snapY,ax
snapRowLoop:
 ; Initialize row to zero; masks and DWORD padding remain clean.
 mov ax,ds
 mov es,ax
 lea di,snapRow
 mov cx,snapStride
 shr cx,1
 xor ax,ax
 rep stosw
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
 lea di,snapPalette
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
