; NOWBAT 0.0.54: compact Windows Automated Scripting runtime (8088 baseline).
; Tiny 8086 Win16 interpreter; native evidence is required for runtime PASS.
; The executor is intentionally line-at-a-time. GOTO scans the script on disk.
.8086
.model small
.stack 2048

extrn InitTask:far
extrn WaitEvent:far
extrn InitApp:far
extrn GetVersion:far
PUBLIC Dos3Call,wasErrorCode,LogLine,EqualStrings
PUBLIC wasInst,wasStop
extrn UiOpen:near,UiClose:near,UiPump:near
extrn WasZeroStart:byte,WasZeroEnd:byte
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
extrn GetModuleHandle:far
extrn GetProcAddress:far
extrn SetActiveWindow:far
extrn GetActiveWindow:far
IFDEF WAS_WIN300
extrn GetMouseEventProc:far
ENDIF
extrn SetCursorPos:far    ; USER.70: Win16 absolute desktop cursor
extrn GetCursorPos:far    ; USER.17: FAR POINT pointer
extrn EnumWindows:far ; USER.54
extrn GetWindowText:far ; USER.36
extrn IsWindow:far ; USER.47
extrn GetClientRect:far ; USER.33
extrn ClientToScreen:far ; USER.28
extrn MakeProcInstance:far ; KERNEL.51
extrn FreeProcInstance:far ; KERNEL.52
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
PUBLIC wasResult,wasIo,wasRect,wasBpp,wasSnapMode
extrn wasInput:byte ; storage in final zero arena (WASUI.ASM)
wasResult      dw 0
wasErrorCode   dw 0
wasIo          dw 0FFFFh
wasRect        dw 4 dup(0FFFFh)
wasBpp         dw 0
wasSnapMode    db 0     ; 0=COMPAT, 1=FAST (SNAP default), 2=AUTO
wasInst        dw 0
wasDefault     db 'WAS.WAS',0
extrn wasScript:byte ; storage in final zero arena (WASUI.ASM)
extrn wasLine:byte ; storage in final zero arena (WASUI.ASM)
wasCommand     db 24 dup(0)
extrn wasArg:byte ; storage in final zero arena (WASUI.ASM)
extrn wasWord:byte ; storage in final zero arena (WASUI.ASM)
extrn wasLHS:byte ; storage in final zero arena (WASUI.ASM)
wasOp          db 16 dup(0)
extrn wasRHS:byte ; storage in final zero arena (WASUI.ASM)
wasCharacter   db 0
wasScriptH     dw 0FFFFh
wasLineNo      dw 0
wasNextSI      dw 0
wasSubDepth    dw 0
wasSubs        dw 8 dup(0)  ; 4 caller offsets, low/high pairs
extrn wasLabel:byte ; storage in final zero arena (WASUI.ASM)
extrn wasVarNames:byte ; 8 x 16
extrn wasVarValues:byte ; 8 x 96
wasVarCount    dw 0
wasNumResult   db 12 dup(0) ; decimal WORD/DWORD output, shared by built-in vars
wasClockResult db 16 dup(0) ; DATE YYYY-MM-DD or TIME HH:MM:SS (live DOS clock)
wasSetTarget   db 16 dup(0)
extrn wasSnapPath:byte ; storage in final zero arena (WASUI.ASM)
wasCRLF        db 13,10
wasLogPath     db 'WAS.LOG',0
; Win16 KERNEL.45 LoadModule parameter block (14 bytes, not a DOS EXEC
; PSP/FCB block): WORD environment, FAR command tail, FAR show-state,
; DWORD reserved. NOWBAT's proven Windows 1.x launcher uses this layout.
; The command tail is length-prefixed and NUL-terminated; the show block
; contains two WORDs: byte length=2 and SW_SHOWNORMAL=1.
extrn wasExecPath:byte ; storage in final zero arena (WASUI.ASM)
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
wasWindowHwnd dw 0
wasWindowCount db 0
wasWaitWindow db 0
wasWindowProc dw 2 dup(0)
extrn wasWindowCaption:byte ; storage in final zero arena (WASUI.ASM)
extrn wasWindowScratch:byte ; storage in final zero arena (WASUI.ASM)
wasWindowRect dw 4 dup(0)
wasWindowOrigin dw 2 dup(0)
wasInputProc dw 2 dup(0) ; validated USER mouse callback
wasDriverName dw offset inputMouseName
wasKeyProc dw 2 dup(0)
wasKeyPair dw 0
wasKeyAction db 0
extrn wasKeysHeld:byte ; indexed by XT scan, value=VK (supports OEM VKs)
; First 7 words are also emitted as private failure-probe metadata.
wasUserCode dw 0
wasUserExportSeg dw 0
wasDriverEntry dw 2 dup(0)
wasDriverExport dw 2 dup(0)
wasDriverData dw 0
wasCandidate dw 0
wasStorageSeg dw 0
wasStoragePrefix db 0
wasDragDX dw 0
wasDragDY dw 0
wasDragBudget dw 0
wasDragCapX dw 0
wasDragCapY dw 0
wasMouseHeld db 0
wasMouseAction db 0
wasFocusSelect db 0
wasMouseMask db 0
wasMouseDownFlag dw 0
wasMouseUpFlag dw 0
wasMouseRelative db 0
wasMouseReqX   dw 0
wasMouseReqY   dw 0
wasMousePoint  dw 2 dup(0FFFFh) ; USER POINT; sentinel on unavailable readback
wasTemp        dw 0
extrn wasRawTail:byte ; storage in final zero arena (WASUI.ASM)
wasTraceH      dw 0FFFFh
wasTracePath   db 'EARLY.LOG',0
traceTask      db 'WAS_INITTASK',0
traceBuild     db 'NOWBAT_BUILD=W054',0 ; resident startup identity for audit
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
 ; Restore all omitted on-disk zero buffers before any script or UI use.
 ; InitTask has supplied DS; preserve its ES:BX command-tail pointer.
 push es
 push ds
 pop es
 mov di,offset WasZeroStart
 mov cx,offset WasZeroEnd
 sub cx,di
 xor ax,ax
 cld
 rep stosb
 pop es
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
 lea di,cmdDOEVENTS
 call IsCommand
 jc commandDoEvents
 lea di,cmdWAITFOR
 call IsCommand
 jc commandWaitFor
 lea di,cmdMOUSEMOVE
 call IsCommand
 jc commandMouseMove
 lea di,cmdWINDOWSELECT
 call IsCommand
 jc commandWindowSelect
 lea di,cmdWINDOWFOCUS
 call IsCommand
 jc commandWindowFocus
 lea di,cmdMOUSEDOWN
 call IsCommand
 jc commandMouseDown
 lea di,cmdMOUSEUP
 call IsCommand
 jc commandMouseUp
 lea di,cmdMOUSECLICK
 call IsCommand
 jc commandMouseClick
 lea di,cmdMOUSEDBLCLICK
 call IsCommand
 jc commandMouseDblClick
 lea di,cmdKEYDOWN
 call IsCommand
 jc commandKeyDown
 lea di,cmdKEYUP
 call IsCommand
 jc commandKeyUp
 lea di,cmdKEYPRESS
 call IsCommand
 jc commandKeyPress
 lea di,cmdKEYCOMBO
 call IsCommand
 jc commandKeyCombo
 lea di,cmdTYPE
 call IsCommand
 jc commandType
 lea di,cmdRELEASEINPUT
 call IsCommand
 jc commandReleaseInput
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

; One bounded message-pump pass followed by a cooperative task yield.
; UiPump normally skips the queue when headless, so temporarily enable it.
; No new window or resident worker is created. Held-input state is untouched.
commandDoEvents:
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasCmdFailure
 xor ax,ax
 mov al,uiPumpAny
 push ax
 mov uiPumpAny,1
 call UiPump
 pop ax
 mov uiPumpAny,al
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 cmp wasStop,0
 jne wasExit
 call Yield
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 cmp wasStop,0
 jne wasExit
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasLoop

; Absolute desktop movement, not a fake WM_MOUSEMOVE. USER does clipping.
; Require exact live readback; never trust the legacy VOID return value.
commandMouseMove:
 mov wasMouseRelative,0
 call FetchArg
 lea si,wasInput
 lea di,winRelName
 call EqualStrings
 jnc wasMouseParseX
 mov wasMouseRelative,1
 call FetchArg
