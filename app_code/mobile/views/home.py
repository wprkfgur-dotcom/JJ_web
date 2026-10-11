"""
=====================================================================
종종이 & 무한매수 주식 매매 시스템 - 홈 탭 뷰 (Home Tab View)
=====================================================================
- 전체 계좌 통합 평가 자산 히어로 카드
- 포트폴리오 자산 성장 추이 인터랙티브 차트 (롱프레스 터치 수치 조회 지원)
- 4대 주요 지표 (총 예수금, 주식 평가액, 총 위기준비금, 총 실가동 시드)
- 운용 계좌별 비중 및 수익률 요약 리스트
- 계좌가 없을 때의 Empty State 뷰
"""

import flet as ft

from mobile.theme import (
    SURFACE_CARD, SURFACE_CONTAINER, BORDER_COLOR, ACCENT_BLUE,
    PROFIT_GREEN, LOSS_RED, RESERVE_AMBER, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_MUTED,
)
from mobile.charts import render_portfolio_chart
from mobile.widgets import (
    build_card, build_metric_tile, build_section_header,
    build_badge, build_empty_state
)


def on_home_chart_inspect(app, local_x: float):
    """홈 포트폴리오 그래프 롱프레스/터치 시 해당 X좌표의 통합 자산 수치를 배너에 표시합니다."""
    if not app.home_chart_dates or not app.home_chart_vals or not app.home_val_banner:
        return
    pad_left = 65
    pad_right = 25
    chart_w = 650 - pad_left - pad_right
    ratio = max(0.0, min(1.0, (local_x - pad_left) / max(1.0, chart_w)))
    idx = int(round(ratio * (len(app.home_chart_dates) - 1)))
    dt = app.home_chart_dates[idx]
    val = app.home_chart_vals[idx]
    krw_text = f"약 {val * app.exchange_rate / 1e8:.2f}억원"
    first_val = app.home_chart_vals[0] if app.home_chart_vals else val
    is_up = val >= first_val

    app.home_val_banner.content = ft.Row(
        controls=[
            ft.Icon(ft.Icons.EVENT_NOTE, color=ACCENT_BLUE, size=15),
            ft.Text(f"{dt}", size=12, weight=ft.FontWeight.BOLD, color=ACCENT_BLUE),
            ft.Container(width=4),
            ft.Text(f"${val:,.0f}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
            ft.Text(f"({krw_text})", size=11, color=PROFIT_GREEN if is_up else LOSS_RED, weight=ft.FontWeight.W_500),
        ],
        spacing=4,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )
    app.page.update()


def build_empty_home_view(app) -> ft.Control:
    """등록된 계좌가 없을 때 표시하는 가이드 뷰입니다."""
    add_btn = ft.FilledButton(
        content=ft.Row(
            controls=[ft.Icon(ft.Icons.ADD, size=18), ft.Text("첫 계좌 생성하기", weight=ft.FontWeight.BOLD)],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=6
        ),
        style=ft.ButtonStyle(
            bgcolor=ACCENT_BLUE,
            color=ft.Colors.BLACK,
            shape=ft.RoundedRectangleBorder(radius=10),
            padding=ft.Padding.symmetric(horizontal=24, vertical=12)
        ),
        on_click=app.open_add_account_dialog
    )
    return build_empty_state(
        icon=ft.Icons.SAVINGS_OUTLINED,
        title="등록된 계좌가 없습니다.",
        subtitle="우측 하단 '+' 버튼 또는 아래 버튼을 눌러\n첫 번째 계좌를 생성해보세요.",
        action_button=add_btn,
        top_padding=80
    )


def build_home_view(app) -> ft.Control:
    """홈 탭(전체 통합 자산 현황 & 포트폴리오 그래프)을 생성합니다."""
    if not app.accounts:
        return build_empty_home_view(app)

    # 전체 계좌 합산 지표 산출
    tot_asset = sum(d.get('current_asset', 0.0) for d in app.accounts_details)
    tot_seed = sum(d.get('initial_seed', 0.0) for d in app.accounts_details)
    tot_profit = sum(d.get('total_profit', 0.0) for d in app.accounts_details)
    tot_return_pct = (tot_profit / tot_seed * 100.0) if tot_seed > 0 else 0.0

    tot_cash = sum(d.get('current_cash', 0.0) for d in app.accounts_details)
    tot_ak = sum(d.get('ak_val', 0.0) for d in app.accounts_details)
    tot_ar = sum(d.get('ar_val', 0.0) for d in app.accounts_details)
    tot_stock_val = max(0.0, tot_asset - tot_cash)

    krw_asset = tot_asset * app.exchange_rate
    is_profit = tot_profit >= 0
    p_color = PROFIT_GREEN if is_profit else LOSS_RED
    p_icon = ft.Icons.ARROW_DROP_UP if is_profit else ft.Icons.ARROW_DROP_DOWN

    # 1. 통합 자산 히어로 카드
    hero_card = build_card(
        elevation=3,
        radius=16,
        padding=18,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("전체 계좌 통합 평가 자산", size=13, color=TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                        build_badge(f"총 {len(app.accounts)}개 계좌", color=ACCENT_BLUE, radius=10, padding_h=8, padding_v=3)
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                    ft.Container(height=4),
                    ft.Text(f"${tot_asset:,.2f}", size=32, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ft.Text(f"약 {krw_asset:,.0f}원 (환율 {app.exchange_rate:,.0f}원)", size=12, color=TEXT_MUTED),
                    ft.Container(height=8),
                    ft.Divider(color=BORDER_COLOR, height=1),
                    ft.Container(height=4),
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(p_icon, color=p_color, size=20),
                                    ft.Text(f"{tot_return_pct:+.2f}%", size=14, weight=ft.FontWeight.BOLD, color=p_color),
                                    ft.Text(f"({tot_profit:+,.2f}달러)", size=12, color=p_color),
                                ],
                                spacing=2
                            ),
                            ft.Text(f"총 원금: ${tot_seed:,.0f}", size=12, color=TEXT_SECONDARY)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ]
            )
        )

    # 2. 통합 자산 추이 그래프
    chart_base64, dates, vals = render_portfolio_chart(app.accounts_details, tot_asset)
    app.home_chart_dates = dates
    app.home_chart_vals = vals

    app.home_val_banner = ft.Container(
        bgcolor=SURFACE_CONTAINER,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        content=ft.Row(
            controls=[
                ft.Icon(ft.Icons.TOUCH_APP_OUTLINED, color=ACCENT_BLUE, size=15),
                ft.Text("그래프를 길게 누르면 해당 위치의 자산 수치가 표시됩니다", size=11, color=TEXT_MUTED)
            ],
            spacing=6
        )
    )

    chart_card = build_card(
        elevation=2,
        radius=14,
        padding=14,
        content=ft.Column(
            controls=[
                build_section_header(
                    title="포트폴리오 자산 성장 추이",
                    subtitle="길게 누르기: 수치확인 | 핀치: 확대",
                    icon=ft.Icons.SHOW_CHART,
                    title_size=13
                ),
                ft.Container(height=4),
                app.home_val_banner,
                ft.Container(height=4),
                ft.Container(
                    height=200,
                    border_radius=8,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                    content=ft.InteractiveViewer(
                        content=ft.GestureDetector(
                            content=ft.Image(src=chart_base64, fit="contain", width=650, height=200),
                            on_long_press_start=lambda e: on_home_chart_inspect(app, e.local_position.x),
                            on_long_press_move_update=lambda e: on_home_chart_inspect(app, e.local_position.x),
                            on_tap_down=lambda e: on_home_chart_inspect(app, e.local_position.x)
                        ),
                        constrained=True,
                        min_scale=1.0,
                        max_scale=4.0,
                        pan_enabled=True,
                        scale_enabled=True,
                        clip_behavior=ft.ClipBehavior.HARD_EDGE
                    )
                ),
            ]
        )
    )

    # 3. 4대 종합 지표 그리드
    def make_metric_card(title, value, subtext, icon, icon_color):
        return build_metric_tile(
            title=title,
            value=value,
            subtext=subtext,
            icon=icon,
            icon_color=icon_color,
            radius=12,
            padding=12,
            expand=True
        )

    row1 = ft.Row(
        controls=[
            make_metric_card("총 예수금 (Cash)", f"${tot_cash:,.0f}", "현금 보유액", ft.Icons.ATTACH_MONEY, PROFIT_GREEN),
            make_metric_card("주식 평가액", f"${tot_stock_val:,.0f}", "보유 주식 총액", ft.Icons.PIE_CHART_OUTLINE, ft.Colors.PURPLE_300),
        ],
        spacing=8
    )

    row2 = ft.Row(
        controls=[
            make_metric_card("총 위기준비금 (AK)", f"${tot_ak:,.0f}", "폭락 안전 준비금", ft.Icons.SHIELD_OUTLINED, RESERVE_AMBER),
            make_metric_card("총 실가동 시드 (AR)", f"${tot_ar:,.0f}", "분할 운용 시드", ft.Icons.ROCKET_LAUNCH_OUTLINED, ACCENT_BLUE),
        ],
        spacing=8
    )

    # 4. 운용 계좌별 비중 요약 리스트
    acc_summary_items = []
    for d in app.accounts_details:
        name = d.get('account_name', '')
        ticker = d.get('ticker', '')
        asset = d.get('current_asset', 0.0)
        ret_pct = d.get('total_return_pct', 0.0)
        ratio = (asset / tot_asset * 100.0) if tot_asset > 0 else 0.0
        r_color = PROFIT_GREEN if ret_pct >= 0 else LOSS_RED

        item = ft.Container(
            bgcolor=SURFACE_CARD,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=10,
            padding=12,
            on_click=lambda e, aid=d.get('account_id'): app.open_account_detail(aid),
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(name, size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    build_badge(ticker, color=ACCENT_BLUE, text_size=10, font_weight=ft.FontWeight.NORMAL),
                                ],
                                spacing=6
                            ),
                            ft.Text(f"포트폴리오 비중: {ratio:.1f}%", size=11, color=TEXT_MUTED)
                        ],
                        spacing=2,
                        expand=True
                    ),
                    ft.Column(
                        controls=[
                            ft.Text(f"${asset:,.2f}", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ft.Text(f"{ret_pct:+.2f}%", size=11, weight=ft.FontWeight.BOLD, color=r_color)
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=1
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=TEXT_MUTED, size=20)
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            )
        )
        acc_summary_items.append(item)

    return ft.ListView(
        controls=[
            hero_card,
            ft.Container(height=6),
            chart_card,
            ft.Container(height=6),
            row1,
            row2,
            ft.Container(height=8),
            ft.Row(
                controls=[
                    ft.Text("계좌별 자산 및 비중", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                ],
                alignment=ft.MainAxisAlignment.START
            ),
            *acc_summary_items,
            ft.Container(height=20)
        ],
        spacing=8,
        expand=True
    )
