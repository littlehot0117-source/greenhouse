@echo off
title Greenhouse Inventory Server
echo ==================================================
echo   Starting Greenhouse Inventory Management System...
echo ==================================================
cd /d "%~dp0"

:: Wait 2 seconds in the background, then open default web browser
start /b cmd /c "timeout /t 2 >nul && start http://localhost:8000"

:: Run the Python server
python server.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start. Please check if Python is installed.
    echo Command run: python server.py
    echo.
    pause
)
