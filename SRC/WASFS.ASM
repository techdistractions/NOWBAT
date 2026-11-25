; WASFS.ASM - 8086/8088 filesystem primitives for WAS (Windows 1/2/3).
; -------------------------------------------------------------------------
; All operations use DOS 2.x/3.x INT 21h through WAS's shared FAR Dos3Call.
; NO Win16 imports, heap, handle table, recursion, or extra transfer segment.
;
; Register/procedure contracts (near calls, DS = WAS DGROUP):
;   FsUnary: AL = DOS function 39h MKDIR, 3Ah RMDIR, 3Bh CHDIR,
;             or 41h DELETE; path in wasInput.
;   FsBinary: AL = 0 COPY, 1 REN, 2 MOVE. Source wasLHS, target wasInput.
;   FsDir: pattern in wasInput (empty means *.*); names go to active LOG.
;   FsPwd: current directory (without drive letter) to active LOG.
; All entry points preserve BX/CX/DX/SI/DI/ES and set:
;   wasResult = 0 on success, 1 on error;
;   wasErrorCode = DOS error number, or 0 on success.
; AX is volatile. Caller does NOT treat error as interpreter abort: IF/ASSERT
; can inspect %RESULT% or %ERRORCODE% after every filesystem command.
;
; Important memory discipline:
;   COPY/MOVE borrow the already-allocated 260-byte wasLine input buffer
;   as a 256-byte transfer block. WAS has finished parsing the current
;   script line before calling us, so overwriting this buffer is safe.
;   DIR owns only a 43-byte DOS DTA (no directory cache or sorting).
;   All DOS handles and the caller's original DTA are restored on exit.
;   Only one WAS script executes at once; this module is non-reentrant.
;
; File semantics:
;   COPY replaces an existing destination (DOS 3Ch) and removes its partial
;   output on copy error. MOVE tries DOS rename first; on error 17 (different
;   device) it performs COPY then deletes source only after full success.
;   REN never replaces an existing file or crosses drives. Wildcards are
;   accepted for DIR only, not for the other filesystem operations.
;   COPY source/destination must be different (case-insensitive path text).
.8086
.model small
extrn Dos3Call:far
extrn EqualStrings:near
extrn LogLine:near
extrn wasInput:byte
extrn wasLHS:byte
extrn wasLine:byte
extrn wasResult:word
extrn wasErrorCode:word
PUBLIC FsUnary,FsBinary,FsDir,FsPwd

.data
fsSourceH   dw 0FFFFh            ; open source, or FFFFh when closed
fsDestH     dw 0FFFFh            ; open destination, or FFFFh when closed
fsLastError dw 0                ; survives DOS close/unlink cleanup
fsMode      db 0                ; 0=COPY, 1=REN, 2=MOVE
extrn fsDta:byte ; DOS findfirst DTA: name at +30
fsOldDta    dw 0,0              ; old offset, segment

.code
; Consolidated DOS mkdir/rmdir/chdir/delete. AH is chosen by script dispatch.
FsUnary proc near
 push bx
 push cx
 push dx
 cmp byte ptr wasInput,0
 je fsUnaryBad
 mov ah,al
 lea dx,wasInput
 call Dos3Call
 jmp fsUnaryStatus
fsUnaryBad:
 mov ax,87                    ; invalid parameter: missing path
 stc
fsUnaryStatus:
 call FsStatus
 pop dx
 pop cx
 pop bx
 ret
FsUnary endp

; FsBinary: two-path dispatcher with a same-volume fast path for MOVE.
FsBinary proc near
 push bx
 push cx
 push dx
 push si
 push di
 push es
 mov fsMode,al
 cmp byte ptr wasLHS,0
 je fsBinaryBad
 cmp byte ptr wasInput,0
 je fsBinaryBad
 cmp al,0
 je fsBinaryCopy
 ; DOS rename uses DS:DX = source, ES:DI = destination.
 push ds
 pop es
 lea dx,wasLHS
 lea di,wasInput
 mov ah,56h
 call Dos3Call
 jnc fsBinaryStatus
 cmp fsMode,2
 jne fsBinaryStatus
 cmp ax,17                  ; DOS ERROR_NOT_SAME_DEVICE
 jne fsBinaryStatus
 ; Cross-drive MOVE: copy completely BEFORE deleting the old file.
 call FsCopy
 jc fsBinaryStatus
 lea dx,wasLHS
 mov ah,41h
 call Dos3Call
 jmp fsBinaryStatus
fsBinaryCopy:
 call FsCopy
 jmp fsBinaryStatus
fsBinaryBad:
 mov ax,87
 stc
fsBinaryStatus:
 call FsStatus
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 ret
FsBinary endp

; Stream file bytes through borrowed 256-byte script-line space. Return
; CF=0 on success; CF=1 and AX=DOS error on failure. No Win16 API calls.
FsCopy proc near
 push bx
 push cx
 push dx
 push si
 push di
 mov fsSourceH,0FFFFh
 mov fsDestH,0FFFFh
 ; Protect the common same-path case before the destructive DOS create.
 lea si,wasLHS
 lea di,wasInput
 call EqualStrings
 jnc fsCopyDifferent
 ; Bail out before opening either handle: never truncate own source.
 mov ax,5
 stc
 jmp fsCopyExit
fsCopyDifferent:
 mov ax,3D00h                ; source open, read only
 lea dx,wasLHS
 call Dos3Call
 jnc fsCopySourceOpened
 jmp fsCopyError           ; unconditional JMP can be near on 8086