wasMouseParseX:
 lea si,wasInput
 call ParseUInt
 jc wasMouseBadArg
 cmp ax,7FFFh
 ja wasMouseBadArg
 mov wasMouseReqX,ax
 call FetchArg
 lea si,wasInput
 call ParseUInt
 jc wasMouseBadArg
 cmp ax,7FFFh
 ja wasMouseBadArg
 mov wasMouseReqY,ax
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasMouseBadArg
 cmp wasMouseRelative,0
 je wasMouseAbsolute
 call WasReadWindow
 jc wasMouseBadArg
 mov ax,wasMouseReqX
 cmp ax,wasWindowRect+4
 jae wasMouseBadArg
 add ax,wasWindowOrigin
 jo wasMouseBadArg
 test ax,8000h
 jnz wasMouseBadArg
 mov wasMouseReqX,ax
 mov ax,wasMouseReqY
 cmp ax,wasWindowRect+6
 jae wasMouseBadArg
 add ax,wasWindowOrigin+2
 jo wasMouseBadArg
 test ax,8000h
 jnz wasMouseBadArg
 mov wasMouseReqY,ax
wasMouseAbsolute:
 ; While a button is held, move through the actual input callback. USER's
 ; absolute cursor setter is retained for ordinary, unheld positioning.
 cmp wasMouseHeld,0
 je wasMouseSetAbsolute
 call WasDragToPoint
 jc wasMouseMismatch
 jmp wasMouseMoveOK
wasMouseSetAbsolute:
 push wasMouseReqX         ; Win16 FAR PASCAL x, y (left to right)
 push wasMouseReqY
 call SetCursorPos
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 call WasReadMouse
 mov ax,wasMousePoint
 cmp ax,wasMouseReqX
 jne wasMouseMismatch
 mov ax,wasMousePoint+2
 cmp ax,wasMouseReqY
 jne wasMouseMismatch
wasMouseMoveOK:
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasLoop
wasMouseBadArg:
 mov wasResult,2
 mov wasErrorCode,87        ; invalid argument
 jmp wasLoop
wasMouseMismatch:
 mov wasResult,2           ; cursor clipped or unavailable
 mov wasErrorCode,0        ; USER gives no extended error
 jmp wasLoop

; Read an actual Win16 POINT. Do not assume GetCursorPos returns BOOL.
WasReadMouse proc near
 mov word ptr wasMousePoint,0FFFFh
 mov word ptr wasMousePoint+2,0FFFFh
 push ds
 mov ax,offset wasMousePoint
 push ax
 call GetCursorPos
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 ; Real-mode desktops have nonnegative signed coordinates. Normalize an
 ; unavailable or negative POINT to the documented sentinel.
 test word ptr wasMousePoint,8000h
 jnz wasMouseReadInvalid
 test word ptr wasMousePoint+2,8000h
 jz wasMouseReadDone
wasMouseReadInvalid:
 mov word ptr wasMousePoint,0FFFFh
 mov word ptr wasMousePoint+2,0FFFFh
wasMouseReadDone:
 ret
WasReadMouse endp

; Exact top-level caption selection. No activation or input is fabricated.
; The enumeration callback always continues, so duplicate captions fail.
commandWindowFocus:
 mov wasFocusSelect,1
 jmp wasWindowSelectStart
commandWindowSelect:
 mov wasFocusSelect,0
wasWindowSelectStart:
 mov wasWindowHwnd,0
 mov wasWindowCount,0
 call FetchArg
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasWindowBad
 lea si,wasInput
 lea di,wasWindowCaption
 mov cx,127
 cmp byte ptr [si],0
 je wasWindowBad
wasWindowCopy:
 lodsb
 stosb
 or al,al
 jz wasWindowEnumerate
 loop wasWindowCopy
 jmp wasWindowBad
wasWindowEnumerate:
 call WasFindWindow
 cmp ax,0
 je wasWindowFound
 cmp ax,1
 je wasWindowMissing
 jmp wasWindowBad
wasWindowFound:
 cmp wasFocusSelect,0
 je wasWindowSelectOK
 push wasWindowHwnd
 call SetActiveWindow
 call WasWindowData
 call GetActiveWindow
 call WasWindowData
 cmp ax,wasWindowHwnd
 jne wasWindowBad
wasWindowSelectOK:
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasLoop
wasWindowMissing:
 mov wasWindowHwnd,0
 mov wasResult,1
 mov wasErrorCode,0
 jmp wasLoop
wasWindowBad:
 mov wasWindowHwnd,0
 mov wasResult,2
 mov wasErrorCode,87
 jmp wasLoop

; Probe a unique usable caption. AX=0 found, 1 missing, 2 error.
; Every probe clears the previous handle; no activation occurs here.
WasFindWindow proc near
 mov wasWindowHwnd,0
 mov wasWindowCount,0
 push cs
 mov ax,offset WasEnumWindow
 push ax
 push wasInst
 call MakeProcInstance
 call WasWindowData
 mov wasWindowProc,ax
 mov wasWindowProc+2,dx
 or ax,dx
 jz wasFindWindowBad
 push wasWindowProc+2
 push wasWindowProc
 xor ax,ax
 push ax
 push ax
 call EnumWindows
 call WasWindowData
 push wasWindowProc+2
 push wasWindowProc
 call FreeProcInstance
 call WasWindowData
 cmp wasWindowCount,0
 je wasFindWindowMissing
 cmp wasWindowCount,1
 jne wasFindWindowBad
 call WasReadWindow
 jc wasFindWindowBad
 xor ax,ax
 ret
wasFindWindowMissing:
 mov ax,1
 ret
wasFindWindowBad:
 mov wasWindowHwnd,0
 mov ax,2
 ret
WasFindWindow endp

; Preserve the return DX:AX from FAR PASCAL calls while restoring segments.
WasWindowData proc near
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 ret
WasWindowData endp

; HWND, LPARAM; callback returns BOOL and removes six argument bytes.
WasEnumWindow proc far
 push bp
 mov bp,sp
 push ds
 push es
 push bx
 push cx
 push dx
 push si
 push di
 call WasWindowData
 mov bx,[bp+10]
 call WasWindowMatch
 jnc wasEnumNext
 cmp wasWindowCount,2
 jae wasEnumNext
 inc wasWindowCount
 mov ax,[bp+10]
 mov wasWindowHwnd,ax
wasEnumNext:
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop es
 pop ds
 mov ax,1
 pop bp
 retf 6
WasEnumWindow endp

; BX=HWND. CF=1 for a full case-insensitive caption match.
WasWindowMatch proc near
 mov byte ptr wasWindowScratch,0
 push bx
 push ds
 mov ax,offset wasWindowScratch
 push ax
 mov ax,128
 push ax
 call GetWindowText
 call WasWindowData
 or ax,ax
 jz wasWindowNoMatch
 cmp ax,127
 jae wasWindowNoMatch
 lea si,wasWindowCaption
 lea di,wasWindowScratch
 call EqualStrings
 ret
wasWindowNoMatch:
 clc
 ret
WasWindowMatch endp

; CF=0 for live client geometry, CF=1 if no valid selected window.
; Re-check the caption to reject stale/reused HWNDs. Keep result variables
; untouched during read-only interpolation. Coordinates are screen pixels.
WasReadWindow proc near
 mov ax,wasWindowHwnd
 or ax,ax
 jz wasWindowReadBad
 push ax
 call IsWindow
 call WasWindowData
 or ax,ax
 jz wasWindowReadBad
 mov bx,wasWindowHwnd
 call WasWindowMatch
 jnc wasWindowReadBad
 mov word ptr wasWindowRect,0FFFFh
 mov word ptr wasWindowRect+2,0FFFFh
 mov word ptr wasWindowRect+4,0
 mov word ptr wasWindowRect+6,0
 push wasWindowHwnd
 push ds
 mov ax,offset wasWindowRect
 push ax
 call GetClientRect
 call WasWindowData
 cmp word ptr wasWindowRect,0
 jne wasWindowReadBad
 cmp word ptr wasWindowRect+2,0
 jne wasWindowReadBad
 mov ax,wasWindowRect+4
 or ax,ax
 jle wasWindowReadBad
 mov ax,wasWindowRect+6
 or ax,ax
 jle wasWindowReadBad
 mov word ptr wasWindowOrigin,0
 mov word ptr wasWindowOrigin+2,0
 push wasWindowHwnd
 push ds
 mov ax,offset wasWindowOrigin
 push ax
 call ClientToScreen
 call WasWindowData
 clc
 ret
