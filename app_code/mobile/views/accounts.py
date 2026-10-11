"""
=====================================================================
종종이 & 무한매수 주식 매매 시스템 - 계좌 현황 탭 뷰 (Accounts Tab View)
=====================================================================
- 등록된 계좌 카드 리스트
- 계좌별 운용 전략, 현재 모드, 평가자산, 수익률, 예수금, 보유량, 위기준비금 요약
- 계좌 카드 클릭 시 계좌 상세 페이지 이동
- 등록 계좌가 없을 시 Empty State 뷰 표시
"""

import flet as ft

from mobile.theme import (
    BORDER_COLOR, ACCENT_BLUE, PROFIT_GREEN,
    LOSS_RED, RESERVE_AMBER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)
from mobile.widgets import build_card, build_badge
from mobile.views.home import build_empty_home_view


def build_accounts_view(app) -> ft.Control:
    """계좌 현황 탭(카드 리스트)을 생성합니다."""
    if not app.accounts:
        return build_empty_home_view(app)

    cards = []
    for acc in app.accounts:
        aid = acc['id']
        dtl = next((d for d in app.accounts_details if d.get('account_id') == aid), {})

        name = acc.get('name', '계좌')
        ticker = acc.get('ticker', 'SOXL')
        strat = acc.get('strategy', '종종이 기본전략')
        seed = acc.get('initial_seed', 0.0)
        reserve_pct = float(acc.get('reserve_ratio', 0.05)) * 100.0

        asset = dtl.get('current_asset', seed)
        ret_pct = dtl.get('total_return_pct', 0.0)
        cash = dtl.get('current_cash', seed)
        hold = dtl.get('current_hold', 0)
        ak_val = dtl.get('ak_val', seed * 0.05)
        mode = dtl.get('mode', 'Normal')

        r_color = PROFIT_GREEN if ret_pct >= 0 else LOSS_RED

        card = build_card(
            padding=16,
            radius=14,
            elevation=2,
            border_color=BORDER_COLOR,
            on_click=lambda e, target_id=aid: app.open_account_detail(target_id),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(name, size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    build_badge(ticker, color=ACCENT_BLUE),
                                ],
                                spacing=6
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=TEXT_MUTED, size=20)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Text(f"{strat} • {mode} 모드", size=11, color=TEXT_SECONDARY),
                        ft.Container(height=4),
                        ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text("평가 자산", size=10, color=TEXT_MUTED),
                                        ft.Text(f"${asset:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                                    ],
                                    spacing=1
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text("총 수익률", size=10, color=TEXT_MUTED),
                                        ft.Text(f"{ret_pct:+.2f}%", size=18, weight=ft.FontWeight.BOLD, color=r_color)
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    spacing=1
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        ft.Container(height=4),
                        ft.Divider(color=BORDER_COLOR, height=1),
                        ft.Container(height=2),
                        ft.Row(
                            controls=[
                                ft.Text(f"원금: ${seed:,.0f}", size=11, color=TEXT_MUTED),
                                ft.Text(f"예수금: ${cash:,.0f}", size=11, color=TEXT_MUTED),
                                ft.Text(f"보유: {hold:,}주", size=11, color=TEXT_MUTED),
                                ft.Text(f"위기: {reserve_pct:.0f}% (${ak_val:,.0f})", size=11, color=RESERVE_AMBER),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        )
                    ],
                    spacing=3
                )
            )
        cards.append(card)

    return ft.ListView(
        controls=[
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=4, vertical=6),
                content=ft.Row(
                    controls=[
                        ft.Text(f"운용 계좌 ({len(app.accounts)}개)", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ft.Text("우측 하단 '+' 버튼으로 새 계좌 추가", size=11, color=TEXT_MUTED)
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                )
            ),
            *cards,
            ft.Container(height=70)  # 플로팅 버튼 여백
        ],
        spacing=8,
        expand=True
    )
