@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_attended_center.ps1"
if errorlevel 1 pause
