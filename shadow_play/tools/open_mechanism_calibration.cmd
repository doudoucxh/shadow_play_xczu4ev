@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_mechanism_calibration.ps1"
if errorlevel 1 pause
