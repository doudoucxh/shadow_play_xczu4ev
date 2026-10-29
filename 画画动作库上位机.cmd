@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0shadow_play\tools\launch_bus_servo.ps1" -Profile "%~dp0shadow_play\config\bus_servo.json" -PoseLibrary
if errorlevel 1 pause
