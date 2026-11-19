; NOWBAT 0.0.47: compact Windows Automated Scripting runtime (8088 baseline).
; Tiny 8086 Win16 interpreter; native evidence is required for runtime PASS.
; The executor is intentionally line-at-a-time. GOTO scans the script on disk.
.8086
.model small
.stack 2048

extrn InitTask:far
extrn WaitEvent:far
extrn InitApp:far
extrn GetVersion:far
PUBLIC Dos3Call,wasLHS,wasLine,wasErrorCode,LogLine,EqualStrings
PUBLIC wasInst,wasStop
extrn UiOpen:near,UiClose:near,UiPump:near
extrn uiFailStage:byte
extrn uiPumpAny:byte
extrn Yield:far
; Win3-only timer-backed WAIT. No additional imports in WIN101/WIN200.
IFDEF WAS_WIN300
extrn SetTimer:far       ; USER.10, HWND/WORD/WORD/FARPROC
extrn KillTimer:far      ; USER.12, HWND/WORD
extrn WaitMessage:far    ; USER.112, cooperative wait until message
ENDIF
extrn LoadModule:far        ; KERNEL.45: early Win16 application loader
extrn GetModuleUsage:far    ; KERNEL.48: query child Win16 module lifetime
extrn GetDC:far           ; USER.66: desktop device context
extrn ReleaseDC:far      ; USER.68
extrn GetDeviceCaps:far  ; GDI.80: horizontal/vertical pixels and bit planes
; Windows 1/2 USER.2 is the original session shutdown entry.
; Win3 USER.7 performs the newer negotiated shutdown.
IFDEF WAS_WIN300
extrn ExitWindows:far
extrn GetWinFlags:far
ELSE
extrn OldExitWindows:far
ENDIF
extrn TarCreate:near
extrn TarAdd:near
extrn TarClose:near
extrn SnapDo:near
extrn snapMethod:byte
extrn snapVideoMode:byte
extrn FsUnary:near
extrn FsBinary:near
extrn FsDir:near
extrn FsPwd:near

.data
 dw 0,0,5,0,0,0,0,0      ; original Win1/Win2 automatic DGROUP prefix
PUBLIC wasInput,wasResult,wasIo,wasRect,wasBpp,wasSnapMode
wasInput       db 260 dup(0)
wasResult      dw 0
wasErrorCode   dw 0
wasIo          dw 0FFFFh
wasRect        dw 4 dup(0FFFFh)
wasBpp         dw 0
wasSnapMode    db 0     ; 0=COMPAT, 1=FAST (SNAP default), 2=AUTO
wasInst        dw 0
wasDefault     db 'WAS.WAS',0
wasScript      db 128 dup(0)
wasLine        db 260 dup(0)
wasCommand     db 24 dup(0)
wasArg         db 260 dup(0)
wasWord        db 32 dup(0)
wasLHS         db 260 dup(0)
wasOp          db 16 dup(0)
wasRHS         db 260 dup(0)
wasCharacter   db 0
wasScriptH     dw 0FFFFh
wasLineNo      dw 0
wasNextSI      dw 0
wasSubDepth    dw 0
wasSubs        dw 8 dup(0)  ; 4 caller offsets, low/high pairs
wasLabel       db 32 dup(0)
wasVarNames    db 128 dup(0)  ; 8 x 16
wasVarValues   db 768 dup(0)  ; 8 x 96
wasVarCount    dw 0
wasNumResult   db 12 dup(0) ; decimal WORD/DWORD output, shared by built-in vars
wasClockResult db 16 dup(0) ; DATE YYYY-MM-DD or TIME HH:MM:SS (live DOS clock)
wasSetTarget   db 16 dup(0)
wasSnapPath    db 260 dup(0)
wasCRLF        db 13,10
wasLogPath     db 'WAS.LOG',0
; Win16 KERNEL.45 LoadModule parameter block (14 bytes, not a DOS EXEC
; PSP/FCB block): WORD environment, FAR command tail, FAR show-state,
; DWORD reserved. NOWBAT's proven Windows 1.x launcher uses this layout.
; The command tail is length-prefixed and NUL-terminated; the show block
; contains two WORDs: byte length=2 and SW_SHOWNORMAL=1.
wasExecPath    db 128 dup(0)
wasCmdTail     db 0,128 dup(0)
wasShow        dw 2,1
wasExecBlock   dw 0,offset wasCmdTail,0,offset wasShow,0,0,0
wasShellUsage  dw 0        ; baseline usage for the launched Win16 instance
; Win1-only, closed 8-byte native wait witness: handle/base/poll/phase.
; Phase 1=baseline, 2=poll active, 3=module usage fell. Audit-only
; reporting: never treat a marker file as a replacement for Windows usage.
wasWaitInfo    dw 4 dup(0)
wasWaitFile    db 'SWWAIT.DAT',0
wasWaitTrace   db 0
wasRC          db 0
wasShutdown    db 0
wasStop        db 0         ; set only by optional iconic system-menu Close
wasWaitCs      dw 0        ; requested delay in centiseconds (max 59 seconds)
wasWaitStart   dw 0        ; DOS 2Ch second-of-minute clock (centiseconds)
IFDEF WAS_WIN300
wasTimerId     dw 0        ; NULL-window task timer for WAIT, 100ms tick
ENDIF
wasTemp        dw 0
wasRawTail     db 128 dup(0)
wasTraceH      dw 0FFFFh
wasTracePath   db 'EARLY.LOG',0
traceTask      db 'WAS_INITTASK',0
traceBuild     db 'NOWBAT_BUILD=W047',0 ; resident startup identity for audit
traceApp       db 'WAS_INITAPP',0
traceVersion   db 'WAS_VERSION=',0
traceWinFlags  db 'WAS_WINFLAGS=',0
wasHex         db 4 dup(0),0
traceTail      db 'WAS_TAIL=',0
traceScript    db 'WAS_SCRIPT=',0
traceOpen      db 'WAS_OPEN=',0
traceSnapDirect db 'SNAP_METHOD=VIDEO_DIRECT',0
traceSnapUnsupported db 'SNAP_METHOD=UNSUPPORTED',0
traceSnapBios db 'SNAP_BIOS_MODE=',0
traceSnapPixel  db 'SNAP_METHOD=GETPIXEL',0
traceShutdown  db 'WAS_SHUTDOWN_REQUESTED',0
traceFailure   db 'WAS_FAILURE',0
traceAssertFail db 'WAS_ASSERT_FAILED',0
traceShellStart db 'SHELL_LAUNCHED',0
traceShellAX    db 'SHELL_LOAD_AX=',0
traceShellDone  db 'SHELLWAIT_COMPLETED',0
traceShellFail  db 'SHELL_LAUNCH_ERROR=',0
traceShellStop  db 'SHELLWAIT_CANCELLED',0
IFDEF WAS_WIN300
traceAPI       db 'WAS_SHUTDOWN_API=USER.7',0
ELSE
traceAPI       db 'WAS_SHUTDOWN_API=USER.2',0
ENDIF
shutdownBad    db 'SHUTFAIL.LOG',0

.code
start:
 db 8 dup(090h)           ; NOWN/NBJWLINK Win1 loader entry convention
 call InitTask
 or ax,ax
 jz wasQuitFail
 mov wasInst,di
 ; Own InitTask ES:BX before any other Windows call. Accept the
 ; original ASCII tail and the DOS length+CR form used by some loaders.
 cld
 lea di,wasRawTail
 mov ax,es
 or ax,ax
 jz wasCmdDone
 or bx,bx
 jz wasCmdDone
 xor ax,ax
 mov al,es:[bx]
 cmp ax,127
 ja wasAsciiTail
 mov si,bx
 inc si
 add si,ax
 cmp byte ptr es:[si],13
 jne wasAsciiTail
 inc bx
 mov cx,ax
 jcxz wasCmdDone
 jmp wasCopyCmd
wasAsciiTail:
 mov cx,127
wasCopyCmd:
 mov al,es:[bx]
 cmp al,13
 je wasCmdDone
 or al,al
 jz wasCmdDone
 mov [di],al
 inc di
 inc bx
 loop wasCopyCmd