fsCopySourceOpened:
 mov fsSourceH,ax
 xor cx,cx                   ; clear normal file attributes
 mov ah,3Ch                  ; create/truncate destination
 lea dx,wasInput
 call Dos3Call
 jnc fsCopyDestOpened
 jmp fsCopyError
fsCopyDestOpened:
 mov fsDestH,ax
fsCopyRead:
 mov bx,fsSourceH
 mov ah,3Fh                  ; DOS sequential read
 mov cx,256
 lea dx,wasLine              ; borrowed interpreter line buffer
 call Dos3Call
 jnc fsCopyReadOk
 jmp fsCopyError
fsCopyReadOk:
 or ax,ax
 jz fsCopyDone
 mov cx,ax                   ; requested write count
 mov bx,fsDestH
 mov ah,40h
 lea dx,wasLine
 call Dos3Call
 jnc fsCopyWriteOk
 jmp fsCopyError
fsCopyWriteOk:
 cmp ax,cx
 je fsCopyRead
 mov ax,112                  ; DOS disk full / short write
 jmp fsCopyError
fsCopyDone:
 mov bx,fsDestH
 mov ah,3Eh
 call Dos3Call
 mov fsDestH,0FFFFh
 jc fsCopyError
 mov bx,fsSourceH
 mov ah,3Eh
 call Dos3Call
 mov fsSourceH,0FFFFh
 jc fsCopyError
 xor ax,ax
 clc
 jmp fsCopyExit
fsCopyError:
 mov fsLastError,ax          ; close/cleanup overwrites AX
 cmp fsDestH,0FFFFh
 je fsCopyCloseSource
 mov bx,fsDestH
 mov ah,3Eh
 call Dos3Call
 mov fsDestH,0FFFFh
 ; An incomplete destination must not be left as apparently valid data.
 lea dx,wasInput
 mov ah,41h
 call Dos3Call
fsCopyCloseSource:
 cmp fsSourceH,0FFFFh
 je fsCopyRestoreError
 mov bx,fsSourceH
 mov ah,3Eh
 call Dos3Call
 mov fsSourceH,0FFFFh
fsCopyRestoreError:
 mov ax,fsLastError
fsCopyExitError:
 stc
fsCopyExit:
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 ret
FsCopy endp

; Unsorted, streaming DOS findfirst/findnext directory listing. Each 8.3
; basename is written as one line into the current WAS log. No RAM array.
; Save/restore DOS DTA because WASTAR also changes it for wildcard TARADD.
FsDir proc near
 push bx
 push cx
 push dx
 push si
 push di
 push es
 cmp byte ptr wasInput,0
 jne fsDirPattern
 mov byte ptr wasInput,'*'
 mov byte ptr wasInput+1,'.'
 mov byte ptr wasInput+2,'*'
 mov byte ptr wasInput+3,0
fsDirPattern:
 mov ah,2Fh                  ; get old DTA pointer ES:BX
 call Dos3Call
 mov fsOldDta,bx
 mov fsOldDta+2,es
 lea dx,fsDta
 mov ah,1Ah                  ; set our private findfirst DTA
 call Dos3Call
 mov dx,offset wasInput
 mov cx,0037h                ; files + directory + hidden/system
 mov ah,4Eh
 call Dos3Call
 jc fsDirError
fsDirNext:
 ; DTA+30 = null-terminated 8.3 name (maximum 12 chars).
 ; wasInput is free after findfirst; reuse as LogLine's output string.
 lea si,fsDta+30
 lea di,wasInput
 mov cx,13
fsDirName:
 lodsb
 mov [di],al
 inc di
 or al,al
 jz fsDirNameDone
 loop fsDirName
 mov byte ptr [di],0
fsDirNameDone:
 lea si,wasInput
 call LogLine
 mov ah,4Fh                  ; find next in our private DTA
 call Dos3Call
 jnc fsDirNext
 cmp ax,18                   ; DOS no more files = successful listing
 je fsDirSuccess
fsDirError:
 mov fsLastError,ax
 stc
 jmp fsDirRestore
fsDirSuccess:
 xor ax,ax
 mov fsLastError,ax
 clc
fsDirRestore:
 pushf                        ; preserve enumeration status across restore
 mov dx,fsOldDta
 mov ax,fsOldDta+2
 push ds
 mov ds,ax
 mov ah,1Ah
 call Dos3Call
 pop ds
 popf
 mov ax,fsLastError
 call FsStatus
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 ret
FsDir endp

; PWD/CWD: DOS get current directory (47h). Appends it to the active LOG;
; drive prefix is not included, matching DOS 47h's documented contract.
FsPwd proc near
 push bx
 push dx
 push si
 mov byte ptr wasInput,0
 lea si,wasInput
 xor dl,dl                   ; DL=0 means current drive
 mov ah,47h
 call Dos3Call
 jc fsPwdResult
 lea si,wasInput
 call LogLine
 xor ax,ax
 clc
fsPwdResult:
 call FsStatus
 pop si
 pop dx
 pop bx
 ret
FsPwd endp

; Common result contract; CF from caller must survive to entry. No extra
; 16-bit Win16 state, no implicit abort and no hidden result conversion.
FsStatus proc near
 jnc fsStatusOk
 mov wasErrorCode,ax
 mov wasResult,1
 ret
fsStatusOk:
 mov wasErrorCode,0
 mov wasResult,0
 ret
FsStatus endp
end