wasWindowReadBad:
 mov wasWindowHwnd,0
 stc
 ret
WasReadWindow endp

 ; W075: genuine native mouse input. Win3 provides the USER callback getter.
; Legacy drivers can store the callback in CS or in DLL automatic data.
; Accept only a unique pointer supported by paired direct stores in Enable
; and a matching indirect FAR call in the driver's code. Never write driver
; memory or call Enable/Disable. Unknown layouts fail closed.
WasLookupOrdinal proc near
 push bx
 push ds
 push si
 call GetModuleHandle
 call WasWindowData
 pop bx
 or ax,ax
 jz wasLookupMissing
 push ax
 xor ax,ax
 push ax
 push bx
 call GetProcAddress
 call WasWindowData
 ret
wasLookupMissing:
 xor dx,dx
 ret
WasLookupOrdinal endp

; Loaded Win1/2 exports may be kernel entry stubs, not the driver body.
; Observed WIN101 form: SAR BYTE PTR CS:[disp16],1; JMP FAR ptr16:16.
; Follow the jump without executing the reference-count instruction. Also
; support a plain far-jump entry. Bound the chain; never call a guess.
; DX:AX in/out, CF on invalid/cyclic chain; other registers unchanged.
WasFollowEntry proc near
 push bx
 push cx
 push si
 push es
 mov cx,8
wasFollowNext:
 or dx,dx
 jz wasFollowBad
 cmp ax,0FFF6h
 ja wasFollowBad
 mov es,dx
 mov si,ax
 cmp byte ptr es:[si],0EAh
 je wasFollowFar
 cmp word ptr es:[si],0D02Eh
 jne wasFollowDone
 cmp byte ptr es:[si+2],3Eh
 jne wasFollowDone
 cmp byte ptr es:[si+5],0EAh
 jne wasFollowDone
 add si,5
wasFollowFar:
 mov bx,es:[si+1]
 mov dx,es:[si+3]
 mov ax,bx
 dec cx
 jnz wasFollowNext
wasFollowBad:
 xor ax,ax
 xor dx,dx
 stc
 jmp wasFollowExit
wasFollowDone:
 clc
wasFollowExit:
 pop es
 pop si
 pop cx
 pop bx
 ret
WasFollowEntry endp

WasResolveMouse proc near
 cmp word ptr wasInputProc+2,0
 jne wasResolveReady
IFDEF WAS_WIN300
 cmp wasDriverName,offset inputMouseName
 jne wasResolveLegacy
 call GetMouseEventProc
 call WasWindowData
 or dx,dx
 jz wasResolveLegacy
 mov wasInputProc,ax
 mov wasInputProc+2,dx
 jmp wasResolveReady
ENDIF
wasResolveLegacy:
 mov wasUserCode,0
 mov wasUserExportSeg,0
 mov word ptr wasDriverEntry,0
 mov word ptr wasDriverEntry+2,0
 mov word ptr wasDriverExport,0
 mov word ptr wasDriverExport+2,0
 mov wasDriverData,0
 lea si,inputUserName
 mov bx,17
 call WasLookupOrdinal
 or dx,dx
 jz wasResolveBad
 mov wasUserExportSeg,dx
 call WasFollowEntry
 jc wasResolveBad
 mov wasUserCode,dx
 mov si,wasDriverName
 mov bx,2
 call WasLookupOrdinal
 or dx,dx
 jz wasResolveBad
 mov wasDriverExport,ax
 mov wasDriverExport+2,dx
 call WasFollowEntry
 jc wasResolveBad
 cmp ax,0FF7Fh
 ja wasResolveBad
 mov wasDriverEntry,ax
 mov wasDriverEntry+2,dx
 mov es,dx
 mov wasDriverData,0
 mov si,wasDriverEntry
 call WasFindDriverData
 cmp wasDriverData,0
 jne wasDriverDataResolved
 ; Some drivers export a thin Enable routine. Inquire is another DLL
 ; export in the same module, so its recognized prologue can supply DS.
 mov si,wasDriverName
 mov bx,1
 call WasLookupOrdinal
 or dx,dx
 jz wasDriverDataResolved
 call WasFollowEntry
 jc wasDriverDataResolved
 cmp ax,0FFF0h
 ja wasDriverDataResolved
 mov es,dx
 mov si,ax
 call WasFindDriverData
wasDriverDataResolved:
 ; KEYBOARD Enable receives a FAR callback plus a FAR key-state buffer.
 ; Win1's ISR lives outside Enable's code segment. Its explicit stack
 ; argument stores identify the live callback without a mouse call-site.
 cmp wasDriverName,offset inputKeyName
 jne wasResolveGeneric
 call WasKeyEnableSlot
 jc wasResolveGeneric
 jmp wasResolveReady
wasResolveGeneric:
 mov es,wasDriverEntry+2
 ; First search CS-relative storage (older single-segment drivers).
 mov ax,wasDriverEntry+2
 mov wasStorageSeg,ax
 mov wasStoragePrefix,2Eh
 call WasScanMouseStores
 jc wasResolveBad
 ; Then search automatic-data storage, where the DLL entry prologue
 ; gives us the actual loaded DS, rather than assuming DS equals CS.
 mov ax,wasDriverData
 or ax,ax
 jz wasResolveCheck
 mov wasStorageSeg,ax
 mov wasStoragePrefix,0
 call WasScanMouseStores
 jc wasResolveBad
wasResolveCheck:
 cmp word ptr wasInputProc+2,0
 je wasResolveBad
wasResolveReady:
 call WasWindowData
 clc
 ret
wasResolveBad:
 mov word ptr wasInputProc,0
 mov word ptr wasInputProc+2,0
 call WasWindowData
 call WasInputProbe
 stc
 ret
WasResolveMouse endp

; Win1 keyboard Enable's explicit callback capture (observed W078):
; LES BX,[BP+0Ah]; MOV AX,ES; MOV [slot],BX; MOV [slot+2],ES.
; Only accept this exact argument/store sequence in the entry prologue,
; with a recognized DLL DS and a live pointer into the known USER segment.
; No fixed physical addresses, interrupts, driver writes or guessed calls.
WasKeyEnableSlot proc near
 mov ax,wasDriverData
 or ax,ax
 jz wasKeySlotBad
 mov es,wasDriverEntry+2
 mov si,wasDriverEntry
 mov cx,32
wasKeySlotScan:
 cmp word ptr es:[si],5EC4h
 jne wasKeySlotNext
 cmp word ptr es:[si+2],8C0Ah
 jne wasKeySlotNext
 cmp word ptr es:[si+4],89C0h
 jne wasKeySlotNext
 cmp byte ptr es:[si+6],1Eh
 jne wasKeySlotNext
 cmp word ptr es:[si+9],068Ch
 jne wasKeySlotNext
 mov bx,es:[si+7]
 cmp bx,0FFFCh
 ja wasKeySlotBad
 mov ax,bx
 add ax,2
 cmp ax,es:[si+11]
 jne wasKeySlotBad
 mov es,wasDriverData
 mov ax,es:[bx]
 mov dx,es:[bx+2]
 or ax,ax
 jz wasKeySlotBad
 cmp dx,wasUserCode
 je wasKeySlotOK
 cmp dx,wasUserExportSeg
 jne wasKeySlotBad
wasKeySlotOK:
 mov wasInputProc,ax
 mov wasInputProc+2,dx
 clc
 ret
wasKeySlotNext:
 inc si
 loop wasKeySlotScan
wasKeySlotBad:
 stc
 ret
WasKeyEnableSlot endp

