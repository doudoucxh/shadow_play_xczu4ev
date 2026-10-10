@echo off
setlocal
if defined XILINX_VITIS goto :have_vitis
if exist "D:\xilinx\Vitis\2022.2\settings64.bat" set "XILINX_VITIS=D:\xilinx\Vitis\2022.2"

:have_vitis
if not defined XILINX_VITIS (
  echo ERROR: Full Vitis 2022.2 was not found. Set XILINX_VITIS or install to D:\xilinx\Vitis\2022.2.
  exit /b 2
)
if not exist "%XILINX_VITIS%\bin\xsct.bat" (
  echo ERROR: "%XILINX_VITIS%\bin\xsct.bat" is missing.
  exit /b 2
)
call "%XILINX_VITIS%\settings64.bat"
if errorlevel 1 exit /b %errorlevel%
set "VITIS_PLATFORM_ONLY=1"
call "%XILINX_VITIS%\bin\xsct.bat" "%~dp0scripts\create_vitis_workspace.tcl"
if errorlevel 1 exit /b %errorlevel%
set "VITIS_PLATFORM_ONLY="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_firmware_direct.ps1"
exit /b %errorlevel%
