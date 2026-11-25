; WASUI - optional Win1/2/3 native iconic window for 4.77 MHz 8088.
; No UI is created unless the script contains ShowIcon=YES.
; WNDCLASS and MSG share a 26-byte union: RegisterClass copies the
; descriptor before PeekMessage uses those same bytes for message storage.
; IMPORTANT ABI: Every Win16 USER import is FAR PASCAL. Parameters are
; pushed LEFT TO RIGHT (first formal argument first), *not* Win32 stdcall
; right-to-left. A FAR pointer is pushed as segment then offset, and a
; DWORD is pushed high word then low word. The last argument sits at the
; lowest address when the callee/callback enters.
; This ordering is essential on Win1.01, Win2.03 and Win3.0 /r.
;
; Calling convention: UiOpen CF=1 on failure, CF=0 on success;
; UiClose/UiPump preserve BX,CX,DX,SI,DI,ES and DS. UiWndProc is FAR
; PASCAL, receiving HWND, UINT, WPARAM, LPARAM and returning DX:AX.
; In the callee BP+6 is LPARAM.low, +8 LPARAM.high, +10 WPARAM,
; +12 UINT message, and +14 HWND (left-to-right PASCAL pushes).
; The callback explicitly restores the data selector: USER may invoke it
; with a different DS on Win1.01 or Win2.03.
;
; USER ordinals are common to Windows 1.01, 2.03 and 3.0 real mode.
; Avoid Win3-only CreateWindowEx, RegisterClassEx and menu APIs.
.8086
.model small

extrn RegisterClass:far   ; USER.57
extrn CreateWindow:far    ; USER.41
extrn ShowWindow:far      ; USER.42
extrn DestroyWindow:far   ; USER.53
extrn GetSystemMenu:far  ; USER.156
extrn ChangeMenu:far     ; USER.153
extrn DefWindowProc:far  ; USER.107
extrn PeekMessage:far    ; USER.109
extrn DispatchMessage:far; USER.114
extrn MessageBox:far     ; USER.1
extrn LoadIcon:far       ; USER.174
extrn GetVersion:far     ; KERNEL.3 - native Windows major version
extrn wasInst:word
extrn wasStop:byte
public UiOpen,UiClose,UiPump,wasIconWnd,uiFailStage,uiPumpAny

.data
; Win16 WNDCLASS: style, FAR wndproc, cbClsExtra, cbWndExtra, hInstance,
; hIcon, hCursor, hBrush, FAR menu name, FAR class name. 26 bytes.
uiClass dw 0
        dw offset UiWndProc,seg UiWndProc
        dw 0,0
uiClassInstance dw 0
uiClassIcon dw 0
        dw 0,0
        dw 0,0
        dw offset uiName,seg uiName
wasIconWnd dw 0
uiPumpAny db 0          ; Win3 task-timer WAIT may pump without an icon
uiClassRegistered db 0   ; set once; class descriptor becomes MSG
uiFailStage db 0        ; 1=class,2=window; system-menu customisation is optional
uiWinMajor db 0         ; Win1: no system menu/About; Win2/3 retain both
uiName db 'NOWBAT',0
uiSwitchName db 'Switch To...',0
uiAboutName db 'About...',0
uiAboutMessage db 'NOWBAT - Windows Admin Script',13,10,'Version: 0.0.54',0
; MSG: HWND,UINT,WPARAM,LPARAM,DWORD time,POINT(x,y), 18 bytes.
; UiClass is already registered before this union is used as message space.
uiMsg EQU uiClass

; W082: contiguous zero-filled DGROUP storage, kept at the end of _DATA.
; All link response files place WASUI last. The host removes only this
; verified zero tail, preserving minalloc, offsets and all relocation chains.
; Startup explicitly clears these bytes before the script is parsed.
 db "NOWBAT_ZERO_W054",0