wasCmdDone:
 mov byte ptr [di],0
 ; Every later string destination is DGROUP, never the command-tail ES.
 push ds
 pop es
 mov ah,3Ch
 xor cx,cx
 lea dx,wasTracePath
 call Dos3Call
 jc wasQuitFail
 mov wasTraceH,ax
 lea si,traceTask
 call TraceLine
 lea si,traceBuild
 call TraceLine
 lea si,traceTail
 call TraceText
 lea si,wasRawTail
 call TraceLine
 xor ax,ax
 push ax
 call WaitEvent
 push wasInst
 call InitApp
 or ax,ax
 jz wasQuitFail
 cld
 push ds
 pop es
 lea si,traceApp
 call TraceLine
 lea si,traceVersion
 call TraceText
 call GetVersion
 call TraceHexLine
IFDEF WAS_WIN300
 lea si,traceWinFlags
 call TraceText
 call GetWinFlags
 call TraceHexLine
ENDIF
 push ds
 pop es
 ; parse one quoted/unquoted filename from the actual owned command tail
 lea si,wasRawTail
 call TrimSI
 cmp byte ptr [si],0
 jne wasHasScriptArg
 ; No-argument startup supports WIN.INI run=NOWBAT.EXE on Win1/2/3.
 ; The default WAS.WAS is in the current DOS working directory.
 ; An explicit NOWBAT.EXE file.was always takes precedence.
 lea si,wasDefault
 lea di,wasScript
 call CopyString128
 jmp wasOpenScript
wasHasScriptArg:
 mov di,offset wasInput
 call NextArgIntoInput
 cmp byte ptr wasInput,0
 je wasQuitFail
 lea si,wasInput
 lea di,wasScript
 call CopyString128
wasOpenScript:
 lea si,traceScript
 call TraceText
 lea si,wasScript
 call TraceLine
 ; open script
 mov ax,3D00h
 lea dx,wasScript
 call Dos3Call
 jc wasQuitFail
 mov wasScriptH,ax
 lea si,traceOpen
 call TraceText
 lea si,wasScript
 call TraceLine
 ; log is opened before the first command; no UI
 mov ah,3Ch
 xor cx,cx
 lea dx,wasLogPath
 call Dos3Call
 jc wasQuitFail
 mov wasIo,ax

wasLoop:
 ; Win16 KERNEL/USER calls may change ES or the direction flag.  Both
 ; ReadLine (STOSB) and every string helper require ES=DS and DF=0.
 ; Re-establish the invariant on EVERY interpreter iteration, including
 ; the first instruction after LoadModule / GetModuleUsage / Yield.
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 ; Only iconic mode pumps messages; normal headless scripts skip UI cost.
 call UiPump
 ; USER message dispatch can change DS on early Win1.01: restore before
 ; reading our stop flag or any DOS file handle.
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 cmp wasStop,0
 jne wasExit
 call ReadLine
 jc wasExit
 lea si,wasLine
 call TrimSI
 mov al,[si]
 cmp al,0
 je wasLoop
 cmp al,'#'
 je wasLoop
 cmp al,';'
 je wasLoop
 cmp al,':'
 je wasLoop
 mov di,offset wasCommand
 mov cx,23
wasCmdWord:
 lodsb
 cmp al,' '
 je wasCmdEnd
 cmp al,9
 je wasCmdEnd
 cmp al,0
 je wasCmdZero
 cmp al,'a'
 jb wasCmdCase
 cmp al,'z'
 ja wasCmdCase
 sub al,32
wasCmdCase:
 stosb
 loop wasCmdWord
wasCmdEnd:
 mov byte ptr [di],0
 call TrimSI
 mov wasNextSI,si
 jmp wasDispatch
wasCmdZero:
 dec si
 jmp wasCmdEnd

wasDispatch:
 ; Assignment syntax is a full keyword: ShowIcon=YES/NO.
 ; Omitted means headless and adds no window to the Windows task list.
 lea si,wasCommand
 lea di,cmdShowIconYes
 call IsCommand
 jc commandShowIconYes
 lea di,cmdShowIconNo
 call IsCommand
 jc commandShowIconNo
 lea si,wasCommand
 lea di,cmdLOG
 call IsCommand
 jc commandLog
 lea di,cmdLOGFILE
 call IsCommand
 jc commandLogFile
 lea di,cmdLOGCLOSE
 call IsCommand
 jc commandLogClose
 lea di,cmdWAIT
 call IsCommand
 jc commandWait
 lea di,cmdSET
 call IsCommand
 jc commandSet
 ; DOS filesystem commands share a tiny DOS 21h backend. All commands
 ; set %RESULT%/%ERRORCODE% instead of aborting the interpreter on I/O error.
 lea di,cmdCHDIR
 call IsCommand
 jc commandChdir
 lea di,cmdCD
 call IsCommand
 jc commandChdir
 lea di,cmdMKDIR
 call IsCommand
 jc commandMkdir
 lea di,cmdMD
 call IsCommand
 jc commandMkdir
 lea di,cmdRMDIR
 call IsCommand
 jc commandRmdir
 lea di,cmdRD
 call IsCommand
 jc commandRmdir
 lea di,cmdDEL
 call IsCommand
 jc commandDelete
 lea di,cmdDELETE
 call IsCommand
 jc commandDelete
 lea di,cmdERASE
 call IsCommand
 jc commandDelete
 lea di,cmdCOPY
 call IsCommand
 jc commandCopy
 lea di,cmdMOVE
 call IsCommand
 jc commandMove
 lea di,cmdREN
 call IsCommand
 jc commandRename
 lea di,cmdRENAME
 call IsCommand
 jc commandRename
 lea di,cmdDIR
 call IsCommand
 jc commandDir
 lea di,cmdPWD
 call IsCommand
 jc commandPwd
 lea di,cmdSHELLWAIT
 call IsCommand
 jc commandShellWait
 lea di,cmdSHELL
 call IsCommand
 jc commandShellNoWait
 lea di,cmdGOTO
 call IsCommand
 jc commandGoto
 lea di,cmdGOSUB
 call IsCommand
 jc commandGosub
 lea di,cmdRETURN
 call IsCommand
 jc commandReturn
 lea di,cmdIF
 call IsCommand
 jc commandIf
 lea di,cmdEXISTS
 call IsCommand
 jc commandExists
 lea di,cmdASSERT
 call IsCommand
 jc commandAssert
 lea di,cmdTARCREATE
 call IsCommand
 jc commandTarCreate
 lea di,cmdTARADD
 call IsCommand
 jc commandTarAdd
 lea di,cmdTARCLOSE
 call IsCommand
 jc commandTarClose
 lea di,cmdSNAPSAFE
 call IsCommand
 jc commandSnap
 lea di,cmdSNAP
 call IsCommand
 jc commandSnap
 lea di,cmdSHUTDOWN
 call IsCommand
 jc commandShutdown
 lea di,cmdPASS
 call IsCommand
 jc commandPass
 lea di,cmdFAIL
 call IsCommand
 jc commandFail
 lea di,cmdEND
 call IsCommand
 jc commandEnd
 ; Unknown syntax is a hard failure (not silently ignored).
 mov wasResult,2
 jmp wasQuitFail

commandShowIconYes:
 call UiOpen
 jc wasIconError
 lea si,wasCommand    ; no extra static trace string / DGROUP
 call TraceLine
 mov wasResult,0
 jmp wasLoop
commandShowIconNo:
 call UiClose
 lea si,wasCommand
 call TraceLine
 mov wasResult,0
 jmp wasLoop
wasIconError:
 ; Preserve why Win16 rejected the optional window/menu. Never hide an
 ; icon failure inside an unrelated snapshot or TAR diagnosis. Stage:
 ; 1=register class, 2=create window, 3=system menu, 4-6=menu items.
 ; Reuse the existing 24-byte parsed-command buffer for a diagnostic:
 ; SHOWICON=YES:1 (class), :2 (window), :3 (system menu),
 ; :4/:5/:6 (Close/Switch/About menu item). No extra DGROUP text.
 mov byte ptr wasCommand+12,':'
 mov al,uiFailStage
 add al,'0'
 mov byte ptr wasCommand+13,al
 mov byte ptr wasCommand+14,0
 lea si,wasCommand
 call TraceLine
 ; A visible-icon request is explicit: never pretend it succeeded.
 mov wasShutdown,1
 jmp wasCmdFailure

commandLog:
 call FetchArg
 lea si,wasInput
 call LogLine
 jmp wasLoop
commandLogFile:
 call FetchArg
 cmp wasIo,0FFFFh
 je wasLogOpen
 mov bx,wasIo
 mov ah,3Eh
 call Dos3Call
wasLogOpen:
 mov ah,3Ch
 xor cx,cx
 lea dx,wasInput
 call Dos3Call
 jc wasCmdFailure
 mov wasIo,ax
 xor ax,ax
 mov wasResult,ax
 jmp wasLoop
