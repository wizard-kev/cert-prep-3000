@echo off
rem Double-click to uninstall. Your practice progress (data\progress.db) is kept unless you add -RemoveProgress.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
pause
