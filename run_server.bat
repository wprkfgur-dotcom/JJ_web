@echo off
chcp 65001 > nul
title JJ Invest Web Trading Server (Windows)

echo ============================================================
echo [JJ Invest] 로컬 개발 웹 서버를 시작합니다 (Windows)
echo ============================================================

cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

%PYTHON_EXE% run_server.py

pause
