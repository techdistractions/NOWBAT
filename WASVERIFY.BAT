@echo off
rem Unlike VERIFY, WASVERIFY does not collide with CMD's built-in VERIFY command.
call "%~dp0VERIFY.BAT"
exit /b %errorlevel%
