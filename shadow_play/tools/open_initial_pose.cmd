@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_initial_pose.ps1"
if errorlevel 1 pause
