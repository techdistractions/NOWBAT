# NOWBAT 0.0.54

A lightweight Windows automation script runner for Windows 1.01, Windows 2.x and Windows 3.0 real mode on 8086/8088-compatible PCs. Run applications, synchronize with windows and files, automate mouse and keyboard input, capture BMP screenshots, and collect evidence in uncompressed TAR archives.

## Run

Use `WIN101\NOWBAT.EXE` under Windows 1.01/2.x and `WIN300\NOWBAT.EXE` under Windows 3.0 real mode (`WIN /R`). Launch NOWBAT **inside Windows** with a `.WAS` script, e.g. `NOWBAT.EXE HELLO.WAS`. See [SCRIPT.TXT](SCRIPT.TXT) for the full language reference, [EXAMPLES](EXAMPLES) for sample scripts and [HISTORY.TXT](HISTORY.TXT) for version history.

## GUI automation

GUI commands use native Windows input callbacks rather than fabricated window messages. Select a window by its unique caption, focus it, and use relative client coordinates or absolute screen coordinates. For example, adapt the caption and coordinates to your own application:

```text
WAITFOR WINDOW "My Application" TIMEOUT 15000
IF %RESULT% NE 0 THEN GOTO FAILED
WINDOWFOCUS "My Application"
IF %RESULT% NE 0 THEN GOTO FAILED
MOUSEMOVE REL,20,20
IF %RESULT% NE 0 THEN GOTO FAILED
MOUSECLICK LEFT
IF %RESULT% NE 0 THEN GOTO FAILED
TYPE "Hello World!"
IF %RESULT% NE 0 THEN GOTO FAILED
KEYCOMBO CTRL+S
IF %RESULT% NE 0 THEN GOTO FAILED
RELEASEINPUT
END
:FAILED
RELEASEINPUT
END
```

`DOEVENTS` lets other Windows applications process queued events. `WAITFOR FILE` and `WAITFOR WINDOW` provide bounded readiness checks. Mouse down/up, double-click and held-button movement support drag operations. Keyboard commands include `KEYDOWN`, `KEYUP`, `KEYPRESS`, `KEYCOMBO` and `TYPE` (US printable ASCII, Caps Lock off). Use `RELEASEINPUT` to recover script-held keys and buttons. Check `%RESULT%` and `%ERRORCODE%`, and verify the application's actual state rather than relying on successful injection alone.

## Capture screenshots

`SNAP` uses fast direct-video capture on supported modes; `SNAPSAFE` uses the slower GDI compatibility path. Both accept the same syntax:

```text
SNAP "SCREEN.BMP"
SNAP "SCREEN.BMP" BPP=4
SNAP "PART.BMP",0,0,319,199,BPP=4
SNAPSAFE "SCREEN.BMP"
```

FAST returns `%RESULT%=2` for unsupported modes instead of silently falling back. FAST region X and width must be divisible by eight. See [capture notes](DOCS/SNAP_MODES.TXT) for limitations.

## Build from source

On a Windows build PC, install [JWASM](https://github.com/JWasm/JWasm), [NBJWLINK](https://github.com/techdistractions/NBJWLINK) and Python 3. Put the tools on PATH or in `TOOLS`, or configure `JWASM_EXE` and `NBJWLINK_EXE` in a private `MAKE.LOCAL.BAT`. Run `MAKE` to build both targets. The executables are in `DIST/WIN101` and `DIST/WIN300`. MAKE also creates `DIST/NOWBAT_SOURCE_0.0.54.ZIP` and `DIST/NOWBAT_BINARIES_0.0.54.ZIP` (versioned from `VERSION.TXT`). MAKE verifies the exact ZIP contents and prints their full paths and SHA-256 hashes. It does not require DOSBox-X or a Windows guest. The tools may also be located in a sibling `TOOLS` directory (including its `HOST` subdirectory).

## Compatibility and limits

GUI automation has been tested with Windows 1.01, 2.x and 3.0 real mode in DOSBox-X. Compatibility with every physical PC, display driver and keyboard layout is not guaranteed. `TYPE` assumes a US keyboard layout and Caps Lock off.

One script runs at a time; up to eight variables and four nested GOSUB calls. `WAIT` accepts 0–59,000 ms. `SHELL`/`SHELLWAIT` launch Windows NE programs, not DOS applications, and do not return a DOS ERRORLEVEL. `END` leaves Windows running; `SHUTDOWN` asks Windows to exit.

Released under [The Unlicense](LICENSE). Windows installations and external build tools are not included.
