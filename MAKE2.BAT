@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem NOWBAT - relocatable JWASM + NBJWLINK 8088-capable build gate.
rem Local machine settings belong in MAKE.LOCAL.BAT (git-ignored).
cd /d "%~dp0"
if not exist SRC\WAS.ASM goto badroot
if exist "%~dp0MAKE.LOCAL.BAT" call "%~dp0MAKE.LOCAL.BAT"
echo NOWBAT MAKE2 (runtime 0.0.54) - active tree: %CD%
if not exist BUILD md BUILD
echo MAKE2: checking source before JWASM/NBJWLINK...
rem Source validation is performed by HOST\AUDIT.PY after toolchain discovery.
rem NEVER invoke VERIFY: this collides with the Windows CMD built-in.
if not exist "HOST\AUDIT.PY" (
 echo MAKE2 FAIL: HOST\AUDIT.PY is missing.
 exit /b 2
)
if not exist "TESTS\WCHILD.ASM" (
 echo MAKE2 FAIL: TESTS\WCHILD.ASM is missing.
 exit /b 2
)
echo MAKE2: complete sources found; locating JWASM and NBJWLINK...
rem New build invalidates old runtime audit evidence.
if exist BUILD\AUDIT.RESULT del /q BUILD\AUDIT.RESULT >nul 2>&1
if exist BUILD\AUDIT.LOG del /q BUILD\AUDIT.LOG >nul 2>&1
if exist RESULT.JSON del /q RESULT.JSON >nul 2>&1
if exist BUILD\RESULT.JSON del /q BUILD\RESULT.JSON >nul 2>&1
if exist BUILD\MANIFEST.JSON del /q BUILD\MANIFEST.JSON >nul 2>&1
if exist UAT\RESULTS rmdir /s /q UAT\RESULTS >nul 2>&1
if exist UAT\REGRESSION rmdir /s /q UAT\REGRESSION >nul 2>&1
if not exist DIST\WIN101 md DIST\WIN101
if not exist DIST\WIN300 md DIST\WIN300
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=ALL"
if /I "%TARGET%"=="WIN1" set "TARGET=WIN101"
if /I "%TARGET%"=="WIN3" set "TARGET=WIN300"
if /I "%TARGET%"=="HIDE" set "TARGET=ALL"
if /I "%TARGET%"=="ALL" goto targetok
if /I "%TARGET%"=="WIN101" goto targetok
if /I "%TARGET%"=="WIN300" goto targetok
echo Usage: MAKE2 ALL ^| WIN101 ^| WIN300
goto bad
:targetok
rem Explicit per-executable overrides take priority over tool-root discovery.
rem Auto-detect CDrive\NOWBAT, NBUTIL\WAS and PATH layouts independently.
set "ASM="
set "LINKER="
if defined JWASM_EXE set "ASM=%JWASM_EXE%"
if defined NBJWLINK_EXE set "LINKER=%NBJWLINK_EXE%"
set "TOOLROOT="
if defined NOWBAT_TOOLROOT set "TOOLROOT=%NOWBAT_TOOLROOT%"
if not defined TOOLROOT if defined WAS_TOOLROOT set "TOOLROOT=%WAS_TOOLROOT%"
if defined TOOLROOT (
  call :probe_tools "%TOOLROOT%"
) else (
  call :probe_tools "%~dp0TOOLS"
  call :probe_tools "%~dp0..\TOOLS"
  call :probe_tools "%~dp0..\..\TOOLS"
  rem Detect a nearby DOSBox-X CDrive regardless of NOWBAT checkout location.
  rem For example C:\Retro\test\nowbat can use C:\Retro\Dosbox-X\CDrive\TOOLS.
  call :probe_tools "%~dp0..\..\Dosbox-X\CDrive\TOOLS"
  call :probe_tools "%~dp0..\..\..\Dosbox-X\CDrive\TOOLS"
  call :probe_tools "%~dp0..\Dosbox-X\CDrive\TOOLS"
)
if not defined ASM for /f "delims=" %%F in ('where JWASM.EXE 2^>nul') do if not defined ASM set "ASM=%%F"
if not defined LINKER for /f "delims=" %%F in ('where NBJWLINK.EXE 2^>nul') do if not defined LINKER set "LINKER=%%F"
rem NBJWLINK is often built inside its own sibling source tree.
rem Search only nearby NBJWLINK trees, not the whole system drive.
for %%D in ("%~dp0..\NBJWLINK" "%~dp0..\..\NBJWLINK" "%~dp0..\..\..\NBJWLINK") do (
  if not defined LINKER if exist "%%~fD\" (
    for /f "delims=" %%F in ('where /r "%%~fD" NBJWLINK.EXE 2^>nul') do if not defined LINKER set "LINKER=%%F"
  )
)
>BUILD\BUILD.LOG echo NOWBAT MAKE2 %TARGET%
>>BUILD\BUILD.LOG echo SOURCE_ROOT=%CD%
>>BUILD\BUILD.LOG echo JWASM=%ASM%
>>BUILD\BUILD.LOG echo NBJWLINK=%LINKER%
if not exist "%ASM%" (
  echo FAIL: JWASM missing: %ASM%
  echo Configure JWASM_EXE or NOWBAT_TOOLROOT in MAKE.LOCAL.BAT.
  >>BUILD\BUILD.LOG echo FAIL: JWASM missing: %ASM%
  goto fail
)
if not exist "%LINKER%" (
  echo FAIL: NBJWLINK missing: %LINKER%
  echo Configure NBJWLINK_EXE or NOWBAT_TOOLROOT in MAKE.LOCAL.BAT.
  >>BUILD\BUILD.LOG echo FAIL: NBJWLINK missing: %LINKER%
  goto fail
)
echo MAKE TOOLCHAIN: JWASM=%ASM%
echo MAKE TOOLCHAIN: NBJWLINK=%LINKER%
rem Perform 8086/source preflight before invoking JWASM.
call :preflight SOURCE
if errorlevel 1 goto fail
rem Build must never accept previous object/executable files as evidence.
del /q BUILD\*.OBJ >nul 2>&1
if /I "%TARGET%"=="ALL" (
  del /q DIST\WIN101\NOWBAT.EXE DIST\WIN300\NOWBAT.EXE >nul 2>&1
) else (
  del /q DIST\%TARGET%\NOWBAT.EXE >nul 2>&1
)
rem Delete obsolete distribution name so there is exactly one current EXE.
del /q DIST\WIN101\WAS.EXE DIST\WIN300\WAS.EXE >nul 2>&1
rem Build the tiny independent Win16 SHELLWAIT fixture for UAT only.
rem It is NOT linked into WAS.EXE and cannot increase WAS DGROUP.
if exist BUILD\WCHILD.EXE del /q BUILD\WCHILD.EXE >nul 2>&1
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WCHILD Win16 test executable
"%ASM%" -0 -omf -FoBUILD\WCHILD.OBJ TESTS\WCHILD.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
>>BUILD\BUILD.LOG echo [NBJWLINK] WCHILD WIN101
"%LINKER%" @LINK\WCHILD.RSP >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if not exist BUILD\WCHILD.EXE goto fail
rem Distinct module *name* and completion marker; never reuse WCHILD for
rem SHELLWAIT immediately after SHELL on Windows 1.01.
if exist BUILD\WWAIT.EXE del /q BUILD\WWAIT.EXE >nul 2>&1
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WWAIT distinct Win16 child
"%ASM%" -0 -omf -DWAS_WAIT_CHILD=1 -FoBUILD\WWAIT.OBJ TESTS\WCHILD.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
>>BUILD\BUILD.LOG echo [NBJWLINK] WWAIT WIN101
"%LINKER%" @LINK\WWAIT.RSP >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if not exist BUILD\WWAIT.EXE goto fail
rem Build independent native window geometry fixture, only for AUDIT.
if exist BUILD\WGEOM.EXE del /q BUILD\WGEOM.EXE >nul 2>&1
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WGEOM native fixture
"%ASM%" -0 -omf -FoBUILD\WGEOM.OBJ TESTS\WGEOM.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
"%LINKER%" @LINK\WGEOM.RSP >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if not exist BUILD\WGEOM.EXE goto fail
rem Build separate objects so Windows 1/2 NEVER imports Windows 3 ExitWindows.
if /I "%TARGET%"=="WIN300" goto asm300
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WAS101 (legacy USER.2)
"%ASM%" -0 -omf -FoBUILD\WAS101.OBJ SRC\WAS.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if /I "%TARGET%"=="WIN101" goto asmcommon
:asm300
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WAS300 (ExitWindows)
"%ASM%" -0 -omf -DWAS_WIN300=1 -FoBUILD\WAS300.OBJ SRC\WAS.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
:asmcommon
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WASTAR
"%ASM%" -0 -omf -FoBUILD\WASTAR.OBJ SRC\WASTAR.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WASFS (DOS filesystem, 8088)
"%ASM%" -0 -omf -FoBUILD\WASFS.OBJ SRC\WASFS.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WASSNAP101 and WASSNAP300
"%ASM%" -0 -omf -FoBUILD\WASSNAP101.OBJ SRC\WASSNAP.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
"%ASM%" -0 -omf -DWAS_WIN300=1 -FoBUILD\WASSNAP300.OBJ SRC\WASSNAP.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
>>BUILD\BUILD.LOG echo [JWASM -0 -omf] WASUI (Win1-compatible iconic window)
"%ASM%" -0 -omf -FoBUILD\WASUI.OBJ SRC\WASUI.ASM >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if /I "%TARGET%"=="WIN300" goto link300
>>BUILD\BUILD.LOG echo [NBJWLINK] WIN101
"%LINKER%" @LINK\WIN101.RSP >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if not exist DIST\WIN101\NOWBAT.EXE goto fail
call :compact DIST\WIN101\NOWBAT.EXE
if errorlevel 1 goto fail
call :icon WIN101
if errorlevel 1 goto fail
call :terminal WIN101
if errorlevel 1 goto fail
if /I "%TARGET%"=="WIN101" goto success
:link300
>>BUILD\BUILD.LOG echo [NBJWLINK] WIN300
"%LINKER%" @LINK\WIN300.RSP >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 goto fail
if not exist DIST\WIN300\NOWBAT.EXE goto fail
call :compact DIST\WIN300\NOWBAT.EXE
if errorlevel 1 goto fail
call :icon WIN300
if errorlevel 1 goto fail
call :terminal WIN300
if errorlevel 1 goto fail
:success
>>BUILD\BUILD.LOG echo ASSEMBLE_AND_LINK=PASS
set "WAS_AUDIT_TARGET=%TARGET%"
call :preflight STATIC
if errorlevel 1 goto fail
call :package
 echo MAKE2: LINK + HEADER STATIC PASS. Run AUDIT for complete Win1/2/3 UAT.
