# jj_invest ⚡ 종종이 & 무한매수 주식 매매 시스템 (Web)

미국 레버리지 ETF(SOXL, TQQQ 등)를 위한 **종종이(JJ) 3단계 LOC 매매 전략 & 라오어 무한매수법 v4.0** 통합 계좌 관리 및 백테스트 플랫폼입니다.
FastAPI 웹 서버 단일 구성이며, 모든 계좌/거래 데이터는 서버 로컬(`data/accounts.json`)에서만 관리됩니다.

## 프로젝트 구조

```text
app_code/
├── core/
│   ├── account_manager.py     # 계좌 영속성(원자적 저장 + 자동 백업) 및 정산 로직
│   ├── backtest_runner.py     # 백테스트 실행/차트 시리즈
│   ├── data.py                # 시세 다운로드 & SQLite 캐시
│   ├── market_calendar.py     # 미국 증시 개장일 캘린더
│   ├── metrics.py             # CAGR, MDD, 샤프/칼마 지표
│   ├── order_netting.py       # 퉁치기(상계) 주문 계산
│   ├── strategy_registry.py   # 전략 레지스트리
│   ├── telegram_notifier.py   # 텔레그램 알림
│   ├── trade_history.py       # 거래 이력 계산
│   └── user_manager.py        # 사용자/세션 관리
├── strategies/                # 종종이, 무한매수 v4, VR v5, 퍼들, 바이앤홀드
├── tools/                     # 백테스트/튜닝 개발 스크립트
└── data/                      # accounts.json, users.json 등 (서버 로컬 DB)
```

웹 서버 코드는 저장소 루트의 `server.py`, `webapp/`, `web/` 에 있습니다.

## 실행

```bash
pip install -r requirements.txt
python run_server.py   # http://localhost:8000
```
