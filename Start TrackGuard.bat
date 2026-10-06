@echo off
title TrackGuard
echo.
echo  ========================================
echo   TrackGuard - Starting...
echo  ========================================
echo.

:: Find the project's Python
set "PROJECT_DIR=%~dp0"

if exist "%PROJECT_DIR%.venv312\Scripts\pythonw.exe" (
    set "PYTHONW=%PROJECT_DIR%.venv312\Scripts\pythonw.exe"
) else if exist "%PROJECT_DIR%.venv\Scripts\pythonw.exe" (
    set "PYTHONW=%PROJECT_DIR%.venv\Scripts\pythonw.exe"
) else (
    echo [ERROR] No Python virtual environment found.
    echo Create one first:
    echo   py -3.12 -m venv .venv312
    echo   .venv312\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo  Using: %PYTHONW%
echo  Starting TrackGuard server, agent, and dashboard...
echo.

start "" "%PYTHONW%" "%PROJECT_DIR%TrackGuardApp.pyw"

echo  TrackGuard is launching!
echo  The dashboard will open in your browser automatically.
echo.
echo  This window will close in 3 seconds...
timeout /t 3 >nul