exit /b 0
rem Resolve a tool root without relying on a fixed source-tree depth.
:probe_tools
if not defined ASM if exist "%~1\HOST\JWASM.EXE" set "ASM=%~1\HOST\JWASM.EXE"
if not defined ASM if exist "%~1\JWASM.EXE" set "ASM=%~1\JWASM.EXE"
if not defined LINKER if exist "%~1\NBJWLINK.EXE" set "LINKER=%~1\NBJWLINK.EXE"
if not defined LINKER if exist "%~1\HOST\NBJWLINK.EXE" set "LINKER=%~1\HOST\NBJWLINK.EXE"
exit /b 0

:badroot
echo ERROR: Run MAKE2 from the NOWBAT source directory.
:bad
exit /b 2
:fail
>>BUILD\BUILD.LOG echo MAKE=FAIL
call :package
 echo NOWBAT MAKE2 FAILURE DETAILS:
findstr /B /C:"AUDIT=FAIL:" /C:"FAIL:" BUILD\BUILD.LOG
 echo MAKE2 FAIL: see BUILD\BUILD.LOG and OUTPUT.ZIP
exit /b 1

:preflight
rem Internal MAKE checks; the only operator audit invocation is AUDIT.
>>BUILD\BUILD.LOG echo [INTERNAL %~1 CHECK]
where py >nul 2>&1
if not errorlevel 1 (
 py -3 -B HOST\AUDIT.PY %~1 >>BUILD\BUILD.LOG 2>&1
 if errorlevel 1 exit /b 1
 exit /b 0
)
python -B HOST\AUDIT.PY %~1 >>BUILD\BUILD.LOG 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:package
rem Python is host-side packaging only, never part of WAS.EXE.
where py >nul 2>&1
if not errorlevel 1 (
 py -3 -B HOST\PACK.PY
 exit /b 0
)
where python >nul 2>&1
if not errorlevel 1 python -B HOST\PACK.PY
exit /b 0