; Recognize the Win16 DLL export prologue: MOV AX,automatic-data-segment,
; optional NOP, INC BP/PUSH BP/MOV BP,SP/PUSH DS/MOV DS,AX. Do not infer
; a data segment from arbitrary immediate values. ES is driver code.
WasFindDriverData proc near
 push si
 cmp si,0FFDFh
 ja wasDriverDataFrameOnly
 mov cx,24
wasDriverCSScan:
 ; Single-segment assembler drivers may load DS directly from CS.
 cmp word ptr es:[si],1F0Eh
 je wasDriverCSFound
 cmp word ptr es:[si],0C88Ch
 jne wasDriverCSNext
 cmp word ptr es:[si+2],0D88Eh
 je wasDriverCSFound
wasDriverCSNext:
 inc si
 loop wasDriverCSScan
wasDriverDataFrameOnly:
 pop si
 cmp byte ptr es:[si],0B8h
 jne wasDriverDataDone
 mov dx,es:[si+1]
 add si,3
 cmp byte ptr es:[si],90h
 jne wasDriverDataFrame
 inc si
wasDriverDataFrame:
 cmp word ptr es:[si],5545h
 jne wasDriverDataDone
 cmp word ptr es:[si+2],0EC8Bh
 je wasDriverDataFrameOK
 cmp word ptr es:[si+2],0E589h
 jne wasDriverDataDone
wasDriverDataFrameOK:
 cmp byte ptr es:[si+4],1Eh
 jne wasDriverDataDone
 cmp word ptr es:[si+5],0D88Eh
 je wasDriverDataFound
 cmp word ptr es:[si+5],1F50h
 jne wasDriverDataDone
wasDriverDataFound:
 mov wasDriverData,dx
 jmp wasDriverDataDone
wasDriverCSFound:
 pop si
 mov wasDriverData,es
wasDriverDataDone:
 ret
WasFindDriverData endp

; Get direct word-store operand at ES:SI for the selected storage model.
; AX/BX scratch, SI unchanged. CF=0 and BX=offset on success.
WasMouseStoreOperand proc near
 push si
 cmp wasStoragePrefix,0
 je wasStoreDefaultSeg
 cmp byte ptr es:[si],2Eh
 jne wasStoreOperandBad
 inc si
 jmp wasStoreOpcode
wasStoreDefaultSeg:
 cmp byte ptr es:[si],3Eh
 jne wasStoreDefaultCheck
 inc si
 jmp wasStoreOpcode
wasStoreDefaultCheck:
 cmp si,wasDriverEntry
 je wasStoreOpcode
 ; Do not misinterpret a CS/ES/SS-prefixed store as a DS store.
 mov al,es:[si-1]
 cmp al,2Eh
 je wasStoreOperandBad
 cmp al,26h
 je wasStoreOperandBad
 cmp al,36h
 je wasStoreOperandBad
wasStoreOpcode:
 mov al,es:[si]
 cmp al,0A3h
 je wasStoreOperandA3
 cmp al,89h
 je wasStoreOperandModRM
 cmp al,8Ch
 je wasStoreOperandModRM
 cmp al,8Fh
 jne wasStoreOperandBad
wasStoreOperandModRM:
 mov al,es:[si+1]
 and al,0C7h
 cmp al,06h
 jne wasStoreOperandBad
 mov bx,es:[si+2]
 jmp wasStoreOperandOK
wasStoreOperandA3:
 mov bx,es:[si+1]
wasStoreOperandOK:
 pop si
 clc
 ret
wasStoreOperandBad:
 pop si
 stc
 ret
WasMouseStoreOperand endp

WasScanMouseStores proc near
 mov si,wasDriverEntry
 mov cx,124
wasResolveScan:
 call WasMouseStoreOperand
 jc wasResolveNext
 cmp bx,0FFFCh
 ja wasResolveNext
 ; A valid pointer must target the known loaded USER code segment.
 push es
 mov es,wasStorageSeg
 mov ax,es:[bx+2]
 pop es
 cmp ax,wasUserCode
 je wasResolveUserSegmentOK
 cmp ax,wasUserExportSeg
 jne wasResolveNext
wasResolveUserSegmentOK:
 push si
 push cx
 push bx
 add bx,2
 call WasFindStore
 pop bx
 jc wasResolveSkip
 call WasFindCall
 jc wasResolveSkip
 push es
 mov es,wasStorageSeg
 mov ax,es:[bx]
 mov dx,es:[bx+2]
 pop es
 cmp word ptr wasInputProc+2,0
 je wasResolveFirst
 cmp wasInputProc,ax
 jne wasResolveConflict
 cmp wasInputProc+2,dx
 jne wasResolveConflict
 jmp wasResolveSkip
wasResolveFirst:
 mov wasInputProc,ax
 mov wasInputProc+2,dx
wasResolveSkip:
 pop cx
 pop si
wasResolveNext:
 inc si
 dec cx
 jz wasResolveScanDone
 jmp wasResolveScan
wasResolveConflict:
 pop cx
 pop si
 stc
 ret
wasResolveScanDone:
 clc
 ret
WasScanMouseStores endp

; Private failure evidence, INABI.DAT: 128 bytes of resolved Enable,
; seven little-endian metadata words (USER resolved/export segments,
; Enable resolved/export far pointers, driver DS), then first 512 bytes
; of the resolved driver code segment. Keyboard failure also appends
; the first 1024 bytes of recognized driver DS (live slot/ISR evidence).
; Never package in public DIST.
; The failure report keeps both the actual routine and its data context.
WasInputProbe proc near
 cmp word ptr wasDriverEntry+2,0
 je wasProbeDone
 push ds
 pop es
 mov ax,wasDriverEntry+2
 mov si,wasDriverEntry
 mov ds,ax
 mov di,offset wasWindowScratch
 mov cx,128
 cld
 rep movsb
 call WasWindowData
 mov ah,3Ch
 xor cx,cx
 lea dx,inputProbePath
 call Dos3Call
 jc wasProbeDone
 mov bx,ax
 push bx
 mov ah,40h
 mov cx,128
 lea dx,wasWindowScratch
 call Dos3Call
 pop bx
 push bx
 mov ah,40h
 mov cx,14
 lea dx,wasUserCode
 call Dos3Call
 pop bx
 push bx
 mov ax,wasDriverEntry+2
 mov ds,ax
 xor dx,dx
 mov cx,512
 mov ah,40h
 call Dos3Call
 call WasWindowData
 pop bx
 cmp wasDriverName,offset inputKeyName
 jne wasProbeClose
 mov ax,wasDriverData
 or ax,ax
 jz wasProbeClose
 push bx
 mov ds,ax
 xor dx,dx
 mov cx,1024
 mov ah,40h
 call Dos3Call
 call WasWindowData
 pop bx
wasProbeClose:
 mov ah,3Eh
 call Dos3Call
wasProbeDone:
 call WasWindowData
 ret
WasInputProbe endp

 ; BX=second word offset, ES=loaded driver code. Check matching store.
WasFindStore proc near
 mov wasCandidate,bx
 mov si,wasDriverEntry
 mov cx,124
wasStoreScan:
 call WasMouseStoreOperand
 jc wasStoreNext
 cmp bx,wasCandidate
 je wasStoreFound
wasStoreNext:
 inc si
 loop wasStoreScan
 stc
 ret
wasStoreFound:
 clc
 ret
WasFindStore endp

; Require a FAR indirect call through the same slot and segment model.
WasFindCall proc near
 xor si,si
 mov cx,4092
wasCallScan:
 push si
 cmp wasStoragePrefix,0
 je wasCallDefault
 cmp byte ptr es:[si],2Eh
 jne wasCallSkip
 inc si
 jmp wasCallOpcode
wasCallDefault:
 cmp byte ptr es:[si],3Eh
 jne wasCallDefaultCheck
 inc si
 jmp wasCallOpcode
wasCallDefaultCheck:
 or si,si
 jz wasCallOpcode
 mov al,es:[si-1]
 cmp al,2Eh
 je wasCallSkip
 cmp al,26h
 je wasCallSkip
 cmp al,36h
 je wasCallSkip
wasCallOpcode:
 cmp word ptr es:[si],1EFFh
 jne wasCallSkip
 cmp es:[si+2],bx
 je wasCallFound
wasCallSkip:
 pop si
 inc si
 dec cx
 jz wasCallMissing
 jmp wasCallScan
