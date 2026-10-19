@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0shadow_play\tools\launch_attended_center.ps1"
if errorlevel 1 pause
