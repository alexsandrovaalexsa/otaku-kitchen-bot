@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_bot.ps1"
echo.
echo Press any key to close this window...
pause > nul
