@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
rem Guest settings are private to the developer and excluded from Git.
if exist "%~dp0AUDIT.LOCAL.BAT" call "%~dp0AUDIT.LOCAL.BAT"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=ALL"
if /I "%MODE%"=="ALL" goto valid
if /I "%MODE%"=="WIN101" goto valid
if /I "%MODE%"=="WIN200" goto valid
if /I "%MODE%"=="WIN300" goto valid
echo Usage: AUTOUAT [WIN101 ^| WIN200 ^| WIN300 ^| ALL]
exit /b 2
:valid
if not "%~2"=="" (
 echo Usage: AUTOUAT [WIN101 ^| WIN200 ^| WIN300 ^| ALL]
 exit /b 2
)
echo NOWBAT AUTOUAT %MODE% - native command matrix, DOSBox-X VISIBLE
if /I "%WAS_AUTO_DRYRUN%"=="1" (
 echo AUTOUAT DISPATCH DRYRUN: MODE=%MODE%
 exit /b 0
)
rem AutoUAT produces AUTOUAT_OUTPUT.ZIP AND replaces OUTPUT.ZIP with the
rem same current native evidence, never a stale static MAKE-only package.
rem A one-command native qualification always builds the CURRENT source first.
rem Never use a stale NOWBAT.EXE/manifest after a runtime overlay.
rem If MAKE fails, preserve its OUTPUT.ZIP and do not launch guests.
set "PYTHON=python"
where py >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
where python >nul 2>&1
if errorlevel 1 if "%PYTHON%"=="python" (
 echo AUTOUAT FAIL: Python 3 unavailable
 exit /b 1
)
echo AUTOUAT: rebuilding current NOWBAT Win16 runtime and test children
call MAKE2.BAT ALL
if errorlevel 1 (
 echo NOWBAT AUTOUAT : FAIL - native build/static verification failed
 echo EVIDENCE: OUTPUT.ZIP
 exit /b 1
)
if not defined WAS_UAT_TIMEOUT set "WAS_UAT_TIMEOUT=300"
%PYTHON% -B -u HOST\AUTOUAT_STREAM.PY %MODE%
exit /b %errorlevel%