:compact
>>BUILD\BUILD.LOG echo [NE zero arena compaction] %~1
where py >nul 2>&1
if not errorlevel 1 (
 py -3 -B HOST\necompact.py "%~1" >>BUILD\BUILD.LOG 2>&1
 if errorlevel 1 exit /b 1
 exit /b 0
)
python -B HOST\necompact.py "%~1" >>BUILD\BUILD.LOG 2>&1
exit /b %errorlevel%

:icon
>>BUILD\BUILD.LOG echo [NE native bat icon] %~1
where py >nul 2>&1
if not errorlevel 1 (
 py -3 -B HOST\iconbuild.py %~1 DIST\%~1\NOWBAT.EXE --asset-dir ASSETS >>BUILD\BUILD.LOG 2>&1
 if errorlevel 1 exit /b 1
 exit /b 0
)
python -B HOST\iconbuild.py %~1 DIST\%~1\NOWBAT.EXE --asset-dir ASSETS >>BUILD\BUILD.LOG 2>&1
exit /b %errorlevel%

:terminal
if not exist BUILD\TERMS\%~1 md BUILD\TERMS\%~1
rem Three separate Win16 module names are essential on Windows 1.x.
rem They use the same 8086 interpreter objects and NO new runtime imports.
for %%N in (NBTEND NBTPASS NBTFAIL) do (
  if exist BUILD\TERMS\%~1\%%N.EXE del /q BUILD\TERMS\%~1\%%N.EXE >nul 2>&1
  >>BUILD\BUILD.LOG echo [NBJWLINK] %~1 AutoUAT %%N
  "%LINKER%" @LINK\TERMS\%~1_%%N.RSP >>BUILD\BUILD.LOG 2>&1
  if errorlevel 1 exit /b 1
  if not exist BUILD\TERMS\%~1\%%N.EXE exit /b 1
  call :compact BUILD\TERMS\%~1\%%N.EXE
  if errorlevel 1 exit /b 1
)
exit /b 0