commandLogClose:
 cmp wasIo,0FFFFh
 je wasLogAlreadyClosed
 mov bx,wasIo
 mov ah,3Eh
 call Dos3Call
 jc wasCmdFailure
 mov wasIo,0FFFFh
wasLogAlreadyClosed:
 mov wasResult,0
 jmp wasLoop

commandWait:
 ; WAIT milliseconds, currently bounded 0..59000; resolves to 10ms ticks.
 ; DOS 2Ch time is available to Win1/2/3 real-mode applications;
 ; Win3 supplements this clock with timer-triggered WaitMessage yielding.
 call FetchArg
 lea si,wasInput
 call ParseUInt
 jc wasCmdFailure
 cmp ax,59000
 ja wasCmdFailure
 xor dx,dx
 mov bx,10
 div bx
 mov wasWaitCs,ax
 call WasClockCs
 mov wasWaitStart,ax
IFDEF WAS_WIN300
 ; Timer-backed, genuinely blocking Windows message wait, not a busy
 ; polling loop. WM_TIMER wakes the task at roughly 100ms intervals,
 ; while other Win3 real-mode applications continue handling input.
 ; hwnd=0 creates a task timer, including in headless scripts.
 mov wasTimerId,0
 cmp wasWaitCs,0
 je wasWaitPoll
 xor ax,ax
 push ax                ; hWnd=NULL
 inc ax
 push ax                ; nIDEvent=1
 mov ax,100
 push ax                ; uElapse=100 milliseconds
 xor ax,ax
 push ax                ; TIMERPROC segment=NULL
 push ax                ; TIMERPROC offset=NULL
 call SetTimer
 mov bx,@data
 mov ds,bx
 mov es,bx
 cld
 mov wasTimerId,ax
 or ax,ax
 jz wasWaitPoll         ; SetTimer failed: keep legacy Yield fallback
 mov uiPumpAny,1        ; pump WM_TIMER even when ShowIcon=NO
ENDIF
wasWaitPoll:
IFDEF WAS_WIN300
 cmp wasTimerId,0
 je wasWaitYield
 ; WaitMessage yields control until Windows has a queued event. Its
 ; timer message is removed by UiPump / PeekMessage below.
 call WaitMessage
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 jmp wasWaitPump
wasWaitYield:
ENDIF
 call Yield              ; Win1/Win2 and Win3 SetTimer failure fallback
wasWaitPump:
 call UiPump             ; drain optional system menu and timer messages
 cmp wasStop,0
 jne wasWaitStopped
 call WasClockCs
 sub ax,wasWaitStart
 jnc wasWaitDelta
 add ax,6000            ; 60-second wrap (max wait 59 seconds)
wasWaitDelta:
 cmp ax,wasWaitCs
 jb wasWaitPoll
IFDEF WAS_WIN300
 call WasStopTimer
ENDIF
 mov wasResult,0
 jmp wasLoop
wasWaitStopped:
IFDEF WAS_WIN300
 call WasStopTimer
ENDIF
 jmp wasExit

commandSet:
 ; SET NAME=VALUE. Name up to 15 chars, value up to 95 chars.
 mov si,wasNextSI
 lea di,wasWord
 mov cx,15
wasSetName:
 lodsb
 cmp al,'='
 je wasSetValue
 or al,al
 jz wasCmdFailure
 cmp al,' '
 je wasSetName
 stosb
 loop wasSetName
 jmp wasCmdFailure
wasSetValue:
 mov byte ptr [di],0
 push si
 lea si,wasWord
 lea di,wasSetTarget
 call CopyString16
 pop si
 call NextArgIntoInput
 lea si,wasSetTarget
 lea di,wasWord
 call CopyString16
 call StoreVar
 jmp wasLoop
; All single-path operations share the same parameter parser and DOS
; status contract. AL is the DOS 21h function, set before parsing.
commandChdir:
 mov al,3Bh
 jmp wasFsUnary
commandMkdir:
 mov al,39h
 jmp wasFsUnary
commandRmdir:
 mov al,3Ah
 jmp wasFsUnary
commandDelete:
 mov al,41h
wasFsUnary:
 push ax
 call FetchArg
 pop ax
 call FsUnary
 jmp wasLoop

; Two-parameter operations: source and destination are both expanded, but
; the source is saved in existing wasLHS before FetchArg overwrites wasInput.
; AL: 0 COPY (overwrite destination), 1 REN (same volume), 2 MOVE.
commandCopy:
 xor al,al
 jmp wasFsBinary
commandRename:
 mov al,1
 jmp wasFsBinary
commandMove:
 mov al,2
wasFsBinary:
 push ax
 call FetchArg
 lea si,wasInput
 lea di,wasLHS
 call CopyString260
 call FetchArg
 pop ax
 call FsBinary
 jmp wasLoop

commandDir:
 call FetchArg              ; optional wildcard pattern, default *.*
 call FsDir                 ; results streamed into the active LOG
 jmp wasLoop
commandPwd:
 call FsPwd                 ; writes cwd to active LOG
 jmp wasLoop
; Windows-only SHELL / SHELLWAIT. No COM launcher or DOS exit status.
; LoadModule (KERNEL.45) exists on Win1.01/2.03/3.0 real mode; its
; parameter block resembles DOS EXEC only because that is the Win16 ABI.
; GetModuleUsage (KERNEL.48) detects a drop from launch-time usage.
; RESULT: 0 on successful launch / completed wait, 1 on launch failure,
;         2 when the optional-icon Close cancels a cooperative wait.
; ERRORCODE: the loader error on failed launch, otherwise zero. Neither
; register is a DOS child ERRORLEVEL or Windows application return code.
; All permanent storage below was already part of the interpreter.
commandShellNoWait:
 xor ax,ax
 jmp wasLaunchWindows
commandShellWait:
 mov ax,1
wasLaunchWindows:
 mov wasTemp,ax             ; transient wait flag; not a permanent buffer
 call FetchArg
 cmp byte ptr wasInput,0
 jne wasShellGotPath
 jmp wasShellInvalid
wasShellGotPath:
 lea si,wasInput
 mov cx,128
wasShellPathLength:
 cmp byte ptr [si],0
 je wasShellPathOk
 inc si
 loop wasShellPathLength
 jmp wasShellInvalid
wasShellPathOk:
 lea si,wasInput
 lea di,wasExecPath
 call CopyString128         ; executable pathname (Win16 NE .EXE)
 ; Windows 2.x displays a blocking "Change Disk / insert drive A:"
 ; dialog for missing LoadModule targets instead of returning an error.
 ; Probe the named executable in DOS first, before entering Windows' loader.
 ; A failed open returns DOS 2/3/5 through the SAME SHELL error path.
 ; This also keeps bad child names from stalling unattended Win1/Win3.
 ; As in WAS's deterministic batch contract, use an explicit filename or
 ; a file in the guest working directory (do not depend on Win search UI).
 mov ax,3D00h
 mov dx,offset wasExecPath
 call Dos3Call
 jnc wasShellFileFound
 jmp wasShellLaunchFailed
wasShellFileFound:
 mov bx,ax
 mov ah,3Eh
 call Dos3Call
 jnc wasShellFileClosed
 jmp wasShellLaunchFailed
wasShellFileClosed:
 ; Preserve the *whole* child command tail, including whitespace/quotes.
 ; Expand interpreter variables before copying to the 127-byte Win16 tail.
 ; NOWBAT passes length-prefixed text followed by NUL (not DOS CR/FCBs).
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],','
 jne wasShellArgsReady
 inc si
 call TrimSI
wasShellArgsReady:
 lea di,wasArg
 call CopyString260
 call ExpandArg
 lea si,wasInput
 lea di,wasCmdTail+1
 xor cx,cx
wasWinTailCopy:
 cmp byte ptr [si],0
 je wasWinTailEnd
 cmp cx,127
 jae wasShellInvalid
 lodsb
 stosb
 inc cx
 jmp wasWinTailCopy
