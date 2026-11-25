@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if exist "%~dp0DISTMAKE.LOCAL.BAT" call "%~dp0DISTMAKE.LOCAL.BAT"
if not exist "LICENSE" (
 echo DISTMAKE FAIL: LICENSE missing. Select and approve a licence before publishing.
 exit /b 2
)
findstr /I /C:"UNSELECTED TEMPLATE" /C:"[COPYRIGHT HOLDER" "LICENSE" >nul 2>&1
if not errorlevel 1 (
 echo DISTMAKE FAIL: LICENSE still contains an unapproved template.
 exit /b 2
)
echo NOWBAT release qualification: rebuilding and testing all Windows targets
call AUTOUAT.BAT ALL
if errorlevel 1 (
 echo DISTMAKE FAIL: full native AUTOUAT did not pass. See OUTPUT.ZIP.
 exit /b 1
)
where py >nul 2>&1
if errorlevel 1 goto direct_python
py -3 -B HOST\RELEASE.PY
if errorlevel 1 exit /b 1
py -3 -B HOST\CHECKDIST.PY
exit /b %errorlevel%
:direct_python
python -B HOST\RELEASE.PY
if errorlevel 1 exit /b 1
python -B HOST\CHECKDIST.PY
exit /b %errorlevel%
