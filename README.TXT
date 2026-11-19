NOWBAT - WINDOWS SCRIPT RUNNER
==============================

NOWBAT runs scripts inside Windows 1.01, Windows 2.x and Windows 3.0
real mode on 8086/8088-compatible computers.

Use WIN101\NOWBAT.EXE with Windows 1/2 and WIN300\NOWBAT.EXE with
Windows 3.0 real mode (start Windows with WIN /R).

Launch inside Windows with a script file:

    NOWBAT.EXE HELLO.WAS

Example:

    ShowIcon=YES
    LOGFILE "HELLO.LOG"
    LOG "Started %DATE% %TIME%"
    WAIT 2000
    LOGCLOSE
    END

SNAP "SCREEN.BMP" captures the entire desktop at its current colour
depth using the fast graphics-memory method on supported displays.
SNAPSAFE "SCREEN.BMP" uses the slower GDI method for compatibility.
Both commands accept optional BPP and region arguments; see SCRIPT.TXT.
Unsupported FAST captures report RESULT=2.

NOWBAT also supports variables, branching, application launches, file
operations, logging and TAR archives. END closes NOWBAT without closing
Windows. SHUTDOWN requests a Windows session exit. Use DOS-style paths
and 8.3 filenames for best compatibility.

To build, install JWASM, NBJWLINK and Python 3 on a Windows PC, then
run MAKE.BAT. See README.md in the source ZIP for details.

The Unlicense. See LICENSE.
