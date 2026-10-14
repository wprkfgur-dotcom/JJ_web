#!/usr/bin/env bash
# =====================================================================
# JJ Invest - Oracle Cloud Ubuntu Linux 실행 스크립트
# =====================================================================

set -e

# 현재 스크립트 디렉터리로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "🚀 [JJ Invest] 오라클 우분투 웹 서버 시작"
echo "============================================================"

# 가상환경 파이썬 확인
if [ -d "venv" ] && [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ Python3을 찾을 수 없습니다. python3-venv 및 python3을 설치해주세요."
    exit 1
fi

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo "📡 서버 주소: http://${HOST}:${PORT}"
"$PYTHON_CMD" run_server.py
