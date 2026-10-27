@echo off
rem Double-click to install or repair. Extra options pass through, e.g.  install.cmd -Port 8080
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
