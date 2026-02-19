@echo off
chcp 65001 >nul
title MangaLib Downloader

echo ================================================
echo          MangaLib Downloader Launcher
echo ================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Check if requirements are installed
if not exist "requirements.txt" (
    echo [WARNING] requirements.txt not found
)

REM Run the main application
echo Starting MangaLib Downloader...
echo.
python main.py

pause
