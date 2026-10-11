"""
백테스트 탭 뷰 (mobile.views.backtest)

종목, 기간, 시드, 멀티 전략 선택 입력 폼 및 성과 지표/비교 차트 렌더링.
"""
from datetime import datetime, timedelta
import flet as ft

from mobile.theme import (
    SURFACE_CARD, SURFACE_CONTAINER, BORDER_COLOR, ACCENT_BLUE, PROFIT_GREEN,
    LOSS_RED, RESERVE_AMBER, VR_PURPLE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED
)
from mobile.helpers import show_toast
from mobile.charts import render_multi_backtest_chart
from core.data import fetch_market_data
from core.strategy_registry import (
    JONGJONG, INFINITE, VR, DISPLAY_NAMES, bnh_display_name
)
from core.backtest_runner import run_strategies, build_chart_series


def build_backtest_view(app) -> ft.Control:
    """백테스트 탭(ListView) 컴포넌트를 빌드합니다."""
    cur_ticker = getattr(app, 'bt_ticker', 'SOXL')
    cur_period = getattr(app, 'bt_period', '최근 3년')
    cur_seed = getattr(app, 'bt_seed', '200000')
    cur_jj = getattr(app, 'bt_strat_jongjong', True)
    cur_inf = getattr(app, 'bt_strat_infinite', True)
    cur_vr = getattr(app, 'bt_strat_vr', True)
    cur_bnh = getattr(app, 'bt_strat_bnh', True)
    cur_s_date = getattr(app, 'bt_start_date', '2022-01-03')
    cur_e_date = getattr(app, 'bt_end_date', datetime.now().strftime('%Y-%m-%d'))
    cur_custom_vis = getattr(app, 'bt_custom_visible', False) or (cur_period == "직접 날짜 선택 (사용자 지정)")

    ticker_dd = ft.Dropdown(
        label="대상 종목",
        label_style=ft.TextStyle(size=11, color=TEXT_SECONDARY),
        value=cur_ticker,
        options=[
            ft.dropdown.Option("SOXL"),
            ft.dropdown.Option("TQQQ"),
            ft.dropdown.Option("UPRO"),
            ft.dropdown.Option("NVDA"),
            ft.dropdown.Option("AAPL")
        ],
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=12.5,
        dense=True,
        content_padding=ft.Padding.only(left=8, right=2, top=4, bottom=4),
        expand=True
    )

    def on_ticker_change(e):
        app.bt_ticker = ticker_dd.value

    ticker_dd.on_change = on_ticker_change

    # 복수 선택 가능한 전략 체크박스
    cb_jongjong = ft.Checkbox(
        label="종종이 전략",
        value=cur_jj,
        active_color=PROFIT_GREEN,
        label_style=ft.TextStyle(color=TEXT_PRIMARY, size=12, weight=ft.FontWeight.W_600)
    )
    cb_infinite = ft.Checkbox(
        label="무한매수 v4",
        value=cur_inf,
        active_color=RESERVE_AMBER,
        label_style=ft.TextStyle(color=TEXT_PRIMARY, size=12, weight=ft.FontWeight.W_600)
    )
    cb_vr = ft.Checkbox(
        label="VR 5.0",
        value=cur_vr,
        active_color=VR_PURPLE,
        label_style=ft.TextStyle(color=TEXT_PRIMARY, size=12, weight=ft.FontWeight.W_600)
    )
    cb_bnh = ft.Checkbox(
        label="단순보유(B&H)",
        value=cur_bnh,
        active_color=ACCENT_BLUE,
        label_style=ft.TextStyle(color=TEXT_PRIMARY, size=12, weight=ft.FontWeight.W_600)
    )

    def on_cb_change(e):
        app.bt_strat_jongjong = cb_jongjong.value
        app.bt_strat_infinite = cb_infinite.value
        app.bt_strat_vr = cb_vr.value
        app.bt_strat_bnh = cb_bnh.value

    cb_jongjong.on_change = on_cb_change
    cb_infinite.on_change = on_cb_change
    cb_vr.on_change = on_cb_change
    cb_bnh.on_change = on_cb_change

    strat_selector = ft.Container(
        bgcolor=SURFACE_CONTAINER,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        content=ft.Column(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.CHECKLIST, color=ACCENT_BLUE, size=15),
                    ft.Text("검증 전략 선택 (복수 선택 시 한 그래프에 동시 비교)", size=12, weight=ft.FontWeight.BOLD, color=TEXT_SECONDARY),
                ], spacing=6),
                ft.Row([cb_jongjong, cb_infinite, cb_vr, cb_bnh], spacing=6, wrap=True)
            ],
            spacing=4
        )
    )

    period_dd = ft.Dropdown(
        label="테스트 기간",
        label_style=ft.TextStyle(size=11, color=TEXT_SECONDARY),
        value=cur_period,
        options=[
            ft.dropdown.Option("최근 1년"),
            ft.dropdown.Option("최근 2년"),
            ft.dropdown.Option("최근 3년"),
            ft.dropdown.Option("최근 5년"),
            ft.dropdown.Option("2019년~현재"),
            ft.dropdown.Option("직접 날짜 선택 (사용자 지정)")
        ],
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=11.5,
        dense=True,
        content_padding=ft.Padding.only(left=8, right=2, top=4, bottom=4),
        expand=True
    )

    seed_field = ft.TextField(
        label="초기 투자 원금 ($)",
        value=cur_seed,
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=12.5,
        dense=True,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        expand=True
    )

    def on_seed_change(e):
        app.bt_seed = seed_field.value

    seed_field.on_change = on_seed_change

    # 직접 날짜 선택 필드
    default_start_date = cur_s_date
    default_end_date = cur_e_date

    custom_date_summary = ft.Text(
        f"직접 기간: {default_start_date} ~ {default_end_date}",
        size=12,
        weight=ft.FontWeight.BOLD,
        color=ACCENT_BLUE
    )

    start_date_field = ft.TextField(
        label="시작일 (YYYY-MM-DD)",
        value=default_start_date,
        read_only=True,
        on_click=lambda _: app.open_custom_date_dialog(start_date_field, end_date_field, custom_date_summary),
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        expand=True,
        suffix=ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_color=ACCENT_BLUE,
            tooltip="시작일 달력 선택",
            on_click=lambda _: app.open_custom_date_dialog(start_date_field, end_date_field, custom_date_summary)
        )
    )

    end_date_field = ft.TextField(
        label="종료일 (YYYY-MM-DD)",
        value=default_end_date,
        read_only=True,
        on_click=lambda _: app.open_custom_date_dialog(start_date_field, end_date_field, custom_date_summary),
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        expand=True,
        suffix=ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_color=ACCENT_BLUE,
            tooltip="종료일 달력 선택",
            on_click=lambda _: app.open_custom_date_dialog(start_date_field, end_date_field, custom_date_summary)
        )
    )

    custom_date_container = ft.Container(
        visible=cur_custom_vis,
        bgcolor=SURFACE_CONTAINER,
        border=ft.Border.all(1, ACCENT_BLUE),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        content=ft.Column(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.DATE_RANGE, color=ACCENT_BLUE, size=16),
                    custom_date_summary,
                    ft.Container(expand=True),
                    ft.FilledButton(
                        "날짜 변경 창 열기",
                        icon=ft.Icons.EDIT_CALENDAR,
                        style=ft.ButtonStyle(
                            bgcolor=ACCENT_BLUE,
                            color=ft.Colors.BLACK,
                            padding=ft.Padding.symmetric(horizontal=10, vertical=6)
                        ),
                        on_click=lambda _: app.open_custom_date_dialog(start_date_field, end_date_field, custom_date_summary)
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([start_date_field, end_date_field], spacing=8)
            ],
            spacing=8
        )
    )

    def open_custom_date_flow(e=None):
        period_dd.value = "직접 날짜 선택 (사용자 지정)"
        app.bt_period = "직접 날짜 선택 (사용자 지정)"
        custom_date_container.visible = True
        app.bt_custom_visible = True
        try:
            period_dd.update()
            custom_date_container.update()
            app.page.update()
        except Exception:
            pass
        app.open_custom_date_dialog(start_date_field, end_date_field, custom_date_summary)

    def on_period_change(e):
        val = getattr(e.control, 'value', None) or period_dd.value
        app.bt_period = val
        if val and "직접" in val:
            open_custom_date_flow()
        else:
            custom_date_container.visible = False
            app.bt_custom_visible = False
            try:
                custom_date_container.update()
                app.page.update()
            except Exception:
                pass

    period_dd.on_select = on_period_change
    period_dd.on_change = on_period_change

    progress_ring = ft.ProgressRing(visible=False, color=ACCENT_BLUE, width=24, height=24)
    run_btn = ft.FilledButton(
        content=ft.Row(
            controls=[
                progress_ring,
                ft.Icon(ft.Icons.ROCKET_LAUNCH, size=16),
                ft.Text("백테스트 실행", size=14, weight=ft.FontWeight.BOLD)
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8
        ),
        style=ft.ButtonStyle(
            bgcolor=ACCENT_BLUE,
            color=ft.Colors.BLACK,
            shape=ft.RoundedRectangleBorder(radius=10),
            padding=ft.Padding.symmetric(vertical=12)
        ),
        width=380
    )

    def handle_run_backtest(e):
        t = ticker_dd.value
        p_val = period_dd.value

        # 사용자가 선택한 입력 상태 보존
        app.bt_ticker = t
        app.bt_period = p_val
        app.bt_seed = seed_field.value
        app.bt_strat_jongjong = cb_jongjong.value
        app.bt_strat_infinite = cb_infinite.value
        app.bt_strat_vr = cb_vr.value
        app.bt_strat_bnh = cb_bnh.value
        app.bt_start_date = start_date_field.value
        app.bt_end_date = end_date_field.value
        app.bt_custom_visible = custom_date_container.visible

        selected_strats = []
        if cb_jongjong.value:
            selected_strats.append((DISPLAY_NAMES[JONGJONG], PROFIT_GREEN, False))
        if cb_infinite.value:
            selected_strats.append((DISPLAY_NAMES[INFINITE], RESERVE_AMBER, False))
        if cb_vr.value:
            selected_strats.append((DISPLAY_NAMES[VR], VR_PURPLE, False))
        if cb_bnh.value:
            selected_strats.append((bnh_display_name(t), ACCENT_BLUE, True))

        if not selected_strats:
            show_toast(app.page, "비교 검증할 전략을 최소 1개 이상 선택해주세요.", is_error=True)
            return

        try:
            cap = float(seed_field.value.strip())
        except Exception:
            cap = 200000.0

        # 기간 환산
        now = datetime.now()
        if p_val == "직접 날짜 선택 (사용자 지정)":
            s_date = start_date_field.value.strip()
            e_date = end_date_field.value.strip()
            try:
                datetime.strptime(s_date, '%Y-%m-%d')
                datetime.strptime(e_date, '%Y-%m-%d')
            except Exception:
                show_toast(app.page, "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)", is_error=True)
                return
            if s_date >= e_date:
                show_toast(app.page, "종료일은 시작일보다 이후여야 합니다.", is_error=True)
                return
        elif p_val == "최근 1년":
            s_date = (now - timedelta(days=365)).strftime('%Y-%m-%d')
            e_date = now.strftime('%Y-%m-%d')
        elif p_val == "최근 2년":
            s_date = (now - timedelta(days=730)).strftime('%Y-%m-%d')
            e_date = now.strftime('%Y-%m-%d')
        elif p_val == "최근 3년":
            s_date = (now - timedelta(days=1095)).strftime('%Y-%m-%d')
            e_date = now.strftime('%Y-%m-%d')
        elif p_val == "최근 5년":
            s_date = (now - timedelta(days=1825)).strftime('%Y-%m-%d')
            e_date = now.strftime('%Y-%m-%d')
        else:
            s_date = '2019-01-01'
            e_date = now.strftime('%Y-%m-%d')

        loading_icon_hourglass = ft.Icon(ft.Icons.HOURGLASS_TOP, color=RESERVE_AMBER, size=24)
        loading_icon_gear = ft.Icon(ft.Icons.SETTINGS, color=ACCENT_BLUE, size=24)

        loading_status_text = ft.Text(
            "[1/3] 📡 야후 파이낸스 시세 데이터 다운로드 중...",
            size=12,
            color=TEXT_PRIMARY,
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER
        )
        loading_sub_text = ft.Text(
            f"{t} ({s_date} ~ {e_date}) 일봉 데이터를 수신하고 있습니다.",
            size=11,
            color=TEXT_SECONDARY,
            text_align=ft.TextAlign.CENTER
        )

        loading_dlg = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                width=330,
                padding=ft.Padding.symmetric(horizontal=18, vertical=22),
                content=ft.Column(
                    controls=[
                        ft.Row([
                            # 모래시계 회전 인디케이터
                            ft.Stack([
                                ft.ProgressRing(color=RESERVE_AMBER, width=56, height=56, stroke_width=3.5),
                                ft.Container(
                                    content=loading_icon_hourglass,
                                    alignment=ft.Alignment(0, 0),
                                    width=56,
                                    height=56
                                )
                            ]),
                            # 톱니바퀴 회전 인디케이터
                            ft.Stack([
                                ft.ProgressRing(color=ACCENT_BLUE, width=56, height=56, stroke_width=3.5),
                                ft.Container(
                                    content=loading_icon_gear,
                                    alignment=ft.Alignment(0, 0),
                                    width=56,
                                    height=56
                                )
                            ]),
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=24),
                        ft.Container(height=8),
                        ft.Text("백테스트 시뮬레이션 진행 중", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ft.Container(height=4),
                        ft.ProgressBar(color=ACCENT_BLUE, bgcolor=SURFACE_CONTAINER, value=None, width=280),
                        ft.Container(height=6),
                        loading_status_text,
                        loading_sub_text,
                        ft.Container(height=4),
                        ft.Container(
                            content=ft.Text(
                                "연산 중 잠시만 기다려주세요 (화면이 멈춘 것이 아닙니다)",
                                size=10,
                                color=TEXT_MUTED,
                                text_align=ft.TextAlign.CENTER
                            ),
                            alignment=ft.Alignment(0, 0)
                        )
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                    tight=True
                )
            ),
            bgcolor=SURFACE_CARD,
            shape=ft.RoundedRectangleBorder(radius=16)
        )

        progress_ring.visible = True
        original_btn_content = run_btn.content
        run_btn.content = ft.Row([
            ft.ProgressRing(width=16, height=16, stroke_width=2.5, color=ft.Colors.BLACK),
            ft.Text("시뮬레이션 연산 진행 중...", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8)
        run_btn.disabled = True

        app.page.show_dialog(loading_dlg)
        app.page.update()

        def worker():
            try:
                # 1. 시세 데이터 다운로드
                loading_icon_hourglass.name = ft.Icons.HOURGLASS_TOP
                loading_status_text.value = f"[1/3] 📡 {t} 시세 데이터 수신 중..."
                loading_sub_text.value = f"{s_date} ~ {e_date} 일봉 데이터를 다운로드하고 있습니다."
                app.page.update()

                df_market = fetch_market_data(t, s_date, e_date)
                if df_market is None or df_market.empty:
                    try:
                        app.page.pop_dialog()
                    except Exception:
                        pass
                    show_toast(app.page, f"{t} 시장 데이터를 불러오지 못했습니다.", is_error=True)
                    return

                # 2. 전략별 시뮬레이션
                loading_icon_hourglass.name = ft.Icons.HOURGLASS_BOTTOM
                loading_status_text.value = "[2/3] ⚙️ 전략별 매매 & 복리 시뮬레이션 연산 중..."
                loading_sub_text.value = f"총 {len(selected_strats)}개 전략의 조각 매수/익절/시간손절을 계산 중입니다."
                app.page.update()

                multi_results = run_strategies(
                    df_market, t, cap, s_date, e_date,
                    [name for name, _, _ in selected_strats]
                )
                series_for_chart = []
                for res, (strat_name, color, is_dash) in zip(multi_results, selected_strats):
                    res['color'] = color
                    series_for_chart.append({
                        'name': strat_name,
                        'color': color,
                        'dash': is_dash,
                        **build_chart_series(res['df'])
                    })

                # 3. 차트 렌더링
                loading_icon_hourglass.name = ft.Icons.HOURGLASS_FULL
                loading_status_text.value = "[3/3] 📊 고해상도 성과 차트 및 지표 렌더링 중..."
                loading_sub_text.value = "결과 대시보드를 생성하고 있습니다."
                app.page.update()

                chart_b64, bt_dates, valid_series = render_multi_backtest_chart(series_for_chart, t)
                app.bt_chart_dates = bt_dates
                app.bt_chart_series = valid_series

                app.bt_results = {
                    'ticker': t,
                    'period': f"{s_date} ~ {e_date}",
                    'initial_capital': cap,
                    'chart_b64': chart_b64,
                    'results': multi_results
                }

                try:
                    app.page.pop_dialog()
                except Exception:
                    pass
                show_toast(app.page, f"{t} ({len(multi_results)}개 전략) 백테스트 완료!")
            except Exception as ex:
                try:
                    app.page.pop_dialog()
                except Exception:
                    pass
                show_toast(app.page, f"백테스트 실패: {ex}", is_error=True)
            finally:
                run_btn.content = original_btn_content
                run_btn.disabled = False
                progress_ring.visible = False
                app._render_current_view()

        app.page.run_thread(worker)

    run_btn.on_click = handle_run_backtest

    # 파라미터 입력 카드
    input_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.TUNE, color=ACCENT_BLUE, size=18),
                        ft.Text("백테스트 환경 설정", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                    ], spacing=6),
                    ft.Container(height=4),
                    ft.Row([
                        ft.Container(content=ticker_dd, width=125),
                        period_dd,
                        ft.OutlinedButton(
                            content=ft.Row([
                                ft.Icon(ft.Icons.CALENDAR_MONTH, size=14, color=ACCENT_BLUE),
                                ft.Text("직접선택", size=11, color=ACCENT_BLUE)
                            ], spacing=3),
                            style=ft.ButtonStyle(
                                side=ft.BorderSide(1, ACCENT_BLUE),
                                shape=ft.RoundedRectangleBorder(radius=8),
                                padding=ft.Padding.symmetric(horizontal=6, vertical=8)
                            ),
                            tooltip="직접 시작일/종료일 선택 창을 엽니다.",
                            on_click=open_custom_date_flow
                        )
                    ], spacing=6),
                    custom_date_container,
                    strat_selector,
                    seed_field,
                    ft.Container(height=4),
                    run_btn
                ],
                spacing=8
            )
        )
    )

    results_widgets = []
    if app.bt_results:
        res = app.bt_results
        res_list = res.get('results', [])

        app.bt_val_banner = ft.Container(
            bgcolor=SURFACE_CONTAINER,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.TOUCH_APP_OUTLINED, color=ACCENT_BLUE, size=15),
                    ft.Text("그래프를 길게 누르면 해당 위치의 각 전략별 Y 수치가 표시됩니다", size=11, color=TEXT_MUTED)
                ],
                spacing=6
            )
        )

        chart_display = ft.Card(
            bgcolor=SURFACE_CARD,
            elevation=2,
            shape=ft.RoundedRectangleBorder(radius=12),
            content=ft.Container(
                padding=12,
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(f"{res['ticker']} 전략 비교 자산 곡선", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                ft.Text("길게 누르기: 수치확인 | 핀치: 확대", size=10, color=TEXT_MUTED)
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        ft.Container(height=4),
                        app.bt_val_banner,
                        ft.Container(height=4),
                        ft.Container(
                            height=220,
                            border_radius=8,
                            clip_behavior=ft.ClipBehavior.HARD_EDGE,
                            content=ft.InteractiveViewer(
                                content=ft.GestureDetector(
                                    content=ft.Image(src=res['chart_b64'], fit="contain", width=650, height=220),
                                    on_long_press_start=lambda e: app._on_bt_chart_inspect(e.local_position.x),
                                    on_long_press_move_update=lambda e: app._on_bt_chart_inspect(e.local_position.x),
                                    on_tap_down=lambda e: app._on_bt_chart_inspect(e.local_position.x)
                                ),
                                constrained=True,
                                min_scale=1.0,
                                max_scale=4.0,
                                pan_enabled=True,
                                scale_enabled=True,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE
                            )
                        )
                    ]
                )
            )
        )

        # 각 전략별 비교 성과 요약 카드 리스트
        strat_cards = []
        for r in res_list:
            m = r['metrics']
            col = r['color']
            name = r['name']
            f_asset = m.get('final_asset', 0.0)
            tot_ret = m.get('total_return', 0.0)
            cagr = m.get('cagr', 0.0)
            mdd = m.get('mdd', 0.0)
            sharpe = m.get('sharpe', 0.0)
            t_days = m.get('trading_days', 0)
            is_win = tot_ret >= 0

            card = ft.Container(
                bgcolor=SURFACE_CARD,
                border=ft.Border.all(1, col if len(res_list) > 1 else BORDER_COLOR),
                border_radius=12,
                padding=12,
                content=ft.Column(
                    controls=[
                        ft.Row([
                            ft.Container(width=10, height=10, bgcolor=col, border_radius=5),
                            ft.Text(f"{name}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY, expand=True),
                            ft.Text(f"{tot_ret:+.2f}%", size=14, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN if is_win else LOSS_RED)
                        ], spacing=6),
                        ft.Divider(color=BORDER_COLOR, height=1),
                        ft.Row([
                            ft.Column([
                                ft.Text("최종 자산", size=10, color=TEXT_MUTED),
                                ft.Text(f"${f_asset:,.0f}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ], spacing=1, expand=True),
                            ft.Column([
                                ft.Text("CAGR (연복리)", size=10, color=TEXT_MUTED),
                                ft.Text(f"{cagr:+.2f}%", size=13, weight=ft.FontWeight.BOLD, color=ACCENT_BLUE),
                            ], spacing=1, expand=True),
                            ft.Column([
                                ft.Text("MDD (최대낙폭)", size=10, color=TEXT_MUTED),
                                ft.Text(f"{mdd:.2f}%", size=13, weight=ft.FontWeight.BOLD, color=LOSS_RED),
                            ], spacing=1, expand=True),
                            ft.Column([
                                ft.Text("샤프 / 거래일", size=10, color=TEXT_MUTED),
                                ft.Text(f"{sharpe:.2f} ({t_days}일)", size=12, color=TEXT_SECONDARY),
                            ], spacing=1, expand=True),
                        ], spacing=6)
                    ],
                    spacing=6
                )
            )
            strat_cards.append(card)

        results_widgets = [
            ft.Container(height=4),
            ft.Row([
                ft.Text(f"📊 검증 결과 비교 ({res['period']})", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
            ]),
            chart_display,
            ft.Container(height=2),
            *strat_cards
        ]
    else:
        results_widgets = [
            ft.Container(height=20),
            ft.Container(
                bgcolor=SURFACE_CARD,
                border=ft.Border.all(1, BORDER_COLOR),
                border_radius=12,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.QUERY_STATS, size=40, color=TEXT_MUTED),
                        ft.Text("백테스트 결과가 여기에 표시됩니다.", size=13, weight=ft.FontWeight.W_600, color=TEXT_SECONDARY),
                        ft.Text("종목, 복수 전략 및 기간을 설정한 후 [백테스트 실행]을 눌러보세요.", size=11, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER)
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6
                )
            )
        ]

    return ft.ListView(
        controls=[
            input_card,
            *results_widgets,
            ft.Container(height=20)
        ],
        spacing=8,
        expand=True
    )

    # =================================================================
    # TAB 3: 💡 투자 전략 (종종이 & 무한매수 전략 상세 소개)