wasWinTailEnd:
 mov byte ptr [di],0
 mov byte ptr wasCmdTail,cl
 ; FAR PASCAL: push first argument (far module path), then second
 ; argument (far pointer to 14-byte Win16 parameter block).
 mov ax,ds
 mov word ptr wasExecBlock+4,ax
 mov word ptr wasExecBlock+8,ax
 push ds
 mov ax,offset wasExecPath
 push ax
 push ds
 mov ax,offset wasExecBlock
 push ax
 call LoadModule
 ; Preserve the loader's returned instance handle before resetting the
 ; Win16 calling-context data segment and STOSB destination segment.
 ; A stale ES makes ReadLine write the *next* command into foreign memory,
 ; leaving DS:wasLine unchanged: the previous SHELL gets run repeatedly.
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 lea si,traceShellAX
 call TraceText
 call TraceHexLine
 cmp ax,32
 jb wasShellLaunchFailed
 ; The launch value is a Windows instance handle, not a return code.
 mov wasResult,0
 mov wasErrorCode,0
 mov word ptr wasLHS,ax ; scratch handle; keep environment slot zero
 lea si,traceShellStart
 call TraceLine
 cmp wasTemp,0
 jne wasWindowsWait
 jmp wasLoop              ; SHELL returns immediately
wasWindowsWait:
 ; NOWBAT records the usage count directly after LoadModule and waits
 ; for it to fall, NOT for the entire module's count to become zero.
 ; Another instance of the same executable may remain running.
 push word ptr wasLHS
 call GetModuleUsage      ; FAR PASCAL: one WORD instance handle
 ; The Win1 loader/task scheduler is allowed to change DS/ES. Keep the
 ; return AX across the repair before touching interpreter-owned data.
 mov bx,ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 mov ax,bx
 mov wasShellUsage,ax
 or ax,ax
 jnz wasWinWaitUsageOk
 mov wasShellUsage,1      ; NOWBAT's Win1 loader race fallback
wasWinWaitUsageOk:
 ; WIN101 evidence is closed immediately; EARLY.LOG remains open until exit.
 ; Unlike WCHILD.OK, this records what the Windows loader actually reports.
 push ax
 call GetVersion
 mov bx,ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 mov wasWaitTrace,0
 cmp bl,1
 jne wasWaitInitDone
 mov wasWaitTrace,1
 mov ax,word ptr wasLHS
 mov wasWaitInfo,ax
 mov ax,wasShellUsage
 mov wasWaitInfo+2,ax
 mov wasWaitInfo+4,ax
 mov word ptr wasWaitInfo+6,1
 call SaveWaitInfo
wasWaitInitDone:
 pop ax
wasWinWaitPoll:
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 push word ptr wasLHS
 call GetModuleUsage
 mov bx,ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 mov ax,bx
 cmp wasWaitTrace,0
 je wasWaitPollChecked
 cmp word ptr wasWaitInfo+6,1
 je wasWaitPollChanged
 cmp ax,wasWaitInfo+4
 je wasWaitPollChecked
wasWaitPollChanged:
 mov wasWaitInfo+4,ax
 mov word ptr wasWaitInfo+6,2
 call SaveWaitInfo
wasWaitPollChecked:
 cmp ax,wasShellUsage
 jb wasWinChildDone
 call UiPump
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 cmp wasStop,0
 jne wasWinWaitCancelled
 call Yield              ; cooperative, no busy spin on a 4.77 MHz 8088
 jmp wasWinWaitPoll
wasWinChildDone:
 mov bx,ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 cmp wasWaitTrace,0
 je wasWinWaitTraceDone
 mov wasWaitInfo+4,bx
 mov word ptr wasWaitInfo+6,3
 call SaveWaitInfo
wasWinWaitTraceDone:
 lea si,traceShellDone
 call TraceLine
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasLoop
wasWinWaitCancelled:
 lea si,traceShellStop
 call TraceLine
 mov wasResult,2
 mov wasErrorCode,0
 jmp wasLoop
wasShellInvalid:
 mov ax,87               ; invalid path or command-line length
wasShellLaunchFailed:
 ; KERNEL can report an unsuccessful zero handle.  A failed SHELL must
 ; NEVER claim ERRORCODE=0 (success), even if raw LoadModule AX was 0.
 or ax,ax
 jnz wasShellErrorNonzero
 mov ax,1
wasShellErrorNonzero:
 mov wasErrorCode,ax
 mov wasResult,1
 lea si,traceShellFail
 call TraceText
 mov ax,wasErrorCode
 call FormatDecimal
 lea si,wasNumResult
 call TraceLine
 jmp wasLoop

commandGoto:
 call FetchArg
 lea si,wasInput
 call GotoLabel
 jc wasCmdFailure
 jmp wasLoop
commandGosub:
 mov ax,wasSubDepth
 cmp ax,4
 jae wasCmdFailure
 mov bx,wasScriptH
 xor cx,cx
 xor dx,dx
 mov ax,4201h
 call Dos3Call
 jc wasCmdFailure
 mov si,wasSubDepth
 shl si,1
 shl si,1
 mov wasSubs[si],ax
 mov wasSubs[si+2],dx
 inc wasSubDepth
 call FetchArg
 lea si,wasInput
 call GotoLabel
 jnc wasLoop
 dec wasSubDepth
 jmp wasCmdFailure
commandReturn:
 cmp wasSubDepth,0
 je wasCmdFailure
 dec wasSubDepth
 mov si,wasSubDepth
 shl si,1
 shl si,1
 mov dx,wasSubs[si]
 mov cx,wasSubs[si+2]
 mov bx,wasScriptH
 mov ax,4200h
 call Dos3Call
 jc wasCmdFailure
 jmp wasLoop
commandIf:
 ; IF <value> (=|<>|EQ|NE) <value> [THEN] GOTO|GOSUB <label>
 ; Whole-token %VAR% interpolation; suitable for ERRORCODE checks.
 call FetchArg
 lea si,wasInput
 lea di,wasLHS
 call CopyString260
 call FetchArg
 lea si,wasInput
 lea di,wasOp
 call CopyString16
 call FetchArg
 lea si,wasInput
 lea di,wasRHS
 call CopyString260
 lea si,wasLHS
 lea di,wasRHS
 call EqualStrings
 mov bl,0
 jc wasIfEqual
 jmp wasIfPredicate
wasIfEqual:
 mov bl,1
wasIfPredicate:
 lea si,wasOp
 lea di,opEQ
 call IsCommand
 jc wasIfMatch
 lea di,opASSIGN
 call IsCommand
 jc wasIfMatch
 lea di,opNE
 call IsCommand
 jc wasIfMismatch
 lea di,opDIFF
 call IsCommand
 jc wasIfMismatch
 jmp wasCmdFailure
wasIfMatch:
 cmp bl,1
 jne wasLoop
 jmp wasIfBranch
wasIfMismatch:
 cmp bl,0
 jne wasLoop
wasIfBranch:
 call FetchArg
 lea si,wasInput
 lea di,cmdTHEN
 call IsCommand
 jnc wasIfAct
 call FetchArg
wasIfAct:
 lea si,wasInput
 lea di,cmdGOTO
 call IsCommand
 jc wasIfGoto
 lea di,cmdGOSUB
 call IsCommand
 jc wasIfGosub
 jmp wasCmdFailure
wasIfGoto:
 call FetchArg
 lea si,wasInput
 call GotoLabel
 jc wasCmdFailure
 jmp wasLoop
wasIfGosub:
 jmp commandGosub

; EXISTS path: RESULT=0 when readable, RESULT=1 when not present/openable.
; ERRORCODE holds DOS open error on failure, zero on success.
; Reuses wasInput and a temporary DOS file handle; no new buffers.
commandExists:
 call FetchArg
 mov ax,3D00h
 lea dx,wasInput
 call Dos3Call
 jc wasExistsMissing
 mov bx,ax
 mov ah,3Eh
 call Dos3Call
 jc wasExistsMissing
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasLoop
wasExistsMissing:
 mov wasErrorCode,ax
 mov wasResult,1
 jmp wasLoop

; ASSERT lhs EQ|NE|=|<> rhs. On mismatch, record a hard failure and
; SHUTDOWN rather than leaving unattended Windows running until timeout.
; Built from existing token buffers and case-insensitive comparison.
commandAssert:
 call FetchArg
 lea si,wasInput
 lea di,wasLHS
 call CopyString260
 call FetchArg
 lea si,wasInput
 lea di,wasOp
 call CopyString16
 call FetchArg
 lea si,wasInput
 lea di,wasRHS
 call CopyString260
 lea si,wasLHS
 lea di,wasRHS
 call EqualStrings
 mov bl,0
 jnc wasAssertPredicate
 mov bl,1
wasAssertPredicate:
 lea si,wasOp
 lea di,opEQ
 call IsCommand
 jc wasAssertEqual
 lea di,opASSIGN
 call IsCommand
 jc wasAssertEqual
 lea di,opNE
 call IsCommand
 jc wasAssertDifferent
 lea di,opDIFF
 call IsCommand
 jc wasAssertDifferent
 jmp wasCmdFailure
