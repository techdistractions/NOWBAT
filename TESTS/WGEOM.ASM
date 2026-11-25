; Independent native Win1-compatible window fixture. No NOWBAT linkage.
; Own USER client geometry is written once to WGEOM.DAT before the message loop.
.8086
.model small
.stack 1024
extrn InitTask:far,WaitEvent:far,InitApp:far
extrn RegisterClass:far,CreateWindow:far,ShowWindow:far
extrn GetClientRect:far,ClientToScreen:far
extrn GetMessage:far,TranslateMessage:far,DispatchMessage:far
extrn DefWindowProc:far,PostQuitMessage:far
extrn GetDC:far,ReleaseDC:far,TextOut:far
.data
 dw 0,0,5,0,0,0,0,0
fixtureClass dw 8
 dw offset FixtureWndProc,seg FixtureWndProc
 dw 0,0
fixtureInst dw 0
 dw 0,0,0
 dw 0,0
 dw offset fixtureClassName,seg fixtureClassName
fixtureClassName db 'NWBGEOM',0
fixtureTitle db 'NOWBAT Geometry Fixture',0
fixtureHwnd dw 0
fixtureMsg db 18 dup(0)
fixtureRect dw 4 dup(0)
fixtureGeometry dw 4 dup(0) ; origin X,Y and width,height; 8-byte witness
fixtureClickText db 'CLICK RECEIVED'
fixtureDragText db 'DRAG RECEIVED '
fixtureDC dw 0
fixtureEventPath db 'WEVENT.DAT',0
fixtureEvent dw 4 dup(0) ; msg, wParam, client x, client y
fixturePath db 'WGEOM.DAT',0
.code
start:
 db 8 dup(090h)
 call InitTask
 or ax,ax
 jnz fixtureTask
 jmp fixtureFail
fixtureTask:
 mov fixtureInst,di
 xor ax,ax
 push ax
 call WaitEvent
 push fixtureInst
 call InitApp
 call FixtureData
 or ax,ax
 jnz fixtureApp
 jmp fixtureFail
fixtureApp:
 push ds
 mov ax,offset fixtureClass
 push ax
 call RegisterClass
 call FixtureData
 or ax,ax
 jnz fixtureRegistered
 jmp fixtureFail
fixtureRegistered:
 push ds
 mov ax,offset fixtureClassName
 push ax
 push ds
 mov ax,offset fixtureTitle
 push ax
 mov ax,00C0h ; WS_CAPTION, valid on Win1 tiled shell as well as Win2/3
 push ax
 xor ax,ax
 push ax ; style low
 mov ax,20
 push ax ; x
 push ax ; y
 mov ax,180
 push ax ; width
 mov ax,100
 push ax ; height
 xor ax,ax
 push ax ; parent
 push ax ; menu
 push fixtureInst
 push ax ; parameter segment
 push ax ; parameter offset
 call CreateWindow
 call FixtureData
 or ax,ax
 jnz fixtureCreated
 jmp fixtureFail
fixtureCreated:
 mov fixtureHwnd,ax
 push ax
 mov ax,1 ; SW_SHOWNORMAL
 push ax
 call ShowWindow
 call FixtureData
 push fixtureHwnd
 push ds
 mov ax,offset fixtureRect
 push ax
 call GetClientRect
 call FixtureData
 mov ax,fixtureRect+4
 sub ax,fixtureRect
 mov fixtureGeometry+4,ax
 mov ax,fixtureRect+6
 sub ax,fixtureRect+2
 mov fixtureGeometry+6,ax
 push fixtureHwnd
 push ds
 mov ax,offset fixtureGeometry
 push ax
 call ClientToScreen
 call FixtureData
 mov ah,3Ch
 xor cx,cx
 lea dx,fixturePath
 int 21h
 jc fixtureFail
 mov bx,ax
 push bx
 mov ah,40h
 mov cx,8
 lea dx,fixtureGeometry
 int 21h
 pop bx
 jc fixtureCloseFail
 cmp ax,8
 jne fixtureCloseFail
 mov ah,3Eh
 int 21h
 jc fixtureFail
