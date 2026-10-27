@echo off
rem Double-click to uninstall. Your practice progress (data\tracker.db) is kept unless you add -RemoveProgress.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
pause
