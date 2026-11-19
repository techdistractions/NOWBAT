# NOWBAT

NOWBAT is a lightweight script runner for **Windows 1.01, Windows 2.x and Windows 3.0 real mode**, including 8086/8088-based PCs. It can launch Windows applications, work with files and directories, log results, take desktop BMP screenshots and create uncompressed TAR archives.

## Run

Use `WIN101\NOWBAT.EXE` on Windows 1.01 or 2.x and `WIN300\NOWBAT.EXE` on Windows 3.0 real mode (`WIN /R`). Start NOWBAT **inside Windows** with a `.WAS` script:

```text
NOWBAT.EXE HELLO.WAS
```

For example:

```text
ShowIcon=YES
LOGFILE "HELLO.LOG"
LOG "Started at %DATE% %TIME%"
WAIT 2000
LOGCLOSE
END
```

See `SCRIPT.TXT` for the current commands and `EXAMPLES` for ready-to-run scripts.

## Capture screenshots

`SNAP` takes a fast direct-video-memory BMP capture on supported display modes, using the full desktop and its detected colour depth unless you specify a region or `BPP`:

```text
SNAP "SCREEN.BMP"
SNAP "SCREEN.BMP" BPP=4
SNAP "PART.BMP",0,0,319,199,BPP=4
```

`SNAPSAFE` uses the slower GDI-based method when the active display driver or graphics mode is not supported by direct capture. It accepts the same filename, region and `BPP` arguments:

```text
SNAPSAFE "SCREEN.BMP"
```

An unsupported fast capture returns `%RESULT%=2`, rather than silently falling back. Supported FAST region captures require an eight-pixel-aligned X position and width. Check `%RESULT%` before using the BMP.

`%TIME%` and `%DATE%` return the live DOS clock (`HH:MM:SS`) and date (`YYYY-MM-DD`) whenever expanded, including in log messages.

## Build from source

Building requires **[JWASM](https://github.com/JWasm/JWasm)** (8086 assembler), **[NBJWLINK](https://github.com/techdistractions/NBJWLINK)** (Win16 NE linker) and Python 3 for icon insertion and ZIP packaging. These are host-side build tools; none is included in NOWBAT or required to run its binaries.

Put `JWASM.EXE` and `NBJWLINK.EXE` on `PATH`, place them in a local `TOOLS` folder, or set `JWASM_EXE` and `NBJWLINK_EXE` (for example in an optional `MAKE.LOCAL.BAT` next to `MAKE.BAT`). The build does not depend on a particular drive or directory.

From the source directory, run:

```bat
MAKE
```

This builds `DIST\WIN101\NOWBAT.EXE` and `DIST\WIN300\NOWBAT.EXE` and creates `DIST\NOWBAT_SOURCE.ZIP` and `DIST\NOWBAT_BINARIES.ZIP`. The source ZIP contains only public project files.

## Limits and licence

NOWBAT runs one script at a time. `SHELL` and `SHELLWAIT` start Windows NE programs, not DOS applications, and do not return a DOS `ERRORLEVEL`. `WAIT` accepts 0–59,000 milliseconds. The interpreter supports up to eight user variables and four nested `GOSUB` calls. NOWBAT does not inject mouse movement or keystrokes. `END` stops NOWBAT without ending the Windows session; `SHUTDOWN` asks Windows to exit.

Released under [The Unlicense](LICENSE). Windows files and external build tools are not bundled.
