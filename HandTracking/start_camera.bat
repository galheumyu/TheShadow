@echo off
rem Apply the execution-policy override only to this launcher process.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_camera.ps1" %*
if errorlevel 1 pause
