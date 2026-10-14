"""
=====================================================================
메리츠증권 Open API 연동 클라이언트 (Meritz Securities Open API Client)
- OAuth 2.0 접근 토큰 발급 및 만료 시간 기반 자동 재사용/갱신
- 미국 해외주식 (SOXL, TQQQ 등) 외화 예수금 및 보유 잔고 조회
- 종종이 3단계 LOC 분할 주문표 기반 미국주식 LOC ("32") / 지정가 ("01") 주문 전송
- 안전 주문 모드 (Dry-Run / 실주문 전환) 및 경고 클래스 코드(PTP 등) 대응
=====================================================================
"""
import os
import sys
import json
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
import requests

logger = logging.getLogger("meritz_client")

# 메리츠증권 Open API 기본 도메인
MERITZ_BASE_URL = "https://openapi.imeritz.com:9443"

# 주요 미국 거래소 식별번호 (ovrs_exch_vndr_idno)
EXCHANGE_CODE_MAP = {
    "NASDAQ": "0537",
    "OQ": "0537",
    "NYSE": "0321",
    "NY": "0321",
    "AMEX": "0066",
    "AX": "0066"
}

# 기본 종목별 거래소 매핑
SYMBOL_EXCHANGE_MAP = {
    "SOXL": "0066",  # AMEX (NYSE American, 메리츠 SOXL.AX)
    "TQQQ": "0537",  # NASDAQ
    "TECL": "0537",  # NASDAQ
    "FNGU": "0321",  # NYSE
    "BULZ": "0321",  # NYSE
    "AAPL": "0537",  # NASDAQ
    "NVDA": "0537",  # NASDAQ
    "TSLA": "0537",  # NASDAQ
    "UPRO": "0321"   # NYSE
}

def get_mac_address() -> str:
    """단말 MAC 주소를 12자리 16진수 문자열로 반환 (메리츠 API 필수 헤더)"""
    raw_mac = f"{uuid.getnode():012X}"
    return raw_mac[:12]


