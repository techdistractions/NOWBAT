@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo ============================================================
echo NOWBAT W083 AUDIT - test only, NEVER builds
echo ============================================================
if exist "%~dp0AUDIT.LOCAL.BAT" call "%~dp0AUDIT.LOCAL.BAT"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=SNAPFAST"
if not "%~3"=="" goto usage
set "NOWBAT_SNAPFAST_DEV="
set "NOWBAT_SNAPFAST_TARGET="
set "NOWBAT_MOUSE_DEV="
set "NOWBAT_WINDOW_DEV="
set "NOWBAT_INPUT_DEV="
set "NOWBAT_KEYBOARD_DEV="
set "NOWBAT_GUISYNC_DEV="
set "NOWBAT_GUISYNC_TARGET="
set "NOWBAT_STARTSHOT="
set "WAS_UAT_BOOT_ONLY="
set "WAS_UAT_DESKTOP=visible"
if /I "%MODE%"=="SNAPFAST" if not "%~2"=="" goto snapfast_target
if /I "%MODE%"=="KEYBOARD" if not "%~2"=="" goto guisync_target
if /I "%MODE%"=="INPUT" if not "%~2"=="" goto guisync_target
if /I "%MODE%"=="WINDOW" if not "%~2"=="" goto guisync_target
if /I "%MODE%"=="MOUSE" if not "%~2"=="" goto guisync_target
if /I "%MODE%"=="GUISYNC" if not "%~2"=="" goto guisync_target
if not "%~2"=="" if /I not "%~2"=="BOOT" goto usage
if /I "%~2"=="BOOT" if /I not "%MODE%"=="WIN200" goto usage
if /I "%~2"=="BOOT" set "WAS_UAT_BOOT_ONLY=1"
if /I "%MODE%"=="INPUTABI" goto inputabi
if /I "%MODE%"=="SNAPFAST" goto snapfast
if /I "%MODE%"=="KEYBOARD" goto guisync
if /I "%MODE%"=="INPUT" goto guisync
if /I "%MODE%"=="WINDOW" goto guisync
if /I "%MODE%"=="MOUSE" goto guisync
if /I "%MODE%"=="GUISYNC" goto guisync
if /I "%MODE%"=="STARTSHOT" goto startshot
if /I "%MODE%"=="ALL" set "MODE=FULL"
if /I "%MODE%"=="REGRESSION" goto ready
if /I "%MODE%"=="FULL" goto ready
if /I "%MODE%"=="WIN101" goto ready
if /I "%MODE%"=="WIN200" goto ready
if /I "%MODE%"=="WIN300" goto ready
goto usage
:snapfast_target
if /I "%~2"=="WIN101" goto snapfast_target_ok
if /I "%~2"=="WIN200" goto snapfast_target_ok
if /I "%~2"=="WIN300" goto snapfast_target_ok
goto usage
:snapfast_target_ok
set "NOWBAT_SNAPFAST_TARGET=%~2"
:snapfast
set "NOWBAT_SNAPFAST_DEV=1"
goto startshot
:guisync_target
if /I "%~2"=="WIN101" goto guisync_target_ok
if /I "%~2"=="WIN200" goto guisync_target_ok
if /I "%~2"=="WIN300" goto guisync_target_ok
goto usage
:guisync_target_ok
set "NOWBAT_GUISYNC_TARGET=%~2"
:guisync
if /I "%MODE%"=="KEYBOARD" set "NOWBAT_KEYBOARD_DEV=1"
if /I "%MODE%"=="INPUT" set "NOWBAT_INPUT_DEV=1"
if /I "%MODE%"=="WINDOW" set "NOWBAT_WINDOW_DEV=1"
if /I "%MODE%"=="MOUSE" set "NOWBAT_MOUSE_DEV=1"
set "NOWBAT_GUISYNC_DEV=1"
goto ready
:startshot
set "NOWBAT_STARTSHOT=1"
set "MODE=STARTSHOT"
goto ready
:inputabi
if not "%~2"=="" goto usage
goto ready
:ready
if /I "%WAS_AUDIT_DRYRUN%"=="1" (
 echo AUDIT DISPATCH DRYRUN: MODE=%MODE%
 exit /b 0
)
rem Never compile, link, verify source, or call MAKE2 from AUDIT.
if not exist BUILD md BUILD
if /I "%MODE%"=="INPUTABI" goto runner
if not exist BUILD\SNAPFAST.READY goto no_build
if not exist DIST\WIN101\NOWBAT.EXE goto no_build
if not exist DIST\WIN300\NOWBAT.EXE goto no_build
if not exist BUILD\WCHILD.EXE goto no_build
if not exist BUILD\WWAIT.EXE goto no_build
if /I "%MODE%"=="KEYBOARD" if not exist BUILD\WGEOM.EXE goto no_build
if /I "%MODE%"=="INPUT" if not exist BUILD\WGEOM.EXE goto no_build
:runner
if not exist HOST\STREAM.PY goto no_runner
if not exist HOST\PACK.PY goto no_runner
if exist OUTPUT.ZIP del /q OUTPUT.ZIP >nul 2>&1
if exist RESULT.JSON del /q RESULT.JSON >nul 2>&1
if exist BUILD\RESULT.JSON del /q BUILD\RESULT.JSON >nul 2>&1
if /I "%MODE%"=="INPUTABI" (
 echo W083 AUDIT: read-only input export inventory, no build or emulator.
) else (
 echo W083 AUDIT: using already-built binaries, no MAKE or MAKE2.
)
if "%NOWBAT_STARTSHOT%"=="1" echo W083 AUDIT: visible Win1/Win2/Win3, 10-second warmup, SNAP then TAR then END.
if "%NOWBAT_MOUSE_DEV%"=="1" echo W083 AUDIT: native cursor movement and readback.
if /I "%MODE%"=="INPUT" echo W083 AUDIT: native mouse dispatch, drag and release; visible guests.
if /I "%MODE%"=="GUISYNC" echo W083 AUDIT: GUISYNC headless DOEVENTS and bounded WAITFOR FILE; native evidence required.
set "PYTHON=python"
where py >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 goto no_python
%PYTHON% -B -u HOST\STREAM.PY %MODE%
set "STATUS=%ERRORLEVEL%"
if "%STATUS%"=="0" goto passed
>BUILD\AUDIT.RESULT echo AUDIT=FAIL
>>BUILD\AUDIT.RESULT echo MODE=%MODE%
>>BUILD\AUDIT.RESULT echo EXITCODE=%STATUS%
goto pack
:passed
>BUILD\AUDIT.RESULT echo AUDIT=PASS
>>BUILD\AUDIT.RESULT echo MODE=%MODE%
>>BUILD\AUDIT.RESULT echo EXITCODE=0
:pack
%PYTHON% -B HOST\PACK.PY
if errorlevel 1 (
 echo W083 AUDIT FAIL: could not package OUTPUT.ZIP
 exit /b 1
)
if not exist OUTPUT.ZIP (
 echo W083 AUDIT FAIL: OUTPUT.ZIP not produced
 exit /b 1
)
if not "%STATUS%"=="0" (
 echo W083 AUDIT FAIL - see OUTPUT.ZIP
 exit /b %STATUS%
)
echo W083 AUDIT PASS - evidence in OUTPUT.ZIP
exit /b 0
:no_build
>BUILD\AUDIT.LOG echo AUDIT=FAIL: Run MAKE first. No verified W083 build exists.
>BUILD\AUDIT.RESULT echo AUDIT=FAIL
>>BUILD\AUDIT.RESULT echo REASON=RUN_MAKE_FIRST
if exist HOST\PACK.PY (
 where py >nul 2>&1
 if not errorlevel 1 (py -3 HOST\PACK.PY) else (python HOST\PACK.PY)
)
echo W083 AUDIT FAIL: No completed MAKE found. Run MAKE first, then AUDIT REGRESSION.
exit /b 2
:no_runner
echo W083 AUDIT FAIL: HOST\STREAM.PY or HOST\PACK.PY missing.
exit /b 2
:no_python
echo W083 AUDIT FAIL: Python 3 not found.
exit /b 2
:usage
echo Usage: AUDIT REGRESSION
echo        AUDIT KEYBOARD [WIN101^|WIN200^|WIN300]
echo        AUDIT INPUT [WIN101^|WIN200^|WIN300]
echo Usage: AUDIT INPUTABI
echo        AUDIT WINDOW [WIN101 ^| WIN200 ^| WIN300]
echo        AUDIT MOUSE [WIN101 ^| WIN200 ^| WIN300]
echo        AUDIT GUISYNC [WIN101 ^| WIN200 ^| WIN300]
echo        AUDIT SNAPFAST [WIN101 ^| WIN200 ^| WIN300]
echo Run MAKE first. AUDIT never builds.
exit /b 2
