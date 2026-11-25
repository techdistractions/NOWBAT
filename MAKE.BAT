@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo ============================================================
echo NOWBAT W082 MAKE - build only, no AUDIT, no DOSBox-X
echo ============================================================
if not "%~1"=="" goto usage
if not exist BUILD md BUILD
if exist BUILD\SNAPFAST.READY del /q BUILD\SNAPFAST.READY >nul 2>&1
if not exist "%~dp0MAKE2.BAT" goto missing
rem Build the runtime and independent native test fixtures.
rem No guest is launched by MAKE.
set "NOWBAT_SNAPFAST_DEV=1"
call "%~dp0MAKE2.BAT" ALL
if errorlevel 1 goto fail
if not exist DIST\WIN101\NOWBAT.EXE goto incomplete
if not exist DIST\WIN300\NOWBAT.EXE goto incomplete
if not exist BUILD\WCHILD.EXE goto incomplete
if not exist BUILD\WWAIT.EXE goto incomplete
if not exist BUILD\WGEOM.EXE goto incomplete
if not exist BUILD\TERMS\WIN101\NBTEND.EXE goto incomplete
if not exist BUILD\TERMS\WIN300\NBTEND.EXE goto incomplete
>BUILD\SNAPFAST.READY echo W082_MAKE_PASS
>>BUILD\SNAPFAST.READY echo BOTH_EXECUTABLES_AND_UAT_FIXTURES_BUILT
if errorlevel 1 goto fail
echo.
set "PYTHON=python"
where py >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"
%PYTHON% -B HOST\RELEASE.PY --local-build
if errorlevel 1 goto fail
%PYTHON% -B HOST\CHECKDIST.PY
if errorlevel 1 goto fail
echo W082 MAKE PASS - Both executables and native test fixtures built.
echo Now run: AUDIT REGRESSION
echo.
exit /b 0
:usage
echo Usage: MAKE
echo MAKE builds both NOWBAT targets.
exit /b 2
:missing
echo W082 MAKE FAIL: MAKE2.BAT is missing from this directory.
exit /b 2
:incomplete
echo W082 MAKE FAIL: Link completed but a required executable/fixture is missing.
echo Check BUILD\BUILD.LOG and OUTPUT.ZIP.
exit /b 1
:fail
echo W082 MAKE FAIL: Build did not pass; audit was NOT started.
echo Check BUILD\BUILD.LOG and OUTPUT.ZIP.
exit /b 1
