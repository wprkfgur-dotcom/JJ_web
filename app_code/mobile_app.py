"""
=====================================================================
종종이 & 무한매수 주식 매매 시스템 - 모바일/안드로이드 앱 (Flet)
=====================================================================
구조:
  - Application Shell & Router: 탭 네비게이션 및 계좌 전환 제어
  - 5대 탭 컴포넌트:
    1. [홈]: mobile.views.home (build_home_view)
    2. [계좌 현황]: mobile.views.accounts (build_accounts_view)
    3. [계좌 상세]: mobile.views.account_detail (build_account_detail_view)
    4. [백테스트]: mobile.views.backtest (build_backtest_view)
    5. [투자 전략]: mobile.views.strategies (build_strategies_view)
    6. [설정]: mobile.views.settings (build_settings_view)
  - 모달 다이얼로그: mobile.views.dialogs
"""
import sys
import os
import threading
from datetime import datetime

# UTF-8 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 모듈 탐색 경로
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import flet as ft

from core.account_manager import AccountManager
from core.cloud_sync import is_sync_enabled, sync_local_with_drive
from core.app_settings import get_exchange_rate
from mobile.theme import (
    BG_DARK, SURFACE_CARD, BORDER_COLOR, ACCENT_BLUE,
    LOSS_RED, TEXT_PRIMARY, TEXT_SECONDARY,
)
from mobile.helpers import (
    show_toast, parse_picked_date_str,
)
from mobile.views import (
    build_home_view,
    build_empty_home_view,
    on_home_chart_inspect,
    build_accounts_view,
    build_account_detail_view,
    build_backtest_view,
    build_strategies_view,
    build_settings_view,
    open_add_account_dialog,
    open_settings_dialog,
    open_delete_account_dialog,
    open_undo_dialog,
    open_edit_trade_dialog,
    open_custom_date_dialog,
)


class MobileTradingApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.am = AccountManager()
        self.exchange_rate = get_exchange_rate()  # 기준 환율 (1 USD = N 원), data/app_settings.json에 저장
        self.accounts = []
        self.accounts_details = []
        self.current_tab_index = 0       # 0: 홈, 1: 계좌 현황, 2: 백테스트, 3: 투자 전략, 4: 설정
        self.viewing_account_id = None    # None이면 메인 탭 표시, 특정 ID면 계좌 상세 화면 표시

        # 백테스트 상태 및 폼 입력값 영구 보존용
        self.bt_results = None
        self.bt_is_loading = False
        self.bt_ticker = "SOXL"
        self.bt_period = "최근 3년"
        self.bt_seed = "200000"
        self.bt_strat_jongjong = True
        self.bt_strat_infinite = True
        self.bt_strat_vr = True
        self.bt_strat_bnh = True
        self.bt_start_date = "2022-01-03"
        self.bt_end_date = datetime.now().strftime('%Y-%m-%d')
        self.bt_custom_visible = False

        # 차트 롱프레스 터치 인스펙션 상태
        self.home_chart_dates = []
        self.home_chart_vals = []
        self.home_val_banner = None

        self.bt_chart_dates = []
        self.bt_chart_series = []
        self.bt_val_banner = None

        # Flet 기본 창 설정 (스마트폰 크기 및 테마)
        self.page.title = "종종 투자 (JongJong Mobile)"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG_DARK
        self.page.padding = 0

        # 데스크톱 실행 시 안드로이드 폰 비율로 크기 고정
        if hasattr(self.page, "window") and self.page.window:
            self.page.window.width = 412
            self.page.window.height = 860
            self.page.window.resizable = True
            self.page.window.min_width = 360
            self.page.window.min_height = 600

        # 메인 컨텐츠 컨테이너
        self.content_container = ft.Container(
            expand=True,
            padding=ft.Padding.only(left=12, right=12, top=8, bottom=8)
        )

        # 상단 네비게이션 & 하단 네비게이션
        self._setup_app_bar()
        self._setup_bottom_nav()

        # 데이터 로드
        self.reload_data()

        # 구글 드라이브 실시간 동기화가 켜져 있는 경우 백그라운드에서 최신 계좌 자동 확인
        if is_sync_enabled():
            def _startup_sync():
                try:
                    ok, msg = sync_local_with_drive(self.am)
                    if ok:
                        self.reload_data()
                except Exception:
                    pass
            threading.Thread(target=_startup_sync, daemon=True).start()

    # -----------------------------------------------------------------
    # 달력 및 날짜 모달
    # -----------------------------------------------------------------
    def open_date_picker_for_field(self, target_field: ft.TextField, on_change_callback=None):
        """달력 모달을 띄워 날짜(YYYY-MM-DD)를 선택할 수 있게 합니다."""
        cur_val = datetime.now()
        if target_field.value:
            try:
                cur_val = datetime.strptime(target_field.value.strip()[:10], '%Y-%m-%d')
            except Exception:
                pass

        def on_date_picked(e):
            val = e.control.value or dp.value
            date_str = parse_picked_date_str(val, getattr(e, 'data', None))
            if date_str:
                target_field.value = date_str
                try:
                    target_field.update()
                except Exception:
                    pass
                if on_change_callback:
                    try:
                        on_change_callback(target_field.value)
                    except Exception:
                        pass
                try:
                    self.page.update()
                except Exception:
                    pass

        dp = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime(2035, 12, 31),
            value=cur_val,
            on_change=on_date_picked
        )
        self.page.show_dialog(dp)

    def open_custom_date_dialog(self, start_field: ft.TextField, end_field: ft.TextField, summary_text: ft.Text = None):
        """백테스트 날짜 범위를 직접 지정할 수 있는 전용 팝업 창을 띄웁니다."""
        open_custom_date_dialog(self, start_field, end_field, summary_text)

    # -----------------------------------------------------------------
    # 차트 인스펙션 핸들러
    # -----------------------------------------------------------------
    def _on_home_chart_inspect(self, local_x: float):
        on_home_chart_inspect(self, local_x)

    def _on_bt_chart_inspect(self, local_x: float):
        """백테스트 차트 롱프레스/터치 시 해당 X좌표의 각 검증 전략별 Y 자산 수치를 배너에 표시합니다."""
        if not self.bt_chart_dates or not self.bt_chart_series or not self.bt_val_banner:
            return
        pad_left = 65
        pad_right = 25
        chart_w = 650 - pad_left - pad_right
        ratio = max(0.0, min(1.0, (local_x - pad_left) / max(1.0, chart_w)))
        idx = int(round(ratio * (len(self.bt_chart_dates) - 1)))
        dt = self.bt_chart_dates[idx]

        items = [
            ft.Icon(ft.Icons.CALENDAR_MONTH, color=ACCENT_BLUE, size=14),
            ft.Text(f"{dt}", size=12, weight=ft.FontWeight.BOLD, color=ACCENT_BLUE),
        ]
        for s in self.bt_chart_series:
            v = s['vals'][idx] if idx < len(s['vals']) else 0.0
            s_name_short = s['name'].split()[0]
            items.append(ft.Container(width=4))
            items.append(ft.Container(width=7, height=7, bgcolor=s['color'], border_radius=4))
            items.append(ft.Text(f"{s_name_short}: ${v:,.0f}", size=11, weight=ft.FontWeight.BOLD, color=s['color']))

        self.bt_val_banner.content = ft.Row(
            controls=items,
            spacing=3,
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.page.update()

    # -----------------------------------------------------------------
    # 상단 및 하단 네비게이션
    # -----------------------------------------------------------------
    def _setup_app_bar(self):
        self.title_text = ft.Text("종종 투자 포트폴리오", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
        self.subtitle_text = ft.Text("전체 계좌 통합 자산", size=11, color=TEXT_SECONDARY)

        self.leading_icon = ft.Container(
            content=ft.Icon(ft.Icons.SAVINGS_OUTLINED, color=ACCENT_BLUE, size=22),
            padding=ft.Padding.only(left=12)
        )

        self.action_buttons = [
            ft.IconButton(
                icon=ft.Icons.CLOUD_SYNC_ROUNDED,
                icon_color=ACCENT_BLUE,
                tooltip="구글 드라이브 동기화",
                on_click=lambda e: self.handle_quick_cloud_sync()
            ),
            ft.IconButton(
                icon=ft.Icons.REFRESH_ROUNDED,
                icon_color=TEXT_SECONDARY,
                tooltip="새로고침",
                on_click=lambda e: self.reload_data(show_message=True)
            )
        ]

        self.page.appbar = ft.AppBar(
            leading=self.leading_icon,
            title=ft.Column(
                controls=[self.title_text, self.subtitle_text],
                spacing=1,
                alignment=ft.MainAxisAlignment.CENTER
            ),
            actions=self.action_buttons,
            bgcolor=SURFACE_CARD,
            elevation=2
        )

    def handle_quick_cloud_sync(self):
        """상단 앱바 클라우드 아이콘 터치 시 구글 드라이브 동기화를 실행합니다."""
        if not is_sync_enabled():
            show_toast(self.page, "설정 탭에서 Google Drive 동기화를 켜주세요.")
            return
        show_toast(self.page, "Google Drive와 동기화 진행 중...")
        def _bg_sync():
            ok, msg = sync_local_with_drive(self.am)
            if ok:
                show_toast(self.page, msg)
                self.reload_data()
            else:
                show_toast(self.page, f"동기화 실패: {msg}", is_error=True)
        threading.Thread(target=_bg_sync, daemon=True).start()

    def _setup_bottom_nav(self):
        self.bottom_nav = ft.NavigationBar(
            selected_index=0,
            bgcolor=SURFACE_CARD,
            indicator_color=ft.Colors.with_opacity(0.2, ACCENT_BLUE),
            destinations=[
                ft.NavigationBarDestination(
                    icon=ft.Icons.HOME_OUTLINED,
                    selected_icon=ft.Icons.HOME_ROUNDED,
                    label="홈"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                    selected_icon=ft.Icons.ACCOUNT_BALANCE_WALLET_ROUNDED,
                    label="계좌 현황"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.ANALYTICS_OUTLINED,
                    selected_icon=ft.Icons.ANALYTICS_ROUNDED,
                    label="백테스트"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.MENU_BOOK_OUTLINED,
                    selected_icon=ft.Icons.MENU_BOOK_ROUNDED,
                    label="투자 전략"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    selected_icon=ft.Icons.SETTINGS_ROUNDED,
                    label="설정"
                ),
            ],
            on_change=self.on_nav_change
        )
        self.page.navigation_bar = self.bottom_nav

    def reload_data(self, show_message: bool = False):
        """모든 계좌 및 각 계좌별 상세 연산을 재실행합니다."""
        self.accounts = self.am.load_accounts()
        self.accounts_details = []

        for acc in self.accounts:
            try:
                dtl = self.am.compute_account_details(acc)
                self.accounts_details.append(dtl)
            except Exception as ex:
                print(f"계좌({acc.get('name')}) 연산 오류: {ex}")

        self._render_current_view()

        if show_message:
            show_toast(self.page, "데이터가 새로고침되었습니다.")

    def on_nav_change(self, e):
        self.current_tab_index = e.control.selected_index
        self.viewing_account_id = None  # 탭 이동 시 상세 화면 탈출
        self._render_current_view()

    def open_account_detail(self, account_id: str):
        """특정 계좌의 상세 페이지로 전환합니다."""
        self.viewing_account_id = account_id
        self._render_current_view()

    def back_to_accounts(self, e=None):
        """계좌 상세 페이지에서 다시 계좌 목록으로 복귀합니다."""
        self.viewing_account_id = None
        self._render_current_view()

    def _render_current_view(self):
        # 1. 상세 페이지 모드인 경우
        if self.viewing_account_id:
            target_acc = next((a for a in self.accounts if a['id'] == self.viewing_account_id), None)
            target_dtl = next((d for d in self.accounts_details if d.get('account_id') == self.viewing_account_id), None)

            if target_acc and target_dtl:
                self._update_appbar_for_detail(target_acc)
                self.page.floating_action_button = None
                self.content_container.content = self._build_account_detail_view(target_acc, target_dtl)
                self.page.update()
                return

        # 2. 메인 탭 모드인 경우
        self._update_appbar_for_tabs()

        if self.current_tab_index == 0:
            self.page.floating_action_button = None
            self.content_container.content = self._build_home_tab()
        elif self.current_tab_index == 1:
            # 계좌 현황 탭: 우측 하단 단일 '+' 원형 FAB 활성화
            self.page.floating_action_button = ft.FloatingActionButton(
                icon=ft.Icons.ADD,
                shape=ft.CircleBorder(),
                bgcolor=ACCENT_BLUE,
                foreground_color=ft.Colors.BLACK,
                tooltip="새 계좌 추가",
                on_click=self.open_add_account_dialog
            )
            self.content_container.content = self._build_accounts_tab()
        elif self.current_tab_index == 2:
            self.page.floating_action_button = None
            self.content_container.content = self._build_backtest_tab()
        elif self.current_tab_index == 3:
            self.page.floating_action_button = None
            self.content_container.content = self._build_strategies_tab()
        elif self.current_tab_index == 4:
            self.page.floating_action_button = None
            self.content_container.content = self._build_settings_tab()

        self.page.update()

    def _update_appbar_for_tabs(self):
        if self.current_tab_index == 0:
            self.title_text.value = "종종 투자 포트폴리오"
            self.subtitle_text.value = "전체 계좌 통합 자산 현황"
            self.leading_icon.content = ft.Icon(ft.Icons.SAVINGS_OUTLINED, color=ACCENT_BLUE, size=22)
        elif self.current_tab_index == 1:
            self.title_text.value = "계좌 현황"
            self.subtitle_text.value = f"총 {len(self.accounts)}개 계좌 운용 중"
            self.leading_icon.content = ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, color=ACCENT_BLUE, size=22)
        elif self.current_tab_index == 2:
            self.title_text.value = "전략 백테스트"
            self.subtitle_text.value = "시뮬레이션 및 복수 전략 비교"
            self.leading_icon.content = ft.Icon(ft.Icons.ANALYTICS_OUTLINED, color=ACCENT_BLUE, size=22)
        elif self.current_tab_index == 3:
            self.title_text.value = "투자 전략 가이드"
            self.subtitle_text.value = "종종이 & 무한매수법 v4.0 핵심 원리"
            self.leading_icon.content = ft.Icon(ft.Icons.MENU_BOOK_ROUNDED, color=ACCENT_BLUE, size=22)
        elif self.current_tab_index == 4:
            self.title_text.value = "환경 설정"
            self.subtitle_text.value = "데이터 내보내기 및 시스템 설정"
            self.leading_icon.content = ft.Icon(ft.Icons.SETTINGS_OUTLINED, color=ACCENT_BLUE, size=22)

        if self.page.appbar:
            self.page.appbar.leading = self.leading_icon
            self.page.appbar.actions = [
                ft.IconButton(
                    icon=ft.Icons.CLOUD_SYNC_ROUNDED,
                    icon_color=ACCENT_BLUE,
                    tooltip="구글 드라이브 동기화",
                    on_click=lambda e: self.handle_quick_cloud_sync()
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH_ROUNDED,
                    icon_color=TEXT_SECONDARY,
                    tooltip="새로고침",
                    on_click=lambda e: self.reload_data(show_message=True)
                )
            ]

    def _update_appbar_for_detail(self, target_acc: dict):
        acc_name = target_acc.get('name', '계좌')
        ticker = target_acc.get('ticker', 'SOXL')
        strat = target_acc.get('strategy', '종종이 기본전략')

        self.title_text.value = f"{acc_name} ({ticker})"
        self.subtitle_text.value = strat

        if self.page.appbar:
            self.page.appbar.leading = ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=TEXT_PRIMARY,
                tooltip="계좌 목록으로",
                on_click=self.back_to_accounts
            )
            self.page.appbar.actions = [
                ft.IconButton(
                    icon=ft.Icons.CLOUD_SYNC_ROUNDED,
                    icon_color=ACCENT_BLUE,
                    tooltip="구글 드라이브 동기화",
                    on_click=lambda e: self.handle_quick_cloud_sync()
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS_OUTLINED,
                    icon_color=TEXT_SECONDARY,
                    tooltip="계좌 설정",
                    on_click=lambda e, aid=target_acc['id']: self.open_settings_dialog(aid)
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=LOSS_RED,
                    tooltip="계좌 삭제",
                    on_click=lambda e, aid=target_acc['id']: self.open_delete_account_dialog(aid)
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH_ROUNDED,
                    icon_color=TEXT_SECONDARY,
                    tooltip="새로고침",
                    on_click=lambda e: self.reload_data(show_message=True)
                )
            ]

    # -----------------------------------------------------------------
    # 각 탭 뷰 위임 (mobile.views)
    # -----------------------------------------------------------------
    def _build_home_tab(self):
        return build_home_view(self)

    def _build_empty_home_view(self):
        return build_empty_home_view(self)

    def _goto_tab(self, index: int):
        self.bottom_nav.selected_index = index
        self.current_tab_index = index
        self.viewing_account_id = None
        self._render_current_view()

    def _build_accounts_tab(self):
        return build_accounts_view(self)

    def _build_account_detail_view(self, acc: dict, dtl: dict):
        return build_account_detail_view(self, acc, dtl)

    def _build_backtest_tab(self):
        return build_backtest_view(self)

    def _build_strategies_tab(self):
        return build_strategies_view()

    def _build_settings_tab(self):
        return build_settings_view(self)

    # -----------------------------------------------------------------
    # 모달 다이얼로그 위임 (mobile.views.dialogs)
    # -----------------------------------------------------------------
    def open_add_account_dialog(self, e=None):
        open_add_account_dialog(self, e)

    def open_settings_dialog(self, acc_id: str):
        open_settings_dialog(self, acc_id)

    def open_delete_account_dialog(self, acc_id: str):
        open_delete_account_dialog(self, acc_id)

    def open_undo_dialog(self, acc_id: str):
        open_undo_dialog(self, acc_id)

    def open_edit_trade_dialog(self, acc_id: str, record_idx: int):
        open_edit_trade_dialog(self, acc_id, record_idx)


# =====================================================================
# 애플리케이션 엔트리 포인트
# =====================================================================
def main(page: ft.Page):
    if sys.platform == "win32":
        page.title = "종종이 & 무한매수 트레이더 (Windows Debug)"
        page.window.width = 440
        page.window.height = 890
        page.window.resizable = True
    app = MobileTradingApp(page)
    page.add(app.content_container)


if __name__ == "__main__":
    ft.run(main)
