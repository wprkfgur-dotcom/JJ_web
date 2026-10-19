"""
시스템 전역 종가 캐시 관리 모듈 (Global Daily Close Price Cache)
- 종목(Ticker)별 최신 마감 종가를 프로세스 전역 메모리(_GLOBAL_PRICE_CACHE)에 영구 보존합니다.
- data/global_price_cache.json에 디스크 영속화하여 서버 재기동 시에도 즉시 복원됩니다.
- 아침 05:30 메리츠 스케줄러, 사용자 정산 입력, 야후 파이낸스 조회 등
  어느 한 곳에서라도 종가가 확인되면 전역 변수에 즉시 등록되어,
  이후 모든 사용자 및 계좌가 야후 파이낸스 추가 호출 없이 0.0001초 만에 즉시 종가를 공유받습니다.
"""
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "global_price_cache.json")

# 메모리 전역 캐시 딕셔너리: { ticker.upper(): { "date": "YYYY-MM-DD", "close_price": float, "source": str, "updated_at": str } }
_GLOBAL_PRICE_CACHE: Dict[str, Dict[str, Any]] = {}


def _get_kst_now_str() -> str:
    """한국 표준시(KST) 현재 시각 문자열 반환"""
    kst = datetime.now(timezone.utc) + timedelta(hours=9)
    return kst.strftime("%Y-%m-%d %H:%M:%S")


def init_price_cache():
    """디스크 파일에서 전역 종가 캐시를 메모리로 로드합니다."""
    global _GLOBAL_PRICE_CACHE
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _GLOBAL_PRICE_CACHE = data
        except Exception as ex:
            print(f"[PriceCache] 캐시 파일 로드 안내: {ex}")


def save_price_cache():
    """메모리 전역 캐시를 디스크 JSON 파일로 원자적 저장합니다."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        temp_file = CACHE_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(_GLOBAL_PRICE_CACHE, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, CACHE_FILE)
    except Exception as ex:
        print(f"[PriceCache] 캐시 디스크 저장 오류: {ex}")


def set_cached_close(ticker: str, close_price: float, date_str: str = None, source: str = "manual") -> Dict[str, Any]:
    """
    특정 종목의 종가를 시스템 전역 변수에 등록하고 디스크에 저장합니다.
    """
    if not ticker or close_price is None or float(close_price) <= 0:
        return {}

    ticker_clean = ticker.strip().upper()
    now_kst = _get_kst_now_str()
    price_val = round(float(close_price), 2)

    if not date_str:
        date_str = now_kst[:10]
    else:
        date_str = str(date_str).strip()[:10]

    entry = {
        "ticker": ticker_clean,
        "date": date_str,
        "close_price": price_val,
        "source": source,
        "updated_at": now_kst
    }

    # 대표 키는 date_str이 기존 대표 키의 날짜보다 최신이거나 같을 때만 갱신 (과거 데이터 입력 시 최신값 보호)
    existing_rep = _GLOBAL_PRICE_CACHE.get(ticker_clean)
    if not existing_rep or str(existing_rep.get("date", "")) <= date_str:
        _GLOBAL_PRICE_CACHE[ticker_clean] = entry

    # 날짜별 복합 키는 항상 보존 (ticker_date)
    _GLOBAL_PRICE_CACHE[f"{ticker_clean}_{date_str}"] = entry

    save_price_cache()
    print(f"[PriceCache] [OK] 전역 종가 등록: [{ticker_clean}] ${price_val:,.2f} (기준일: {date_str}, 출처: {source})")
    return entry


def get_cached_close(ticker: str, date_str: str = None) -> Optional[Dict[str, Any]]:
    """
    시스템 전역 변수에서 종목의 종가를 조회합니다.
    1) date_str이 명시된 경우: 반드시 해당 날짜(date == date_str)의 캐시 항목만 반환합니다.
       (해당 날짜의 데이터가 없으면 다른 날짜의 종가를 반환하지 않고 None을 반환)
    2) date_str이 생략된 경우(None): 해당 종목의 가장 최근 등록된 종가를 반환합니다.
    """
    global _GLOBAL_PRICE_CACHE
    if not _GLOBAL_PRICE_CACHE:
        init_price_cache()

    ticker_clean = ticker.strip().upper() if ticker else "SOXL"

    if date_str:
        d_clean = str(date_str).strip()[:10]
        exact_key = f"{ticker_clean}_{d_clean}"
        if exact_key in _GLOBAL_PRICE_CACHE:
            return _GLOBAL_PRICE_CACHE[exact_key]

        # 종목 대표 캐시가 있을 경우, 그 캐시의 날짜가 일치할 때만 허용
        if ticker_clean in _GLOBAL_PRICE_CACHE:
            entry = _GLOBAL_PRICE_CACHE[ticker_clean]
            if entry.get("date") == d_clean:
                return entry

        # 날짜가 지정되었는데 일치하는 데이터가 없으면 다른 날짜 것을 반환하면 안 됨!
        return None

    # date_str이 None일 때만 가장 최근 등록된 종가 반환
    if ticker_clean in _GLOBAL_PRICE_CACHE:
        return _GLOBAL_PRICE_CACHE[ticker_clean]

    return None


def get_all_cached_closes() -> Dict[str, Any]:
    """현재 전역 변수에 캐싱된 모든 종목의 최신 종가 현황 반환"""
    global _GLOBAL_PRICE_CACHE
    if not _GLOBAL_PRICE_CACHE:
        init_price_cache()
    return {k: v for k, v in _GLOBAL_PRICE_CACHE.items() if "_" not in k}


# 모듈 임포트 시 자동 초기화
init_price_cache()