wasCallMissing:
 stc
 ret
wasCallFound:
 pop si
 clc
 ret
WasFindCall endp

; Actual held-button motion: use bounded relative mickey events, checking
; USER's live position after each event. Acceleration/rounding can differ
; between versions; small corrections converge without fake WM_MOUSEMOVE.
WasDragToPoint proc near
 mov wasDragBudget,512
 mov wasDragCapX,8
 mov wasDragCapY,8
 mov wasDragDX,0
 mov wasDragDY,0
wasDragNext:
 call WasReadMouse
 cmp word ptr wasMousePoint,0FFFFh
 je wasDragBad
 mov ax,wasMouseReqX
 sub ax,wasMousePoint
 mov bx,wasDragDX
 mov cx,wasDragCapX
 call WasDragClamp
 jc wasDragBad
 mov wasDragCapX,cx
 mov wasDragDX,ax
 mov ax,wasMouseReqY
 sub ax,wasMousePoint+2
 mov bx,wasDragDY
 mov cx,wasDragCapY
 call WasDragClamp
 jc wasDragBad
 mov wasDragCapY,cx
 mov wasDragDY,ax
 or ax,wasDragDX
 jz wasDragDone
 mov ax,1
 call WasMouseEvent
 jc wasDragBad
 call WasInputYield
 dec wasDragBudget
 jnz wasDragNext
 ; Allow the last delivered event to satisfy the exact target.
 call WasReadMouse
 mov ax,wasMousePoint
 cmp ax,wasMouseReqX
 jne wasDragBad
 mov ax,wasMousePoint+2
 cmp ax,wasMouseReqY
 jne wasDragBad
wasDragDone:
 clc
 ret
wasDragBad:
 lea si,inputDragTrace
 call TraceLine
 stc
 ret
WasDragToPoint endp

; Clamp each relative step, reducing overshoot at accelerated mouse speeds.
; AX = signed remaining pixel error, BX = last relative input for this axis,
; CX = positive step cap. Return AX = next input, CX = adjusted cap.
; USER may accelerate mickeys. Reduce the cap on crossing the target, using
; half the actual previous input (not half the old cap). Keep axes independent.
; A reversal at one mickey cannot be refined further: fail, never fake success.
WasDragClamp proc near
 or ax,ax
 jz wasDragClampDone
 or bx,bx
 jz wasDragClampApply
 mov dx,ax
 xor dx,bx
 jns wasDragClampApply
 or bx,bx
 jns wasDragClampMagnitude
 neg bx
wasDragClampMagnitude:
 cmp bx,1
 jbe wasDragClampImpossible
 shr bx,1
 cmp bx,cx
 jae wasDragClampApply
 mov cx,bx
wasDragClampApply:
 cmp ax,cx
 jle wasDragClampLow
 mov ax,cx
 jmp short wasDragClampDone
wasDragClampLow:
 mov dx,cx
 neg dx
 cmp ax,dx
 jge wasDragClampDone
 mov ax,dx
wasDragClampDone:
 clc
 ret
wasDragClampImpossible:
 stc
 ret
WasDragClamp endp

; AX mouse status. Driver ABI: AX flags, BX/CX relative motion, DX button
; count, SI/DI zero. Preserve FLAGS and the caller's general/segment regs.
WasMouseEvent proc near
 push ax
 call WasResolveMouse
 pop ax
 jc wasEventBad
 pushf
 push ax
 push bp
 push bx
 push cx
 push dx
 push si
 push di
 push ds
 push es
 xor bx,bx
 xor cx,cx
 test ax,1
 jz wasEventButton
 mov bx,wasDragDX
 mov cx,wasDragDY
wasEventButton:
 mov dx,2
 xor si,si
 xor di,di
 cld
 call dword ptr wasInputProc
 pop es
 pop ds
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop bp
 pop ax
 popf
 call WasWindowData
 clc
 ret
wasEventBad:
 stc
 ret
WasMouseEvent endp

; Explicit states are kept until released. Invalid transitions fail without
; injecting anything. Down/up are separate real driver events, with Yield.
commandMouseDown:
 mov wasMouseAction,0
 jmp wasMouseButtonArg
commandMouseUp:
 mov wasMouseAction,1
 jmp wasMouseButtonArg
commandMouseClick:
 mov wasMouseAction,2
 jmp wasMouseButtonArg
commandMouseDblClick:
 mov wasMouseAction,3
wasMouseButtonArg:
 call FetchArg
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasButtonBad
 lea si,wasInput
 lea di,inputLeftName
 call EqualStrings
 jnc wasButtonRight
 mov wasMouseMask,1
 mov wasMouseDownFlag,2
 mov wasMouseUpFlag,4
 jmp wasButtonParsed
wasButtonRight:
 lea si,wasInput
 lea di,inputRightName
 call EqualStrings
 jnc wasButtonBad
 mov wasMouseMask,2
 mov wasMouseDownFlag,8
 mov wasMouseUpFlag,16
wasButtonParsed:
 mov al,wasMouseMask
 test wasMouseHeld,al
 jz wasButtonNotHeld
 cmp wasMouseAction,1
 jne wasButtonBad
 call WasButtonUp
 jc wasButtonUnavailable
 jmp wasButtonOK
wasButtonNotHeld:
 cmp wasMouseAction,1
 je wasButtonBad
 call WasButtonDown
 jc wasButtonUnavailable
 cmp wasMouseAction,0
 je wasButtonOK
 call WasButtonUp
 jc wasButtonUnavailable
 cmp wasMouseAction,3
 jne wasButtonOK
 call WasButtonDown
 jc wasButtonUnavailable
 call WasButtonUp
 jc wasButtonUnavailable
wasButtonOK:
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasLoop
wasButtonBad:
 mov wasResult,2
 mov wasErrorCode,87
 jmp wasLoop
wasButtonUnavailable:
 lea si,inputUnavailableTrace
 call TraceLine
 mov wasResult,2
 mov wasErrorCode,50
 jmp wasLoop
WasButtonDown proc near
 mov ax,wasMouseDownFlag
 call WasMouseEvent
 jc wasButtonDownBad
 mov al,wasMouseMask
 or wasMouseHeld,al
 call WasInputYield
 clc
wasButtonDownBad:
 ret
WasButtonDown endp
WasButtonUp proc near
 mov ax,wasMouseUpFlag
 call WasMouseEvent
 jc wasButtonUpBad
 mov al,wasMouseMask
 not al
 and wasMouseHeld,al
 call WasInputYield
 clc
wasButtonUpBad:
 ret
WasButtonUp endp
WasInputYield proc near
 call Yield
 call WasWindowData
 ret
WasInputYield endp
keyNameTable label byte
 db 49,2,'1',0
 db 50,3,'2',0
 db 51,4,'3',0
 db 52,5,'4',0
 db 53,6,'5',0
 db 54,7,'6',0
 db 55,8,'7',0
 db 56,9,'8',0
 db 57,10,'9',0
 db 48,11,'0',0
 db 81,16,'Q',0
 db 87,17,'W',0
 db 69,18,'E',0
 db 82,19,'R',0
 db 84,20,'T',0
 db 89,21,'Y',0
 db 85,22,'U',0
 db 73,23,'I',0
 db 79,24,'O',0
 db 80,25,'P',0
 db 65,30,'A',0
 db 83,31,'S',0
 db 68,32,'D',0
 db 70,33,'F',0
 db 71,34,'G',0
 db 72,35,'H',0
 db 74,36,'J',0
 db 75,37,'K',0
 db 76,38,'L',0
 db 90,44,'Z',0
 db 88,45,'X',0
 db 67,46,'C',0
 db 86,47,'V',0
 db 66,48,'B',0
 db 78,49,'N',0
 db 77,50,'M',0
 db 27,1,'ESC',0
 db 8,14,'BACKSPACE',0
 db 9,15,'TAB',0
 db 13,28,69,78,84,69,82,0
 db 17,29,'CTRL',0
 db 16,42,'SHIFT',0
 db 18,56,'ALT',0
 db 32,57,'SPACE',0
 db 36,71,'HOME',0
 db 38,72,'UP',0
 db 33,73,'PGUP',0
 db 37,75,'LEFT',0
 db 39,77,'RIGHT',0
 db 35,79,'END',0
 db 40,80,'DOWN',0
 db 34,81,'PGDN',0
 db 45,82,'INSERT',0
 db 46,83,'DELETE',0
 db 112,59,'F1',0
 db 113,60,'F2',0
 db 114,61,'F3',0
 db 115,62,'F4',0
 db 116,63,'F5',0
 db 117,64,'F6',0
 db 118,65,'F7',0
 db 119,66,'F8',0
 db 120,67,'F9',0
 db 121,68,'F10',0