wasAssertEqual:
 cmp bl,1
 jne wasAssertFailed
 jmp wasAssertPassed
wasAssertDifferent:
 cmp bl,0
 jne wasAssertFailed
wasAssertPassed:
 mov wasResult,0
 jmp wasLoop
wasAssertFailed:
 mov wasResult,1
 mov wasRC,1
 lea si,traceAssertFail
 call TraceLine
 lea si,traceFailure
 call TraceLine
 mov wasShutdown,1
 jmp wasExit

; TAR primitives set %RESULT%; on I/O failure the next IF can write
; an evidence marker before END. Do not abort the interpreter here.
commandTarCreate:
 call FetchArg
 call TarCreate
 jmp wasLoop
commandTarAdd:
 call FetchArg
 call TarAdd
 jmp wasLoop
commandTarClose:
 call TarClose
 jmp wasLoop
commandSnap:
 call FetchArg
 lea si,wasInput
 lea di,wasSnapPath
 call CopyString260
 ; All SNAP options are per-command. No mode leaks between instructions.
 mov word ptr wasRect,0FFFFh
 mov word ptr wasRect+2,0FFFFh
 mov word ptr wasRect+4,0FFFFh
 mov word ptr wasRect+6,0FFFFh
 mov wasBpp,0
 mov wasSnapMode,1       ; SNAP defaults to strict FAST (no silent GDI fallback)
wasSnapOption:
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 je wasDoSnap
 call FetchArg
 lea si,wasInput
 mov al,[si]
 and al,0DFh
 cmp al,'B'
 je wasSnapCheckBpp
 cmp al,'M'
 je wasSnapCheckMode
 ; Numeric coordinates: X,Y,X1,Y1; optional legacy trailing BPP.
 cmp word ptr wasRect,0FFFFh
 jne wasSnapTrailingBpp
 xor bx,bx
wasSnapCoord:
 call ParseUInt
 jc wasCmdFailure
 mov wasRect[bx],ax
 add bx,2
 cmp bx,8
 jae wasSnapOption
 call FetchArg
 lea si,wasInput
 jmp wasSnapCoord
wasSnapTrailingBpp:
 cmp wasBpp,0
 jne wasCmdFailure
 call ParseUInt
 jc wasCmdFailure
 mov wasBpp,ax
 jmp wasSnapOption
wasSnapCheckBpp:
 mov al,[si+1]
 and al,0DFh
 cmp al,'P'
 jne wasCmdFailure
 mov al,[si+2]
 and al,0DFh
 cmp al,'P'
 jne wasCmdFailure
 cmp byte ptr [si+3],'='
 jne wasCmdFailure
 add si,4
 call ParseUInt
 jc wasCmdFailure
 mov wasBpp,ax
 jmp wasSnapOption
wasSnapCheckMode:
 mov al,[si+1]
 and al,0DFh
 cmp al,'O'
 jne wasCmdFailure
 mov al,[si+2]
 and al,0DFh
 cmp al,'D'
 jne wasCmdFailure
 mov al,[si+3]
 and al,0DFh
 cmp al,'E'
 jne wasCmdFailure
 cmp byte ptr [si+4],'='
 jne wasCmdFailure
 lea si,wasInput+5
 lea di,snapModeFastName
 call IsCommand
 jc wasSnapFastSet
 lea di,snapModeCompatName
 call IsCommand
 jc wasSnapCompatSet
 lea di,snapModeAutoName
 call IsCommand
 jc wasSnapAutoSet
 jmp wasCmdFailure
wasSnapFastSet:
 mov wasSnapMode,1
 jmp wasSnapOption
wasSnapCompatSet:
 mov wasSnapMode,0
 jmp wasSnapOption
wasSnapAutoSet:
 mov wasSnapMode,2
 jmp wasSnapOption
wasDoSnap:
 ; SNAPSAFE unconditionally uses original GDI, even if MODE=FAST is passed.
 lea si,wasCommand
 lea di,cmdSNAPSAFE
 call IsCommand
 jnc wasSnapReady
 mov wasSnapMode,0
wasSnapReady:
 lea si,wasSnapPath
 lea di,wasInput
 call CopyString260
 call SnapDo
 lea si,traceSnapBios
 call TraceText
 xor ax,ax
 mov al,snapVideoMode
 call TraceHexLine
 cmp snapMethod,3
 je wasSnapTraceUnsupported
 cmp snapMethod,2
 je wasSnapTraceDirect
 lea si,traceSnapPixel
 jmp wasSnapTrace
wasSnapTraceDirect:
 lea si,traceSnapDirect
 jmp wasSnapTrace
wasSnapTraceUnsupported:
 lea si,traceSnapUnsupported
wasSnapTrace:
 call TraceLine
 jmp wasLoop
commandShutdown:
 ; Stop script processing; all files are flushed before closing Windows.
 lea si,traceShutdown
 call TraceLine
 mov wasShutdown,1
 jmp wasExit
commandEnd:
 ; Native terminal witness, no new data and no result-code emulation.
 lea si,wasCommand
 call TraceLine
 jmp wasExit
commandPass:
 lea si,wasCommand
 call TraceLine
 mov wasRC,0
 jmp wasExit
commandFail:
 lea si,wasCommand
 call TraceLine
 mov wasRC,1
 jmp wasExit
wasCmdFailure:
 mov wasResult,1
 jmp wasQuitFail
wasQuitFail:
 lea si,traceFailure
 call TraceLine
 mov wasRC,1
wasExit:
 ; Return the optional iconic window before closing files/Windows.
 call UiClose
 cmp wasShutdown,0
 je wasNoTarClose
 ; Uncompressed archive must be terminated before Windows goes away.
 ; TarClose on an unopened archive is harmless to the shutdown path.
 call TarClose
wasNoTarClose:
 cmp wasScriptH,0FFFFh
 je wasCloseLog
 mov bx,wasScriptH
 mov ah,3Eh
 call Dos3Call
wasCloseLog:
 cmp wasIo,0FFFFh
 je wasTerm
 mov bx,wasIo
 mov ah,3Eh
 call Dos3Call
wasTerm:
 cmp wasShutdown,0
 je wasTraceClose
 lea si,traceAPI
 call TraceLine
wasTraceClose:
 cmp wasTraceH,0FFFFh
 je wasTraceClosed
 mov bx,wasTraceH
 mov ah,3Eh
 call Dos3Call
 mov wasTraceH,0FFFFh
wasTraceClosed:
 cmp wasShutdown,0
 je wasDosTerminate
IFDEF WAS_WIN300
 ; BOOL FAR PASCAL ExitWindows(DWORD reserved, WORD returnCode).
 xor ax,ax
 push ax                  ; reserved high
 push ax                  ; reserved low
 push ax                  ; returnCode
 call ExitWindows
ELSE
 ; Original Win1/Win2 session exit (USER.2), no parameters.
 ; These fixtures have no USER.7 export. A WM_ENDSESSION broadcast
 ; alone neither initiates shutdown nor unwinds Windows to DOS.
 call OldExitWindows
ENDIF
 ; A returning shutdown API is failure, even if the application exits.
 mov ah,3Ch
 xor cx,cx
 lea dx,shutdownBad
 call Dos3Call
 jc wasShutdownReturned
 mov bx,ax
 mov ah,3Eh
 call Dos3Call
wasShutdownReturned:
 mov wasRC,1
wasDosTerminate:
 mov ah,4Ch
 mov al,wasRC
 int 21h

; Closed diagnostic witness for Win1 GetModuleUsage. Never called by
; the normal WIN200/WIN300 path, and never changes SHELLWAIT result.
SaveWaitInfo proc near
 push ax
 push bx
 push cx
 push dx
 mov ax,3C00h
 xor cx,cx
 lea dx,wasWaitFile
 call Dos3Call
 jc saveWaitDone
 mov bx,ax
 mov ah,40h
 mov cx,8
 lea dx,wasWaitInfo
 call Dos3Call
 mov ah,3Eh
 call Dos3Call
saveWaitDone:
 pop dx
 pop cx
 pop bx
 pop ax
 ret
SaveWaitInfo endp

IFDEF WAS_WIN300
; Stop only the timer owned by WAIT. No residual callback/message can
; touch the interpreter after END, FAIL, SHUTDOWN or icon Close.
WasStopTimer proc near
 push ax
 push bx
 mov uiPumpAny,0
 cmp wasTimerId,0
 je wasStopTimerDone
 xor ax,ax
 push ax                ; hWnd=NULL task timer
 push wasTimerId         ; timer ID returned by SetTimer
 call KillTimer
 mov bx,@data
 mov ds,bx
 mov es,bx
 cld
 mov wasTimerId,0
