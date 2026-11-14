@echo off
rem Keep the terminal open if setup fails so the error remains readable.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_simulation.ps1" %*
if errorlevel 1 pause