keyNameCount equ 64
typeMap label byte
 db 32,57 ; ASCII 32
 db 49,130 ; ASCII 33
 db 222,168 ; ASCII 34
 db 51,132 ; ASCII 35
 db 52,133 ; ASCII 36
 db 53,134 ; ASCII 37
 db 55,136 ; ASCII 38
 db 222,40 ; ASCII 39
 db 57,138 ; ASCII 40
 db 48,139 ; ASCII 41
 db 56,137 ; ASCII 42
 db 187,141 ; ASCII 43
 db 188,51 ; ASCII 44
 db 189,12 ; ASCII 45
 db 190,52 ; ASCII 46
 db 191,53 ; ASCII 47
 db 48,11 ; ASCII 48
 db 49,2 ; ASCII 49
 db 50,3 ; ASCII 50
 db 51,4 ; ASCII 51
 db 52,5 ; ASCII 52
 db 53,6 ; ASCII 53
 db 54,7 ; ASCII 54
 db 55,8 ; ASCII 55
 db 56,9 ; ASCII 56
 db 57,10 ; ASCII 57
 db 186,167 ; ASCII 58
 db 186,39 ; ASCII 59
 db 188,179 ; ASCII 60
 db 187,13 ; ASCII 61
 db 190,180 ; ASCII 62
 db 191,181 ; ASCII 63
 db 50,131 ; ASCII 64
 db 65,158 ; ASCII 65
 db 66,176 ; ASCII 66
 db 67,174 ; ASCII 67
 db 68,160 ; ASCII 68
 db 69,146 ; ASCII 69
 db 70,161 ; ASCII 70
 db 71,162 ; ASCII 71
 db 72,163 ; ASCII 72
 db 73,151 ; ASCII 73
 db 74,164 ; ASCII 74
 db 75,165 ; ASCII 75
 db 76,166 ; ASCII 76
 db 77,178 ; ASCII 77
 db 78,177 ; ASCII 78
 db 79,152 ; ASCII 79
 db 80,153 ; ASCII 80
 db 81,144 ; ASCII 81
 db 82,147 ; ASCII 82
 db 83,159 ; ASCII 83
 db 84,148 ; ASCII 84
 db 85,150 ; ASCII 85
 db 86,175 ; ASCII 86
 db 87,145 ; ASCII 87
 db 88,173 ; ASCII 88
 db 89,149 ; ASCII 89
 db 90,172 ; ASCII 90
 db 219,26 ; ASCII 91
 db 220,43 ; ASCII 92
 db 221,27 ; ASCII 93
 db 54,135 ; ASCII 94
 db 189,140 ; ASCII 95
 db 192,41 ; ASCII 96
 db 65,30 ; ASCII 97
 db 66,48 ; ASCII 98
 db 67,46 ; ASCII 99
 db 68,32 ; ASCII 100
 db 69,18 ; ASCII 101
 db 70,33 ; ASCII 102
 db 71,34 ; ASCII 103
 db 72,35 ; ASCII 104
 db 73,23 ; ASCII 105
 db 74,36 ; ASCII 106
 db 75,37 ; ASCII 107
 db 76,38 ; ASCII 108
 db 77,50 ; ASCII 109
 db 78,49 ; ASCII 110
 db 79,24 ; ASCII 111
 db 80,25 ; ASCII 112
 db 81,16 ; ASCII 113
 db 82,19 ; ASCII 114
 db 83,31 ; ASCII 115
 db 84,20 ; ASCII 116
 db 85,22 ; ASCII 117
 db 86,47 ; ASCII 118
 db 87,17 ; ASCII 119
 db 88,45 ; ASCII 120
 db 89,21 ; ASCII 121
 db 90,44 ; ASCII 122
 db 219,154 ; ASCII 123
 db 220,171 ; ASCII 124
 db 221,155 ; ASCII 125
 db 192,169 ; ASCII 126


; Keyboard events use the actual USER driver callback, never posted messages.
; Win3 exposes the documented register ABI at USER.289; Win1/2 resolve
; the live KEYBOARD Enable slot with the same guarded mouse-driver scanner.
WasResolveKey proc near
 cmp word ptr wasKeyProc+2,0
 jne wasKeyResolveOK
IFDEF WAS_WIN300
 lea si,inputUserName
 mov bx,289
 call WasLookupOrdinal
 or dx,dx
 jz wasKeyResolveLegacy
 mov wasKeyProc,ax
 mov wasKeyProc+2,dx
 jmp wasKeyResolveOK
ENDIF
wasKeyResolveLegacy:
 push word ptr wasInputProc
 push word ptr wasInputProc+2
 mov word ptr wasInputProc,0
 mov word ptr wasInputProc+2,0
 mov wasDriverName,offset inputKeyName
 call WasResolveMouse
 pushf
 mov ax,wasInputProc
 mov wasKeyProc,ax
 mov ax,wasInputProc+2
 mov wasKeyProc+2,ax
 popf
 pop word ptr wasInputProc+2
 pop word ptr wasInputProc
 mov wasDriverName,offset inputMouseName
 jc wasKeyResolveBad
wasKeyResolveOK:
 clc
 ret
wasKeyResolveBad:
 stc
 ret
WasResolveKey endp

; AX=VK with AH=0 down/80h up; BX=XT scan code, BH=0.
WasKeyEvent proc near
 push ax
 push bx
 call WasResolveKey
 pop bx
 pop ax
 jc wasKeyEventBad
 pushf
 push ax
 push bp
 push bx
 push cx
 push dx
 push si
 push di
 push ds
 push es
 xor cx,cx
 xor dx,dx
 xor si,si
 xor di,di
 cld
 call dword ptr wasKeyProc
 pop es
 pop ds
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop bp
 pop ax
 popf
 call WasWindowData
 clc
 ret
wasKeyEventBad:
 stc
 ret
WasKeyEvent endp

commandKeyDown:
 mov wasKeyAction,0
 jmp wasKeyArg
commandKeyUp:
 mov wasKeyAction,1
 jmp wasKeyArg
commandKeyPress:
 mov wasKeyAction,2
wasKeyArg:
 call FetchArg
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasButtonBad
 lea si,wasInput
 call WasFindKey
 jc wasButtonBad
 mov wasKeyPair,ax
 mov bl,ah
 xor bh,bh
 cmp byte ptr wasKeysHeld[bx],0
 je wasKeyNotHeld
 cmp wasKeyAction,1
 jne wasButtonBad
 call WasKeyUp
 jc wasKeyUnavailable
 jmp wasButtonOK
wasKeyNotHeld:
 cmp wasKeyAction,1
 je wasButtonBad
 call WasKeyDown
 jc wasKeyUnavailable
 cmp wasKeyAction,0
 je wasButtonOK
 call WasKeyUp
 jc wasKeyUnavailable
 jmp wasButtonOK
wasKeyUnavailable:
 lea si,keyUnavailableTrace
 call TraceLine
 mov wasResult,2
 mov wasErrorCode,50
 jmp wasLoop
 ; SI = NUL-terminated name. AX = scan:VK; CF if unknown.
 ; Preserve caller's parse pointers. Compact variable-length CODE records.
WasFindKey proc near
 push bx
 push cx
 push si
 push di
 mov bx,offset keyNameTable
 mov cx,keyNameCount
wasKeyFind:
 push si
 lea di,[bx+2]
wasKeyCompare:
 lodsb
 cmp al,'a'
 jb wasKeyCompareUpper
 cmp al,'z'
 ja wasKeyCompareUpper
 sub al,32
