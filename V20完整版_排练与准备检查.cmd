@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0shadow_play\tools\open_v20_full_preparation.ps1" %*
if errorlevel 1 pause