PUBLIC WasZeroStart,WasZeroEnd
WasZeroStart LABEL BYTE
PUBLIC wasInput
wasInput       db 260 dup(0)
PUBLIC wasScript
wasScript      db 128 dup(0)
PUBLIC wasLine
wasLine        db 260 dup(0)
PUBLIC wasArg
wasArg         db 260 dup(0)
PUBLIC wasWord
wasWord        db 32 dup(0)
PUBLIC wasLHS
wasLHS         db 260 dup(0)
PUBLIC wasRHS
wasRHS         db 260 dup(0)
PUBLIC wasLabel
wasLabel       db 32 dup(0)
PUBLIC wasVarNames
wasVarNames    db 128 dup(0)  ; 8 x 16
PUBLIC wasVarValues
wasVarValues   db 768 dup(0)  ; 8 x 96
PUBLIC wasSnapPath
wasSnapPath    db 260 dup(0)
PUBLIC wasExecPath
wasExecPath    db 128 dup(0)
PUBLIC wasWindowCaption
wasWindowCaption db 128 dup(0)
PUBLIC wasWindowScratch
wasWindowScratch db 128 dup(0)
PUBLIC wasKeysHeld
wasKeysHeld db 128 dup(0) ; indexed by XT scan, value=VK (supports OEM VKs)
PUBLIC wasRawTail
wasRawTail     db 128 dup(0)
PUBLIC tarSource
tarSource   db 260 dup(0)
PUBLIC tarPrefix
tarPrefix   db 130 dup(0)
PUBLIC tarName
tarName     db 100 dup(0)
PUBLIC tarDTA
tarDTA      db 43 dup(0)
PUBLIC tarHeader
tarHeader   db 512 dup(0)
PUBLIC tarBuffer
tarBuffer   db 1024 dup(0)  ; 2x I/O throughput without large DGROUP cost
PUBLIC snapBF
snapBF       db 54 dup(0)
PUBLIC snapRow
snapRow      db 4096 dup(0)   ; COMPAT row or FAST batch, never a framebuffer
PUBLIC snapPlaneBuf
snapPlaneBuf db 400 dup(0)    ; four 100-byte planar slots; 640/800 widths
PUBLIC fsDta
fsDta       db 43 dup(0)        ; DOS findfirst DTA: name at +30
WasZeroEnd LABEL BYTE

.code
; UiOpen - register a tiny class and display the native iconic window.
; An embedded native file-tree icon is used, with a stock-icon fallback.
UiOpen proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 cmp wasIconWnd,0
 je uiNeedWindow
 jmp uiOpenGood
uiNeedWindow:
 mov uiFailStage,1        ; class setup / RegisterClass
 cmp uiClassRegistered,0
 jne uiAlreadyRegistered
 mov ax,wasInst
 mov uiClassInstance,ax
 ; Load the application's native file-tree icon from its NE resource.
 ; Win1/2 use an early 1-bit RT_ICON #1; Win3 uses group RT_GROUP_ICON #1.
 ; Fall back to the stock icon only if the native resource is unavailable.
 mov ax,wasInst
 push ax                 ; first parameter: hInstance = WAS
 xor ax,ax
 push ax                 ; second: resource ID segment = 0
 inc ax
 push ax                 ; second: resource ID offset = 1
 call LoadIcon
 or ax,ax
 jnz uiIconReady
 xor ax,ax
 push ax                 ; hInstance=NULL => system stock icon
 push ax                 ; IDI_APPLICATION segment = 0
 mov ax,32512
 push ax                 ; IDI_APPLICATION offset
 call LoadIcon
uiIconReady:
 mov uiClassIcon,ax
 push ds
 mov ax,offset uiClass
 push ax
 call RegisterClass
 or ax,ax
 jnz uiRegOK
 jmp uiOpenBad
uiRegOK:
 mov uiClassRegistered,1
