@echo off
setlocal
title Unified Switch Collector

echo =====================================================================
echo                    Starting Unified Switch Collector
echo =====================================================================
echo.

:: Portable release: prefer the bundled executable, so no Python is needed.
if exist "Switch-Collector.exe" (
    Switch-Collector.exe %*
    goto :after_run
)

:: Source checkout: fall back to the interpreter.
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Neither Switch-Collector.exe nor Python was found!
    echo This folder does not look like a portable release.
    echo Download the portable ZIP from release/, or install Python 3.8+ from
    echo https://www.python.org/ and tick "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

:: Check inventory file with real credentials
if not exist "switch.txt" (
    echo [ERROR] Inventory file switch.txt not found!
    if exist "switch.example.txt" (
        echo Please copy switch.example.txt to switch.txt and configure switch IPs and credentials.
    )
    echo.
    pause
    exit /b 1
)

:: Ensure working directories exist
if not exist "logs" (
    mkdir logs
)
if not exist "outputs" (
    mkdir outputs
)

echo Running collector from source. Any --mode argument is passed straight through.
echo Press Ctrl + C at any time to stop.
echo.

python switch_collector.py %*

:after_run
if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARNING] Collector exited with code %ERRORLEVEL%
    pause
)