wasStopTimerDone:
 pop bx
 pop ax
 ret
WasStopTimer endp
ENDIF

; Clock time in centiseconds within the current minute, from DOS 2Ch.
; AH=2Ch returns DH=second, DL=hundredths. Valid across midnight.
WasClockCs proc near
 push bx
 push cx
 push dx
 mov ah,2Ch
 call Dos3Call
 mov bl,dl             ; retain hundredths: MUL overwrites DX
 xor bh,bh
 mov al,dh
 xor ah,ah
 mov cx,100
 mul cx
 add ax,bx
 pop dx
 pop cx
 pop bx
 ret
WasClockCs endp

; Win1.01 has no KERNEL.102 (DOS3CALL) export. The existing NOWBASIC
; runtime uses INT 21h directly. Keep the shared FAR call contract for
; WASTAR/WASSNAP, preserving DOS flags including carry across RETF.
Dos3Call proc far
 int 21h
 retf
Dos3Call endp

 ; Trace is interpreter-owned and independent of script LOG/LOGFILE.
 ; Preserve registers, including ES, across DOS and string operations.
TraceText proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 cmp wasTraceH,0FFFFh
 je traceTextDone
 mov dx,si
 xor cx,cx
traceTextCount:
 cmp byte ptr [si],0
 je traceTextWrite
 inc si
 inc cx
 jmp traceTextCount
traceTextWrite:
 mov bx,wasTraceH
 mov ah,40h
 call Dos3Call
traceTextDone:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
TraceText endp

TraceLine proc near
 call TraceText
 push ax
 push bx
 push cx
 push dx
 push es
 cmp wasTraceH,0FFFFh
 je traceLineDone
 mov bx,wasTraceH
 mov dx,offset wasCRLF
 mov cx,2
 mov ah,40h
 call Dos3Call
traceLineDone:
 pop es
 pop dx
 pop cx
 pop bx
 pop ax
 ret
TraceLine endp

TraceHexLine proc near
 push ax
 push bx
 push cx
 push si
 push di
 mov bx,ax
 mov cx,4
 lea di,wasHex
traceHexDigit:
 rol bx,1
 rol bx,1
 rol bx,1
 rol bx,1
 mov al,bl
 and al,0Fh
 add al,'0'
 cmp al,'9'
 jbe traceHexStore
 add al,7
traceHexStore:
 mov [di],al
 inc di
 loop traceHexDigit
 lea si,wasHex
 call TraceLine
 pop di
 pop si
 pop cx
 pop bx
 pop ax
 ret
TraceHexLine endp

; ReadLine: single-byte disk streaming to avoid script storage in memory.
; Carry set only on EOF with no buffered data.
ReadLine proc near
 push bx
 push cx
 push dx
 push di
 inc wasLineNo
 lea di,wasLine
 mov cx,259
wasReadChar:
 mov bx,wasScriptH
 mov ah,3Fh
 mov dx,offset wasCharacter
 push cx
 mov cx,1
 call Dos3Call
 pop cx
 jc wasLineIOError
 or ax,ax
 jz wasLineEOF
 mov al,wasCharacter
 cmp al,13
 je wasReadChar
 cmp al,10
 je wasLineEnd
 or al,al
 jz wasLineEnd
 stosb
 loop wasReadChar
 ; overlong line is rejected, never truncated into another command.
 mov wasResult,2
 mov wasRC,1
 stc
 jmp wasReadDone
wasLineIOError:
 mov wasRC,1             ; a DOS read error is not clean script EOF
 stc
 jmp wasReadDone
wasLineEOF:
 cmp di,offset wasLine
 je wasLineEmpty
wasLineEnd:
 mov byte ptr [di],0
 clc
 jmp wasReadDone
wasLineEmpty:
 stc
wasReadDone:
 pop di
 pop dx
 pop cx
 pop bx
 ret
ReadLine endp

TrimSI proc near
wasTrim:
 cmp byte ptr [si],' '
 je wasSkip
 cmp byte ptr [si],9
 jne wasTrimEnd
wasSkip:
 inc si
 jmp wasTrim
wasTrimEnd:
 ret
TrimSI endp

; NextArgIntoInput: in SI, token to wasInput; quote aware.
NextArgIntoInput proc near
 push ax
 push bx
 push cx
 push di
 call TrimSI
 cmp byte ptr [si],','
 jne wasArgBegin
 inc si
 call TrimSI
wasArgBegin:
 lea di,wasArg
 mov cx,259
 mov bl,0
 cmp byte ptr [si],'"'
 jne wasArgLoop
 mov bl,1
 inc si
wasArgLoop:
 mov al,[si]
 or al,al
 jz wasArgEnd
 cmp bl,0
 jne wasArgQuoted
 cmp al,' '
 je wasArgEnd
 cmp al,9
 je wasArgEnd
 cmp al,','
 je wasArgEnd
 jmp wasArgStore
wasArgQuoted:
 cmp al,'"'
 jne wasArgStore
 inc si
 jmp wasArgEnd
wasArgStore:
 stosb
 inc si
 loop wasArgLoop
wasArgEnd:
 mov byte ptr [di],0
 mov wasNextSI,si
 call ExpandArg
 pop di
 pop cx
 pop bx
 pop ax
 ret
NextArgIntoInput endp

FetchArg proc near
 mov si,wasNextSI
 call NextArgIntoInput
 ret
FetchArg endp

; ExpandArg: variable interpolation %NAME% into wasInput, cap 259.
ExpandArg proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 lea si,wasArg
 lea di,wasInput
 mov dx,259
wasExpandLoop:
 lodsb
 or al,al
 jz wasExpandDone
 cmp al,'%'
 jne wasExpandCopy
 push si
 lea bx,wasWord
 mov cx,31
wasExpandVarName:
 mov al,[si]
 or al,al
 jz wasExpandBad
 cmp al,'%'
 je wasExpandVarEnd
 mov [bx],al
 inc bx
 inc si
 loop wasExpandVarName
wasExpandBad:
 pop si
 mov al,'%'
 jmp wasExpandCopy
wasExpandVarEnd:
 mov byte ptr [bx],0
 inc si
 add sp,2                 ; discard saved input position
 push si
 call FindVar
 jc wasExpandNoVar
 mov si,bx
wasExpandValue:
 lodsb
 or al,al
 jz wasExpandNoVar
 cmp dx,0
 je wasExpandNoVar
 stosb
 dec dx
 jmp wasExpandValue
wasExpandNoVar:
 pop si
 jmp wasExpandLoop
wasExpandCopy:
 or dx,dx
 jz wasExpandDone
 stosb
 dec dx
 jmp wasExpandLoop
wasExpandDone:
 mov byte ptr [di],0
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
ExpandArg endp

; FindVar: wasWord -> BX pointer to value, carry set if absent.
FindVar proc near
 push ax
 push cx
 push dx
 push si
 push di
 lea si,wasWord
 lea di,sysERRORCODE
 call EqualStrings
 jnc wasCheckResult
 call FormatErrorCode
 mov bx,offset wasNumResult
 clc
 jmp wasFindDone
wasCheckResult:
 ; EqualStrings advances SI on a partial match (SCREENW vs SCREENH).
 lea si,wasWord
 lea di,sysRESULT
 call EqualStrings
 jnc wasCheckWinVer
 call FormatResult
 jmp wasBuiltInReady
wasCheckWinVer:
 ; EqualStrings advances SI on a partial match (SCREENW vs SCREENH).
 lea si,wasWord
 lea di,sysWINVER
 call EqualStrings
 jnc wasCheckTime
 ; The only version field used for runtime feature gates is the major
 ; version reported by KERNEL.GetVersion (1/2/3 for current targets).
 ; In particular, Windows 1.01's GetVersion returns 0001h, NOT 0101h.
 call GetVersion
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 xor ah,ah
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckTime:
 ; DOS 2Ch evaluated at EVERY interpolation, not a cached startup time.
 lea si,wasWord
 lea di,sysTIME
 call EqualStrings
 jnc wasCheckDate
 mov ah,2Ch
 call Dos3Call
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 lea di,wasClockResult
 mov al,ch                 ; hours, 0..23
 call WriteTwoDigits
 mov al,':'
 stosb
 mov al,cl                 ; minutes, 0..59
 call WriteTwoDigits
 mov al,':'
 stosb
 mov al,dh                 ; seconds, 0..59
 call WriteTwoDigits
 xor al,al
 stosb
 jmp wasClockBuilt