wasKeyCompareUpper:
 cmp al,cs:[di]
 jne wasKeyNext
 inc di
 or al,al
 jnz wasKeyCompare
 pop si
 mov ax,cs:[bx]
 clc
 jmp wasKeyFindDone
wasKeyNext:
 pop si
 add bx,2
wasKeySkipName:
 inc bx
 cmp byte ptr cs:[bx-1],0
 jne wasKeySkipName
 loop wasKeyFind
 stc
wasKeyFindDone:
 pop di
 pop si
 pop cx
 pop bx
 ret
WasFindKey endp

; Composite commands require no script-held keys, so rollback never releases
; unrelated script state. Physical keyboard state is not changed or queried.
WasCompositeReady proc near
 mov bx,127
wasCompositeHeld:
 cmp byte ptr wasKeysHeld[bx],0
 jne wasCompositeBusy
 dec bx
 jnz wasCompositeHeld
 clc
 ret
wasCompositeBusy:
 stc
 ret
WasCompositeReady endp

; KEYCOMBO CTRL+SHIFT+F2: validate entire chord before emitting any event.
; Reuse wasLHS scratch (four pairs + sentinel); no extra resident buffer.
commandKeyCombo:
 call FetchArg
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasButtonBad
 call WasCompositeReady
 jc wasButtonBad
 lea si,wasInput
 lea di,wasLHS
 xor dx,dx                 ; modifier mask (DL)
wasComboPart:
 mov bx,si
wasComboScan:
 mov al,[bx]
 or al,al
 jz wasComboFound
 cmp al,'+'
 je wasComboFound
 inc bx
 jmp wasComboScan
wasComboFound:
 mov byte ptr [bx],0
 mov dh,al                 ; separator or end
 call WasFindKey
 jc wasButtonBad
 cmp dh,0
 je wasComboLast
 cmp al,16
 jb wasButtonBad
 cmp al,18
 ja wasButtonBad
 mov cl,al
 sub cl,16
 mov ch,1
 shl ch,cl
 test dl,ch
 jnz wasButtonBad
 or dl,ch
 stosw
 lea si,[bx+1]
 jmp wasComboPart
wasComboLast:
 cmp dl,0
 je wasButtonBad
 cmp al,16
 jb wasComboStore
 cmp al,18
 jbe wasButtonBad
wasComboStore:
 stosw
 xor ax,ax
 stosw
 lea si,wasLHS
wasComboDown:
 lodsw
 or ax,ax
 jz wasComboUpStart
 mov wasKeyPair,ax
 push si
 call WasKeyDown
 pop si
 jc wasCompositeError
 cmp wasStop,0
 jne wasCompositeError
 jmp wasComboDown
wasComboUpStart:
 sub si,4
wasComboUp:
 mov ax,[si]
 mov wasKeyPair,ax
 push si
 call WasKeyUp
 pop si
 jc wasCompositeError
 cmp si,offset wasLHS
 je wasButtonOK
 sub si,2
 jmp wasComboUp

; TYPE requires a complete quoted argument; validate all characters before
; starting, then emit native key transitions using a US keyboard map.
commandType:
 mov si,wasNextSI
 cmp byte ptr [si],'"'
 jne wasButtonBad
 inc si
wasTypeQuote:
 lodsb
 or al,al
 jz wasButtonBad
 cmp al,'"'
 jne wasTypeQuote
 call TrimSI
 cmp byte ptr [si],0
 jne wasButtonBad
 call FetchArg
 call WasCompositeReady
 jc wasButtonBad
 lea si,wasInput
wasTypeValidate:
 lodsb
 or al,al
 jz wasTypeStart
 cmp al,32
 jb wasButtonBad
 cmp al,126
 ja wasButtonBad
 jmp wasTypeValidate
wasTypeStart:
 lea si,wasInput
wasTypeNext:
 lodsb
 or al,al
 jz wasButtonOK
 cmp wasStop,0
 jne wasCompositeError
 sub al,32
 xor ah,ah
 shl ax,1
 mov bx,ax
 mov ax,word ptr cs:typeMap[bx]
 push si
 test ah,80h
 jz wasTypePress
 and ah,7Fh
 push ax
 mov wasKeyPair,2A10h      ; SHIFT, scan 42
 call WasKeyDown
 pop ax
 jc wasTypeErrorPop
wasTypePress:
 mov wasKeyPair,ax
 call WasKeyDown
 jc wasTypeErrorPop
 call WasKeyUp
 jc wasTypeErrorPop
 cmp byte ptr wasKeysHeld[42],0
 je wasTypeDone
 mov wasKeyPair,2A10h
 call WasKeyUp
 jc wasTypeErrorPop
wasTypeDone:
 pop si
 jmp wasTypeNext
wasTypeErrorPop:
 pop si
wasCompositeError:
 call WasReleaseKeys
 jmp wasKeyUnavailable

WasKeyDown proc near
 mov ax,wasKeyPair
 mov bl,ah
 xor bh,bh
 xor ah,ah
 call WasKeyEvent
 jc wasKeyDownBad
 mov ax,wasKeyPair
 mov bl,ah
 xor bh,bh
 mov wasKeysHeld[bx],al
 call WasInputYield
 clc
wasKeyDownBad:
 ret
WasKeyDown endp
WasKeyUp proc near
 mov ax,wasKeyPair
 mov bl,ah
 xor bh,bh
 mov ah,80h
 call WasKeyEvent
 jc wasKeyUpBad
 mov ax,wasKeyPair
 mov bl,ah
 xor bh,bh
 mov byte ptr wasKeysHeld[bx],0
 call WasInputYield
 clc
wasKeyUpBad:
 ret
WasKeyUp endp
; Release only keys pressed by this script, including modifiers, on END/FAIL.
WasReleaseKeys proc near
 mov bx,127
wasReleaseKeyNext:
 mov al,wasKeysHeld[bx]
 or al,al
 jz wasReleaseKeySkip
 mov ah,bl
 mov wasKeyPair,ax
 push bx
 call WasKeyUp
 pop bx
 jc wasReleaseKeyBad
wasReleaseKeySkip:
 dec bx
 jnz wasReleaseKeyNext
 clc
wasReleaseKeyBad:
 ret
WasReleaseKeys endp
; Both recovery paths are attempted even if either callback fails.
WasReleaseAll proc near
 call WasReleaseMouse
 pushf
 call WasReleaseKeys
 pop ax
 jc wasReleaseAllBad
 test ax,1
 jnz wasReleaseAllBad
 clc
 ret
wasReleaseAllBad:
 stc
 ret
WasReleaseAll endp

commandReleaseInput:
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasButtonBad
 call WasReleaseAll
 jc wasButtonUnavailable
 jmp wasButtonOK
WasReleaseMouse proc near
 test wasMouseHeld,1
 jz wasReleaseRight
 mov wasMouseMask,1
 mov wasMouseUpFlag,4
 call WasButtonUp
 jc wasReleaseBad
wasReleaseRight:
 test wasMouseHeld,2
 jz wasReleaseDone
 mov wasMouseMask,2
 mov wasMouseUpFlag,16
 call WasButtonUp
 jc wasReleaseBad
wasReleaseDone:
 clc
wasReleaseBad:
 ret
WasReleaseMouse endp

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

; WAITFOR FILE "path" TIMEOUT n (milliseconds; required 0..59000).
; This is a cooperative, bounded witness poll, never a blocking DOS wait.
; RESULT 0=readable file; 1=timeout; 2=DOS open/close error.
; ERRORCODE is the real DOS failure on RESULT=2, zero otherwise.
; Reuse the idle SNAP path buffer (no extra 260-byte DGROUP buffer).
commandWaitFor:
 mov wasWaitWindow,0
 call FetchArg
 lea si,wasInput
 lea di,cmdFILE
 call EqualStrings
 jc wasWaitForFileArg
 lea si,wasInput
 lea di,cmdWINDOW
 call EqualStrings
 jnc wasCmdFailure
 mov wasWaitWindow,1
 mov wasWindowHwnd,0
 call FetchArg
 lea si,wasInput
 lea di,wasWindowCaption
 mov cx,127
 cmp byte ptr [si],0
 je wasWaitForWindowArgBad
wasWaitForCaptionCopy:
 lodsb
 stosb
 or al,al
 jz wasWaitForTimeoutArg
 loop wasWaitForCaptionCopy
