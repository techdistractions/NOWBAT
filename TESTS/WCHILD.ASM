; WAS WCHILD.EXE - audit-only native Win16 child, 8086 and Windows 1.01.
; The parent launches this NE image with SHELL and SHELLWAIT. The child
; reads KERNEL GetVersion: Windows 1.01 and 2.03 exit immediately
; (no Yield, to avoid scheduler-sensitive dormant child tasks). Windows
; 3.0 /r retains the two-second cooperative Yield stress. This is a
; test-fixture difference, not a change to SHELLWAIT runtime semantics. The closed WCHILD.OK / WWAIT.OK carries ASCII 1/2/3, which
; verifies actual target execution, but does NOT alone prove module unloading.
; This is NEVER linked into WAS.EXE and is not a runtime dependency.
.8086
.model small
.stack 512
extrn InitTask:far
extrn WaitEvent:far
extrn InitApp:far
extrn Yield:far
extrn GetVersion:far  ; KERNEL.3: Win1/2/3 use different task schedulers
.data
 dw 0,0,5,0,0,0,0,0    ; Windows 1/2 automatic-data prefix
IFDEF WAS_WAIT_CHILD
marker db 'WWAIT.OK',0  ; distinct Win16 child for SHELLWAIT
ELSE
marker db 'WCHILD.OK',0 ; first asynchronous SHELL child
ENDIF
startSecond db 0
childVersion db '0'  ; closed marker carries actual Win16 major version
childInst dw 0
.code
start:
 db 8 dup(090h)       ; same Win1-compatible startup envelope as WAS
 call InitTask
 or ax,ax
 jnz childInitOK
 jmp childExit
childInitOK:
 mov childInst,di       ; instance hInst from InitTask
 xor ax,ax
 push ax
 call WaitEvent
 push childInst
 call InitApp
 or ax,ax
 jnz childAppOK
 jmp childExit
childAppOK:
 ; Windows may leave DS/ES in a different context after InitApp/Yield.
 ; This independent NE child must not read its variables through a foreign DS.
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 ; Win1/Win2 can leave a minimal windowless Yield-based child suspended
 ; with module usage still 1, despite the child being otherwise runnable.
 ; Run the 37-command baseline using a child that terminates promptly on
 ; Win1 and Win2; test delayed/yielding child termination separately.
 ; Win3 /r continues the delayed child exercise.  No change to NOWBAT
 ; module unloading criteria or its scheduler is implied here.
 call GetVersion
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 add al,'0'
 mov childVersion,al
 cmp al,'1'
 je childWrite
 cmp al,'2'
 je childWrite
 ; DOS clock seconds within minute. Use modulo-60 adjustment so a child
 ; launched at 23:59:59 does not spuriously complete at the minute roll.
 mov ah,2Ch
 int 21h
 mov startSecond,dh
childWait:
 call Yield
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 mov ah,2Ch
 int 21h
 mov al,dh
 cmp al,startSecond
 jae childNoWrap
 add al,60
childNoWrap:
 sub al,startSecond
 cmp al,2
 jb childWait
childWrite:
 ; The version-stamped marker is emitted only by the live Win16 child.
 ; Win1/Win2: no Yield; Win3: after the cooperative delay.
 mov ah,3Ch
 xor cx,cx
 lea dx,marker
 int 21h
 jc childExit
 mov bx,ax
 mov ah,40h
 mov cx,1
 lea dx,childVersion
 int 21h
 mov ah,3Eh
 int 21h
childExit:
 mov ax,4C00h
 int 21h
end start