wasCheckDate:
 ; DOS 2Ah, YYYY-MM-DD. All arithmetic is 8086 unsigned 16-bit.
 lea si,wasWord
 lea di,sysDATE
 call EqualStrings
 jnc wasCheckScreenW
 mov ah,2Ah
 call Dos3Call
 push dx                   ; preserve DH=month and DL=day
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 lea di,wasClockResult
 mov ax,cx                 ; 4-digit year
 mov cx,100
 xor dx,dx
 div cx                     ; AX=century, DX=year remainder
 push dx
 call WriteTwoDigits
 pop dx
 mov al,dl
 call WriteTwoDigits
 mov al,'-'
 stosb
 pop dx
 mov al,dh                 ; month
 call WriteTwoDigits
 mov al,'-'
 stosb
 mov al,dl                 ; day
 call WriteTwoDigits
 xor al,al
 stosb
wasClockBuilt:
 mov bx,offset wasClockResult
 clc
 jmp wasFindDone
wasCheckScreenW:
 ; EqualStrings advances SI on a partial match (SCREENW vs SCREENH).
 lea si,wasWord
 lea di,sysSCREENW
 call EqualStrings
 jnc wasCheckScreenH
 mov ax,8                ; HORZRES
 jmp wasQueryScreen
wasCheckScreenH:
 ; EqualStrings advances SI on a partial match (SCREENW vs SCREENH).
 lea si,wasWord
 lea di,sysSCREENH
 call EqualStrings
 jnc wasCheckBpp
 mov ax,10               ; VERTRES
 jmp wasQueryScreen
wasCheckBpp:
 ; EqualStrings advances SI on a partial match (SCREENW vs SCREENH).
 lea si,wasWord
 lea di,sysBPP
 call EqualStrings
 jnc wasCheckDiskFree
 mov ax,12               ; BITSPIXEL, multiply by PLANES=14
 jmp wasQueryScreen
wasCheckDiskFree:
 ; DISKFREE(C) is evaluated on demand via DOS INT 21h AH=36h,
 ; returning decimal BYTES. A 32-bit saturated maximum is permitted.
 ; The letter in parentheses is the DOS drive parameter A..Z.
 lea si,wasWord
 lea di,sysDISKFREE
 mov cx,9
wasDiskPrefix:
 mov al,[si]
 mov ah,[di]
 cmp al,'a'
 jb wasDiskCaseOK
 cmp al,'z'
 ja wasDiskCaseOK
 sub al,32
wasDiskCaseOK:
 cmp al,ah
 jne wasDiskUnknown
 inc si
 inc di
 loop wasDiskPrefix
 mov al,[si]
 cmp al,'a'
 jb wasDiskDriveUpper
 cmp al,'z'
 ja wasDiskDriveUpper
 sub al,32
wasDiskDriveUpper:
 cmp al,'A'
 jb wasDiskUnknown
 cmp al,'Z'
 ja wasDiskUnknown
 cmp byte ptr [si+1],')'
 jne wasDiskUnknown
 cmp byte ptr [si+2],0
 jne wasDiskUnknown
 jmp wasDiskDriveReady
wasDiskUnknown:
 jmp wasSearchVars
wasDiskDriveReady:
 sub al,'A'-1
 mov dl,al
 mov ah,36h
 call Dos3Call
 cmp ax,0FFFFh
 je wasDiskUnavailable
 ; AX=sectors per cluster, BX=free clusters, CX=bytes per sector.
 ; Compute free bytes saturating at 0FFFFFFFFh for overflow.
 mov si,ax
 mov di,cx
 mov ax,bx
 mul si                  ; DX:AX = free sectors
 mov bx,dx
 mul di                  ; DX:AX = low-sectors * bytes/sector
 mov si,ax
 mov cx,dx
 mov ax,bx
 mul di                  ; DX:AX = high-sectors * bytes/sector
 or dx,dx
 jnz wasDiskSaturated
 add ax,cx
 jc wasDiskSaturated
 mov dx,ax
 mov ax,si
 jmp wasDiskFormat
wasDiskSaturated:
 mov ax,0FFFFh
 mov dx,ax
wasDiskFormat:
 ; INT 21h does not promise ES; FormatDword copies with STOSB.
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 call FormatDword
 jmp wasBuiltInReady
wasDiskUnavailable:
 ; Unlike a DOS EXE, evaluating an environment query never launches a
 ; modal Windows dialog. For invalid/unready drives report zero bytes.
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 xor ax,ax
 call FormatDecimal
 jmp wasBuiltInReady
wasQueryScreen:
 ; Keep device-cap index on the stack, never in wasTemp: screen values
 ; can be expanded inside SHELLWAIT arguments while wasTemp holds WAIT=1.
 push ax                 ; requested GetDeviceCaps index (8/10/12)
 xor ax,ax
 push ax                 ; desktop HWND = NULL
 call GetDC
 pop cx                  ; requested cap index, keep AX=HDC
 or ax,ax
 jz wasScreenUnavailable
 mov bx,ax               ; HDC, preserved by Win16 FAR PASCAL calls
 push cx                 ; cap index (Win16 functions may overwrite CX)
 push bx                 ; preserve HDC across potentially clobbering GDI BX
 push bx
 push cx
 call GetDeviceCaps
 pop bx                 ; retrieve the original HDC
 pop cx
 cmp cx,12
 jne wasScreenRelease
 push ax                 ; BITSPIXEL
 push bx                 ; save HDC across second GDI call
 push bx                 ; HDC formal argument
 mov ax,14               ; PLANES
 push ax                 ; index formal argument
 call GetDeviceCaps
 pop bx                  ; original HDC
 pop cx                  ; BITSPIXEL
 mul cx
wasScreenRelease:
 push ax                 ; preserve count through ReleaseDC
 xor ax,ax
 push ax                 ; HWND=NULL
 push bx
 call ReleaseDC
 pop ax
 ; Do not assume GDI restores ES (ExpandArg uses STOSB).
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 call FormatDecimal
 jmp wasBuiltInReady
wasScreenUnavailable:
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 xor ax,ax
 call FormatDecimal
wasBuiltInReady:
 mov bx,offset wasNumResult
 clc
 jmp wasFindDone
wasSearchVars:
 mov cx,wasVarCount
 xor dx,dx
wasFindNext:
 or cx,cx
 jz wasVarMissing
 mov ax,dx
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 lea di,wasVarNames
 add di,ax
 lea si,wasWord
 call EqualStrings
 jc wasVarFound
 inc dx
 dec cx
 jmp wasFindNext
wasVarFound:
 mov ax,dx
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 mov bx,dx
 shl bx,1
 shl bx,1
 shl bx,1
 shl bx,1
 shl bx,1
 add ax,bx                ; 64 + 32 = 96
 add ax,offset wasVarValues
 mov bx,ax
 clc
 jmp wasFindDone
wasVarMissing:
 stc
wasFindDone:
 pop di
 pop si
 pop dx
 pop cx
 pop ax
 ret
FindVar endp

StoreVar proc near
 ; wasWord / wasInput; create or overwrite one of 8 slots.
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 call FindVar
 jc wasStoreNewVar
 ; Dynamic built-ins and RESULT/ERRORCODE share the numeric result slot.
 ; SET WINVER=..., SET BPP=..., SET DISKFREE(C)=..., etc. are no-ops.
 cmp bx,offset wasNumResult
 je wasStoreDone
 cmp bx,offset wasClockResult
 je wasStoreDone
 jmp wasExistingVar
wasStoreNewVar:
 mov ax,wasVarCount
 cmp ax,8
 jae wasStoreDone
 inc wasVarCount
 mov dx,ax
 ; name slot = index*16
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 lea di,wasVarNames
 add di,ax
 lea si,wasWord
 mov cx,15
wasStoreName:
 lodsb
 stosb
 or al,al
 jz wasNameStored
 loop wasStoreName
 mov byte ptr [di],0
wasNameStored:
 mov bx,dx
 shl bx,1
 shl bx,1
 shl bx,1
 shl bx,1
 shl bx,1
 mov ax,dx
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 shl ax,1
 add bx,ax
 add bx,offset wasVarValues
wasExistingVar:
 mov di,bx
 lea si,wasInput
 mov cx,95
wasStoreValue:
 lodsb
 stosb
 or al,al
 jz wasStoreDone
 loop wasStoreValue
 mov byte ptr [di],0
wasStoreDone:
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
StoreVar endp

; Format result as decimal for %ERRORCODE%.
FormatErrorCode proc near
 mov ax,wasErrorCode
 jmp FormatDecimal