fixtureLoop:
 push ds
 mov ax,offset fixtureMsg
 push ax
 xor ax,ax
 push ax
 push ax
 push ax
 call GetMessage
 call FixtureData
 or ax,ax
 jz fixtureExit
 push ds
 mov ax,offset fixtureMsg
 push ax
 call TranslateMessage
 call FixtureData
 push ds
 mov ax,offset fixtureMsg
 push ax
 call DispatchMessage
 call FixtureData
 jmp fixtureLoop
fixtureCloseFail:
 mov ah,3Eh
 int 21h
fixtureFail:
 mov ax,4C01h
 int 21h
fixtureExit:
 mov ax,4C00h
 int 21h
FixtureData proc near
 push ax
 mov ax,@data
 mov ds,ax
 mov es,ax
 cld
 pop ax
 ret
FixtureData endp
FixtureWndProc proc far
 push bp
 mov bp,sp
 push ds
 push es
 push bx
 push cx
 push si
 push di
 call FixtureData
 mov ax,[bp+12]
 cmp ax,0100h
 jb fixtureNotMouse
 cmp ax,0102h
 jbe fixtureEventRecord
 cmp ax,0104h
 jb fixtureCheckMouse
 cmp ax,0106h
 jbe fixtureEventRecord
fixtureCheckMouse:
 cmp ax,0200h
 jb fixtureNotMouse
 cmp ax,0206h
 ja fixtureNotMouse
 ; Only record dispatched native mouse input. Skip ordinary motion unless
 ; the left button is held. Mouse transitions are written independently.
 cmp ax,0200h
 jne fixtureEventRecord
 test word ptr [bp+10],1
 jz fixtureNotMouse
fixtureEventRecord:
 mov fixtureEvent,ax
 mov ax,[bp+10]
 mov fixtureEvent+2,ax
 mov ax,[bp+6]
 mov fixtureEvent+4,ax
 mov ax,[bp+8]
 mov fixtureEvent+6,ax
 mov ax,3D01h
 lea dx,fixtureEventPath
 int 21h
 jnc fixtureEventOpen
 mov ah,3Ch
 xor cx,cx
 lea dx,fixtureEventPath
 int 21h
 jc fixtureNotMouse
fixtureEventOpen:
 mov bx,ax
 mov ax,4202h
 xor cx,cx
 xor dx,dx
 int 21h
 jc fixtureEventClose
 mov ah,40h
 mov cx,8
 lea dx,fixtureEvent
 int 21h
fixtureEventClose:
 mov ah,3Eh
 int 21h
 ; Draw independent app-observed state for purposeful visual evidence.
 cmp word ptr fixtureEvent,0202h
 jne fixtureCheckDrag
 mov ax,offset fixtureClickText
 mov dx,42
 jmp fixtureDrawEvent
fixtureCheckDrag:
 cmp word ptr fixtureEvent,0200h
 jne fixtureNotMouse
 mov ax,offset fixtureDragText
 mov dx,54
fixtureDrawEvent:
 push ax
 push dx
 push fixtureHwnd
 call GetDC
 call FixtureData
 mov fixtureDC,ax
 pop dx
 pop si
 or ax,ax
 jz fixtureNotMouse
 push ax
 mov ax,5
 push ax
 push dx
 push ds
 push si
 mov ax,14
 push ax
 call TextOut
 call FixtureData
 push fixtureHwnd
 push fixtureDC
 call ReleaseDC
 call FixtureData
fixtureNotMouse:
 cmp word ptr [bp+12],2 ; WM_DESTROY
 jne fixtureDefault
 xor ax,ax
 push ax
 call PostQuitMessage
 xor ax,ax
 xor dx,dx
 jmp fixtureWndReturn
fixtureDefault:
 push word ptr [bp+14]
 push word ptr [bp+12]
 push word ptr [bp+10]
 push word ptr [bp+8]
 push word ptr [bp+6]
 call DefWindowProc
fixtureWndReturn:
 pop di
 pop si
 pop cx
 pop bx
 pop es
 pop ds
 pop bp
 retf 10
FixtureWndProc endp
end start