wasWaitForWindowArgBad:
 mov wasResult,2
 mov wasErrorCode,87
 jmp wasLoop
wasWaitForFileArg:
 call FetchArg
 cmp byte ptr wasInput,0
 je wasCmdFailure
 lea si,wasInput
 lea di,wasSnapPath
 call CopyString260
wasWaitForTimeoutArg:
 call FetchArg
 lea si,wasInput
 lea di,cmdTIMEOUT
 call EqualStrings
 jnc wasCmdFailure
 call FetchArg
 lea si,wasInput
 call ParseUInt
 jc wasCmdFailure
 cmp ax,59000
 ja wasCmdFailure
 mov si,wasNextSI
 call TrimSI
 cmp byte ptr [si],0
 jne wasCmdFailure
 ; Round up to a full 10-ms tick (TIMEOUT 0 makes one probe).
 add ax,9
 xor dx,dx
 mov bx,10
 div bx
 mov wasWaitCs,ax
 call WasClockCs
 mov wasWaitStart,ax
IFDEF WAS_WIN300
 ; Use the proven NULL-window timer/WaitMessage path from WAIT so
 ; headless Windows 3 tasks do not consume a busy-spin CPU loop.
 mov wasTimerId,0
 cmp wasWaitCs,0
 je wasWaitForPoll
 xor ax,ax
 push ax               ; hWnd=NULL
 inc ax
 push ax               ; timer ID 1
 mov ax,100
 push ax               ; pulse every 100ms
 xor ax,ax
 push ax               ; TIMERPROC segment=NULL
 push ax               ; TIMERPROC offset=NULL
 call SetTimer
 mov bx,@data
 mov ds,bx
 mov es,bx
 cld
 mov wasTimerId,ax
 or ax,ax
 jz wasWaitForPoll
 mov uiPumpAny,1
ENDIF
wasWaitForPoll:
 cmp wasWaitWindow,0
 je wasWaitForFilePoll
 call WasFindWindow
 cmp ax,1
 je wasWaitForPending
 mov wasResult,ax
 mov wasErrorCode,0
 or ax,ax
 jz wasWaitForDone
 mov wasErrorCode,87
 jmp wasWaitForDone
wasWaitForFilePoll:
 mov ax,3D00h
 lea dx,wasSnapPath
 call Dos3Call
 jnc wasWaitForOpened
 cmp ax,2              ; DOS file not found: still pending
 je wasWaitForPending
 cmp ax,3              ; DOS path not found: still pending
 je wasWaitForPending
 mov wasErrorCode,ax  ; unexpected access/device error: fail explicitly
 mov wasResult,2
 jmp wasWaitForDone
wasWaitForOpened:
 mov bx,ax
 mov ah,3Eh
 call Dos3Call
 jc wasWaitForCloseError
 mov wasResult,0
 mov wasErrorCode,0
 jmp wasWaitForDone
wasWaitForCloseError:
 mov wasErrorCode,ax
 mov wasResult,2
 jmp wasWaitForDone
wasWaitForPending:
 call WasClockCs
 sub ax,wasWaitStart
 jnc wasWaitForDelta
 add ax,6000           ; DOS 2Ch minute wrap; timeout < 60s
wasWaitForDelta:
 cmp ax,wasWaitCs
 jae wasWaitForTimeout
IFDEF WAS_WIN300
 cmp wasTimerId,0
 je wasWaitForYield
 call WaitMessage
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 jmp wasWaitForPump
wasWaitForYield:
ENDIF
 call Yield
wasWaitForPump:
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 ; Pump even headless, with UiPump's fixed eight-message bound.
 xor ax,ax
 mov al,uiPumpAny
 push ax
 mov uiPumpAny,1
 call UiPump
 pop ax
 mov uiPumpAny,al
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 cmp wasStop,0
 jne wasWaitForStopped
 jmp wasWaitForPoll
wasWaitForTimeout:
 mov wasResult,1
 mov wasErrorCode,0
wasWaitForDone:
IFDEF WAS_WIN300
 call WasStopTimer
ENDIF
 jmp wasLoop
wasWaitForStopped:
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
 call WasReleaseAll
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
 jnc wasCheckMouseX
 mov ax,12               ; BITSPIXEL, multiply by PLANES=14
 jmp wasQueryScreen
wasCheckMouseX:
 lea si,wasWord
 lea di,sysMOUSEHELD
 call EqualStrings
 jnc wasCheckMouseXActual
 xor ax,ax
 mov al,wasMouseHeld
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckMouseXActual:
 lea si,wasWord
 lea di,sysMOUSEX
 call EqualStrings
 jnc wasCheckMouseY
 call WasReadMouse
 mov ax,wasMousePoint
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckMouseY:
 lea si,wasWord
 lea di,sysMOUSEY
 call EqualStrings
 jnc wasCheckWinX
 call WasReadMouse
 mov ax,wasMousePoint+2
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckWinX:
 lea si,wasWord
 lea di,sysWINX
 call EqualStrings
 jnc wasCheckWinY
 call WasReadWindow
 jc wasWindowVarMissing
 mov ax,wasWindowOrigin
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckWinY:
 lea si,wasWord
 lea di,sysWINY
 call EqualStrings
 jnc wasCheckWinW
 call WasReadWindow
 jc wasWindowVarMissing
 mov ax,wasWindowOrigin+2
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckWinW:
 lea si,wasWord
 lea di,sysWINW
 call EqualStrings
 jnc wasCheckWinH
 call WasReadWindow
 jc wasWindowVarMissing
 mov ax,wasWindowRect+4
 call FormatDecimal
 jmp wasBuiltInReady
wasCheckWinH:
 lea si,wasWord
 lea di,sysWINH
 call EqualStrings
 jnc wasCheckDiskFree
 call WasReadWindow
 jc wasWindowVarMissing
 mov ax,wasWindowRect+6
 call FormatDecimal
 jmp wasBuiltInReady
wasWindowVarMissing:
 mov ax,0FFFFh
 call FormatDecimal
 jmp wasBuiltInReady
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
cmdDOEVENTS  db 'DOEVENTS',0
cmdWAITFOR   db 'WAITFOR',0
cmdMOUSEMOVE db 'MOUSEMOVE',0
cmdMOUSEDOWN db 'MOUSEDOWN',0
cmdMOUSEUP db 'MOUSEUP',0
cmdMOUSECLICK db 'MOUSECLICK',0
cmdMOUSEDBLCLICK db 'MOUSEDBLCLICK',0
cmdRELEASEINPUT db 'RELEASEINPUT',0
cmdKEYDOWN db 'KEYDOWN',0
cmdKEYUP db 'KEYUP',0
cmdKEYPRESS db 'KEYPRESS',0
cmdKEYCOMBO db 'KEYCOMBO',0
cmdTYPE db 'TYPE',0
inputKeyName db 'KEYBOARD',0
keyUnavailableTrace db 'KEYBOARD_CALLBACK_UNAVAILABLE',0


cmdWINDOWFOCUS db 'WINDOWFOCUS',0
inputUserName db 'USER',0
inputMouseName db 'MOUSE',0
inputLeftName db 'LEFT',0
inputRightName db 'RIGHT',0
inputUnavailableTrace db 'INPUT_CALLBACK_UNAVAILABLE',0
inputDragTrace db 'INPUT_DRAG_FAILED',0
inputProbePath db 'INABI.DAT',0
cmdWINDOWSELECT db 'WINDOWSELECT',0
winRelName db 'REL',0
cmdFILE      db 'FILE',0
cmdWINDOW    db 'WINDOW',0
cmdTIMEOUT   db 'TIMEOUT',0
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
sysMOUSEX    db 'MOUSEX',0
sysMOUSEHELD db 'MOUSEHELD',0
sysMOUSEY    db 'MOUSEY',0
sysWINX db 'WINX',0
sysWINY db 'WINY',0
sysWINW db 'WINW',0
sysWINH db 'WINH',0
sysSCREENW   db 'SCREENW',0
sysSCREENH   db 'SCREENH',0
sysBPP       db 'BPP',0
sysDISKFREE  db 'DISKFREE(',0
end start