FormatErrorCode endp

FormatResult proc near
 mov ax,wasResult
 jmp FormatDecimal
FormatResult endp

 ; AL=0..99, append two ASCII digits at ES:DI; preserves AL/BX.
WriteTwoDigits proc near
 push ax
 push bx
 xor ah,ah
 mov bl,10
 div bl
 add al,'0'
 stosb
 mov al,ah
 add al,'0'
 stosb
 pop bx
 pop ax
 ret
WriteTwoDigits endp

FormatDecimal proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 lea di,wasNumResult+6
 mov byte ptr [di],0
 mov bx,10
wasFormatLoop:
 xor dx,dx
 div bx
 add dl,'0'
 dec di
 mov [di],dl
 or ax,ax
 jnz wasFormatLoop
 ; move to start of wasNumResult
 mov si,di
 lea di,wasNumResult
wasFormatMove:
 lodsb
 stosb
 or al,al
 jnz wasFormatMove
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
FormatDecimal endp

; DX:AX unsigned bytes to decimal string, up to 4294967295.
; Uses only 8086 16-bit DIV: divide high word by 10, feed its
; remainder into low-word DIV, and repeat until both words zero.
FormatDword proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 lea di,wasNumResult+11
 mov byte ptr [di],0
 mov bx,10
wasDwordDigit:
 mov cx,ax               ; save low word
 mov ax,dx               ; high word
 xor dx,dx
 div bx                  ; high quotient AX, remainder DX
 mov si,ax
 mov ax,cx
 div bx                  ; low quotient AX, decimal remainder DX
 add dl,'0'
 dec di
 mov [di],dl
 mov dx,si
 or dx,dx
 jne wasDwordDigit
 or ax,ax
 jne wasDwordDigit
 mov si,di
 lea di,wasNumResult
wasDwordCopy:
 lodsb
 stosb
 or al,al
 jne wasDwordCopy
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
FormatDword endp

; GotoLabel: source at SI, read from start, jump after matching :LABEL.
GotoLabel proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 lea di,wasLabel
 mov cx,31
wasCopyLabel:
 lodsb
 stosb
 or al,al
 jz wasLabelReady
 loop wasCopyLabel
 mov byte ptr [di],0
wasLabelReady:
 mov bx,wasScriptH
 xor cx,cx
 xor dx,dx
 mov ax,4200h
 call Dos3Call
 jc wasLabelMissing
wasSeekLabel:
 call ReadLine
 jc wasLabelMissing
 lea si,wasLine
 call TrimSI
 cmp byte ptr [si],':'
 jne wasSeekLabel
 inc si
 lea di,wasLabel
 call EqualStrings
 jnc wasSeekLabel
 clc
 jmp wasLabelDone
wasLabelMissing:
 stc
wasLabelDone:
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
GotoLabel endp

; Case-insensitive equality, SI and DI NUL terminated, CF=1 equal.
EqualStrings proc near
 push ax
 push bx
wasEqualLoop:
 mov al,[si]
 mov bl,[di]
 cmp al,'a'
 jb wasUpperA
 cmp al,'z'
 ja wasUpperA
 sub al,32
wasUpperA:
 cmp bl,'a'
 jb wasUpperB
 cmp bl,'z'
 ja wasUpperB
 sub bl,32
wasUpperB:
 cmp al,bl
 jne wasNotEqual
 or al,al
 je wasEqual
 inc si
 inc di
 jmp wasEqualLoop
wasEqual:
 stc
 jmp wasEqualDone
wasNotEqual:
 clc
wasEqualDone:
 pop bx
 pop ax
 ret
EqualStrings endp
IsCommand proc near
 push si
 push di
 call EqualStrings
 pop di
 pop si
 ret
IsCommand endp

; String copy helpers: in SI,DI, always NUL terminate within cap.
CopyString128 proc near
 mov cx,127
 jmp CopyBounded
CopyString128 endp
CopyString260 proc near
 mov cx,259
 jmp CopyBounded
CopyString260 endp
CopyString16 proc near
 mov cx,15
 jmp CopyBounded
CopyString16 endp
CopyBounded proc near
 push ax
wasCopyBound:
 lodsb
 stosb
 or al,al
 jz wasCopyBoundDone
 loop wasCopyBound
 mov byte ptr [di],0
wasCopyBoundDone:
 pop ax
 ret
CopyBounded endp

; Parse unsigned 0..65535 in SI; carry set on invalid.
ParseUInt proc near
 push bx
 push cx
 push dx
 xor ax,ax
 xor cx,cx
 mov bx,10
wasParseDigit:
 mov dl,[si]
 cmp dl,'0'
 jb wasParseEnd
 cmp dl,'9'
 ja wasParseEnd
 sub dl,'0'
 xor dh,dh
 push dx
 mul bx
 or dx,dx
 jnz wasParseOverflow
 pop dx
 add ax,dx
 jc wasParseError
 inc si
 inc cx
 jmp wasParseDigit
wasParseOverflow:
 pop dx
 jmp wasParseError
wasParseEnd:
 or cx,cx
 jz wasParseError
 cmp byte ptr [si],0
 jne wasParseError
 clc
 jmp wasParseDone
wasParseError:
 stc
wasParseDone:
 pop dx
 pop cx
 pop bx
 ret
ParseUInt endp

LogLine proc near
 push ax
 push bx
 push cx
 push dx
 push si
 cmp wasIo,0FFFFh
 je wasLogDone
 xor cx,cx
wasLogLen:
 cmp byte ptr [si],0
 je wasLogWrite
 inc si
 inc cx
 jmp wasLogLen
wasLogWrite:
 mov bx,wasIo
 mov dx,offset wasInput
 mov ah,40h
 call Dos3Call
 mov bx,wasIo
 mov dx,offset wasCRLF
 mov cx,2
 mov ah,40h
 call Dos3Call
wasLogDone:
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
LogLine endp

; Read-only text constants (within DGROUP for Win1 startup discipline).
.data
cmdShowIconYes db 'SHOWICON=YES',0
cmdShowIconNo  db 'SHOWICON=NO',0
cmdLOG       db 'LOG',0
cmdLOGFILE   db 'LOGFILE',0
PUBLIC cmdLOGCLOSE
cmdLOGCLOSE  db 'LOGClose',0
cmdWAIT      db 'WAIT',0
cmdSET       db 'SET',0
cmdCHDIR     db 'CHDIR',0
cmdCD        db 'CD',0
cmdMKDIR     db 'MKDIR',0
cmdMD        db 'MD',0
cmdRMDIR     db 'RMDIR',0
cmdRD        db 'RD',0
cmdDEL       db 'DEL',0
cmdDELETE    db 'DELETE',0
cmdERASE     db 'ERASE',0
cmdCOPY      db 'COPY',0
cmdMOVE      db 'MOVE',0
cmdREN       db 'REN',0
cmdRENAME    db 'RENAME',0
cmdDIR       db 'DIR',0
cmdPWD       db 'PWD',0
cmdSHELLWAIT db 'SHELLWAIT',0
cmdSHELL     db 'SHELL',0
cmdGOTO      db 'GOTO',0
cmdGOSUB     db 'GOSUB',0
cmdRETURN    db 'RETURN',0
cmdIF        db 'IF',0
cmdEXISTS    db 'EXISTS',0
cmdASSERT    db 'ASSERT',0
cmdTHEN      db 'THEN',0
cmdTARCREATE db 'TARCREATE',0
cmdTARADD    db 'TARADD',0
cmdTARCLOSE  db 'TARCLOSE',0
cmdSNAP      db 'SNAP',0
cmdSNAPSAFE  db 'SNAPSAFE',0
snapModeFastName db 'FAST',0
snapModeCompatName db 'COMPAT',0
snapModeAutoName db 'AUTO',0
cmdSHUTDOWN  db 'SHUTDOWN',0
cmdPASS      db 'PASS',0
cmdFAIL      db 'FAIL',0
cmdEND       db 'END',0
opEQ         db 'EQ',0
opASSIGN     db '=',0
opNE         db 'NE',0
opDIFF       db '<>',0
sysTIME      db 'TIME',0
sysDATE      db 'DATE',0
sysERRORCODE db 'ERRORCODE',0
sysRESULT    db 'RESULT',0
sysWINVER    db 'WINVER',0
sysSCREENW   db 'SCREENW',0
sysSCREENH   db 'SCREENH',0
sysBPP       db 'BPP',0
sysDISKFREE  db 'DISKFREE(',0
end start
