@echo off
setlocal
title Unified Switch Collector - Setup & Installation

echo =====================================================================
echo            Unified Switch Collector - Automated Setup
echo =====================================================================
echo.

:: Check Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found on this system!
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to tick "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [1/3] Checking Python version...
python --version

echo.
echo [2/3] Installing Python dependencies (netmiko, openpyxl)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Failed to install Python dependencies!
    echo.
    pause
    exit /b 1
)

echo.
echo [3/3] Preparing working directories...
if not exist "logs" (
    mkdir logs
)
if not exist "outputs" (
    mkdir outputs
)

if exist "switch.txt" (
    echo [OK] Inventory file switch.txt found.
) else (
    if exist "switch.example.txt" (
        echo [INFO] switch.txt not found yet.
        echo Copy switch.example.txt to switch.txt, then fill in your switch IPs and credentials.
    ) else (
        echo [WARNING] switch.example.txt template is missing!
    )
)

echo.
echo =====================================================================
echo              Setup Complete - Ready to Use!
echo   Run start_collector.bat to launch the collector.
echo   switch.txt is git-ignored; never commit real credentials.
echo =====================================================================
echo.
pause
