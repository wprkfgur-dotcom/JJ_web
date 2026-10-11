"""
=====================================================================
종종이 & 무한매수 주식 매매 시스템 - 모달 대화상자 (Modal Dialogs)
=====================================================================
1. 신규 계좌 등록 다이얼로그 (open_add_account_dialog)
2. 계좌 설정 변경 다이얼로그 (open_settings_dialog)
3. 계좌 영구 삭제 확인 다이얼로그 (open_delete_account_dialog)
4. 직전 거래일 Undo 확인 다이얼로그 (open_undo_dialog)
5. 거래 슬롯 직접 수정 다이얼로그 (open_edit_trade_dialog)
6. 백테스트 기간 직접 선택 다이얼로그 (open_custom_date_dialog)
"""

from datetime import datetime, timedelta
import flet as ft

from core.strategy_registry import ACCOUNT_STRATEGY_OPTIONS
from mobile.theme import (
    SURFACE_CARD, SURFACE_CONTAINER, BORDER_COLOR, ACCENT_BLUE,
    LOSS_RED, RESERVE_AMBER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
)
from mobile.helpers import (
    show_toast, format_kr_date,
)


def open_add_account_dialog(app, e=None):
    """신규 계좌 추가 다이얼로그를 표시합니다."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    cnt = len(app.accounts) + 1

    name_f = ft.TextField(label="계좌 별칭", value=f"SOXL 종종이 {cnt}호", border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY)
    ticker_f = ft.TextField(label="종목 티커", value="SOXL", border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY, expand=True)
    strat_f = ft.Dropdown(
        label="전략 선택",
        value="종종이 기본전략",
        options=[ft.dropdown.Option(o) for o in ACCOUNT_STRATEGY_OPTIONS],
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY
    )
    date_f = ft.TextField(
        label="시작일 (YYYY-MM-DD)",
        value=today_str,
        hint_text="오늘날짜 (달력선택 가능)",
        read_only=True,
        on_click=lambda _: app.open_date_picker_for_field(date_f),
        suffix=ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_color=ACCENT_BLUE,
            tooltip="달력에서 시작일 선택",
            on_click=lambda _: app.open_date_picker_for_field(date_f)
        ),
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        expand=True
    )
    seed_f = ft.TextField(label="초기 시드 ($)", value="100000", keyboard_type=ft.KeyboardType.NUMBER, border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY, expand=True)
    reserve_f = ft.TextField(label="위기준비금(%)", value="5", keyboard_type=ft.KeyboardType.NUMBER, border_color=BORDER_COLOR, focused_border_color=RESERVE_AMBER, color=TEXT_PRIMARY, expand=True)
    memo_f = ft.TextField(label="메모 (선택)", value="모바일 실전 운용", border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY)

    def handle_create(evt):
        name = name_f.value.strip()
        ticker = ticker_f.value.strip().upper()
        strat_val = strat_f.value.strip()
        s_d = date_f.value.strip()
        memo = memo_f.value.strip()

        if not name:
            show_toast(app.page, "계좌명을 입력해주세요.", is_error=True)
            return

        try:
            seed = float(seed_f.value.strip())
            res_pct = float(reserve_f.value.strip())
            res_ratio = max(0.0, min(1.0, res_pct / 100.0))
        except Exception:
            show_toast(app.page, "시드 및 위기준비금 숫자를 확인해주세요.", is_error=True)
            return

        app.am.add_account(
            name=name,
            strategy=strat_val,
            ticker=ticker,
            start_date=s_d,
            initial_seed=seed,
            memo=memo,
            reserve_ratio=res_ratio
        )
        app.page.pop_dialog()
        show_toast(app.page, f"'{name}' 계좌가 생성되었습니다!")
        app.reload_data()

    dlg = ft.AlertDialog(
        title=ft.Row([ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=ACCENT_BLUE), ft.Text("새 계좌 등록", weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)], spacing=8),
        content=ft.Container(
            width=350,
            content=ft.Column(
                controls=[name_f, strat_f, ft.Row([ticker_f, date_f], spacing=6), ft.Row([seed_f, reserve_f], spacing=6), memo_f],
                spacing=8,
                tight=True
            )
        ),
        actions=[
            ft.TextButton("취소", on_click=lambda _: app.page.pop_dialog()),
            ft.FilledButton("계좌 생성", style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK), on_click=handle_create)
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=SURFACE_CARD
    )
    app.page.show_dialog(dlg)


def open_settings_dialog(app, acc_id: str):
    """계좌 설정 변경 대화상자를 표시합니다."""
    target = next((a for a in app.accounts if a['id'] == acc_id), None)
    if not target:
        return

    cur_reserve_pct = float(target.get('reserve_ratio', 0.05)) * 100.0
    name_f = ft.TextField(label="계좌 별칭", value=target.get('name', ''), border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY)
    seed_f = ft.TextField(label="초기 시드 ($)", value=str(target.get('initial_seed', 100000.0)), keyboard_type=ft.KeyboardType.NUMBER, border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY)

    slider_text = ft.Text(f"위기준비금: {cur_reserve_pct:.1f}%", size=13, weight=ft.FontWeight.BOLD, color=RESERVE_AMBER)
    slider = ft.Slider(min=0, max=20, divisions=20, value=cur_reserve_pct, active_color=RESERVE_AMBER, thumb_color=RESERVE_AMBER)
    slider.on_change = lambda e: (setattr(slider_text, 'value', f"위기준비금: {e.control.value:.1f}%"), app.page.update())

    memo_f = ft.TextField(label="메모", value=target.get('memo', ''), border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE, color=TEXT_PRIMARY)

    def handle_save(evt):
        try:
            new_name = name_f.value.strip()
            new_seed = float(seed_f.value.strip())
            new_res = slider.value / 100.0
            new_memo = memo_f.value.strip()

            app.am.update_account_settings(acc_id=acc_id, name=new_name, initial_seed=new_seed, reserve_ratio=new_res, memo=new_memo)
            app.page.pop_dialog()
            show_toast(app.page, "계좌 설정이 저장되었습니다.")
            app.reload_data()
        except Exception as ex:
            show_toast(app.page, f"저장 실패: {ex}", is_error=True)

    dlg = ft.AlertDialog(
        title=ft.Row([ft.Icon(ft.Icons.SETTINGS, color=ACCENT_BLUE), ft.Text("계좌 설정 변경", weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)], spacing=8),
        content=ft.Container(
            width=340,
            content=ft.Column(
                controls=[
                    name_f, seed_f, ft.Container(height=2), slider_text, slider, memo_f,
                    ft.Container(height=4),
                    ft.Row([
                        ft.Icon(ft.Icons.CODE_ROUNDED, size=14, color=ACCENT_BLUE),
                        ft.Text("App Dev: 이혁", size=11, color=ACCENT_BLUE, weight=ft.FontWeight.BOLD)
                    ], alignment=ft.MainAxisAlignment.END, spacing=4)
                ],
                spacing=8,
                tight=True
            )
        ),
        actions=[
            ft.TextButton("취소", on_click=lambda _: app.page.pop_dialog()),
            ft.FilledButton("설정 저장", style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK), on_click=handle_save)
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=SURFACE_CARD
    )
    app.page.show_dialog(dlg)


from mobile.widgets import build_confirm_dialog


def open_delete_account_dialog(app, acc_id: str):
    """계좌 삭제 확인 대화상자를 표시합니다."""
    target = next((a for a in app.accounts if a['id'] == acc_id), None)
    if not target:
        return
    name = target.get('name', '계좌')

    def handle_delete(evt):
        app.page.pop_dialog()
        success = app.am.delete_account(acc_id)
        if success:
            show_toast(app.page, f"'{name}' 계좌가 삭제되었습니다.")
            app.viewing_account_id = None
            app.reload_data()
        else:
            show_toast(app.page, "삭제 실패", is_error=True)

    dlg = build_confirm_dialog(
        title="계좌 삭제 확인",
        content=f"정말로 '{name}' 계좌를 영구 삭제하시겠습니까?\n모든 매매 기록 및 설정이 삭제됩니다.",
        on_confirm=handle_delete,
        confirm_text="계좌 삭제",
        cancel_text="닫기",
        is_danger=True,
        icon=ft.Icons.WARNING_AMBER_ROUNDED,
        page=app.page,
    )
    app.page.show_dialog(dlg)


def open_undo_dialog(app, acc_id: str):
    """최근 거래일 정산 기록 취소(Undo) 확인 대화상자를 표시합니다."""
    def handle_undo(evt):
        app.page.pop_dialog()
        ok = app.am.delete_last_day_record(acc_id)
        if ok:
            show_toast(app.page, "최근 거래일 정산 기록이 취소되었습니다.")
            app.reload_data()
        else:
            show_toast(app.page, "취소할 기록이 없습니다.", is_error=True)

    dlg = build_confirm_dialog(
        title="거래일 Undo 확인",
        content="가장 최근 거래일의 정산 기록을 삭제하고 이전 상태로 되돌리시겠습니까?",
        on_confirm=handle_undo,
        confirm_text="취소 실행",
        cancel_text="닫기",
        is_danger=True,
        icon=ft.Icons.UNDO,
        page=app.page,
    )
    app.page.show_dialog(dlg)


def open_edit_trade_dialog(app, acc_id: str, record_idx: int):
    """거래 슬롯 기록을 직접 수정하는 대화상자를 엽니다 (4대 섹션: 시장/매수/매도/손익)."""
    acc = next((a for a in app.accounts if a['id'] == acc_id), None)
    if not acc:
        return
    records = acc.get('trade_records', [])
    if record_idx < 0 or record_idx >= len(records):
        return

    target = records[record_idx]
    cur_d = str(target.get('Date', ''))
    cur_close = float(target.get('Close', 0.0))
    cur_mode = str(target.get('Mode', 'Normal'))
    cur_bq = int(target.get('BuyQty', target.get('R', 0)))
    cur_u = float(target.get('U', 0.0)) if target.get('U') is not None else 0.0
    cur_wd = str(target.get('W', '')) if (target.get('Sold') and target.get('W')) else ""
    cur_sp = float(target.get('X', 0.0)) if (target.get('Sold') and target.get('X') is not None) else 0.0
    cur_profit = float(target.get('Profit', 0.0)) if (target.get('Sold') and target.get('Profit') is not None) else 0.0

    date_f = ft.TextField(
        label="1. 거래일자 (매수일: YYYY-MM-DD)",
        value=cur_d,
        border_color=BORDER_COLOR,
        focused_border_color="#4ADE80",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )
    close_f = ft.TextField(
        label="종가 ($)",
        value=f"{cur_close:.2f}",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color="#4ADE80",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )
    mode_dd = ft.Dropdown(
        label="시장 모드",
        value=cur_mode if cur_mode in ["Normal", "Safe", "Riskoff"] else "Normal",
        options=[ft.dropdown.Option("Normal"), ft.dropdown.Option("Safe"), ft.dropdown.Option("Riskoff")],
        border_color=BORDER_COLOR,
        focused_border_color="#4ADE80",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )

    buy_q_f = ft.TextField(
        label="2. 매수량 (주)",
        value=str(cur_bq),
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color="#F472B6",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )
    target_u_f = ft.TextField(
        label="익절 목표가 ($)",
        value=f"{cur_u:.2f}" if cur_u > 0 else "",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color="#F472B6",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )

    sell_d_f = ft.TextField(
        label="3. 매도일 (미매도 시 빈칸)",
        value=cur_wd,
        border_color=BORDER_COLOR,
        focused_border_color="#60A5FA",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )
    sell_p_f = ft.TextField(
        label="매도가 ($)",
        value=f"{cur_sp:.2f}" if cur_sp > 0 else "",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color="#60A5FA",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )

    profit_f = ft.TextField(
        label="4. 실현 손익 ($)",
        value=f"{cur_profit:.2f}" if cur_profit != 0.0 else "",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color="#FBBF24",
        color=TEXT_PRIMARY,
        text_size=12,
        expand=True
    )

    def handle_save_edit(e):
        try:
            n_date = date_f.value.strip()
            n_close = float(close_f.value.strip())
            n_mode = mode_dd.value or "Normal"
            n_bq = int(buy_q_f.value.strip())
            n_u = float(target_u_f.value.strip()) if target_u_f.value.strip() else None
            n_sell_d = sell_d_f.value.strip()
            n_sell_p = float(sell_p_f.value.strip()) if sell_p_f.value.strip() else None
            n_profit = float(profit_f.value.strip()) if profit_f.value.strip() else None

            target['Date'] = n_date
            target['Close'] = n_close
            target['Mode'] = n_mode
            target['BuyQty'] = n_bq
            target['R'] = n_bq
            if n_u is not None:
                target['U'] = n_u

            if n_sell_d and n_sell_p is not None:
                target['Sold'] = True
                target['W'] = n_sell_d
                target['X'] = n_sell_p
                if n_profit is not None:
                    target['Profit'] = n_profit
                else:
                    bp = float(target.get('BuyPrice', n_close))
                    target['Profit'] = round((n_sell_p - bp) * n_bq, 2)
                bp = float(target.get('BuyPrice', n_close))
                target['ProfitRate'] = round((n_sell_p / bp - 1.0) * 100.0, 2) if bp > 0 else 0.0
            else:
                target['Sold'] = False
                target['W'] = None
                target['X'] = None
                target['Profit'] = None
                target['ProfitRate'] = None

            # Recompute Asset
            target_hold = int(target.get('Hold', 0))
            target_cash = float(target.get('Cash', 0.0))
            target['Asset'] = round(target_cash + n_close * target_hold, 2)

            app.am.save_accounts(app.accounts)
            app.page.pop_dialog()
            show_toast(app.page, f"{n_date} 거래 슬롯 정보가 수정되었습니다.")
            app.reload_data()
        except Exception as ex:
            show_toast(app.page, f"수정 저장 오류: {ex}", is_error=True)

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.EDIT_NOTE, color=ACCENT_BLUE),
            ft.Text(f"거래 슬롯 수정 ({format_kr_date(cur_d)})", weight=ft.FontWeight.BOLD, size=15, color=TEXT_PRIMARY)
        ], spacing=6),
        content=ft.Container(
            width=360,
            content=ft.Column(
                controls=[
                    ft.Text("🌿 1. 시장 정보", size=11, weight=ft.FontWeight.BOLD, color="#4ADE80"),
                    ft.Row([date_f, mode_dd], spacing=6),
                    close_f,
                    ft.Container(height=2),
                    ft.Text("🌸 2. 매수 정보", size=11, weight=ft.FontWeight.BOLD, color="#F472B6"),
                    ft.Row([buy_q_f, target_u_f], spacing=6),
                    ft.Container(height=2),
                    ft.Text("🌊 3. 매도 정보", size=11, weight=ft.FontWeight.BOLD, color="#60A5FA"),
                    ft.Row([sell_d_f, sell_p_f], spacing=6),
                    ft.Container(height=2),
                    ft.Text("🌾 4. 손익 정보", size=11, weight=ft.FontWeight.BOLD, color="#FBBF24"),
                    profit_f,
                    ft.Text("💡 한 행은 하나의 슬롯입니다. 매도일/매도가 입력 시 청산 처리됩니다.", size=10, color=TEXT_MUTED)
                ],
                spacing=6,
                tight=True,
                scroll=ft.ScrollMode.AUTO
            )
        ),
        actions=[
            ft.TextButton("취소", on_click=lambda _: app.page.pop_dialog()),
            ft.FilledButton(
                "수정 저장",
                style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK),
                on_click=handle_save_edit
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=SURFACE_CARD
    )
    app.page.show_dialog(dlg)


def open_custom_date_dialog(app, start_field: ft.TextField, end_field: ft.TextField, summary_text: ft.Text = None):
    """백테스트 날짜 범위를 직접 지정할 수 있는 전용 팝업 창을 띄웁니다."""
    cur_s = start_field.value or "2022-01-03"
    cur_e = end_field.value or datetime.now().strftime('%Y-%m-%d')

    dlg_start_f = ft.TextField(
        label="시작일 (YYYY-MM-DD)",
        value=cur_s,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        keyboard_type=ft.KeyboardType.DATETIME,
        expand=True,
        suffix=ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_color=ACCENT_BLUE,
            tooltip="달력 선택",
            on_click=lambda _: app.open_date_picker_for_field(dlg_start_f)
        )
    )

    dlg_end_f = ft.TextField(
        label="종료일 (YYYY-MM-DD)",
        value=cur_e,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        keyboard_type=ft.KeyboardType.DATETIME,
        expand=True,
        suffix=ft.IconButton(
            icon=ft.Icons.CALENDAR_MONTH,
            icon_color=ACCENT_BLUE,
            tooltip="달력 선택",
            on_click=lambda _: app.open_date_picker_for_field(dlg_end_f)
        )
    )

    def apply_preset(s, e):
        dlg_start_f.value = s
        dlg_end_f.value = e
        try:
            dlg_start_f.update()
            dlg_end_f.update()
        except Exception:
            pass

    now = datetime.now()
    presets = [
        ("최근 6개월", (now - timedelta(days=180)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
        ("최근 1년", (now - timedelta(days=365)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
        ("최근 2년", (now - timedelta(days=730)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')),
        ("2024~현재", "2024-01-02", now.strftime('%Y-%m-%d')),
        ("2023 랠리", "2023-01-03", "2023-12-29"),
        ("2022 하락장", "2022-01-03", "2022-12-30"),
        ("2020 코로나", "2020-01-02", "2020-09-30"),
        ("2019~2020", "2019-09-20", "2020-12-31"),
    ]

    preset_chips = [
        ft.Container(
            content=ft.Text(label, size=11, color=TEXT_PRIMARY, weight=ft.FontWeight.W_500),
            bgcolor=SURFACE_CONTAINER,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            on_click=lambda _, s=s, e=e: apply_preset(s, e)
        )
        for label, s, e in presets
    ]

    def handle_confirm(e):
        s_val = dlg_start_f.value.strip()
        e_val = dlg_end_f.value.strip()
        try:
            dt_s = datetime.strptime(s_val, '%Y-%m-%d')
            dt_e = datetime.strptime(e_val, '%Y-%m-%d')
        except Exception:
            show_toast(app.page, "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)", is_error=True)
            return

        if dt_s >= dt_e:
            show_toast(app.page, "종료일은 시작일보다 이후여야 합니다.", is_error=True)
            return

        start_field.value = s_val
        end_field.value = e_val
        app.bt_start_date = s_val
        app.bt_end_date = e_val
        try:
            start_field.update()
            end_field.update()
        except Exception:
            pass

        if summary_text is not None:
            summary_text.value = f"직접 기간: {s_val} ~ {e_val}"
            try:
                summary_text.update()
            except Exception:
                pass

        app.page.pop_dialog()
        app.page.update()
        show_toast(app.page, f"백테스트 기간이 설정되었습니다: {s_val} ~ {e_val}")

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.DATE_RANGE, color=ACCENT_BLUE, size=20),
            ft.Text("백테스트 날짜 직접 선택", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
        ], spacing=8),
        content=ft.Container(
            width=340,
            content=ft.Column(
                controls=[
                    ft.Text("원하는 날짜를 직접 입력하거나 달력/추천 프리셋을 터치하세요.", size=12, color=TEXT_SECONDARY),
                    ft.Container(height=4),
                    dlg_start_f,
                    dlg_end_f,
                    ft.Container(height=6),
                    ft.Text("자주 쓰는 추천 기간 프리셋:", size=11, color=TEXT_MUTED, weight=ft.FontWeight.BOLD),
                    ft.Row(controls=preset_chips, wrap=True, spacing=6),
                ],
                spacing=8
            )
        ),
        actions=[
            ft.TextButton("취소", on_click=lambda _: app.page.pop_dialog()),
            ft.FilledButton(
                "설정 적용",
                style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK),
                on_click=handle_confirm
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=SURFACE_CARD,
        shape=ft.RoundedRectangleBorder(radius=14)
    )
    app.page.show_dialog(dlg)
