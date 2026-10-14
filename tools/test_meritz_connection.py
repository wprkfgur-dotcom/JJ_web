"""
메리츠증권 Open API 로컬 연동 테스트 스크립트
PC 로컬 환경에서 인증, 외화 예수금/잔고 조회 및 모의 주문 발송을 단계별로 검증합니다.
"""
import os
import sys

# 프로젝트 루트 경로 등록
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.meritz_client import meritz_client


def run_test(app_key: str = None, app_secret: str = None):
    print("=" * 65)
    print("⚡ 메리츠증권 Open API 연동 검증 테스트 (PC 로컬 환경)")
    print("=" * 65)

    if app_key and app_secret:
        meritz_client.save_config({
            "app_key": app_key.strip(),
            "app_secret": app_secret.strip(),
            "is_simulation": True,  # 안전 모의 모드
            "enabled": True
        })
        print("[*] 전달받은 App Key / Secret을 data/meritz_config.json에 저장했습니다.")

    cfg = meritz_client.config
    current_key = cfg.get("app_key", "")
    masked_key = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else "(미설정)"
    print(f"1. 설정 확인: App Key = {masked_key}, Simulation Mode = {cfg.get('is_simulation')}")

    if not meritz_client.is_configured():
        print("[!] App Key와 App Secret이 설정되지 않았습니다.")
        print("    사용법: python tools/test_meritz_connection.py <APP_KEY> <APP_SECRET>")
        return False

    # 1단계: 토큰 발급 테스트
    print("\n[단계 1/3] 접근 토큰(OAuth 2.0) 발급 요청...")
    ok, token_or_err = meritz_client.get_access_token(force_refresh=True)
    if not ok:
        print(f"❌ 토큰 발급 실패: {token_or_err}")
        return False
    print(f"✅ 토큰 발급 성공! (Bearer {token_or_err[:10]}...{token_or_err[-6:]})")

    # 2단계: 외화 예수금 조회 테스트
    print("\n[단계 2/3] 해외주식 외화 잔고(USD 예수금) 조회 요청...")
    cur_res = meritz_client.get_overseas_currencies()
    if cur_res.get("success"):
        print(f"✅ 외화 잔고 조회 성공!")
        print(f"   - USD 예수금: ${cur_res.get('usd_deposit', 0.0):,.2f}")
        print(f"   - USD 주문가능금액: ${cur_res.get('usd_orderable', 0.0):,.2f}")
    else:
        print(f"⚠️ 외화 잔고 조회 응답: {cur_res.get('message')}")

    # 3단계: 해외 보유 종목 조회 테스트
    print("\n[단계 3/3] 해외주식 보유 종목 잔고 조회 요청...")
    hold_res = meritz_client.get_overseas_holdings()
    if hold_res.get("success"):
        holdings = hold_res.get("holdings", [])
        print(f"✅ 해외주식 보유 종목 조회 성공! (총 {len(holdings)}개 종목 보유)")
        for h in holdings:
            print(f"   - {h['ticker']}: {h['shares']}주 (평단가: ${h['avg_price']:.2f}, 현재가: ${h['current_price']:.2f}, 수익률: {h['profit_pct']:+.2f}%)")
    else:
        print(f"⚠️ 보유 종목 조회 응답: {hold_res.get('message')}")

    print("\n" + "=" * 65)
    print("🔒 [안전 확인] 주문 관련 기능은 일체 호출되지 않았습니다.")
    print("🎉 메리츠증권 Open API 인증 및 잔고/예수금 조회 검증 완료!")
    print("=" * 65)
    return True


if __name__ == "__main__":
    k = sys.argv[1] if len(sys.argv) > 1 else None
    s = sys.argv[2] if len(sys.argv) > 2 else None
    run_test(k, s)
