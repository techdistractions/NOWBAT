@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not "%~1"=="" goto usage
if exist "%~dp0MAKE.LOCAL.BAT" call "%~dp0MAKE.LOCAL.BAT"
set "ASM="
set "LINKER="
if defined JWASM_EXE set "ASM=%JWASM_EXE%"
if defined NBJWLINK_EXE set "LINKER=%NBJWLINK_EXE%"
if not defined ASM for /f "delims=" %%F in ('where JWASM.EXE 2^>nul') do if not defined ASM set "ASM=%%F"
if not defined LINKER for /f "delims=" %%F in ('where NBJWLINK.EXE 2^>nul') do if not defined LINKER set "LINKER=%%F"
if not defined ASM call :probe "%~dp0TOOLS"
if not defined LINKER call :probe "%~dp0TOOLS"
if not defined ASM goto missingasm
if not defined LINKER goto missinglink
if not exist "%ASM%" goto missingasm
if not exist "%LINKER%" goto missinglink
set "PY=python"
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 goto missingpython
if not exist BUILD md BUILD
if not exist DIST\WIN101 md DIST\WIN101
if not exist DIST\WIN300 md DIST\WIN300
rem Always build both targets; never reuse stale binaries.
del /q BUILD\*.OBJ >nul 2>&1
del /q DIST\WIN101\NOWBAT.EXE DIST\WIN300\NOWBAT.EXE >nul 2>&1
del /q DIST\NOWBAT_SOURCE.ZIP DIST\NOWBAT_BINARIES.ZIP >nul 2>&1
echo Building NOWBAT for Windows 1/2 and Windows 3 real mode...
"%ASM%" -0 -omf -FoBUILD\WAS101.OBJ SRC\WAS.ASM
if errorlevel 1 goto fail
"%ASM%" -0 -omf -DWAS_WIN300=1 -FoBUILD\WAS300.OBJ SRC\WAS.ASM
if errorlevel 1 goto fail
for %%M in (WASTAR WASFS WASSNAP WASUI) do (
 "%ASM%" -0 -omf -FoBUILD\%%M.OBJ SRC\%%M.ASM
 if errorlevel 1 goto fail
)
"%LINKER%" @LINK\WIN101.RSP
if errorlevel 1 goto fail
"%LINKER%" @LINK\WIN300.RSP
if errorlevel 1 goto fail
if not exist DIST\WIN101\NOWBAT.EXE goto fail
if not exist DIST\WIN300\NOWBAT.EXE goto fail
%PY% -B HOST\iconbuild.py WIN101 DIST\WIN101\NOWBAT.EXE --asset-dir ASSETS
if errorlevel 1 goto fail
%PY% -B HOST\iconbuild.py WIN300 DIST\WIN300\NOWBAT.EXE --asset-dir ASSETS
if errorlevel 1 goto fail
%PY% -B HOST\packdist.py
if errorlevel 1 goto fail
echo.
echo MAKE PASS: DIST\NOWBAT_SOURCE.ZIP and DIST\NOWBAT_BINARIES.ZIP
echo Executables: DIST\WIN101\NOWBAT.EXE and DIST\WIN300\NOWBAT.EXE
exit /b 0
:probe
if not defined ASM if exist "%~1\JWASM.EXE" set "ASM=%~1\JWASM.EXE"
if not defined LINKER if exist "%~1\NBJWLINK.EXE" set "LINKER=%~1\NBJWLINK.EXE"
exit /b 0
:missingasm
echo MAKE FAIL: JWASM.EXE not found. Put JWASM on PATH or configure JWASM_EXE.
exit /b 1
:missinglink
echo MAKE FAIL: NBJWLINK.EXE not found. Put NBJWLINK on PATH or configure NBJWLINK_EXE.
exit /b 1
:missingpython
echo MAKE FAIL: Python 3 not found. Python 3 is needed for ZIPs and icons.
exit /b 1
:usage
echo Usage: MAKE
exit /b 2
:fail
del /q DIST\NOWBAT_SOURCE.ZIP DIST\NOWBAT_BINARIES.ZIP >nul 2>&1
echo MAKE FAIL: no valid new package was produced. Check the error above.
exit /b 1