uiAlreadyRegistered:
 ; The *same* WIN101 NE runs on Windows 1.01 AND 2.03. Detect at
 ; runtime: Windows 1 has the icon but no custom system-menu/About UI.
 ; Do not call GetSystemMenu/ChangeMenu on Win1 (problematic on 1.01).
 call GetVersion
 mov bx,ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 mov uiWinMajor,bl
 mov uiFailStage,2        ; CreateWindow
 ; HWND CreateWindow(class,title,style,x,y,cx,cy,parent,menu,inst,param).
 ; All 11 parameters are passed in formal LEFT-TO-RIGHT order on Win16.
 ; WNDCLASS was copied by RegisterClass; its storage is now reusable MSG.
 push ds                  ; class LPSTR segment
 mov ax,offset uiName
 push ax                  ; class LPSTR offset
 push ds                  ; window title LPSTR segment
 mov ax,offset uiName
 push ax                  ; window title LPSTR offset
 mov ax,020C8h           ; WS_MINIMIZE|CAPTION|SYSMENU for Win2/3
 cmp uiWinMajor,1
 jne uiWindowStyleReady
 mov ax,020C0h           ; Win1: minimized caption ONLY, no system menu
uiWindowStyleReady:
 push ax                  ; style high word of Win16 WS_* flags
 xor ax,ax
 push ax                  ; style low
 push ax                  ; x
 push ax                  ; y
 mov ax,160
 push ax                  ; width
 mov ax,80
 push ax                  ; height
 xor ax,ax
 push ax                  ; parent HWND=NULL
 push ax                  ; hMenu=NULL
 push wasInst             ; hInstance
 push ax                  ; lpParam segment=NULL
 push ax                  ; lpParam offset=NULL
 call CreateWindow
 or ax,ax
 jnz uiWindowOK
 jmp uiOpenBad
uiWindowOK:
 mov wasIconWnd,ax
 cmp uiWinMajor,1
 je uiShow                ; Win1: skip custom menu and About entirely
 ; WS_CAPTION|WS_SYSMENU already provides a fully functional native
 ; system menu. Leave its Restore/Move/Size/Close entries intact; replacing
 ; them (especially deleting by position) removes system functionality on
 ; Windows 1.x/2.x. These two extra entries are opportunistic, not fatal.
 push wasIconWnd
 xor ax,ax
 push ax
 call GetSystemMenu
 mov bx,ax
 or bx,bx
 jz uiShow
 mov dx,offset uiSwitchName
 mov cx,0F130h           ; SC_TASKLIST: handled by DefWindowProc
 mov ax,0100h            ; MF_APPEND | MF_STRING
 call UiChangeMenu
 mov dx,offset uiAboutName
 mov cx,01000h           ; private ID (below F000h)
 mov ax,0100h
 call UiChangeMenu
uiShow:
 push wasIconWnd         ; first parameter: HWND
 mov ax,2                ; second: SW_SHOWMINIMIZED
 push ax
 call ShowWindow
uiOpenGood:
 mov uiFailStage,0
 clc
 jmp uiOpenDone
uiOpenBad:
 call UiClose              ; undo any partially created GUI resources
 stc
uiOpenDone:
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
UiOpen endp

; ChangeMenu(HMENU,oldItem,LPSTR,newID,flags), USER.153 FAR PASCAL.
; Input: BX=system menu, AX=flags, CX=command ID, DX=string offset.
; Preserve working registers and pass left-to-right in declaration order.
; The oldItem index is zero for delete/append (MF_BYPOSITION on delete).
UiChangeMenu proc near
 push bx
 push cx
 push dx
 push si
 push ds
 push bx                  ; first parameter: menu handle
 xor si,si
 push si                  ; second parameter: oldItem index 0
 push ds                  ; third parameter: far string segment
 push dx                  ; far string offset (or 0 for MF_DELETE)
 push cx                  ; fourth parameter: new command ID
 push ax                  ; fifth parameter: flags
 call ChangeMenu
 pop ds
 pop si
 pop dx
 pop cx
 pop bx
 ret
UiChangeMenu endp

; UiPump - nonblocking, bounded message dispatch between script commands
; and during WAIT. The absent-icon path costs one word comparison only.
UiPump proc near
 push ax
 push bx
 push cx
 push dx
 push si
 push di
 push es
 push ds
 cmp uiPumpAny,0
 jne uiPumpActive
 cmp wasIconWnd,0
 je uiPumpDone
uiPumpActive:
 mov cx,8
