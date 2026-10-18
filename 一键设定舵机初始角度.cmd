@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0shadow_play\tools\launch_initial_pose.ps1"
if errorlevel 1 pause
