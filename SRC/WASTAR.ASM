; WAS TAR writer - standard USTAR / method STORE (uncompressed).
; DOS 3.3 sequential I/O; fixed two 512-byte blocks; no archive index.
.8086
.model small
extrn Dos3Call:far
extrn wasInput:byte
extrn wasResult:word
PUBLIC TarCreate,TarAdd,TarClose

.data
tarHandle   dw 0FFFFh
tarReadH    dw 0FFFFh
tarSource   db 260 dup(0)
tarPrefix   db 130 dup(0)
tarName     db 100 dup(0)
tarDTA      db 43 dup(0)
tarOldDTA   dw 0,0
tarHeader   db 512 dup(0)
tarBuffer   db 1024 dup(0)  ; 2x I/O throughput without large DGROUP cost
tarWriteBytes dw 0
tarBytes    dw 0
tarSizeLo   dw 0
tarSizeHi   dw 0

.code
TarCreate proc near
 push ax
 push bx
 push cx
 push dx
 cmp tarHandle,0FFFFh
 je tarOpen
 mov bx,tarHandle
 mov ah,3Eh
 call Dos3Call
 mov tarHandle,0FFFFh
tarOpen:
 mov ah,3Ch
 xor cx,cx
 mov dx,offset wasInput
 call Dos3Call
 jc tarCreateFail
 mov tarHandle,ax
 mov wasResult,0
 clc
 jmp tarCreateDone
tarCreateFail:
 mov wasResult,ax
 stc
tarCreateDone:
 pop dx
 pop cx
 pop bx
 pop ax
 ret
TarCreate endp

TarAdd proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 cmp tarHandle,0FFFFh
 je tarAddFail
 ; Copy source path, test for wildcard and extract parent directory.
 lea si,wasInput
 lea di,tarSource
 mov cx,259
 xor bx,bx                 ; BX=last separator index (end of prefix)
 xor dx,dx                 ; DX=1 wildcard found
 tarPathLoop:
 lodsb
 or al,al
 jz tarPathDone
 cmp al,'*'
 je tarWildcard
 cmp al,'?'
 je tarWildcard
 cmp al,5Ch
 je tarSeparator
 cmp al,'/'
 je tarSeparator
 jmp tarPathStore
 tarWildcard:
 mov dx,1
 jmp tarPathStore
 tarSeparator:
 mov bx,di
 sub bx,offset tarSource
 inc bx
 tarPathStore:
 stosb
 loop tarPathLoop
 tarPathDone:
 mov byte ptr [di],0
 cmp dx,0
 jne tarFindSet
 ; No wildcard: use filename after final backslash or drive separator.
 lea si,tarSource
 lea di,tarName
 xor dx,dx
 tarNameScan:
 mov al,[si]
 or al,al
 jz tarNameCopy
 cmp al,5Ch
 je tarNameSep
 cmp al,'/'
 je tarNameSep
 cmp al,':'
 jne tarNameNext
 tarNameSep:
 mov dx,si
 inc dx
 tarNameNext:
 inc si
 jmp tarNameScan
 tarNameCopy:
 cmp dx,0
 je tarNameRoot
 mov si,dx
 jmp tarNameStart
 tarNameRoot:
 lea si,tarSource
 tarNameStart:
 mov cx,99
 tarNameCp:
 lodsb
 stosb
 or al,al
 jz tarNameSaved
 loop tarNameCp
 mov byte ptr [di],0
 tarNameSaved:
 call TarAddOne
 jmp tarAddDone

 tarFindSet:
 ; Build parent directory prefix for DOS findfirst results.
 lea si,tarSource
 lea di,tarPrefix
 mov cx,bx
 jcxz tarPrefixDone
 cmp cx,129
 ja tarAddFail
 rep movsb
 tarPrefixDone:
 mov byte ptr [di],0
 mov ah,2Fh                 ; Save previous DTA, restore on return
 call Dos3Call
 mov tarOldDTA,bx
 mov tarOldDTA+2,es
 mov ax,ds
 mov es,ax
 mov dx,offset tarDTA
 mov ah,1Ah
 call Dos3Call
 mov dx,offset tarSource
 xor cx,cx
 mov ah,4Eh
 call Dos3Call
 jc tarFindError
 tarFindLoop:
 lea si,tarPrefix
 lea di,tarSource
 mov cx,259
 tarPrefixCopy:
 lodsb
 or al,al
 jz tarPrefixCopied
 stosb
 loop tarPrefixCopy
 tarPrefixCopied:
 mov byte ptr [di],0
 lea si,tarDTA+30
 lea di,tarName
 mov cx,99
 tarFindNameCopy:
 lodsb
 stosb
 or al,al
 jz tarFindNameSaved
 loop tarFindNameCopy
 tarFindNameSaved:
 lea si,tarName
 lea di,tarSource
 tarFindAppendBase:
 cmp byte ptr [di],0
 je tarFindAppend
 inc di
 jmp tarFindAppendBase
 tarFindAppend:
 mov cx,100
 tarFindAppendLoop:
 lodsb
 stosb
 or al,al
 jz tarFindAppendDone
 loop tarFindAppendLoop
 tarFindAppendDone:
 call TarAddOne
 jc tarFindError
 mov ah,4Fh
 call Dos3Call
 jnc tarFindLoop
 ; No more matches is normal (DOS error 18).
 cmp ax,18
 jne tarFindError
 mov wasResult,0
 clc
 jmp tarFindRestore
 tarFindError:
 mov wasResult,ax
 stc
 tarFindRestore:
 pushf
 mov dx,tarOldDTA
 mov ax,tarOldDTA+2
 push ds
 mov ds,ax
 mov ah,1Ah
 call Dos3Call
 pop ds
 popf
 jmp tarAddDone
 tarAddFail:
 mov wasResult,1
 stc
 tarAddDone:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