uiNextMessage:
 push cx
 ; PeekMessage(LPMSG,HWND,min,max,remove) is FAR PASCAL.
 push ds                  ; first parameter: MSG far segment
 mov ax,offset uiMsg
 push ax                  ; MSG far offset
 xor ax,ax
 push ax                  ; second: HWND=NULL (all task messages)
 push ax                  ; third: min filter=0
 push ax                  ; fourth: max filter=0
 inc ax
 push ax                  ; fifth: PM_REMOVE (AX was zero)
 call PeekMessage
 ; Any Win16 USER entry may return with a changed DS/ES. The next MSG
 ; pointer must always use the interpreter's own DGROUP, not the last
 ; application/window context. Preserve PeekMessage's boolean AX.
 push ax                  ; save the Win16 PeekMessage result compactly
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax                   ; restore the boolean result after fixing DS/ES
 pop cx
 or ax,ax
 jz uiPumpDone
 ; USER is free to modify CX, which holds our bounded message count.
 push cx
 push ds
 mov ax,offset uiMsg
 push ax
 call DispatchMessage
 ; A window callback can switch the task data context. Restore it before
 ; reading wasStop and before the next PeekMessage iteration.
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop cx
 cmp wasStop,0
 jne uiPumpDone
 loop uiNextMessage
uiPumpDone:
 pop ds
 pop es
 pop di
 pop si
 pop dx
 pop cx
 pop bx
 pop ax
 ret
UiPump endp

; UiClose - destroy the window before script termination or session exit.
UiClose proc near
 push ax
 xor ax,ax
 xchg ax,wasIconWnd       ; atomically detach old HWND, leave zero in state
 or ax,ax
 jz uiCloseDone
 push ax
 call DestroyWindow
uiCloseDone:
 pop ax
 ret
UiClose endp

; Win16 callback. Win16 FAR PASCAL stores *last* argument nearest
; the return address: BP+6/+8=lParam, +10=wParam, +12=message,
; +14=hWnd. Callee removes 10 parameter bytes. DX:AX is LRESULT.
UiWndProc proc far
 push bp
 mov bp,sp
 push ds
 mov ax,@data
 mov ds,ax
 mov ax,[bp+12]          ; WM message; LPARAM starts at BP+6
 cmp ax,0112h            ; WM_SYSCOMMAND
 je uiSysCommand
 cmp ax,0010h            ; WM_CLOSE
 je uiStopScript
 cmp ax,0013h            ; WM_QUERYOPEN: stay minimized
 je uiReturnZero
 jmp uiDefProc
uiSysCommand:
 cmp uiWinMajor,1
 je uiDefProc             ; no WAS custom system menu on Win1
 mov ax,[bp+10]          ; WPARAM
 cmp ax,01000h           ; our About... item
 je uiAbout
 cmp ax,0F060h           ; Close: stop WAS, not Windows
 je uiStopScript
 ; SC_TASKLIST forwarded to Windows' native task switcher.
 jmp uiDefProc
uiAbout:
 cmp uiWinMajor,1
 je uiDefProc             ; defensive: disallow About on Win1
 ; MessageBox(HWND, text LPSTR, caption LPSTR, style): Win16 Pascal.
 push word ptr [bp+14]   ; first parameter: owner HWND
 push ds                  ; text far segment
 mov ax,offset uiAboutMessage
 push ax                  ; text far offset
 push ds                  ; caption far segment
 mov ax,offset uiName
 push ax                  ; caption far offset
 xor ax,ax
 push ax                  ; fourth parameter: MB_OK
 call MessageBox
 jmp uiReturnZero
uiStopScript:
 mov wasStop,1
uiReturnZero:
 xor ax,ax
 xor dx,dx
 jmp uiWndDone
uiDefProc:
 ; DefWindowProc(HWND,message,wParam,lParam) uses left-to-right.
 push word ptr [bp+14]   ; hWnd
 push word ptr [bp+12]   ; message
 push word ptr [bp+10]   ; wParam
 push word ptr [bp+8]    ; lParam high
 push word ptr [bp+6]    ; lParam low
 call DefWindowProc
uiWndDone:
 pop ds
 pop bp
 ret 10
UiWndProc endp
end
