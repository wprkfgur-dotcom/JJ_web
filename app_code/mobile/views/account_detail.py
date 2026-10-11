"""
=====================================================================
종종이 & 무한매수 주식 매매 시스템 - 계좌 상세 뷰 (Account Detail View)
=====================================================================
1. 계좌 기본 정보 & KPI 카드 (평가자산, 총수익률, 위기준비금, 실가동시드, 하루예산, 예수금)
2. 매입 조각(슬롯) 현황 (미매도 조각별 수량, 매입단가, 손익률, 익절목표가)
3. 금일 매수·매도 주문표 (직관적인 수량 중심 UI 및 밴드 예약)
4. 실시간 시세 조회 및 일일 정산 입력 폼 (매도 자동 체결 및 정산 마감/다음 거래일)
5. 최근 거래 내역 (슬롯 단위 라이프사이클 4대 섹션 구분 테이블 및 인라인 수정 버튼)
"""

from datetime import datetime
import flet as ft

from core.data import get_stock_price_for_date, get_exact_stock_price_for_date
from core.strategy_registry import is_vr, is_infinite, is_jongjong
from core.trade_history import build_trade_rows
from mobile.theme import (
    BG_DARK, SURFACE_CARD, BORDER_COLOR, ACCENT_BLUE,
    PROFIT_GREEN, LOSS_RED, RESERVE_AMBER, VR_PURPLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)
from mobile.helpers import (
    show_toast, compute_suggested_trades, extract_pct_str,
)
from mobile.widgets import (
    build_card, build_section_header, build_badge,
)


