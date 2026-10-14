"""
주문 상계 및 퉁치기 엔진 (Order Netting Engine)
매수 LOC 주문과 매도 LOC 주문의 중복 체결 구간을 분석하여,
불필요한 자전거래(스스로 매수/매도 동시 체결)를 사전에 100% 상계(퉁치기)하고
실제 거래가 필요한 순주문(Net Orders)만 산출합니다.
"""
from typing import List, Dict, Any
from strategies.jongjong import safe_round4, round_down, excel_round


def calculate_order_netting(raw_buy_orders: List[Dict[str, Any]], 
                            raw_sell_orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    원시 매수 주문 및 매도 주문 목록을 받아 중복 호가 구간을 상계 처리한 순주문 목록을 반환합니다.
    """
    clean_buys = []
    for b in raw_buy_orders:
        p = float(b.get('price', 0.0))
        q = int(b.get('qty', 0))
        if p > 0 and q > 0:
            clean_buys.append({
                'price': round(p, 2),
                'qty': q,
                'stage': b.get('stage', b.get('호가단계', '매수')),
                'type': b.get('type', b.get('주문유형', 'LOC 매수')),
                'raw': b
            })

    clean_sells = []
    for s in raw_sell_orders:
        p = float(s.get('price', 0.0))
        q = int(s.get('qty', 0))
        if p > 0 and q > 0:
            clean_sells.append({
                'price': round(p, 2),
                'qty': q,
                'stage': s.get('stage', s.get('구분', '목표 매도')),
                'type': s.get('type', s.get('주문유형', 'LOC 매도')),
                'raw': s
            })

    # 매수 또는 매도가 없는 경우 -> 상계 불필요
    if not clean_buys or not clean_sells:
        formatted_sells = []
        accum_s = 0
        sorted_sells = sorted(clean_sells, key=lambda x: x['price'], reverse=True)
        for idx, s in enumerate(sorted_sells):
            accum_s += s['qty']
            formatted_sells.append({
                '구분': s['stage'],
                '주문유형': s['type'],
                '주문단가': f"${s['price']:.2f}",
                '주문수량': f"{s['qty']:,}주",
                '누적수량': f"{accum_s:,}주",
                '예상금액': f"${s['price'] * s['qty']:,.2f}",
                '체결조건': f"종가 ≥ ${s['price']:.2f}",
                '비고': '단방향 주문 (매도)',
                'price': s['price'],
                'qty': s['qty']
            })

        formatted_buys = []
        accum_b = 0
        sorted_buys = sorted(clean_buys, key=lambda x: x['price'], reverse=True)
        for idx, b in enumerate(sorted_buys):
            accum_b += b['qty']
            formatted_buys.append({
                '호가단계': b['stage'],
                '주문유형': b['type'],
                '주문단가': f"${b['price']:.2f}",
                '주문수량': f"{b['qty']:,}주",
                '누적수량': f"{accum_b:,}주",
                '예상금액': f"${b['price'] * b['qty']:,.2f}",
                '체결조건': f"종가 ≤ ${b['price']:.2f}",
                '비고': '단방향 주문 (매수)',
                'price': b['price'],
                'qty': b['qty']
            })

        return {
            'net_sell_orders': formatted_sells,
            'net_buy_orders': formatted_buys,
            'max_offset_qty': 0,
            'is_netted': False,
            'overlap_price_min': None,
            'overlap_price_max': None,
            'summary_text': '단방향 주문(매수 또는 매도만 존재)으로 퉁치기 대상이 없습니다.',
            'raw_sell_orders': clean_sells,
            'raw_buy_orders': clean_buys
        }

    # 매수 최고가와 매도 최저가 비교
    max_buy_price = max(b['price'] for b in clean_buys)
    min_sell_price = min(s['price'] for s in clean_sells)

    if max_buy_price < min_sell_price:
        # 가격 구간이 겹치지 않음
        formatted_sells = []
        accum_s = 0
        sorted_sells = sorted(clean_sells, key=lambda x: x['price'], reverse=True)
        for idx, s in enumerate(sorted_sells):
            accum_s += s['qty']
            formatted_sells.append({
                '구분': s['stage'],
                '주문유형': s['type'],
                '주문단가': f"${s['price']:.2f}",
                '주문수량': f"{s['qty']:,}주",
                '누적수량': f"{accum_s:,}주",
                '예상금액': f"${s['price'] * s['qty']:,.2f}",
                '체결조건': f"종가 ≥ ${s['price']:.2f}",
                '비고': '중복 없음 (정상)',
                'price': s['price'],
                'qty': s['qty']
            })

        formatted_buys = []
        accum_b = 0
        sorted_buys = sorted(clean_buys, key=lambda x: x['price'], reverse=True)
        for idx, b in enumerate(sorted_buys):
            accum_b += b['qty']
            formatted_buys.append({
                '호가단계': b['stage'],
                '주문유형': b['type'],
                '주문단가': f"${b['price']:.2f}",
                '주문수량': f"{b['qty']:,}주",
                '누적수량': f"{accum_b:,}주",
                '예상금액': f"${b['price'] * b['qty']:,.2f}",
                '체결조건': f"종가 ≤ ${b['price']:.2f}",
                '비고': '중복 없음 (정상)',
                'price': b['price'],
                'qty': b['qty']
            })

        return {
            'net_sell_orders': formatted_sells,
            'net_buy_orders': formatted_buys,
            'max_offset_qty': 0,
            'is_netted': False,
            'overlap_price_min': None,
            'overlap_price_max': None,
            'summary_text': f'매수 최고가(${max_buy_price:.2f}) < 매도 최저가(${min_sell_price:.2f})로 중복 구간이 없어 원본 주문이 유지됩니다.',
            'raw_sell_orders': clean_sells,
            'raw_buy_orders': clean_buys
        }

    # 중복 구간 존재 -> 퉁치기(상계) 수행
    overlap_min = min_sell_price
    overlap_max = max_buy_price

    # 모든 관심 가격점 및 경계점 수집
    key_prices = set()
    for b in clean_buys:
        p = b['price']
        key_prices.add(p)
        key_prices.add(round(p - 0.01, 2))
        key_prices.add(round(p + 0.01, 2))
    for s in clean_sells:
        p = s['price']
        key_prices.add(p)
        key_prices.add(round(p - 0.01, 2))
        key_prices.add(round(p + 0.01, 2))

    sorted_prices = sorted(p for p in key_prices if p > 0)

    def gross_buy(price):
        return sum(b['qty'] for b in clean_buys if price <= b['price'] + 1e-4)

    def gross_sell(price):
        return sum(s['qty'] for s in clean_sells if price >= s['price'] - 1e-4)

    price_stats = []
    max_offset = 0
    for p in sorted_prices:
        gb = gross_buy(p)
        gs = gross_sell(p)
        offset = min(gb, gs)
        if offset > max_offset:
            max_offset = offset
        price_stats.append({
            'price': p,
            'gross_buy': gb,
            'gross_sell': gs,
            'net': gb - gs,
            'offset': offset
        })

    # 1. 순 매도 주문 도출: NetSell(p) = gross_sell(p) - gross_buy(p)
    raw_net_sells = []
    prev_net_sell = 0
    for stat in price_stats:
        p = stat['price']
        ns = max(0, -stat['net'])
        if ns > prev_net_sell:
            order_q = ns - prev_net_sell
            raw_net_sells.append({'price': p, 'qty': order_q})
            prev_net_sell = ns

    # 매도는 가격별 내림차순 정렬 (높은 가격 -> 낮은 가격)
    raw_net_sells.sort(key=lambda x: x['price'], reverse=True)

    # 2. 순 매수 주문 도출: NetBuy(p) = gross_buy(p) - gross_sell(p)
    raw_net_buys = []
    prev_net_buy = 0
    for stat in reversed(price_stats):
        p = stat['price']
        nb = max(0, stat['net'])
        if nb > prev_net_buy:
            order_q = nb - prev_net_buy
            raw_net_buys.append({'price': p, 'qty': order_q})
            prev_net_buy = nb

    # 포맷팅
    formatted_net_sells = []
    accum_s = 0
    for idx, s in enumerate(raw_net_sells):
        accum_s += s['qty']
        formatted_net_sells.append({
            '구분': f"{idx+1}차 순매도 (퉁치기)",
            '주문유형': 'LOC 매도',
            '주문단가': f"${s['price']:.2f}",
            '주문수량': f"{s['qty']:,}주",
            '누적수량': f"{accum_s:,}주",
            '예상금액': f"${s['price'] * s['qty']:,.2f}",
            '체결조건': f"종가 ≥ ${s['price']:.2f}",
            '비고': "자전거래 상계 후 잔여 매도",
            'price': s['price'],
            'qty': s['qty']
        })

    formatted_net_buys = []
    accum_b = 0
    for idx, b in enumerate(raw_net_buys):
        accum_b += b['qty']
        formatted_net_buys.append({
            '호가단계': f"{idx+1}차 순매수 (퉁치기)",
            '주문유형': 'LOC 매수',
            '주문단가': f"${b['price']:.2f}",
            '주문수량': f"{b['qty']:,}주",
            '누적수량': f"{accum_b:,}주",
            '예상금액': f"${b['price'] * b['qty']:,.2f}",
            '체결조건': f"종가 ≤ ${b['price']:.2f}",
            '비고': "자전거래 상계 후 순매수",
            'price': b['price'],
            'qty': b['qty']
        })

    summary = (
        f"⚡ [퉁치기 적용] 매수/매도 중복 호가 구간(${overlap_min:.2f} ~ ${overlap_max:.2f})에서 "
        f"최대 {max_offset:,}주의 불필요한 자전거래를 상계하여 순주문표로 재구성했습니다."
    )

    return {
        'net_sell_orders': formatted_net_sells,
        'net_buy_orders': formatted_net_buys,
        'max_offset_qty': max_offset,
        'is_netted': True,
        'overlap_price_min': overlap_min,
        'overlap_price_max': overlap_max,
        'summary_text': summary,
        'raw_sell_orders': clean_sells,
        'raw_buy_orders': clean_buys
    }


def generate_jongjong_orders(
    unsold_lots: List[Dict[str, Any]],
    yest_close: float,
    p_budget: float,
    mode: str = 'Normal',
    C2: float = 0.128,
    C3: float = -0.17,
    C4: int = 6,
    C6: float = 1.0,
    target_yield: float = 0.0275
) -> Dict[str, Any]:
    """
    종종이 실매매 주문표 생성 엔진 (퉁치기 및 슬롯 기반 1:1 매도 완벽 구현)
    - 매도는 부분 매도나 분할 슬라이싱 없이 미매도 슬롯당 최대 1개 주문 (미매도 슬롯 수와 매도 주문 수가 1:1 일치)
    - 퉁치기 슬롯: BB3 이하 목표가를 가진 슬롯 중 최저 목표가 슬롯(AU3, AV3)
      -> 맥스 +12.8%(BB3)에 전량 매도 주문 (12.8% 급등 시 퉁치기 없이 전량 청산)
    - 나머지 미매도 슬롯: 각자의 고유 목표가(U)에 매도 주문
    - 순 매수 주문:
      1차 매수: AU3 - 0.01 (AV3주 상계 순매수)
      2차 매수: yest_close * (1 - C2) (하단 잔여 순매수: int(AU1/AY3) - int(AU1/AY2))
      3차 매수: yest_close * (1 + C3) (폭락 대비 매수)
    """
    AU1 = max(0.0, float(p_budget))
    AU2 = float(yest_close)
    is_normal = (mode == 'Normal')

    moc_lots = [l for l in unsold_lots if l.get('hold_days', 0) >= 10]
    loc_lots = [l for l in unsold_lots if l.get('hold_days', 0) < 10]

    BB3 = excel_round(AU2 * (1.0 + C2), 2)

    AU3, AV3, tung_lot = None, 0, None
    if loc_lots:
        min_u = min(l['U'] for l in loc_lots)
        if is_normal and BB3 >= min_u:
            AU3 = min_u
            for l in loc_lots:
                if l['U'] == min_u:
                    tung_lot = l
                    AV3 = l['R']
                    break

    # 1. 매도 주문 생성 (슬롯 단위 및 퉁치기 초과분 정밀 분할)
    formatted_sells = []
    accum_s = 0

    # (1) MOC 만기 매도
    for l in moc_lots:
        q = l['R']
        accum_s += q
        d_str = l.get('date', '만기')
        formatted_sells.append({
            '구분': f"MOC 청산 ({d_str} 10일 만기)",
            '주문유형': 'MOC 매도',
            '주문단가': f"${AU2:.2f}",
            '주문수량': f"{q:,}주",
            '누적수량': f"{accum_s:,}주",
            '예상금액': f"${AU2 * q:,.2f}",
            '체결조건': "10영업일 보유 만기 종가 전량 청산",
            '비고': "MOC 종가 시장가 청산",
            'price': AU2,
            'qty': q
        })

    # (2) LOC 목표 매도 (퉁치기 슬롯 및 일반 슬롯)
    if tung_lot is not None:
        # 하루 매수예정금(AU1)으로 AU3(목표가)에서 매수 가능한 최대 수량 산출
        buyable_at_target = int(AU1 / AU3) if AU3 > 0 else 0

        # 상계 수량과 예산 초과 수량 분리
        if AV3 > buyable_at_target and buyable_at_target > 0:
            excess_q = AV3 - buyable_at_target
            q_net = buyable_at_target

            # 1) 맥스 상한선(BB3)에 상계 수량 매도 주문
            accum_s += q_net
            formatted_sells.append({
                '구분': '맥스 익절 매도 (퉁치기 로트)',
                '주문유형': 'LOC 매도',
                '주문단가': f"${BB3:.2f}",
                '주문수량': f"{q_net:,}주",
                '누적수량': f"{accum_s:,}주",
                '예상금액': f"${BB3 * q_net:,.2f}",
                '체결조건': f"종가 ≥ ${BB3:.2f} (+{C2*100:.1f}%)",
                '비고': f"상계 수량 상한선 청산 ({AV3}주 중 {q_net}주)",
                'price': BB3,
                'qty': q_net
            })

            # 2) 원래 목표가(AU3)에 당일 매수예산 초과분 순매도 주문 (수익 실현)
            accum_s += excess_q
            pct_u = (AU3 / AU2 - 1.0) * 100.0
            formatted_sells.append({
                '구분': f"목표 익절 매도 ({tung_lot.get('date', '')} 로트)",
                '주문유형': 'LOC 매도',
                '주문단가': f"${AU3:.2f}",
                '주문수량': f"{excess_q:,}주",
                '누적수량': f"{accum_s:,}주",
                '예상금액': f"${AU3 * excess_q:,.2f}",
                '체결조건': f"종가 ≥ ${AU3:.2f} ({pct_u:+.1f}%)",
                '비고': f"매수 예산 초과분 실매도 익절 ({AV3}주 중 {excess_q}주)",
                'price': AU3,
                'qty': excess_q
            })
        else:
            # 보유량이 매수가능수량 이하인 경우 전량을 맥스 상한선(BB3)에 매도
            q = tung_lot['R']
            accum_s += q
            formatted_sells.append({
                '구분': '맥스 익절 매도 (퉁치기 로트)',
                '주문유형': 'LOC 매도',
                '주문단가': f"${BB3:.2f}",
                '주문수량': f"{q:,}주",
                '누적수량': f"{accum_s:,}주",
                '예상금액': f"${BB3 * q:,.2f}",
                '체결조건': f"종가 ≥ ${BB3:.2f} (+{C2*100:.1f}%)",
                '비고': "12.8% 상한 도달 시 전량 청산 (퉁치기 미발생)",
                'price': BB3,
                'qty': q
            })

        # 나머지 슬롯들은 원래 목표가(U)에 매도
        for l in loc_lots:
            if l is not tung_lot:
                q = l['R']
                accum_s += q
                pct = (l['U'] / AU2 - 1.0) * 100.0
                d_str = l.get('date', '')
                formatted_sells.append({
                    '구분': f"목표 익절 매도 ({d_str} 로트)",
                    '주문유형': 'LOC 매도',
                    '주문단가': f"${l['U']:.2f}",
                    '주문수량': f"{q:,}주",
                    '누적수량': f"{accum_s:,}주",
                    '예상금액': f"${l['U'] * q:,.2f}",
                    '체결조건': f"종가 ≥ ${l['U']:.2f} ({pct:+.1f}%)",
                    '비고': "개별 슬롯 목표가 도달 시 전량 매도",
                    'price': l['U'],
                    'qty': q
                })
    else:
        for l in loc_lots:
            q = l['R']
            accum_s += q
            pct = (l['U'] / AU2 - 1.0) * 100.0
            d_str = l.get('date', '')
            formatted_sells.append({
                '구분': f"목표 익절 매도 ({d_str} 로트)",
                '주문유형': 'LOC 매도',
                '주문단가': f"${l['U']:.2f}",
                '주문수량': f"{q:,}주",
                '누적수량': f"{accum_s:,}주",
                '예상금액': f"${l['U'] * q:,.2f}",
                '체결조건': f"종가 ≥ ${l['U']:.2f} ({pct:+.1f}%)",
                '비고': "개별 슬롯 목표가 도달 시 전량 매도",
                'price': l['U'],
                'qty': q
            })

    # 매도 주문 가격별 내림차순 정렬 (높은 가격 -> 낮은 가격 순서, 최저 목표가가 맨 아래로 위치)
    formatted_sells.sort(key=lambda x: float(x.get('price', 0.0)), reverse=True)
    accum_s = 0
    for s in formatted_sells:
        accum_s += int(s.get('qty', 0))
        s['누적수량'] = f"{accum_s:,}주"

    # 2. 매수 주문 생성
    formatted_buys = []
    accum_b = 0

    if AU1 > 0:
        if tung_lot is not None and is_normal:
            buyable_at_target = int(AU1 / AU3) if AU3 > 0 else 0
            primary_buy_qty = min(AV3, buyable_at_target) if buyable_at_target > 0 else AV3

            # 1차 매수: AU3 - 0.01
            AY2 = safe_round4(AU3 - 0.01)
            pct1 = (AY2 / AU2 - 1.0) * 100.0
            accum_b += primary_buy_qty
            formatted_buys.append({
                '호가단계': '1차 순매수 (퉁치기 상계)',
                '주문유형': 'LOC 매수',
                '주문단가': f"${AY2:.2f}",
                '주문수량': f"{primary_buy_qty:,}주",
                '누적수량': f"{accum_b:,}주",
                '예상금액': f"${AY2 * primary_buy_qty:,.2f}",
                '체결조건': f"종가 ≤ ${AY2:.2f} ({pct1:+.1f}%)",
                '비고': f"목표가(${AU3:.2f}) 하단 1차 상계 순매수 ({primary_buy_qty}주)",
                'price': AY2,
                'qty': primary_buy_qty
            })

            # 2차 추가 매수: BE3
            add_qty = AV3 - primary_buy_qty
            if add_qty > 0 and AV3 > 0:
                BE3 = round(round_down(AU1 / (AV3 + 1.0), 2) + 0.01, 2)
                if BE3 < AY2:
                    accum_b += add_qty
                    pct_be3 = (BE3 / AU2 - 1.0) * 100.0
                    formatted_buys.append({
                        '호가단계': '2차 순매수 (예산 소진)',
                        '주문유형': 'LOC 매수',
                        '주문단가': f"${BE3:.2f}",
                        '주문수량': f"{add_qty:,}주",
                        '누적수량': f"{accum_b:,}주",
                        '예상금액': f"${BE3 * add_qty:,.2f}",
                        '체결조건': f"종가 ≤ ${BE3:.2f} ({pct_be3:+.1f}%)",
                        '비고': f"단가 하락 시 하루 거래금액 100% 소진 추가 매수 (+{add_qty}주)",
                        'price': BE3,
                        'qty': add_qty
                    })

            # 3차 매수: 하단 밴드 (-12.8%)
            AY3_raw = AU2 * (1.0 - C2)
            AY3 = excel_round(AY3_raw, 2)
            total_at_ay3 = int(AU1 / AY3_raw) if AY3_raw > 0 else 0
            q_band = max(0, total_at_ay3 - max(accum_b, AV3))
            if q_band > 0:
                accum_b += q_band
                formatted_buys.append({
                    '호가단계': f"{len(formatted_buys)+1}차 순매수 (-12.8% 하단)",
                    '주문유형': 'LOC 매수',
                    '주문단가': f"${AY3:.2f}",
                    '주문수량': f"{q_band:,}주",
                    '누적수량': f"{accum_b:,}주",
                    '예상금액': f"${AY3 * q_band:,.2f}",
                    '체결조건': f"종가 ≤ ${AY3:.2f} (-{C2*100:.1f}%)",
                    '비고': f"하단 밴드 잔여 순매수 (총 {total_at_ay3}주 채움)",
                    'price': AY3,
                    'qty': q_band
                })

            # 4차 매수: 폭락장 대비 (-17.0%)
            BE4_raw = AU2 * (1.0 + C3)
            BE4 = excel_round(BE4_raw, 2)
            BF4 = excel_round(AU1 / BE4_raw, 0) if BE4_raw > 0 else 0
            if BF4 > 0:
                accum_b += BF4
                formatted_buys.append({
                    '호가단계': f"{len(formatted_buys)+1}차 순매수 (-17.0% 폭락 대비)",
                    '주문유형': 'LOC 매수',
                    '주문단가': f"${BE4:.2f}",
                    '주문수량': f"{BF4:,}주",
                    '누적수량': f"{accum_b:,}주",
                    '예상금액': f"${BE4 * BF4:,.2f}",
                    '체결조건': f"종가 ≤ ${BE4:.2f} ({C3*100:.1f}%)",
                    '비고': "폭락장 대비 1회분 추가 LOC 매수",
                    'price': float(BE4),
                    'qty': int(BF4)
                })
        else:
            # 퉁치기 없는 일반 분할 매수
            is_riskoff = (mode == 'Riskoff')
            a_val = C2 if is_normal else (-0.055 if is_riskoff else 0.0)
            if is_normal:
                BB3 = excel_round(AU2 * (1.0 + C2), 2)
                AY2 = round(BB3 - 0.02, 2)
                AY3_raw = AU2 * (1.0 - C2)
                AY3 = round(round_down(AY3_raw, 2) - 0.01, 2)
            else:
                AY2 = safe_round4(AU2 * (1.0 + a_val) - 0.01)
                AY3 = safe_round4(AU2 * (1.0 - C2))

            AZ2 = int(AU1 / AY2) if AY2 > 0 else 0

            AY4 = C4 - 1
            ay_list = [AY2]
            if AY4 - 1 > 0:
                for i_seq in range(AY4 - 1):
                    if AY4 - 2 == 0:
                        ay_list.append(None)
                    else:
                        denom = AY3 + ((AY4 - 2.0 - i_seq) / (AY4 - 2.0)) ** C6 * (AY2 - AY3)
                        val = round_down(denom, 2) if (AU1 > 0 and denom > 0) else None
                        ay_list.append(val)

            az_list = [AZ2]
            for k in range(1, len(ay_list)):
                if ay_list[k] is None or ay_list[k-1] is None or ay_list[k] <= 0 or ay_list[k-1] <= 0:
                    az_list.append(0)
                else:
                    diff = int(AU1 / ay_list[k]) - int(AU1 / ay_list[k-1])
                    az_list.append(max(0, diff))

            step_idx = 1
            for k in range(len(ay_list)):
                p = ay_list[k]
                q = az_list[k]
                if p is not None and q > 0:
                    accum_b += q
                    pct = (p / AU2 - 1.0) * 100.0
                    formatted_buys.append({
                        '호가단계': f"{step_idx}차 분할매수",
                        '주문유형': 'LOC 매수',
                        '주문단가': f"${p:.2f}",
                        '주문수량': f"{q:,}주",
                        '누적수량': f"{accum_b:,}주",
                        '예상금액': f"${p * q:,.2f}",
                        '체결조건': f"종가 ≤ ${p:.2f} ({pct:+.1f}%)",
                        '비고': "일반 분할 LOC 매수",
                        'price': float(p),
                        'qty': int(q)
                    })
                    step_idx += 1

            # 폭락장 대비 매수 (-17.0%)
            BE4_raw = AU2 * (1.0 + C3)
            BE4 = excel_round(BE4_raw, 2)
            BF4 = excel_round(AU1 / BE4_raw, 0) if BE4_raw > 0 else 0
            if BF4 > 0:
                accum_b += BF4
                formatted_buys.append({
                    '호가단계': f"{step_idx}차 매수 (폭락 대비 -17.0%)",
                    '주문유형': 'LOC 매수',
                    '주문단가': f"${BE4:.2f}",
                    '주문수량': f"{BF4:,}주",
                    '누적수량': f"{accum_b:,}주",
                    '예상금액': f"${BE4 * BF4:,.2f}",
                    '체결조건': f"종가 ≤ ${BE4:.2f} ({C3*100:.1f}%)",
                    '비고': "폭락장 대비 1회분 추가 LOC 매수",
                    'price': float(BE4),
                    'qty': int(BF4)
                })

    is_netted = (tung_lot is not None)
    max_offset_qty = AV3 if is_netted else 0
    if is_netted:
        summary_text = (
            f"⚡ [종종이 퉁치기 적용] 최저 목표가 슬롯({tung_lot.get('date', '')}, {AV3:,}주)을 당일 매수와 상계하여 "
            f"맥스 익절(+{C2*100:.1f}%) 매도 1개 및 순매수 3단계로 재구성했습니다 (총 매도 주문: {len(formatted_sells)}개)."
        )
    else:
        summary_text = f"미매도 슬롯({len(formatted_sells)}개)에 대한 개별 목표가 매도 주문이 유지됩니다."

    return {
        'net_sell_orders': formatted_sells,
        'net_buy_orders': formatted_buys,
        'is_netted': is_netted,
        'max_offset_qty': max_offset_qty,
        'overlap_price_min': round(AU2 * (1.0 - C2), 2) if is_netted else None,
        'overlap_price_max': BB3 if is_netted else None,
        'summary_text': summary_text
    }
