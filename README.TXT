NOWBAT 0.0.54 - WINDOWS SCRIPT RUNNER
==============================

NOWBAT runs simple automation scripts under Windows 1.01, Windows 2.x, and
Windows 3.0 real mode. Use WIN101\NOWBAT.EXE for Windows 1/2 and
WIN300\NOWBAT.EXE for Windows 3. Start it from WITHIN Windows, giving
it the name of a .WAS script:

    NOWBAT.EXE HELLO.WAS

HELLO.WAS:

    ShowIcon=YES
    LOGFILE "HELLO.LOG"
    LOG "Hello from NOWBAT"
    WAIT 2000
    LOGCLOSE
    END

Supported tasks: file/directory operations, variables and branches,
logging, Windows application launch/wait, BMP screenshots, TAR archives,
window selection and native mouse/keyboard automation.
Read SCRIPT.TXT for syntax, EXAMPLES for samples and HISTORY.TXT for changes.

IMPORTANT
---------
END exits NOWBAT; Windows stays open. SHUTDOWN requests that Windows quit
and may present a confirmation dialog. ASSERT failure also requests a
Windows shutdown. SHELL and SHELLWAIT launch Win16 applications only,
not DOS programs; they do not provide a DOS child exit code.

WAIT supports 0-59000 milliseconds. Up to eight variables and four nested
GOSUB calls are supported. Quote paths containing spaces, and use DOS 8.3
filenames where possible. Screenshots are BMP; TAR output is uncompressed.
NOWBAT supports native mouse and keyboard automation, window selection,
window readiness, KEYCOMBO and TYPE (US printable ASCII). See SCRIPT.TXT.

BUILDING FROM SOURCE
--------------------
On a Windows build PC, install JWASM (assembler) and NBJWLINK (16-bit
Windows executable linker), plus Python 3 for icons and ZIP creation.
Run MAKE.BAT in the source directory. See README.md for tool setup.
MAKE builds both targets and creates versioned source and binary ZIPs
in DIST, e.g. NOWBAT_SOURCE_0.0.54.ZIP and NOWBAT_BINARIES_0.0.54.ZIP.
These build tools are NOT needed to run NOWBAT.

GUI automation tested in DOSBox-X on Windows 1/2/3 real mode.
Other drivers, layouts and physical hardware may behave differently.
Check RESULT and ERRORCODE after automation operations.

License: The Unlicense. See LICENSE.