def build_account_detail_view(app, acc: dict, dtl: dict) -> ft.Control:
    """계좌 상세 화면을 생성합니다."""
    acc_id = acc['id']
    name = acc.get('name', '')
    ticker = acc.get('ticker', 'SOXL')
    strat = acc.get('strategy', '종종이 기본전략')
    curr_d = dtl.get('current_date', '')
    target_date = dtl.get('target_order_date', '')

    asset = dtl.get('current_asset', 0.0)
    ret_pct = dtl.get('total_return_pct', 0.0)
    profit = dtl.get('total_profit', 0.0)
    cash = dtl.get('current_cash', 0.0)
    hold = dtl.get('current_hold', 0)
    ak_val = dtl.get('ak_val', 0.0)
    ar_val = dtl.get('ar_val', 0.0)
    budget = dtl.get('daily_budget', 0.0)
    mode = dtl.get('mode', 'Normal')
    latest_price = dtl.get('current_price', 0.0)

    # 1. 계좌 기본 정보 & KPI 카드
    # -------------------------------------------------------------
    basic_info_card = build_card(
        elevation=2,
        radius=14,
        padding=16,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Row([
                                    ft.Text(name, size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    build_badge(ticker, color=ACCENT_BLUE),
                                ], spacing=6),
                                ft.Text(
                                    f"{strat} • {mode} (2주 리밸런싱)" if is_vr(strat) else (
                                        f"{strat} • {mode}" if is_infinite(strat) else f"{strat} • {mode} 모드"
                                    ),
                                    size=11,
                                    color=VR_PURPLE if is_vr(strat) else (ACCENT_BLUE if is_infinite(strat) else TEXT_SECONDARY)
                                )
                            ],
                            spacing=2
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START
                ),
                    ft.Container(height=6),
                    ft.Row(
                        controls=[
                            ft.Column([
                                ft.Text("평가 자산", size=11, color=TEXT_MUTED),
                                ft.Text(f"${asset:,.2f}", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                            ], spacing=1),
                            ft.Column([
                                ft.Text("총 수익률", size=11, color=TEXT_MUTED),
                                ft.Text(f"{ret_pct:+.2f}% ({profit:+,.0f}$)", size=18, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN if profit >= 0 else LOSS_RED)
                            ], horizontal_alignment=ft.CrossAxisAlignment.END, spacing=1)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Container(height=4),
                    ft.Divider(color=BORDER_COLOR, height=1),
                    ft.Container(height=4),
                    ft.Row(
                        controls=[
                            ft.Column([
                                ft.Text("2주 사이클" if is_vr(strat) else ("운용 상태" if is_infinite(strat) else "위기준비금 (AK)"), size=10, color=VR_PURPLE if is_vr(strat) else (ACCENT_BLUE if is_infinite(strat) else RESERVE_AMBER)),
                                ft.Text(f"{mode}" if (is_vr(strat) or is_infinite(strat)) else f"${ak_val:,.0f}", size=12 if (is_vr(strat) or is_infinite(strat)) else 14, weight=ft.FontWeight.BOLD, color=VR_PURPLE if is_vr(strat) else (ACCENT_BLUE if is_infinite(strat) else RESERVE_AMBER))
                            ], spacing=1),
                            ft.Column([
                                ft.Text("보유 수량" if (is_vr(strat) or is_infinite(strat)) else "실가동시드 (AR)", size=10, color=ACCENT_BLUE),
                                ft.Text(f"{hold:,}주" if (is_vr(strat) or is_infinite(strat)) else f"${ar_val:,.0f}", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                            ], spacing=1),
                            ft.Column([
                                ft.Text("가용 Pool 예산" if is_vr(strat) else ("1회 매수 예산" if is_infinite(strat) else "하루 배분 예산"), size=10, color=TEXT_SECONDARY),
                                ft.Text(f"${budget:,.2f}", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                            ], spacing=1),
                            ft.Column([
                                ft.Text("예수금 (Pool)" if is_vr(strat) else "예수금", size=10, color=TEXT_SECONDARY),
                                ft.Text(f"${cash:,.0f}", size=14, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN)
                            ], spacing=1),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ]
            )
        )

    # -------------------------------------------------------------
    # 2. 매입 정보 (전체 몇 조각 매입했고, 각각의 수량/매입가/손실비율)
    # -------------------------------------------------------------
    df_res = dtl.get('df_res')
    unsold_lots = []
    if df_res is not None and not df_res.empty:
        unsold_df = df_res[(df_res['R'] > 0) & (~df_res['Sold'])]
        for idx, r_row in unsold_df.iterrows():
            unsold_lots.append(r_row)

    total_pieces = len(unsold_lots)
    lot_cards = []

    if total_pieces > 0:
        for i, lot in enumerate(unsold_lots):
            r_q = int(lot['R'])
            bp = float(lot.get('BuyPrice', lot['Close']))
            d_str = str(lot['Date'])[:10]
            cur_p = latest_price if latest_price > 0 else bp
            ret_loss = (cur_p / bp - 1.0) * 100.0
            target_u = float(lot['U']) if lot.get('U') is not None else bp * 1.0275
            invest_amt = float(lot.get('S', bp * r_q))

            loss_color = PROFIT_GREEN if ret_loss >= 0 else LOSS_RED

            l_card = ft.Container(
                bgcolor=SURFACE_CARD,
                border=ft.Border.all(1, ft.Colors.with_opacity(0.3, loss_color)),
                border_radius=10,
                padding=12,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Row([
                                    ft.Container(
                                        content=ft.Text(f"조각 #{i+1}", size=11, weight=ft.FontWeight.BOLD, color=ACCENT_BLUE),
                                        bgcolor=ft.Colors.with_opacity(0.15, ACCENT_BLUE),
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                        border_radius=4
                                    ),
                                    ft.Text(f"매입일: {d_str}", size=12, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                                ], spacing=6),
                                ft.Text(f"현재 손익률: {ret_loss:+.2f}%", size=12, weight=ft.FontWeight.BOLD, color=loss_color)
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        ft.Container(height=4),
                        ft.Row(
                            controls=[
                                ft.Column([
                                    ft.Text("매입 수량", size=10, color=TEXT_MUTED),
                                    ft.Text(f"{r_q:,}주", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                                ], spacing=1),
                                ft.Column([
                                    ft.Text("매입 단가", size=10, color=TEXT_MUTED),
                                    ft.Text(f"${bp:.2f}", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                                ], spacing=1),
                                ft.Column([
                                    ft.Text("매입 총액", size=10, color=TEXT_MUTED),
                                    ft.Text(f"${invest_amt:,.2f}", size=13, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY)
                                ], spacing=1),
                                ft.Column([
                                    ft.Text("익절 목표가", size=10, color=TEXT_MUTED),
                                    ft.Text(f"${target_u:.2f}", size=14, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN)
                                ], spacing=1),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        )
                    ],
                    spacing=2
                )
            )
            lot_cards.append(l_card)
    else:
        lot_cards.append(
            ft.Container(
                bgcolor=SURFACE_CARD,
                border=ft.Border.all(1, BORDER_COLOR),
                border_radius=10,
                padding=16,
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=PROFIT_GREEN, size=20),
                        ft.Text("현재 보유 중인 매입 조각이 없습니다. (100% 현금 대기 중)", size=12, color=TEXT_SECONDARY)
                    ],
                    spacing=8
                )
            )
        )

    if is_vr(strat):
        holdings_section = ft.Container(
            bgcolor=SURFACE_CARD,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, VR_PURPLE)),
            border_radius=12,
            padding=14,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.AUTO_AWESOME, color=VR_PURPLE, size=18),
                        ft.Text("VR 5.0 밸류리밸런싱 2주 사이클 안내", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=6),
                    ft.Text(
                        f"현재 보유: {hold:,}주 (평가액: ${hold*latest_price:,.2f}) • 예수금(Pool): ${cash:,.2f}\n"
                        f"2주(10거래일) 동안 아래의 예약 주문표를 증권사에 기간예약 주문으로 걸어두세요. "
                        f"주가가 밴드를 이탈할 때만 자동 매매되어 밴드 안으로 복귀합니다.",
                        size=11.5, color=TEXT_SECONDARY
                    )
                ],
                spacing=6
            )
        )
    elif is_infinite(strat):
        avg_p = dtl.get('avg_price', 0.0)
        eval_amt = hold * latest_price
        ret_loss = ((latest_price / avg_p - 1.0) * 100.0) if avg_p > 0 else 0.0
        loss_color = PROFIT_GREEN if ret_loss >= 0 else LOSS_RED
        holdings_section = ft.Container(
            bgcolor=SURFACE_CARD,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ACCENT_BLUE)),
            border_radius=12,
            padding=14,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.ALL_INCLUSIVE, color=ACCENT_BLUE, size=18),
                        ft.Text("무한매수법 v4.0 포지션 현황", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=6),
                    ft.Row([
                        ft.Column([
                            ft.Text("보유 수량", size=10, color=TEXT_MUTED),
                            ft.Text(f"{hold:,}주", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ], spacing=1),
                        ft.Column([
                            ft.Text("매입 평단가", size=10, color=TEXT_MUTED),
                            ft.Text(f"${avg_p:.2f}" if avg_p > 0 else "-", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ], spacing=1),
                        ft.Column([
                            ft.Text("현재 평가액", size=10, color=TEXT_MUTED),
                            ft.Text(f"${eval_amt:,.2f}", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ], spacing=1),
                        ft.Column([
                            ft.Text("평가 손익률", size=10, color=TEXT_MUTED),
                            ft.Text(f"{ret_loss:+.2f}%" if hold > 0 else "-", size=14, weight=ft.FontWeight.BOLD, color=loss_color)
                        ], spacing=1),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text(
                        f"현재 운용 모드: {mode} • 40분할 원칙에 따라 매일 산출되는 LOC 주문을 접수합니다.",
                        size=11, color=TEXT_SECONDARY
                    )
                ],
                spacing=8
            )
        )
    else:
        holdings_section = ft.Column(
            controls=[
                build_section_header(
                    title="매입 조각 현황",
                    icon=ft.Icons.LAYERS_OUTLINED,
                    title_size=14,
                    action=ft.Text(f"총 {total_pieces}조각 보유 중 ({hold:,}주)", size=12, color=ACCENT_BLUE, weight=ft.FontWeight.BOLD),
                ),
                *lot_cards
            ],
            spacing=8
        )

    # -------------------------------------------------------------
    # 3. 금일 매수·매도 주문표 (간결하고 직관적인 수량 중심 UI)
    # -------------------------------------------------------------
    sell_orders = list(dtl.get('sell_orders', []))
    buy_orders = list(dtl.get('buy_orders', []))

    def _extract_order_price(o):
        p = o.get('price')
        if p is not None:
            try:
                return float(p)
            except (ValueError, TypeError):
                pass
        raw = str(o.get('주문단가', '')).replace('$', '').replace(',', '').strip()
        try:
            return float(raw)
        except (ValueError, TypeError):
            return 0.0

    # VR 전략의 밴드 예약 순서를 제외하고는 매도/매수 주문을 가격별 내림차순(높은 가격 -> 낮은 가격)으로 일관 정렬
    if not is_vr(strat):
        sell_orders = sorted(sell_orders, key=_extract_order_price, reverse=True)
        buy_orders = sorted(buy_orders, key=_extract_order_price, reverse=True)

    total_sell_qty = 0
    for s in sell_orders:
        raw_q = str(s.get('주문수량', s.get('qty', '0'))).replace('주', '').replace(',', '').strip()
        try:
            total_sell_qty += int(raw_q)
        except Exception:
            pass

    total_buy_qty = 0
    for b in buy_orders:
        raw_q = str(b.get('주문수량', b.get('qty', '0'))).replace('주', '').replace(',', '').strip()
        try:
            total_buy_qty += int(raw_q)
        except Exception:
            pass

    # 3-1. 매도 주문 박스 (얼마에 몇 주 걸건지 + 변동률만 심플 표시)
    sell_items = []
    ref_p = latest_price if latest_price > 0 else 142.29
    if sell_orders:
        for s in sell_orders:
            price = str(s.get('주문단가', '$0.00'))
            qty = str(s.get('주문수량', s.get('qty', '0'))).replace('주', '').replace(',', '').strip()
            pct_str = extract_pct_str(s, ref_p)

            row = ft.Container(
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
                bgcolor=ft.Colors.with_opacity(0.06, LOSS_RED),
                border_radius=8,
                content=ft.Row(
                    controls=[
                        ft.Row([
                            ft.Text(price, size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ft.Text(pct_str, size=13, weight=ft.FontWeight.W_600, color=LOSS_RED if '-' in pct_str else PROFIT_GREEN) if pct_str else ft.Container(),
                        ], spacing=6),
                        ft.Text(f"{qty}주", size=15, weight=ft.FontWeight.BOLD, color=LOSS_RED)
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                )
            )
            sell_items.append(row)
    else:
        sell_items.append(
            ft.Container(
                padding=ft.Padding.symmetric(vertical=8, horizontal=8),
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=TEXT_MUTED, size=15),
                        ft.Text("체결 대상 매도 주문 없음 (보유 홀딩)", size=12, color=TEXT_MUTED)
                    ],
                    spacing=6
                )
            )
        )

    sell_box = ft.Container(
        bgcolor=SURFACE_CARD,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, LOSS_RED)),
        border_radius=12,
        padding=12,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row([
                            ft.Icon(ft.Icons.ARROW_UPWARD, color=LOSS_RED, size=16),
                            ft.Text("🔴 2주 매도 예약 (상단 밴드)" if is_vr(strat) else "🔴 매도 주문", size=13, weight=ft.FontWeight.BOLD, color=LOSS_RED),
                        ], spacing=6),
                        ft.Container(
                            content=ft.Text(f"총 {total_sell_qty:,}주" if total_sell_qty > 0 else "0건", size=10, color=LOSS_RED, weight=ft.FontWeight.BOLD),
                            bgcolor=ft.Colors.with_opacity(0.15, LOSS_RED),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            border_radius=4
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(color=BORDER_COLOR, height=1),
                *sell_items
            ],
            spacing=6
        )
    )

    # 3-2. 매수 주문 박스 (얼마에 몇 주 걸건지 + 변동률만 심플 표시)
    buy_items = []
    if buy_orders:
        for b in buy_orders:
            price = str(b.get('주문단가', '$0.00'))
            qty = str(b.get('주문수량', b.get('qty', '0'))).replace('주', '').replace(',', '').strip()
            pct_str = extract_pct_str(b, ref_p)

            row = ft.Container(
                padding=ft.Padding.symmetric(vertical=8, horizontal=10),
                bgcolor=ft.Colors.with_opacity(0.06, PROFIT_GREEN),
                border_radius=8,
                content=ft.Row(
                    controls=[
                        ft.Row([
                            ft.Text(price, size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ft.Text(pct_str, size=13, weight=ft.FontWeight.W_600, color=LOSS_RED if '-' in pct_str else PROFIT_GREEN) if pct_str else ft.Container(),
                        ], spacing=6),
                        ft.Text(f"{qty}주", size=15, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN)
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                )
            )
            buy_items.append(row)
    else:
        buy_items.append(
            ft.Container(
                padding=ft.Padding.symmetric(vertical=8, horizontal=8),
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=TEXT_MUTED, size=15),
                        ft.Text("체결 대상 매수 주문 없음", size=12, color=TEXT_MUTED)
                    ],
                    spacing=6
                )
            )
        )

    buy_box = ft.Container(
        bgcolor=SURFACE_CARD,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, PROFIT_GREEN)),
        border_radius=12,
        padding=12,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row([
                            ft.Icon(ft.Icons.ARROW_DOWNWARD, color=PROFIT_GREEN, size=16),
                            ft.Text("🟢 2주 매수 예약 (하단 밴드)" if is_vr(strat) else "🟢 매수 주문", size=13, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN),
                        ], spacing=6),
                        ft.Container(
                            content=ft.Text(f"총 {total_buy_qty:,}주" if total_buy_qty > 0 else "0건", size=10, color=PROFIT_GREEN, weight=ft.FontWeight.BOLD),
                            bgcolor=ft.Colors.with_opacity(0.15, PROFIT_GREEN),
                            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                            border_radius=4
                        )
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(color=BORDER_COLOR, height=1),
                *buy_items
            ],
            spacing=6
        )
    )

    # 주문표 섹션 모드 배지 (Normal/Safe/Riskoff 구분)
    order_mode_color = "#3B82F6" if mode == 'Normal' else ("#EAB308" if mode == 'Safe' else "#EF4444")
    order_mode_badge = ft.Container(
        content=ft.Row([
            ft.Container(width=6, height=6, border_radius=3, bgcolor=order_mode_color),
            ft.Text(f"{mode} 모드", size=11, weight=ft.FontWeight.BOLD, color=order_mode_color),
        ], spacing=5, alignment=ft.MainAxisAlignment.CENTER),
        bgcolor=ft.Colors.with_opacity(0.15, order_mode_color),
        padding=ft.Padding.symmetric(horizontal=8, vertical=3.5),
        border_radius=6,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, order_mode_color))
    )

    orders_section = ft.Column(
        controls=[
            build_section_header(
                title=f"금일 매수·매도 주문표 ({target_date})",
                icon=ft.Icons.RECEIPT_LONG,
                title_size=14,
                action=order_mode_badge,
            ),
            sell_box,
            buy_box
        ],
        spacing=8
    )

    # -------------------------------------------------------------
    # 4. 실시간 시세 조회 및 일일 정산 입력 폼
    # -------------------------------------------------------------
    records = acc.get('trade_records', [])
    fallback_p = latest_price
    if fallback_p <= 0 and records:
        fallback_p = float(records[-1].get('Close', 142.50))
    elif fallback_p <= 0:
        fallback_p = 142.50

    default_settle_date = curr_d or target_date or datetime.now().strftime('%Y-%m-%d')

    unsold_lots_data = dtl.get('unsold_lots', [])
    if not unsold_lots_data and records:
        unsold_lots_data = [r for r in records if int(r.get('R', 0)) > 0 and not bool(r.get('Sold', False))]
    strat_name = acc.get('strategy', '')
    net_info = dtl.get('netting_info', {})

    exact_close = get_exact_stock_price_for_date(ticker, default_settle_date)
    if exact_close is not None and exact_close > 0:
        calc_buy_q, calc_sell_q = compute_suggested_trades(
            exact_close, buy_orders, sell_orders, unsold_lots=unsold_lots_data, strategy_name=strat_name, netting_info=net_info
        )
        initial_close_str = f"{exact_close:.2f}"
        initial_buy_str = str(calc_buy_q)
        initial_sell_str = str(calc_sell_q)
    else:
        initial_close_str = ""
        initial_buy_str = "0"
        initial_sell_str = "0"

    settle_date_field = ft.TextField(
        label="정산 일자 (YYYY-MM-DD)",
        label_style=ft.TextStyle(size=11, color=TEXT_SECONDARY),
        value=default_settle_date,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=12,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        expand=True
    )

    close_field = ft.TextField(
        label="종가($)",
        label_style=ft.TextStyle(size=11, color=TEXT_SECONDARY),
        value=initial_close_str,
        hint_text="종가 직접 입력",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=12,
        text_align=ft.TextAlign.RIGHT,
        dense=True,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        expand=True
    )

    buy_qty_field = ft.TextField(
        label="매수(주)",
        label_style=ft.TextStyle(size=11, color=PROFIT_GREEN),
        value=initial_buy_str,
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color=PROFIT_GREEN,
        color=TEXT_PRIMARY,
        text_size=12,
        text_align=ft.TextAlign.RIGHT,
        dense=True,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        expand=True
    )

    sell_qty_field = ft.TextField(
        label="매도(자동)",
        label_style=ft.TextStyle(size=11, color=LOSS_RED),
        value=initial_sell_str,
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color=LOSS_RED,
        color=LOSS_RED,
        text_size=12,
        text_align=ft.TextAlign.RIGHT,
        dense=True,
        content_padding=ft.Padding.symmetric(horizontal=8, vertical=8),
        expand=True,
        read_only=True
    )

    def on_settle_date_picked(new_date_str):
        if not new_date_str:
            return
        d_clean = str(new_date_str).strip()[:10]
        if len(d_clean) == 10:
            p = get_exact_stock_price_for_date(ticker, d_clean)
            if p is not None and p > 0:
                close_field.value = f"{p:.2f}"
                b_q, s_q = compute_suggested_trades(
                    p, buy_orders, sell_orders, unsold_lots=unsold_lots_data, strategy_name=strat_name, netting_info=net_info
                )
                buy_qty_field.value = str(b_q)
                sell_qty_field.value = str(s_q)
            else:
                # 해당 날짜의 마감 종가를 확인할 수 없는 경우 비움
                close_field.value = ""
                buy_qty_field.value = "0"
                sell_qty_field.value = "0"
            try:
                close_field.update()
                buy_qty_field.update()
                sell_qty_field.update()
            except Exception:
                pass

    settle_date_field.on_change = lambda e: on_settle_date_picked(settle_date_field.value)

    def on_close_changed(e):
        val_str = close_field.value.strip() if close_field.value else ""
        if not val_str:
            buy_qty_field.value = "0"
            sell_qty_field.value = "0"
            try:
                buy_qty_field.update()
                sell_qty_field.update()
            except Exception:
                pass
            return
        try:
            val = float(val_str)
            b_q, s_q = compute_suggested_trades(
                val, buy_orders, sell_orders, unsold_lots=unsold_lots_data, strategy_name=strat_name, netting_info=net_info
            )
            buy_qty_field.value = str(b_q)
            sell_qty_field.value = str(s_q)
            buy_qty_field.update()
            sell_qty_field.update()
        except Exception:
            pass

    close_field.on_change = on_close_changed

    def handle_settle(e):
        s_date = settle_date_field.value.strip() if settle_date_field.value else ""
        c_p_str = close_field.value.strip() if close_field.value else ""
        if not c_p_str:
            show_toast(app.page, f"{s_date}의 마감 종가를 확인할 수 없습니다. 종가를 직접 입력해주세요.", is_error=True)
            return
        try:
            c_p = float(c_p_str)
            b_q = int(buy_qty_field.value.strip() or "0")
            s_q = int(sell_qty_field.value.strip() or "0")
            app.am.record_daily_close(acc_id=acc_id, close_price=c_p, buy_qty=b_q, sell_qty=s_q, buy_price=c_p, trade_date=s_date, mode=dtl.get('mode', 'Normal'))
            show_toast(app.page, f"{s_date} 정산 데이터가 저장되었습니다! 다음 날짜 주문표로 넘어가려면 [다음 거래일 진행]을 누르세요.")
            app.reload_data()
        except Exception as ex:
            show_toast(app.page, f"정산 오류: {ex}", is_error=True)

    def handle_next_day(e):
        res = app.am.advance_next_day(acc_id)
        if res:
            show_toast(app.page, f"다음 거래일({res.get('current_date')})로 진행되었습니다!")
            app.reload_data()
        else:
            show_toast(app.page, "다음 거래일 진행 실패", is_error=True)

    settle_card = build_card(
        elevation=2,
        radius=12,
        padding=14,
        content=ft.Column(
            controls=[
                build_section_header(
                    title="일일 정산 입력 (매도 자동 체결 / 매수 입력)",
                    icon=ft.Icons.CALCULATE_ROUNDED,
                    title_size=13,
                ),
                ft.Row([
                        settle_date_field,
                        ft.IconButton(
                            icon=ft.Icons.CALENDAR_MONTH,
                            icon_color=ACCENT_BLUE,
                            tooltip="정산 일자 달력 선택",
                            on_click=lambda _: app.open_date_picker_for_field(settle_date_field, on_change_callback=on_settle_date_picked)
                        )
                    ], spacing=4),
                    ft.Row([close_field, buy_qty_field, sell_qty_field], spacing=6),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                        content=ft.Row([
                            ft.Icon(ft.Icons.INFO_OUTLINE, size=13, color=TEXT_MUTED),
                            ft.Text(
                                "목표가 이상 도달 슬롯은 매도 자동 체결(수정불가)되며, 매수 수량만 확인/입력하세요.",
                                size=10.5,
                                color=TEXT_MUTED
                            )
                        ], spacing=4)
                    ),
                    ft.Row(
                        controls=[
                            ft.FilledButton(
                                "정산 마감 확정",
                                style=ft.ButtonStyle(bgcolor=PROFIT_GREEN, color=ft.Colors.WHITE),
                                expand=True,
                                on_click=handle_settle
                            ),
                            ft.FilledButton(
                                "다음 거래일 진행",
                                style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK),
                                expand=True,
                                on_click=handle_next_day
                            ),
                        ],
                        spacing=6
                    ),
                    ft.OutlinedButton(
                        content=ft.Row([ft.Icon(ft.Icons.UNDO, size=15, color=LOSS_RED), ft.Text("최근 거래일 Undo", size=11, color=LOSS_RED)], alignment=ft.MainAxisAlignment.CENTER, spacing=4),
                        style=ft.ButtonStyle(side=ft.BorderSide(1, ft.Colors.with_opacity(0.3, LOSS_RED))),
                        width=380,
                        on_click=lambda _: app.open_undo_dialog(acc_id)
                    )
                ],
                spacing=8
            )
        )

    # -------------------------------------------------------------
    # 5. 최근 거래 내역 (슬롯 단위 라이프사이클 & 4대 섹션 구분 표)
    #    한 행 = 하나의 매수 슬롯(Lot) 정보
    #    섹션 1: 거래일자/종가/변동률/모드 , 섹션 2: 매수량/목표가 , 섹션 3: 매도일/매도가 , 섹션 4: 손익금액/손익률/누적손익
    # -------------------------------------------------------------
    table_rows = []
    if records:
        for row in build_trade_rows(records, strat):
            orig_idx = row['idx']
            r_d_kr = row['date_kr']
            r_cp = row['close']
            chg_f = row['chg']
            chg_str = row['chg_str']
            chg_color = LOSS_RED if chg_f > 0 else (ACCENT_BLUE if chg_f < 0 else TEXT_MUTED)

            r_mode = row['mode']
            mode_color = "#3B82F6" if r_mode == 'Normal' else ("#EAB308" if r_mode == 'Safe' else "#EF4444")

            r_bq = row['buy_qty']
            r_u = row['target_price']
            r_wd = row['sell_date_str']
            sell_price_str = row['sell_price_str']

            profit_str = row['profit_str']
            pr_str = row['profit_rate_str']
            p_num = row['profit']
            profit_color = TEXT_MUTED if p_num is None else (PROFIT_GREEN if p_num >= 0 else LOSS_RED)

            cum_str = row['cum_str']
            cum_num = row['cum_profit']
            cum_color = TEXT_MUTED if cum_num is None else (PROFIT_GREEN if cum_num >= 0 else LOSS_RED)

            def make_edit_fn(idx_to_edit):
                return lambda _: app.open_edit_trade_dialog(acc_id, idx_to_edit)

            table_rows.append(
                ft.DataRow(
                    cells=[
                        # 섹션 1: 시장 정보
                        ft.DataCell(ft.Text(r_d_kr, size=11, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600)),
                        ft.DataCell(ft.Text(f"${r_cp:.2f}", size=11, color=TEXT_PRIMARY)),
                        ft.DataCell(ft.Text(chg_str, size=11, color=chg_color, weight=ft.FontWeight.W_500)),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(r_mode, size=9, weight=ft.FontWeight.BOLD, color=mode_color),
                                bgcolor=ft.Colors.with_opacity(0.15, mode_color),
                                padding=ft.Padding.symmetric(horizontal=5, vertical=2),
                                border_radius=4,
                                border=ft.Border(right=ft.BorderSide(1.5, ft.Colors.with_opacity(0.35, BORDER_COLOR)))
                            )
                        ),
                        # 섹션 2: 매수 정보
                        ft.DataCell(ft.Text(f"{r_bq:,}주" if r_bq > 0 else "관망", size=11, color=PROFIT_GREEN if r_bq > 0 else TEXT_MUTED, weight=ft.FontWeight.BOLD if r_bq > 0 else ft.FontWeight.NORMAL)),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(f"${r_u:.2f}" if r_u > 0 else "-", size=11, color=TEXT_SECONDARY),
                                border=ft.Border(right=ft.BorderSide(1.5, ft.Colors.with_opacity(0.35, BORDER_COLOR)))
                            )
                        ),
                        # 섹션 3: 매도 정보
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(r_wd, size=10.5, color=RESERVE_AMBER if "보유중" in r_wd else (TEXT_PRIMARY if r_wd != "-" else TEXT_MUTED), weight=ft.FontWeight.W_600 if "보유중" in r_wd else ft.FontWeight.NORMAL),
                                bgcolor=ft.Colors.with_opacity(0.12, RESERVE_AMBER) if "보유중" in r_wd else ft.Colors.TRANSPARENT,
                                padding=ft.Padding.symmetric(horizontal=4, vertical=2) if "보유중" in r_wd else None,
                                border_radius=4 if "보유중" in r_wd else 0
                            )
                        ),
                        ft.DataCell(
                            ft.Container(
                                content=ft.Text(sell_price_str, size=11, color=TEXT_PRIMARY if sell_price_str != "-" else TEXT_MUTED),
                                border=ft.Border(right=ft.BorderSide(1.5, ft.Colors.with_opacity(0.35, BORDER_COLOR)))
                            )
                        ),
                        # 섹션 4: 손익 정보
                        ft.DataCell(ft.Text(profit_str, size=11, color=profit_color, weight=ft.FontWeight.BOLD if profit_str != "-" else ft.FontWeight.NORMAL)),
                        ft.DataCell(ft.Text(pr_str, size=11, color=profit_color, weight=ft.FontWeight.W_600 if pr_str != "-" else ft.FontWeight.NORMAL)),
                        ft.DataCell(ft.Text(cum_str, size=11, color=cum_color, weight=ft.FontWeight.BOLD if cum_str != "-" else ft.FontWeight.NORMAL)),
                        # 관리
                        ft.DataCell(
                            ft.IconButton(
                                icon=ft.Icons.EDIT_OUTLINED,
                                icon_size=15,
                                icon_color=ACCENT_BLUE,
                                tooltip="슬롯 수정",
                                on_click=make_edit_fn(orig_idx)
                            )
                        ),
                    ],
                    on_long_press=make_edit_fn(orig_idx)
                )
            )

        section_badges = ft.Container(
            bgcolor=BG_DARK,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            border=ft.Border.all(1, BORDER_COLOR),
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Row([
                            ft.Container(width=7, height=7, border_radius=4, bgcolor="#4ADE80"),
                            ft.Text("거래일자/종가/변동률/모드", size=10.5, weight=ft.FontWeight.BOLD, color="#4ADE80"),
                        ], spacing=4),
                        bgcolor=ft.Colors.with_opacity(0.12, "#4ADE80"),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                        border_radius=6,
                    ),
                    ft.Text(",", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SECONDARY),
                    ft.Container(
                        content=ft.Row([
                            ft.Container(width=7, height=7, border_radius=4, bgcolor="#F472B6"),
                            ft.Text("매수량/목표가", size=10.5, weight=ft.FontWeight.BOLD, color="#F472B6"),
                        ], spacing=4),
                        bgcolor=ft.Colors.with_opacity(0.12, "#F472B6"),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                        border_radius=6,
                    ),
                    ft.Text(",", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SECONDARY),
                    ft.Container(
                        content=ft.Row([
                            ft.Container(width=7, height=7, border_radius=4, bgcolor="#60A5FA"),
                            ft.Text("매도일/매도가", size=10.5, weight=ft.FontWeight.BOLD, color="#60A5FA"),
                        ], spacing=4),
                        bgcolor=ft.Colors.with_opacity(0.12, "#60A5FA"),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                        border_radius=6,
                    ),
                    ft.Text(",", size=14, weight=ft.FontWeight.BOLD, color=TEXT_SECONDARY),
                    ft.Container(
                        content=ft.Row([
                            ft.Container(width=7, height=7, border_radius=4, bgcolor="#FBBF24"),
                            ft.Text("손익금액/손익률/누적손익", size=10.5, weight=ft.FontWeight.BOLD, color="#FBBF24"),
                        ], spacing=4),
                        bgcolor=ft.Colors.with_opacity(0.12, "#FBBF24"),
                        padding=ft.Padding.symmetric(horizontal=6, vertical=3),
                        border_radius=6,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
                spacing=5,
                vertical_alignment=ft.CrossAxisAlignment.CENTER
            )
        )

        history_table = ft.DataTable(
            columns=[
                # 섹션 1: 시장 정보
                ft.DataColumn(ft.Text("거래일자", weight=ft.FontWeight.BOLD, size=11, color="#4ADE80")),
                ft.DataColumn(ft.Text("종가", weight=ft.FontWeight.BOLD, size=11, color="#4ADE80"), numeric=True),
                ft.DataColumn(ft.Text("변동률", weight=ft.FontWeight.BOLD, size=11, color="#4ADE80"), numeric=True),
                ft.DataColumn(ft.Text("모드", weight=ft.FontWeight.BOLD, size=11, color="#4ADE80")),
                # 섹션 2: 매수 정보
                ft.DataColumn(ft.Text("매수량", weight=ft.FontWeight.BOLD, size=11, color="#F472B6"), numeric=True),
                ft.DataColumn(ft.Text("목표가", weight=ft.FontWeight.BOLD, size=11, color="#F472B6"), numeric=True),
                # 섹션 3: 매도 정보
                ft.DataColumn(ft.Text("매도일", weight=ft.FontWeight.BOLD, size=11, color="#60A5FA")),
                ft.DataColumn(ft.Text("매도가", weight=ft.FontWeight.BOLD, size=11, color="#60A5FA"), numeric=True),
                # 섹션 4: 손익 정보
                ft.DataColumn(ft.Text("손익금액", weight=ft.FontWeight.BOLD, size=11, color="#FBBF24"), numeric=True),
                ft.DataColumn(ft.Text("손익률", weight=ft.FontWeight.BOLD, size=11, color="#FBBF24"), numeric=True),
                ft.DataColumn(ft.Text("누적손익", weight=ft.FontWeight.BOLD, size=11, color="#FBBF24"), numeric=True),
                # 관리
                ft.DataColumn(ft.Text("수정", weight=ft.FontWeight.BOLD, size=11, color=TEXT_SECONDARY)),
            ],
            rows=table_rows,
            border=ft.Border.all(1, BORDER_COLOR),
            heading_row_color=ft.Colors.with_opacity(0.4, BG_DARK),
            data_row_min_height=38,
            data_row_max_height=42,
            column_spacing=12,
            horizontal_margin=8,
        )

        history_view = ft.Container(
            bgcolor=SURFACE_CARD,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=10,
            padding=6,
            content=ft.Column(
                controls=[
                    section_badges,
                    ft.Container(height=4),
                    ft.Row(
                        controls=[history_table],
                        scroll=ft.ScrollMode.ALWAYS
                    )
                ],
                spacing=2
            )
        )
    else:
        history_view = ft.Container(
            bgcolor=SURFACE_CARD,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=10,
            padding=20,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("기록된 거래 내역이 없습니다.", size=12, color=TEXT_MUTED)
        )

    history_section = ft.Column(
        controls=[
            build_section_header(
                title="거래 슬롯별 상세 내역 (4대 섹션)",
                subtitle="(길게 탭 또는 ✏️ 눌러 수정)",
                icon=ft.Icons.TABLE_VIEW_ROUNDED,
                title_size=13,
            ),
            history_view
        ],
        spacing=6
    )

    return ft.ListView(
        controls=[
            basic_info_card,
            ft.Container(height=6),
            holdings_section,
            ft.Container(height=6),
            orders_section,
            ft.Container(height=6),
            settle_card,
            ft.Container(height=6),
            history_section,
            ft.Container(height=20)
        ],
        spacing=8,
        expand=True
    )
