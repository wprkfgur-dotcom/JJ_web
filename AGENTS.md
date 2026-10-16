# 🏛️ JJ Invest 프로젝트 개발 및 운영 절대 수칙 (AGENTS Guidelines)

본 문서는 Antigravity AI 어시스턴트가 세션 재시작, 컨텍스트 압축, 또는 새로운 대화 시에도 **항상 최우선 순위로 로딩하여 준수해야 하는 프로젝트 핵심 원칙**입니다.

---

## 1. 🚀 배포 원칙 (Deployment Protocol) - CRITICAL

1. **임의 파일 전송 절대 금지**:
   - `sftp.put` 또는 스크립트로 원격 서버의 소스 코드를 직접 덮어쓰는 행위는 **절대 금지**한다.
   - 이는 로컬과 원격 간의 Git 형상 관리를 파괴하고 추적 불가능한 장애를 유발한다.

2. **표준 배포 워크플로우 준수 ([README_ORACLE_DEPLOY.md](file:///c:/oracle_web_server/README_ORACLE_DEPLOY.md))**:
   - **Step 1 (로컬 검증)**: 모든 코드 수정, 신규 기능, 버그 픽스는 반드시 **Windows 로컬 환경**에서 먼저 테스트하고 검증한다.
   - **Step 2 (Git 반영)**: 로컬에서 `git add`, `git commit`, `git push origin main`을 통해 GitHub 원격 저장소에 먼저 반영한다.
   - **Step 3 (원격 배포)**: 원격 배포는 반드시 로컬의 [`tools/deploy_to_oracle.py`](file:///c:/oracle_web_server/tools/deploy_to_oracle.py)를 실행한다.
     - 이 스크립트는 원격 서버(오라클 Ubuntu)에서 `git pull origin main`을 수행하여 소스를 동기화한 후 `sudo systemctl restart jj_invest`로 서비스를 안전하게 재시작한다.

---

## 2. 📈 투자 전략 수식 및 무결성 보존 원칙 (Strategy Integrity)

1. **종종이 분할매수 전략의 고유 공식 보존**:
   - 전략의 기본 공식(10일 주기 실투자원금 $AR$ 기준 모드별 분할, 곡률 0.7 곡선, Safe 모드 종가 부근 퉁치기, -17% 폭락 대비 1회분 배정)을 절대 훼손하지 않는다.
   - 사용자의 동의 없이 임의의 '안전 분할 배분(예산 단순 쪼개기)' 같은 엉터리 로직을 도입하여 주문표 수량을 왜곡해서는 안 된다.

2. **10일 주기 시즌 예산 소진 규칙 (Budget Exhaustion Rule)**:
   - **시즌 분할 기준**:
     - $\text{Normal}: P = AR / 8$ (8분할)
     - $\text{Safe}: P = AR / 7$ (7분할)
     - $\text{Risk-off}: P = AR / 5$ (5분할)
   - **시즌 기집행액 및 잔여 예산 추적**:
     - 시즌 내에 매수 체결된 일자들의 집행금 누적액을 차감하여 잔여 예산($\text{Remaining} = \max(0, AR - \text{Used})$)을 추적한다.
     - **모드 전환 규칙**: Normal 모드로 7일을 보내 7회분을 썼다면, 8일차에 Safe 모드로 전환되더라도 남은 예산은 Normal 1회분뿐이므로 Safe 1회분이 아닌 **남은 Normal 1회분 금액으로만 매수**된다.
     - **9~10일차 예산 소진 규칙**: 시즌 총 예산이 전액 소진되면 당일 매수 배정 예산은 $0이며, **매수 주문은 0건으로 매수 불가 상태가 되고 기존 보유 주식의 매도 주문만 유지하면서 관망 대기**한다.

3. **Safe 모드 상계(퉁치기) 복원 원칙**:
   - 당일 종가 부근($\le AU2 \times 1.01$)의 목표가 매도 수량이 존재할 경우, 당일 1차 매수 수량에서 해당 매도 수량을 상계하여 순매수 수량만 주문표에 산출한다.

---

## 3. 🤖 자동매매 체결 및 매매일지 정산 원칙 (Execution & Settlement)

1. **실제 체결 내역 기반 정산**:
   - 장 마감 후 또는 정산 스케줄러(`05:30 KST`) 실행 시 주문표를 보고 임의로 "체결되었겠지" 하고 추정 체결하는 폴백 로직을 절대 사용하지 않는다.
   - 반드시 **메리츠 증권 Open API의 실제 체결 내역(주문체결조회)**을 조회하여 실제 체결된 수량과 단가만 정산에 반영한다.

2. **매매일지 표기와 예수금 차감의 분리**:
   - **매매일지 기록**: 사용자 가독성 및 백테스트 정합성을 위해 일지 표시 가격(`BuyPrice`)은 **당일 종가(`Close`)**로 기록한다.
   - **예수금(`Cash`) 계산**: 예수금 증감 반영 시에만 **실제 체결 단가와 거래 수수료(0.1%)가 포함된 실결제 금액**으로 가감한다.

---

## 4. 🛠️ 개발 환경 및 프론트엔드 관리 수칙

1. **파이썬 환경 경로**:
   - Windows 로컬: `c:\oracle_web_server\venv\Scripts\python.exe`
   - 오라클 우분투 서버: `/home/huxley/oracle_web_server/venv/bin/python`

2. **프론트엔드 스크립트 수정 시 캐시 버스팅 관리**:
   - [`web/static/js/app.js`](file:///c:/oracle_web_server/web/static/js/app.js) 또는 [`web/static/js/mobile.js`](file:///c:/oracle_web_server/web/static/js/mobile.js) 수정 시, 반드시 [`web/templates/index.html`](file:///c:/oracle_web_server/web/templates/index.html) 및 [`web/templates/mobile.html`](file:///c:/oracle_web_server/web/templates/mobile.html)의 `?v=...` 버전을 올려주어 브라우저 캐시로 인한 구문 오류나 오동작을 원천 방지한다.
   - JavaScript 코드 작성 시 문법 오류(삼항 연산자 콜론 누락, 괄호 불일치 등)가 없는지 배포 전 철저히 검증한다.