class MeritzClient:
    """메리츠증권 Open API 통합 클라이언트"""

    def __init__(self, config_path: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = config_path or os.path.join(base_dir, "data", "meritz_config.json")
        self.base_url = MERITZ_BASE_URL
        self.session = requests.Session()
        
        # 토큰 메모리 캐시
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """로컬 설정 파일(data/meritz_config.json) 로드"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"설정 파일 읽기 실패 ({self.config_path}): {e}")
        return {
            "app_key": "",
            "app_secret": "",
            "account_number": "",  # 참고용 (메리츠 API는 앱키에 계좌가 바인딩됨)
            "is_simulation": True, # 안전을 위해 기본값은 모의(Dry-run) 모드
            "enabled": False
        }

    def save_config(self, config: Dict[str, Any]):
        """설정 파일 안전 저장"""
        self.config.update(config)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        tmp_file = f"{self.config_path}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, self.config_path)

    def is_configured(self) -> bool:
        """App Key 및 App Secret 설정 여부 확인"""
        return bool(self.config.get("app_key") and self.config.get("app_secret"))

    # -----------------------------------------------------------------
    # 1. 인증 및 토큰 관리 (OAuth 2.0)
    # -----------------------------------------------------------------
    def get_access_token(self, force_refresh: bool = False) -> Tuple[bool, str]:
        """
        접근 토큰 발급 및 만료 전 재사용.
        POST /oauth2/token (application/x-www-form-urlencoded, scope=login)
        """
        now = time.time()
        # 만료 60초 전까지는 캐시된 토큰 재사용
        if not force_refresh and self._access_token and now < (self._token_expires_at - 60):
            return True, self._access_token

        app_key = self.config.get("app_key", "").strip()
        app_secret = self.config.get("app_secret", "").strip()

        if not app_key or not app_secret:
            return False, "메리츠 App Key 및 App Secret이 설정되지 않았습니다."

        url = f"{self.base_url}/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "mac_address": get_mac_address()
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": app_key,
            "client_secret": app_secret,
            "scope": "login"
        }

        try:
            resp = self.session.post(url, headers=headers, data=data, timeout=10)
            res_json = resp.json()
            
            # 메리츠 토큰 응답 형식: {"access_token": "...", "expires_in": 86400, "token_type": "Bearer"}
            if resp.status_code == 200 and "access_token" in res_json:
                self._access_token = res_json["access_token"]
                expires_in = int(res_json.get("expires_in", 86400))
                self._token_expires_at = now + expires_in
                return True, self._access_token
            else:
                msg = res_json.get("error_description") or res_json.get("rsp_msg") or str(res_json)
                return False, f"토큰 발급 실패 ({resp.status_code}): {msg}"

        except Exception as e:
            return False, f"토큰 요청 통신 에러: {e}"

    def _get_headers(self, token: str) -> Dict[str, str]:
        """공통 요청 헤더 생성"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "mac_address": get_mac_address()
        }

    # -----------------------------------------------------------------
    # 2. 계좌 잔고 및 예수금 조회
    # -----------------------------------------------------------------
    def get_overseas_currencies(self) -> Dict[str, Any]:
        """
        해외주식 외화잔고 / 예수금 조회
        GET /accounts/v1/me/overseas/currencies
        (계좌번호는 앱키에 바인딩되어 있으므로 파라미터 제외)
        """
        ok, token = self.get_access_token()
        if not ok:
            return {"success": False, "message": token}

        url = f"{self.base_url}/accounts/v1/me/overseas/currencies"
        try:
            resp = self.session.get(url, headers=self._get_headers(token), timeout=10)
            res_json = resp.json()
            data = res_json.get("data") or {}
            rsp_cd = res_json.get("rsp_cd")

            if rsp_cd in ("0000", "0001", "5820", "5822") or bool(data):
                # USD 통화 항목 추출
                usd_info = {}
                if isinstance(data, list):
                    for item in data:
                        if item.get("crcd") == "USD" or item.get("crnc_code") == "USD":
                            usd_info = item
                            break
                elif isinstance(data, dict):
                    usd_info = data

                estm_amt = float(usd_info.get("estm_frcr_amt") or usd_info.get("frcr_dncl_amt_smtl") or usd_info.get("frcr_amt") or 0.0)
                total_asset = float(usd_info.get("entm_aset_vltn_amt") or 0.0)
                ex_rate = float(usd_info.get("vltn_exrt") or 0.0)

                return {
                    "success": True,
                    "data": data,
                    "usd_deposit": estm_amt,
                    "usd_total_asset": total_asset,
                    "exchange_rate": ex_rate,
                    "message": "외화 잔고 조회 성공"
                }
            else:
                return {
                    "success": False,
                    "message": f"[{rsp_cd}] {res_json.get('rsp_msg')} ({res_json.get('rsp_sub_msg', '')})"
                }
        except Exception as e:
            return {"success": False, "message": f"외화 잔고 조회 오류: {e}"}

    def get_overseas_holdings(self) -> Dict[str, Any]:
        """
        해외주식 보유 종목 잔고 조회
        GET /accounts/v1/me/overseas/holdings
        """
        ok, token = self.get_access_token()
        if not ok:
            return {"success": False, "message": token}

        url = f"{self.base_url}/accounts/v1/me/overseas/holdings"
        try:
            resp = self.session.get(url, headers=self._get_headers(token), timeout=10)
            res_json = resp.json()
            data = res_json.get("data") or []
            rsp_cd = res_json.get("rsp_cd")

            if rsp_cd in ("0000", "0001", "5620", "5762", "5766", "5820", "5822") or isinstance(data, list):
                holdings = []
                for row in (data if isinstance(data, list) else []):
                    ticker = row.get("ovrs_stck_symb_iscd") or (row.get("iscd", "").split(".")[0])
                    shares = int(float(row.get("rmnd_dqty") or row.get("seln_able_dqty") or row.get("cblc_qty") or 0))
                    holdings.append({
                        "ticker": ticker,
                        "name": row.get("isnm") or row.get("ovrs_isnm") or row.get("kor_isnm") or ticker,
                        "shares": shares,
                        "avg_price": float(row.get("avrg_unpr") or row.get("pchs_avg_pric") or 0.0),
                        "current_price": float(row.get("psnt_prc") or row.get("now_pric") or 0.0),
                        "eval_amt": float(row.get("frcr_vltn_amt") or row.get("evlu_amt") or 0.0),
                        "profit_amt": float(row.get("vltn_prls_camt") or 0.0),
                        "profit_pct": float(row.get("vltn_ert") or row.get("evlu_pfls_rt") or 0.0),
                        "exchange_code": row.get("ovrs_exch_vndr_idno") or "0537"
                    })
                return {
                    "success": True,
                    "holdings": holdings,
                    "message": "해외주식 잔고 조회 성공"
                }
            else:
                return {
                    "success": False,
                    "message": f"[{rsp_cd}] {res_json.get('rsp_msg')} ({res_json.get('rsp_sub_msg', '')})"
                }
        except Exception as e:
            return {"success": False, "message": f"해외주식 잔고 조회 오류: {e}"}

    # -----------------------------------------------------------------
    # 3. 해외주식 주문 (LOC / 지정가)
    # -----------------------------------------------------------------
    def send_overseas_order(self,
                            symbol: str,
                            side: str,              # "BUY" 또는 "SELL"
                            order_type: str,        # "LOC" (32) 또는 "LIMIT" (01)
                            qty: int,
                            price: float,
                            exchange_code: Optional[str] = None,
                            dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """
        미국 주식 LOC 및 지정가 주문 접수.
        POST /trading/v1/overseas/orders/buy
        POST /trading/v1/overseas/orders/sell
        """
        if qty <= 0:
            return {"success": False, "message": "주문 수량이 0 이하입니다."}

        # 모의 실행 여부 판별 (파라미터 우선, 미지정 시 설정값 확인)
        is_simulation = self.config.get("is_simulation", True) if dry_run is None else dry_run

        symbol = symbol.upper().strip()
        exch_code = exchange_code or SYMBOL_EXCHANGE_MAP.get(symbol, "0537")  # 기본 나스닥

        # 주문 구분 코드 매핑
        if order_type.upper() == "LOC":
            oder_cls_code = "32"       # LOC (종가 체결 지정가)
            oder_cond_cls_code = "7"  # 장마감 조건
        else:
            oder_cls_code = "01"       # 일반 지정가
            oder_cond_cls_code = "0"  # 일반 조건

        order_data = {
            "ovrs_stck_symb_iscd": symbol,
            "ovrs_exch_vndr_idno": exch_code,
            "oder_cls_code": oder_cls_code,
            "oder_cond_cls_code": oder_cond_cls_code,
            "odqt": int(qty),
            "ovrs_stck_oder_prc": f"{price:.2f}",
            "warn_cnfr_yn": "Y"        # 미국 PTP/위험 확인 시 자동 'Y' 재전송 플래그
        }

        # Dry-Run (모의 시뮬레이션 모드)인 경우 API 호출 없이 성공 모의 응답
        if is_simulation:
            return {
                "success": True,
                "simulation": True,
                "order_id": f"SIM_{int(time.time()*1000)}",
                "symbol": symbol,
                "side": side.upper(),
                "order_type": order_type.upper(),
                "qty": qty,
                "price": price,
                "message": f"[모의 실행(Dry-Run)] {symbol} {side.upper()} {qty}주 @ ${price:.2f} ({order_type.upper()}) 주문 시뮬레이션 성공"
            }

        # 실주문 발송
        ok, token = self.get_access_token()
        if not ok:
            return {"success": False, "message": token}

        endpoint = "/trading/v1/overseas/orders/buy" if side.upper() == "BUY" else "/trading/v1/overseas/orders/sell"
        url = f"{self.base_url}{endpoint}"

        try:
            resp = self.session.post(url, headers=self._get_headers(token), json=order_data, timeout=12)
            res_json = resp.json()
            rsp_cd = res_json.get("rsp_cd")
            data = res_json.get("data") or {}

            # 주문 경고 확인 체크: warn_cls_code 가 0 이 아니면 미접수 상태
            warn_cls_code = str(data.get("warn_cls_code", "0"))
            if warn_cls_code not in ("0", ""):
                warn_msg = data.get("warn_msg", "") or res_json.get("rsp_msg", "")
                return {
                    "success": False,
                    "warn_cls_code": warn_cls_code,
                    "message": f"주문 경고(미접수): [{warn_cls_code}] {warn_msg}"
                }

            if rsp_cd in ("0000", "0001"):
                odno = data.get("odno") or data.get("oder_no") or "UNKNOWN"
                return {
                    "success": True,
                    "simulation": False,
                    "order_id": odno,
                    "symbol": symbol,
                    "side": side.upper(),
                    "order_type": order_type.upper(),
                    "qty": qty,
                    "price": price,
                    "data": data,
                    "message": f"[{symbol}] {side.upper()} {qty}주 @ ${price:.2f} ({order_type.upper()}) 실주문 접수 완료 (주문번호: {odno})"
                }
            else:
                return {
                    "success": False,
                    "rsp_cd": rsp_cd,
                    "message": f"주문 실패 [{rsp_cd}]: {res_json.get('rsp_msg')} ({res_json.get('rsp_sub_msg', '')})"
                }
        except Exception as e:
            return {"success": False, "message": f"주문 전송 네트워크 오류: {e}"}

    # -----------------------------------------------------------------
    # 4. 당일 주문 및 체결 내역 조회
    # -----------------------------------------------------------------
    def get_today_orders(self) -> Dict[str, Any]:
        """
        당일 해외주식 주문체결내역 조회
        GET /trading/v1/overseas/orders/today
        """
        ok, token = self.get_access_token()
        if not ok:
            return {"success": False, "message": token}

        url = f"{self.base_url}/trading/v1/overseas/orders/today"
        params = {"cntg_cls_code": "0", "seln_byov_clcd": "0"}  # 전체 조회

        try:
            resp = self.session.get(url, headers=self._get_headers(token), params=params, timeout=10)
            res_json = resp.json()
            data = res_json.get("data") or []
            return {
                "success": True,
                "orders": data if isinstance(data, list) else [],
                "message": "당일 주문체결내역 조회 성공"
            }
        except Exception as e:
            return {"success": False, "message": f"주문체결내역 조회 오류: {e}"}

    # -----------------------------------------------------------------
    # 5. 종종이 당일 주문표 일괄 전송 파이프라인
    # -----------------------------------------------------------------
    def execute_jongjong_orders_batch(self,
                                      symbol: str,
                                      formatted_buys: List[Dict[str, Any]],
                                      formatted_sells: List[Dict[str, Any]],
                                      dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """
        종종이 당일 주문표(LOC 매수 / 매도 목록)를 일괄 전송
        """
        results = {
            "symbol": symbol,
            "buys": [],
            "sells": [],
            "total_success": 0,
            "total_failed": 0,
            "is_simulation": self.config.get("is_simulation", True) if dry_run is None else dry_run
        }

        # 1. 매수 주문 발송
        for b in (formatted_buys or []):
            qty = int(b.get("qty", 0))
            price = float(b.get("price", 0.0))
            if qty > 0 and price > 0:
                res = self.send_overseas_order(
                    symbol=symbol,
                    side="BUY",
                    order_type="LOC",
                    qty=qty,
                    price=price,
                    dry_run=dry_run
                )
                results["buys"].append(res)
                if res.get("success"):
                    results["total_success"] += 1
                else:
                    results["total_failed"] += 1

        # 2. 매도 주문 발송
        for s in (formatted_sells or []):
            qty = int(s.get("qty", 0))
            price = float(s.get("price", 0.0))
            if qty > 0 and price > 0:
                res = self.send_overseas_order(
                    symbol=symbol,
                    side="SELL",
                    order_type="LOC",
                    qty=qty,
                    price=price,
                    dry_run=dry_run
                )
                results["sells"].append(res)
                if res.get("success"):
                    results["total_success"] += 1
                else:
                    results["total_failed"] += 1

        return results


# 싱글턴 인스턴스
meritz_client = MeritzClient()

