@echo off
chcp 65001 >nul
echo ========================================
echo Information Frontier Launcher
echo ========================================
echo.
echo Starting backend and frontend...
echo Backend port: 8472
echo Conda env: ifrontier
echo.
echo Close this window to stop all services
echo.

powershell -ExecutionPolicy Bypass -File "%~dp0start-game.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Failed to start, press any key to exit...
    pause >nul
)
