# NOWBAT

NOWBAT is a small script runner for **Windows 1.01, Windows 2.x, and Windows 3.0 real mode** on 8086/8088-compatible PCs. It handles file operations, logging, application launches, timed waits, BMP screen capture, and uncompressed TAR archives.

## Run

Use `WIN101\NOWBAT.EXE` for Windows 1.01/2.x or `WIN300\NOWBAT.EXE` for Windows 3.0 started in real mode (`WIN /R`). Launch the program **inside Windows** with a `.WAS` filename:

```text
NOWBAT.EXE HELLO.WAS
```

For example, `HELLO.WAS` can contain:

```text
ShowIcon=YES
LOGFILE "HELLO.LOG"
LOG "Hello from NOWBAT"
WAIT 2000
LOGCLOSE
END
```

`END` closes NOWBAT without closing Windows. `SHUTDOWN` asks Windows to close the session and may trigger a confirmation dialog. Use DOS-style paths; 8.3 filenames are safest. See `SCRIPT.TXT` for supported command syntax and `EXAMPLES` for working scripts.

## Build

**[JWASM](https://github.com/JWasm/JWasm)** is required to assemble the 8086 source. **[NBJWLINK](https://github.com/techdistractions/NBJWLINK)** is required to produce the Windows NE executables for Windows 1/2/3 real mode. Python 3 is used only on the build PC to insert icons and create ZIP files. These tools are not needed to run NOWBAT. Neither JWASM nor NBJWLINK is bundled.

On a Windows development PC, put `JWASM.EXE` and `NBJWLINK.EXE` on `PATH`, or set their full paths in `MAKE.LOCAL.BAT`. `MAKE` does not search system-specific tool directories or neighbouring repositories. It also accepts tools placed in a `TOOLS` folder under the NOWBAT source directory. Then run:

```bat
MAKE
```

This builds both executables and creates `DIST\NOWBAT_SOURCE.ZIP` and `DIST\NOWBAT_BINARIES.ZIP`. For developer tests and release checks, run `MAKE2 ALL` and `AUTOUAT ALL` as explained in `DEVELOPMENT.TXT`. No DOSBox-X or Windows guest is required by the basic `MAKE` command; native testing is separate. The source tree belongs in the GitHub repository; upload the two `DIST` ZIPs as GitHub Release assets rather than committing generated executables to the repository.

## Limits

NOWBAT runs one script at a time. `SHELL` and `SHELLWAIT` launch Windows NE applications, not DOS programs; they do not return a DOS `ERRORLEVEL`. `WAIT` supports 0 to 59,000 ms. The language supports up to eight user variables and four nested `GOSUB` calls. `ASSERT` failure requests Windows shutdown. It does not provide mouse or keyboard injection.

The source is released under [The Unlicense](LICENSE). Windows operating-system files, JWASM, and NBJWLINK are not part of this repository.
