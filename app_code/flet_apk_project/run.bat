@echo off
chcp 65001 > nul
title 종종이 트레이더 윈도우 실행기
cd /d "%~dp0"
echo ==============================================
echo  종종이 & 무한매수 트레이더 (Windows 디버깅 실행 중)
echo ==============================================
"..\.venv\Scripts\python.exe" main.py
pause
