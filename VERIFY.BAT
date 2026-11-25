@echo off
rem Stable current-version verifier; use VERIFY instead of old VERIFY_Wxxx.
cd /d "%~dp0"
if not exist "SRC\WAS.ASM" goto missing
if not exist "HOST\runuat.py" goto missing
if not exist "HOST\iconbuild.py" goto missing
if not exist "TESTS\BOOT.WAS" goto missing
findstr /C:"NOWBAT_BUILD=W054" "SRC\WAS.ASM" >nul
if errorlevel 1 goto missing
findstr /C:"STARTUP_TRACE_LIMIT_SECONDS = 50" "HOST\runuat.py" >nul
if errorlevel 1 goto missing
findstr /C:"EXPECTED_BUILD_MARKER = 'NOWBAT_BUILD=W054'" "HOST\runuat.py" >nul
if errorlevel 1 goto missing
findstr /C:"0.0.54" VERSION.TXT >nul
if errorlevel 1 goto missing
echo NOWBAT SOURCE VERIFIED in %CD%
exit /b 0
:missing
echo NOWBAT SOURCE VERIFICATION FAILED in %CD%
exit /b 2
