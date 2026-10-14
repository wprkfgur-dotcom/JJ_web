#!/usr/bin/env bash
# =====================================================================
# JJ Invest - 오라클 우분투 서버 원클릭 업데이트 스크립트
# =====================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "🔄 [JJ Invest] 최신 코드 가져오기 (git pull)..."
echo "============================================================"
git pull origin main || git pull origin master

echo "📦 패키지 의존성 확인..."
if [ -d "venv" ]; then
    ./venv/bin/pip install -r requirements.txt
fi

echo "⚙️  systemd 서비스 재시작 (jj_invest)..."
sudo systemctl restart jj_invest

echo "============================================================"
echo "✅ 서버가 최신 버전으로 업데이트되고 재시작되었습니다!"
echo "============================================================"
sudo systemctl status jj_invest --no-pager
