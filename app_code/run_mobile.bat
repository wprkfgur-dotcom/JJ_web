@echo off
set PYTHONIOENCODING=utf-8
title JongJong Mobile App

echo ========================================================
echo  JongJong Mobile App Launcher (Windows)
echo ========================================================
echo.
echo Starting mobile application in 412x860 phone view...
echo.

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0mobile_app.py"
) else (
    python "%~dp0mobile_app.py"
)

if errorlevel 1 (
    echo.
    echo [Error] Failed to run mobile application.
    pause
)