TarAdd endp

TarAddOne proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 mov ax,3D00h
 mov dx,offset tarSource
 call Dos3Call
 jc tarAddOneFail
 mov tarReadH,ax
 ; Read size from DOS seek-end (DX:AX), then reset to beginning.
 mov bx,ax
 xor cx,cx
 xor dx,dx
 mov ax,4202h
 call Dos3Call
 jc tarAddOneCloseFail
 mov tarSizeLo,ax
 mov tarSizeHi,dx
 xor cx,cx
 xor dx,dx
 mov ax,4200h
 call Dos3Call
 jc tarAddOneCloseFail
 ; Clear header and prepare USTAR values.
 mov ax,ds
 mov es,ax
 lea di,tarHeader
 xor ax,ax
 mov cx,256
 rep stosw
 lea si,tarName
 lea di,tarHeader
 mov cx,99
 tarHName:
 lodsb
 or al,al
 jz tarHNameDone
 stosb
 loop tarHName
 tarHNameDone:
 lea si,tarMode
 lea di,tarHeader+100
 mov cx,8
 rep movsb
 lea si,tarZeros8
 lea di,tarHeader+108
 mov cx,8
 rep movsb
 lea si,tarZeros8
 lea di,tarHeader+116
 mov cx,8
 rep movsb
 lea si,tarZeros12
 lea di,tarHeader+136
 mov cx,12
 rep movsb
 ; POSIX USTAR checksum is computed treating bytes 148..155 as spaces.
 mov di,offset tarHeader+148
 mov cx,8
 mov al,' '
 rep stosb
 mov byte ptr tarHeader+156,'0'
 mov word ptr tarHeader+257,7375h    ; 'us'
 mov word ptr tarHeader+259,6174h    ; 'ta'
 mov byte ptr tarHeader+261,'r'
 mov word ptr tarHeader+263,3030h     ; '00'
 ; Octal 11 digits, null terminator in header.size (offset 124).
 mov ax,tarSizeLo
 mov dx,tarSizeHi
 lea di,tarHeader+134
 mov cx,11
 tarOctSize:
 mov bx,ax
 and bx,7
 add bl,'0'
 mov [di],bl
 dec di
 shr dx,1
 rcr ax,1
 shr dx,1
 rcr ax,1
 shr dx,1
 rcr ax,1
 loop tarOctSize
 ; 16-bit checksum enough for standard 512-byte headers.
 lea si,tarHeader
 mov cx,512
 xor ax,ax
 tarChkSum:
 mov bl,[si]
 xor bh,bh
 add ax,bx
 inc si
 loop tarChkSum
 lea di,tarHeader+153
 mov cx,6
 tarChkDigits:
 mov bx,ax
 and bx,7
 add bl,'0'
 mov [di],bl
 dec di
 shr ax,1
 shr ax,1
 shr ax,1
 loop tarChkDigits
 mov byte ptr tarHeader+154,0
 mov byte ptr tarHeader+155,' '
 mov bx,tarHandle
 mov ah,40h
 mov cx,512
 mov dx,offset tarHeader
 call Dos3Call
 jc tarAddOneCloseFail
 cmp ax,512
 jne tarAddOneCloseFail
 ; Up to two 512-byte TAR blocks per DOS I/O. The source length is
 ; never rounded for the header; only the final disk write is padded.
 ; This halves guest DOS 21h traffic without exceeding the 10% DGROUP
 ; growth budget on a 640K XT.
 tarCopyNext:
 mov bx,tarReadH
 mov ah,3Fh
 mov cx,1024
 mov dx,offset tarBuffer
 call Dos3Call
 jc tarAddOneCloseFail
 or ax,ax
 jz tarCopySuccess
 mov tarBytes,ax
 cmp ax,1024
 je tarBlockFull
 mov cx,ax
 add cx,511
 and cx,0FE00h        ; round up to whole 512-byte USTAR blocks
 mov tarWriteBytes,cx
 mov di,offset tarBuffer
 add di,ax
 sub cx,ax
 xor al,al
 rep stosb
 jmp tarBlockWrite
 tarBlockFull:
 mov tarWriteBytes,1024
 tarBlockWrite:
 mov bx,tarHandle
 mov ah,40h
 mov cx,tarWriteBytes
 mov dx,offset tarBuffer
 call Dos3Call
 jc tarAddOneCloseFail
 cmp ax,tarWriteBytes
 jne tarAddOneCloseFail
 cmp tarBytes,1024
 je tarCopyNext
 tarCopySuccess:
 mov bx,tarReadH
 mov ah,3Eh
 call Dos3Call
 mov tarReadH,0FFFFh
 mov wasResult,0
 clc
 jmp tarAddOneDone
 tarAddOneCloseFail:
 mov bx,tarReadH
 mov ah,3Eh
 call Dos3Call
 mov tarReadH,0FFFFh
 tarAddOneFail:
 mov wasResult,1
 stc
 tarAddOneDone:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
TarAddOne endp

TarClose proc near
 push ax
 push bx
 push cx
 push dx
 push di
 push es
 cmp tarHandle,0FFFFh
 je tarCloseFail
 mov ax,ds
 mov es,ax
 lea di,tarBuffer
 xor ax,ax
 mov cx,256
 rep stosw
 mov cx,2
 tarCloseNext:
 push cx
 mov bx,tarHandle
 mov ah,40h
 mov cx,512
 mov dx,offset tarBuffer
 call Dos3Call
 pop cx
 jc tarCloseFail
 cmp ax,512
 jne tarCloseFail
 loop tarCloseNext
 mov bx,tarHandle
 mov ah,3Eh
 call Dos3Call
 mov tarHandle,0FFFFh
 mov wasResult,0
 clc
 jmp tarCloseDone
 tarCloseFail:
 mov wasResult,1
 stc
 tarCloseDone:
 pop es
 pop di
 pop dx
 pop cx
 pop bx
 pop ax
 ret
TarClose endp

.data
tarMode    db '0000644',0
tarZeros8  db '0000000',0
tarZeros12 db '00000000000',0
end
