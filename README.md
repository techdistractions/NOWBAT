# NOWBAT

NOWBAT is a lightweight scripting utility for **Windows 1.01, Windows 2.x and Windows 3.0 real mode**, including 8086/8088-based PCs. It can launch Windows programs, perform file operations, log results, capture BMP screenshots and create uncompressed TAR archives.

## Download and run

Use `WIN101\NOWBAT.EXE` under Windows 1.01 or 2.x, or `WIN300\NOWBAT.EXE` under Windows 3.0 real mode (`WIN /R`). Run NOWBAT *inside Windows*, passing a `.WAS` script filename:

```text
NOWBAT.EXE HELLO.WAS
```

Example script:

```text
ShowIcon=YES
LOGFILE "HELLO.LOG"
LOG "Hello from NOWBAT"
WAIT 2000
LOGCLOSE
END
```

The `EXAMPLES` directory contains scripts for logging, file copying and screen capture. See `SCRIPT.TXT` for command syntax and `README.TXT` for usage notes.

## Build from source

Building requires **JWASM** (8086 assembler), **NBJWLINK** (Windows NE linker), and **Python 3** (icon insertion and ZIP packaging) on the build PC:

- JWASM: https://github.com/JWasm/JWasm
- NBJWLINK: https://github.com/techdistractions/NBJWLINK

Install `JWASM.EXE` and `NBJWLINK.EXE` on `PATH`, place them in the local `TOOLS` directory, or set `JWASM_EXE` and `NBJWLINK_EXE` to their complete paths. You can set these environment variables in an optional `MAKE.LOCAL.BAT` next to `MAKE.BAT`. NOWBAT does not bundle these tools or depend on a particular installation directory.

Then, from the source directory, run:

```bat
MAKE
```

The public build produces `DIST\WIN101\NOWBAT.EXE`, `DIST\WIN300\NOWBAT.EXE`, `DIST\NOWBAT_SOURCE.ZIP` and `DIST\NOWBAT_BINARIES.ZIP`. The generated ZIPs include only the public source and runtime files.

## Supported operations and limits

Supported operations include logging; variables and branching; Windows application launch and wait; file and directory commands; cooperative timed waits; desktop or region BMP capture; and uncompressed TAR creation. `SHELL` launches Windows NE programs, not DOS executables. `END` exits NOWBAT without ending the Windows session; `SHUTDOWN` requests that Windows exit. `WAIT` accepts 0–59,000 milliseconds. Up to eight user variables and four nested `GOSUB` calls are supported. NOWBAT does not provide keystroke or mouse injection.

NOWBAT is released under [The Unlicense](LICENSE). Neither Microsoft Windows files nor external build tools are included.
