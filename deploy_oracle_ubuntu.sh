#!/usr/bin/env bash
# =====================================================================
# JJ Invest - 오라클 클라우드 우분투(Ubuntu Linux) 원클릭 자동 배포 스크립트
# =====================================================================

set -e

echo "============================================================"
echo "⚡ [JJ Invest] 오라클 클라우드 우분투 자동 배포를 시작합니다."
echo "============================================================"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 1. 필수 시스템 패키지 설치
echo "📦 [1/5] 우분투 시스템 패키지 업데이트 및 파이썬 환경 설치..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip curl iptables-persistent

# 2. 파이썬 가상환경 생성 및 의존성 설치
echo "🐍 [2/5] 파이썬 가상환경(venv) 생성 및 패키지 설치..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 3. 우분투 OS 방화벽 8000 포트 개방
echo "🛡️  [3/5] 방화벽 포트 8000 개방 설정..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 8000/tcp || true
fi
# 오라클 리눅스/우분투 기본 iptables 규칙 추가
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT || true
sudo netfilter-persistent save || true

# 4. systemd 서비스 등록 (서버 재부팅 시 24시간 자동 실행)
echo "⚙️  [4/5] systemd 백그라운드 서비스 등록 (jj_invest.service)..."
SERVICE_FILE="/etc/systemd/system/jj_invest.service"

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=JJ Invest Web Trading Platform & Backtest Engine
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/run_server.py
Restart=always
RestartSec=5
Environment=PORT=8000
Environment=HOST=0.0.0.0

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable jj_invest
sudo systemctl restart jj_invest

# 실행 권한 부여
chmod +x run_server.sh update_server.sh deploy_oracle_ubuntu.sh

# 5. 상태 확인
echo "============================================================"
echo "🎉 [5/5] 배포 완료! 서비스가 백그라운드에서 실행 중입니다."
echo "============================================================"
echo "상태 확인: sudo systemctl status jj_invest"
echo "로그 확인: sudo journalctl -u jj_invest -f"
echo "웹 접속:   http://$(curl -s ifconfig.me || echo '오라클서버_공인IP'):8000"
echo "============================================================"
