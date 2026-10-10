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

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package_preboard.ps1"
if errorlevel 1 exit /b %errorlevel%
powershell.exe -NoProfile -Command "$p = '%~dp0..\deploy\artifacts\preboard\preboard_manifest.json'; $m = [IO.File]::ReadAllText($p, [Text.Encoding]::UTF8) | ConvertFrom-Json; if (-not $m.status.ready_for_physical_jtag) { Write-Error 'Pre-board gate failed. Resolve camera pin constraints and rebuild bitstream/XSA before JTAG.'; exit 3 }"
if errorlevel 1 exit /b %errorlevel%

echo Starting Vitis 2022.2 environment from %XILINX_VITIS%...
call "%XILINX_VITIS%\settings64.bat"
if errorlevel 1 goto :failed

echo Starting XSCT programming script...
call "%XILINX_VITIS%\bin\xsct.bat" "%~dp0scripts\program_vitis_jtag.tcl"
if errorlevel 1 goto :failed

echo.
echo Programming completed. Check HDMI and the PS UART serial terminal.
exit /b 0

:failed
echo.
echo Programming failed. Keep this window open and capture the error text.
exit /b 1
