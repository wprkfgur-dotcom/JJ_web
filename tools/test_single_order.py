"""
단일 해외주식 LOC 주문 테스트 스크립트
SOXL LOC 매수 1주 @ $101.00 주문 전송 및 당일 주문 내역 확인
"""
import os
import sys
import json

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


def main():
    print("=" * 65)
    print("🚀 [메리츠 Open API] 해외주식 실주문 테스트")
    print("   - 종목: SOXL (거래소: AMEX 0066)")
    print("   - 유형: LOC 매수 (종가 체결 지정가)")
    print("   - 수량: 1주")
    print("   - 단가: $101.00")
    print("=" * 65)

    # 1. 실주문 발송 (dry_run=False)
    print("\n[1/2] 메리츠증권으로 LOC 매수 주문 전송 중...")
    res = meritz_client.send_overseas_order(
        symbol="SOXL",
        side="BUY",
        order_type="LOC",
        qty=1,
        price=101.00,
        exchange_code="0066",  # AMEX
        dry_run=False           # 실제 주문 전송!
    )

    print("\n[주문 전송 결과]")
    print(json.dumps(res, indent=2, ensure_ascii=False))

    # 2. 당일 주문 접수 내역 확인
    print("\n[2/2] 당일 주문 내역(Today Orders) 확인 중...")
    today_res = meritz_client.get_today_orders()
    if today_res.get("success"):
        orders = today_res.get("orders", [])
        print(f"✅ 당일 접수된 총 주문 수: {len(orders)}건")
        for o in orders[:5]:
            odno = o.get("odno") or o.get("oder_no")
            symb = o.get("ovrs_stck_symb_iscd") or o.get("iscd")
            side = "매수" if o.get("sll_buy_cls_code") == "02" or o.get("seln_byov_clcd") == "2" else "매도"
            q = o.get("odqt") or o.get("oder_qty")
            p = o.get("ovrs_stck_oder_prc") or o.get("oder_prc")
            print(f"   - 주문번호 {odno}: {symb} {side} {q}주 @ ${p}")
    else:
        print(f"⚠️ 주문 내역 조회 응답: {today_res.get('message')}")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
