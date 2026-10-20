@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0shadow_play\tools\board_serial.ps1" -PortName COM17 -CommandFile "%~dp0shadow_play\tools\stop_uart_text_stream.sh" -TimeoutSeconds 15
pause
