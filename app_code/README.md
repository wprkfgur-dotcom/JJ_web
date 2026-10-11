# jj_invest ⚡ 종종이 & 무한매수 주식 매매 시스템

미국 레버리지 ETF(SOXL, TQQQ 등)를 위한 **종종이(JJ) 3단계 LOC 매매 전략 & 라오어 무한매수법 v4.0** 통합 실매매 관리 및 백테스트 플랫폼입니다.

---

## 🎯 지원 플랫폼 및 공식 배포 타깃

본 프로젝트는 **모바일 우선(Mobile-First)** 단일 코드베이스로 운영되며, 공식 배포 타깃은 아래 2종입니다:

1. 📱 **안드로이드 릴리스 앱**: `dist\JongJongTrader_ARM64.apk`
2. 💻 **윈도우 모바일 뷰 앱**: `dist\JongJongTrader_Mobile.exe`

---

## ✨ 주요 기능

1. **💼 내 투자 계좌 관리 및 실시간 대시보드 (Live & Accounts)**
   - **다중 계좌 관리**: 여러 투자 계좌 생성, 설정(위기준비금 비율, 시드, 메모 등) 수정 및 삭제
   - **위기준비금(AK) Risk-Off 병합 시스템**: 평상시(Normal/Safe)에는 비상금(기본 5%)을 엄격 격리 보관하고, 급락장(Risk-Off) 진입 시 누적된 모든 준비금을 투자금에 전액 병합하여 저점 분할 매수 집행
   - **오늘의 LOC 순 주문표 (퉁치기 상계 반영)**: 당일 장전에 걸어야 할 1차~4차 LOC 분할 매수 및 익절/손절 매도 주문을 실시간 자동 계산
   - **일일 체결 정산 & 캘린더 연동**: 미국 정규장 일정에 맞춘 Next Day 진행 및 일일 종가/체결 수량 입력 정산
   - **자산 입출금 및 세금 인출 관리**: 투자금 추가 입금 및 세금 납부를 위한 출금 이력 관리
   - **구글 드라이브 클라우드 동기화**: PC와 모바일 간 계좌 및 거래 데이터 실시간 양방향 연동

2. **📊 백테스트 시뮬레이터 (Backtest Simulator)**
   - 기간별, 종목별(SOXL, TQQQ 등), 초기 시드별 전략 성과 정밀 분석
   - 총수익률, 연평균 성장률(CAGR), 최대 낙폭(MDD), 샤프 지수, 칼마 비율 및 자산 성장 곡선 차트 제공

3. **🔄 원클릭 자동 업데이트 시스템**
   - GitHub Releases와 연동되어 신규 버전 출시 시 앱 내에서 즉시 감지 및 다이렉트 업데이트 지원

---

## 📁 프로젝트 구조

```text
jj_invest/
├── core/                       # 공통 코어 모듈
│   ├── app_update.py           # GitHub Releases 연동 자동 업데이트 엔진
│   ├── cloud_sync.py           # 구글 드라이브(GAS) 실시간 클라우드 동기화
│   ├── data.py                 # 야후 파이낸스 시세 다운로드 & SQLite DB 캐시
│   ├── market_calendar.py      # 미국 증시 개장일 캘린더
│   └── metrics.py              # CAGR, MDD, 샤프/칼마비율 성과 분석
├── strategies/                 # 투자 전략 모듈
│   ├── base.py                 # BaseStrategy 추상 기본 클래스
│   ├── jongjong.py             # 종종이(JJ) 3단계 모드 & LOC 4분할 매매 전략
│   ├── infinite_buying_v4.py   # 라오어 무한매수법 v4.0 전략
│   └── buy_and_hold.py         # 단순 보유(Buy & Hold) 벤치마크 전략
├── gui/                        # 핵심 비즈니스 로직
│   ├── account_manager.py      # 계좌 데이터 영속성 관리
│   └── order_netting.py        # 퉁치기(상계) 주문 계산 엔진
├── mobile/                     # 모바일 UI 보조 모듈
│   ├── theme.py                # 색상 테마 및 스타일링 상수
│   ├── helpers.py              # 클립보드, 토스트, 날짜 파싱 헬퍼
│   └── charts.py               # 벡터 SVG 차트 렌더러
├── data/                       # 데이터 저장소 (accounts.json 등)
│   ├── accounts.example.json   # 계좌 템플릿 예시 파일
│   └── market_data.db          # 시세 로컬 캐시 DB
├── flet_apk_project/           # Flutter/SeriousPython 안드로이드 APK 빌드 프로젝트
├── dist/                       # 컴파일된 최종 산출물 (바이너리 전용 보관함)
│   ├── JongJongTrader_ARM64.apk   # 안드로이드 실기기 설치 APK
│   └── JongJongTrader_Mobile.exe  # 윈도우 모바일뷰 실행파일
├── mobile_app.py               # 모바일 Flet 애플리케이션 메인 소스
├── run_mobile.bat              # 윈도우 로컬 모바일 프리뷰 실행기
├── build_mobile_exe.py         # 윈도우 모바일 실행파일 빌드 스크립트
├── build_arm64_release_apk.ps1 # 안드로이드 ARM64 Release APK 빌드 스크립트
├── sync_app.py                 # 소스코드 -> APK 빌드 프로젝트 동기화 스크립트
├── DEVELOPMENT_POLICY.md       # 개발 및 릴리스 정책 가이드
├── CHANGELOG.md                # 버전별 릴리스 노트
└── requirements.txt            # 의존성 패키지 목록
```

---

## 🚀 빠른 시작

### 1. 로컬 환경에서 모바일 뷰 실행 (Windows)
```powershell
.\run_mobile.bat
```

### 2. 안드로이드 Release APK 빌드
```powershell
powershell -ExecutionPolicy Bypass -File .\build_arm64_release_apk.ps1
```

### 3. 윈도우용 모바일 실행파일 빌드
```powershell
python build_mobile_exe.py
```
