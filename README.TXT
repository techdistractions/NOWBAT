NOWBAT - WINDOWS SCRIPT RUNNER
==============================

NOWBAT runs simple scripts inside Windows 1.01, Windows 2.x and Windows
3.0 real mode on 8086/8088-compatible computers.

Use WIN101\NOWBAT.EXE with Windows 1/2, and WIN300\NOWBAT.EXE with
Windows 3.0 real mode (start Windows with WIN /R).

From inside Windows, run:

    NOWBAT.EXE HELLO.WAS

Example HELLO.WAS:

    ShowIcon=YES
    LOGFILE "HELLO.LOG"
    LOG "Hello from NOWBAT"
    WAIT 2000
    LOGCLOSE
    END

NOWBAT supports logging, variables, control flow, application launches,
file and directory operations, BMP screen captures and TAR archives.
Refer to SCRIPT.TXT for commands and EXAMPLES for sample scripts.

END closes NOWBAT but leaves Windows running. SHUTDOWN requests Windows
shutdown and may open a confirmation dialog. SHELL and SHELLWAIT start
Windows NE applications, not DOS programs. WAIT accepts 0-59000 ms.
Up to eight user variables and four nested GOSUB calls are supported.
Use DOS-compatible paths and 8.3 names when possible. NOWBAT cannot
inject mouse movement or keystrokes.

To build from source, install JWASM, NBJWLINK and Python 3 on a Windows
build PC, then run MAKE.BAT. The linker creates Windows 1/2 and Windows
3.0 real-mode executables. See README.md in the source package for setup details.

The Unlicense. See LICENSE.
