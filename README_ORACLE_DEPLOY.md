# 🚀 JJ Invest 오라클 서버(Ubuntu) 복사 및 배포 가이드

본 프로젝트는 **Windows 로컬 환경**에서 개발 및 검증을 완료한 후, **오라클 클라우드(Oracle Cloud) 우분투(Ubuntu Linux) 서버**로 그대로 복사하여 24시간 무중단으로 구동할 수 있도록 설계되었습니다.

---

## 📌 주요 특징
1. **Windows & Ubuntu 크로스 플랫폼 호환**:
   - 운영체제에 구애받지 않는 경로 설계 (`pathlib.Path`, `os.path.join`)
   - Windows용 원클릭 실행기 (`run_server.bat`)
   - Ubuntu용 서비스 데몬 및 원클릭 배포기 (`deploy_oracle_ubuntu.sh`)
2. **오라클 서버 24시간 자동 백그라운드 운용**:
   - `systemd` 서비스 등록으로 서버 재부팅 시에도 자동 재시작
3. **핵심 기능**:
   - 💼 **자산 & 다중 계좌 현황**: 총 평가자산, 예수금, 수익률, 미매도 보유 슬롯, 일일 매매일지
   - 📋 **오늘의 LOC 순 주문표 (퉁치기 상계 엔진)**: 장전 LOC 매수/매도 상계 주문 자동 도출
   - ⚡ **백테스트 시뮬레이터**: SOXL, TQQQ 등 종목별 3단계 종종이 vs 무한매수 v4.0 vs VR 5.0 vs 단순보유 비교 및 인터랙티브 자산 성장 차트
   - 🤖 **향후 자동매매 서버 확장 준비**: 스케줄러 및 데몬 구조 구축 완료

---

## 💻 1단계: Windows 로컬에서 실행 및 테스트

Windows 환경에서는 터미널이나 탐색기에서 더블클릭으로 바로 실행할 수 있습니다:

```powershell
# 1. 터미널에서 실행 시
.\venv\Scripts\python.exe run_server.py

# 또는 탐색기에서 run_server.bat 더블클릭
```

브라우저에서 `http://localhost:8000` 으로 접속하여 기능 및 UI를 확인합니다.

---

## 🐧 2단계: Git을 통한 오라클 서버 배포 및 운영 워크플로우

개발 및 운영은 아래의 순서로 진행됩니다:
**윈도우 개발** ➡️ **`git push`** ➡️ **오라클 우분투에서 `git pull`** ➡️ **서버 프로그램 자동 업데이트**

### A. 최초 1회 오라클 서버에 설치 (Initial Setup)
오라클 우분투 서버에 SSH 접속 후 홈 디렉토리에서 실행합니다:
```bash
# 1. 저장소 클론
git clone https://github.com/wprkfgur-dotcom/JJ_web.git oracle_web_server
cd oracle_web_server

# 2. 원클릭 배포 스크립트 실행 (패키지 설치, venv 생성, 방화벽 개방, systemd 자동 등록)
chmod +x deploy_oracle_ubuntu.sh
./deploy_oracle_ubuntu.sh
```

---

## 🔄 3단계: 이후 코드 수정 시 업데이트 방법 (Routine Update)

1. **윈도우 개발 환경에서 작업 후 Push**:
   ```powershell
   git add .
   git commit -m "기능 추가 및 버그 수정"
   git push origin main
   ```

2. **오라클 우분투 서버에서 원클릭 업데이트**:
   오라클 서버 터미널에서 다음 명령어 한 줄만 입력하면 최신 코드를 pull 받고 백그라운드 서비스를 자동 재시작합니다:
   ```bash
   cd ~/oracle_web_server
   ./update_server.sh
   ```
   *(내부적으로 `git pull` ➡️ `pip install` ➡️ `sudo systemctl restart jj_invest` 가 실행됩니다)*

---

## 🛡️ 4단계: 오라클 클라우드 콘솔 방화벽(포트 8000) 개방

웹 브라우저로 접속하기 위해 오라클 클라우드 웹 콘솔에서 **포트 8000**을 열어주어야 합니다:

1. **오라클 클라우드 콘솔** 로그인
2. `네트워킹` → `가상 클라우드 네트워크(VCN)` → 해당 인스턴스의 VCN 클릭
3. `보안 목록(Security Lists)` → `기본 보안 목록(Default Security List)` 클릭
4. **수신 규칙 추가 (Add Ingress Rules)** 클릭:
   - **소스 CIDR**: `0.0.0.0/0`
   - **IP 프로토콜**: `TCP`
   - **대상 포트 범위**: `8000`
   - **설명**: `JJ Invest Web Platform`
5. 저장 후 완료!

---

## 🌐 5단계: 웹 브라우저 접속 및 관리

스마트폰이나 PC 브라우저에서 아래 주소로 접속합니다:
```text
http://<오라클_공인_IP>:8000
```

### 서버 관리 명령어
```bash
# 서비스 상태 확인
sudo systemctl status jj_invest

# 서비스 재시작
sudo systemctl restart jj_invest

# 서비스 중지
sudo systemctl stop jj_invest

# 실시간 서버 로그 모니터링
sudo journalctl -u jj_invest -f
```
