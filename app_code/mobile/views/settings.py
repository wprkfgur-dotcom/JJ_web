import os
import sys
import subprocess
import threading
from datetime import datetime
import flet as ft

CURRENT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
설정 탭 뷰 (mobile.views.settings)

CSV 내보내기, Google Drive 동기화, 기준 환율 설정, 시장 DB 동기화,
GitHub Releases 자동 업데이트, 시스템 정보 및 버그 제보 카드 렌더링.
"""

from mobile.theme import (
    SURFACE_CARD, SURFACE_CONTAINER, BORDER_COLOR, ACCENT_BLUE, PROFIT_GREEN,
    LOSS_RED, RESERVE_AMBER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED
)
from mobile.helpers import (
    copy_text_to_clipboard, show_toast, make_bug_report_mailto
)
from core.cloud_sync import (
    get_sync_config, save_sync_config, is_sync_enabled,
    test_connection, upload_accounts_to_drive, download_accounts_from_drive,
    sync_local_with_drive, get_gas_script_code
)
from core.app_update import (
    APP_VERSION, APP_BUILD_DATE_STR, get_update_config, save_update_config, parse_download_url,
    DEFAULT_UPDATE_CHANNEL_URL, DEFAULT_RELEASES_WEB_URL,
    check_remote_version_info, trigger_apk_download
)
from core.data import fetch_market_data, get_db_date_range
from core.app_settings import set_exchange_rate


def build_settings_view(app) -> ft.Control:
    """설정 탭(ListView) 컴포넌트를 빌드합니다."""

    storage_base = os.environ.get("FLET_APP_STORAGE_DATA") or CURRENT_DIR
    exports_dir = os.path.join(storage_base, "exports")
    os.makedirs(exports_dir, exist_ok=True)

    acc_options = []
    for a in app.accounts:
        acc_options.append(ft.dropdown.Option(key=a['id'], text=f"{a.get('name', '계좌')} ({a.get('ticker', '')})"))

    selected_acc_id = app.accounts[0]['id'] if app.accounts else None

    export_acc_dd = ft.Dropdown(
        label="내보낼 계좌 선택",
        value=selected_acc_id,
        options=acc_options,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        expand=True
    )

    def handle_export_csv(e):
        aid = export_acc_dd.value
        if not aid:
            show_toast(app.page, "내보낼 계좌를 선택해주세요.", is_error=True)
            return

        target = next((a for a in app.accounts if a['id'] == aid), None)
        if not target:
            show_toast(app.page, "계좌를 찾을 수 없습니다.", is_error=True)
            return

        acc_name = target.get('name', '계좌').replace(' ', '_')
        now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{acc_name}_매매일지_{now_str}.csv"
        filepath = os.path.join(exports_dir, filename)

        try:
            ok = app.am.export_trade_records_csv(aid, filepath)
            if ok:
                show_toast(app.page, f"'{filename}' 파일로 저장되었습니다!")
            else:
                show_toast(app.page, "저장할 매매 일지 기록이 없습니다.", is_error=True)
        except Exception as ex:
            show_toast(app.page, f"CSV 내보내기 실패: {ex}", is_error=True)

    def handle_open_folder(e):
        try:
            if sys.platform == "win32":
                os.startfile(exports_dir)
            else:
                subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", exports_dir])
        except Exception as ex:
            show_toast(app.page, f"폴더 열기 실패: {ex}", is_error=True)

    # 1. CSV 내보내기 카드
    export_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.FILE_DOWNLOAD_OUTLINED, color=ACCENT_BLUE, size=20),
                            ft.Text("계좌 매매 내역 CSV 내보내기", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ],
                        spacing=6
                    ),
                    ft.Text("선택한 계좌의 일일 매매 기록(체결가, 수량, 현금, 잔고, 실현손익)을 엑셀용 CSV 파일로 저장합니다.", size=11, color=TEXT_SECONDARY),
                    ft.Container(height=4),
                    export_acc_dd,
                    ft.Container(height=4),
                    ft.Row(
                        controls=[
                            ft.FilledButton(
                                content=ft.Row([ft.Icon(ft.Icons.DOWNLOAD, size=16), ft.Text("CSV 내보내기", size=13, weight=ft.FontWeight.BOLD)], spacing=6),
                                style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK, shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding.symmetric(vertical=11)),
                                expand=True,
                                on_click=handle_export_csv
                            ),
                            ft.OutlinedButton(
                                content=ft.Row([ft.Icon(ft.Icons.FOLDER_OPEN, size=16, color=TEXT_PRIMARY), ft.Text("저장 폴더 열기", size=12, color=TEXT_PRIMARY)], spacing=4),
                                style=ft.ButtonStyle(side=ft.BorderSide(1, BORDER_COLOR), shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding.symmetric(vertical=11)),
                                expand=True,
                                on_click=handle_open_folder
                            )
                        ],
                        spacing=8
                    )
                ],
                spacing=8
            )
        )
    )

    # 2. Google Drive 클라우드 실시간 동기화 (Multi-Device Sync) 카드
    sync_cfg = get_sync_config()
    is_enabled = sync_cfg.get("sync_enabled", False)
    curr_url = sync_cfg.get("web_app_url", "")
    last_t = sync_cfg.get("last_sync_time") or "기록 없음"
    last_m = sync_cfg.get("last_sync_message") or ""

    sync_url_field = ft.TextField(
        label="Google Apps Script 웹 앱 URL",
        label_style=ft.TextStyle(size=11, color=TEXT_SECONDARY),
        value=curr_url,
        hint_text="https://script.google.com/macros/s/.../exec",
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=11.5,
        dense=True,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        expand=True
    )

    sync_status_text = ft.Text(
        f"• 상태: {'실시간 자동 동기화 가동 중 (Sync ON)' if (is_enabled and curr_url) else '동기화 꺼짐 (Sync OFF - 로컬 기기 보관)'}\n"
        f"• 최근 동기화: {last_t} ({last_m})\n"
        f"• 드라이브 폴더: Google Drive / JongJongTrader / accounts.json",
        size=11,
        color=PROFIT_GREEN if (is_enabled and curr_url) else TEXT_MUTED
    )

    sync_loading = ft.ProgressBar(visible=False, color=ACCENT_BLUE)

    def update_sync_status_ui():
        cfg = get_sync_config()
        en = cfg.get("sync_enabled", False)
        u = cfg.get("web_app_url", "")
        t = cfg.get("last_sync_time") or "기록 없음"
        m = cfg.get("last_sync_message") or ""
        is_active = bool(en and u)
        sync_status_text.value = (
            f"• 상태: {'실시간 자동 동기화 가동 중 (Sync ON)' if is_active else '동기화 꺼짐 (Sync OFF - 로컬 기기 보관)'}\n"
            f"• 최근 동기화: {t} ({m})\n"
            f"• 드라이브 폴더: Google Drive / JongJongTrader / accounts.json"
        )
        sync_status_text.color = PROFIT_GREEN if is_active else TEXT_MUTED
        sync_badge.content = ft.Text("Sync ON" if is_active else "Sync OFF", color=ft.Colors.WHITE, size=11, weight=ft.FontWeight.BOLD)
        sync_badge.bgcolor = PROFIT_GREEN if is_active else LOSS_RED
        sync_control_box.border = ft.Border.all(1, PROFIT_GREEN if is_active else BORDER_COLOR)
        sync_switch.value = is_active
        try:
            sync_status_text.update()
            sync_badge.update()
            sync_control_box.update()
            sync_switch.update()
        except Exception:
            pass

    def on_sync_switch_change(e):
        val = e.control.value
        cfg = get_sync_config()
        u = sync_url_field.value.strip()
        if val and (not u or not u.startswith("http")):
            e.control.value = False
            e.control.update()
            show_toast(app.page, "Google Apps Script 웹 앱 URL을 먼저 입력해주세요.", is_error=True)
            return
        cfg["sync_enabled"] = val
        cfg["web_app_url"] = u
        save_sync_config(cfg)
        update_sync_status_ui()
        if val:
            show_toast(app.page, "Google Drive 실시간 동기화가 활성화되었습니다!")
            import threading
            def _initial_sync():
                sync_loading.visible = True
                sync_loading.update()
                ok, msg = sync_local_with_drive(app.am)
                sync_loading.visible = False
                sync_loading.update()
                update_sync_status_ui()
                if ok:
                    show_toast(app.page, msg)
                    app.reload_data()
                else:
                    show_toast(app.page, f"동기화 오류: {msg}", is_error=True)
            threading.Thread(target=_initial_sync, daemon=True).start()
        else:
            show_toast(app.page, "Google Drive 동기화가 비활성화되었습니다. (로컬 단독 저장)")

    sync_badge = ft.Container(
        content=ft.Text("Sync ON" if is_enabled else "Sync OFF", color=ft.Colors.WHITE, size=11, weight=ft.FontWeight.BOLD),
        bgcolor=PROFIT_GREEN if is_enabled else LOSS_RED,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        border_radius=6
    )

    sync_switch = ft.Switch(
        value=is_enabled,
        active_color=PROFIT_GREEN,
        inactive_thumb_color=ft.Colors.GREY_500,
        on_change=on_sync_switch_change
    )

    sync_control_box = ft.Container(
        bgcolor=SURFACE_CONTAINER,
        border=ft.Border.all(1, PROFIT_GREEN if is_enabled else BORDER_COLOR),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        content=ft.Row(
            controls=[
                ft.Row([
                    ft.Icon(ft.Icons.POWER_SETTINGS_NEW, size=18, color=PROFIT_GREEN if is_enabled else TEXT_MUTED),
                    ft.Text("실시간 동기화 상태:", size=12.5, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    sync_badge
                ], spacing=6),
                sync_switch
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )
    )

    def handle_save_url(e):
        u = sync_url_field.value.strip()
        if not u or not u.startswith("http"):
            show_toast(app.page, "올바른 URL을 입력하세요 (https://...)", is_error=True)
            return
        cfg = get_sync_config()
        cfg["web_app_url"] = u
        save_sync_config(cfg)
        show_toast(app.page, "Google Apps Script URL이 저장되었습니다.")
        update_sync_status_ui()

    def handle_test_conn(e):
        u = sync_url_field.value.strip()
        if not u or not u.startswith("http"):
            show_toast(app.page, "Google Apps Script URL을 입력하세요.", is_error=True)
            return
        sync_loading.visible = True
        sync_loading.update()
        import threading
        def _bg():
            ok, msg = test_connection(u)
            sync_loading.visible = False
            sync_loading.update()
            if ok:
                show_toast(app.page, msg)
            else:
                show_toast(app.page, f"연결 실패: {msg}", is_error=True)
        threading.Thread(target=_bg, daemon=True).start()

    def handle_sync_now(e):
        if not is_sync_enabled():
            show_toast(app.page, "Google Drive 동기화 스위치를 먼저 켜주세요.", is_error=True)
            return
        sync_loading.visible = True
        sync_loading.update()
        import threading
        def _bg():
            ok, msg = sync_local_with_drive(app.am)
            sync_loading.visible = False
            sync_loading.update()
            update_sync_status_ui()
            if ok:
                show_toast(app.page, msg)
                app.reload_data()
            else:
                show_toast(app.page, f"동기화 실패: {msg}", is_error=True)
        threading.Thread(target=_bg, daemon=True).start()

    def handle_force_upload(e):
        u = sync_url_field.value.strip()
        if not u or not u.startswith("http"):
            show_toast(app.page, "웹 앱 URL을 먼저 입력해주세요.", is_error=True)
            return
        sync_loading.visible = True
        sync_loading.update()
        import threading
        def _bg():
            accs = app.am.load_accounts()
            ok, msg = upload_accounts_to_drive(accs, u)
            sync_loading.visible = False
            sync_loading.update()
            update_sync_status_ui()
            if ok:
                show_toast(app.page, f"구글 드라이브로 계좌 백업 업로드 완료 ({len(accs)}개 계좌)")
            else:
                show_toast(app.page, f"업로드 실패: {msg}", is_error=True)
        threading.Thread(target=_bg, daemon=True).start()

    def handle_force_download(e):
        u = sync_url_field.value.strip()
        if not u or not u.startswith("http"):
            show_toast(app.page, "웹 앱 URL을 먼저 입력해주세요.", is_error=True)
            return
        sync_loading.visible = True
        sync_loading.update()
        import threading
        def _bg():
            ok, drive_accs, msg = download_accounts_from_drive(u)
            sync_loading.visible = False
            sync_loading.update()
            update_sync_status_ui()
            if ok and drive_accs is not None:
                try:
                    if os.path.exists(app.am.filepath):
                        with open(app.am.filepath, 'r', encoding='utf-8') as rf:
                            with open(os.path.join(os.path.dirname(app.am.filepath), "accounts.backup.json"), 'w', encoding='utf-8') as wf:
                                wf.write(rf.read())
                except Exception:
                    pass
                app.am.save_accounts(drive_accs, skip_cloud_sync=True)
                show_toast(app.page, f"구글 드라이브에서 {len(drive_accs)}개 계좌를 복원했습니다!")
                app.reload_data()
            else:
                show_toast(app.page, f"다운로드 실패: {msg}", is_error=True)
        threading.Thread(target=_bg, daemon=True).start()

    def open_gas_guide_dialog(e):
        script_code = get_gas_script_code()
        guide_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(ft.Icons.CLOUD_DONE, color=ACCENT_BLUE, size=20),
                ft.Text("Google Drive 1분 연동 가이드", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
            ], spacing=8),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    controls=[
                        ft.Container(
                            padding=10,
                            bgcolor=SURFACE_CONTAINER,
                            border_radius=8,
                            content=ft.Column(
                                controls=[
                                    ft.Row([
                                        ft.Icon(ft.Icons.DESKTOP_WINDOWS, size=16, color=ACCENT_BLUE),
                                        ft.Text("PC 브라우저에서 1회 배포 권장 (1분 소요)", size=12, weight=ft.FontWeight.BOLD, color=ACCENT_BLUE)
                                    ], spacing=6),
                                    ft.Text(
                                        "모바일 웹 브라우저는 구글 정책상 개발자 도구('Google Apps Script') 메뉴가 보이지 않습니다.\n"
                                        "PC 브라우저에서 1분 만에 배포 후, 발급된 URL만 카카오톡(나에게 보내기) 등으로 폰에 복사해 오시면 가장 간편합니다!",
                                        size=11, color=TEXT_SECONDARY
                                    ),
                                    ft.Text("※ 폰에서 직접 하려면: 모바일 브라우저 메뉴(⋮)에서 '데스크톱 사이트'를 체크하세요.", size=10, color=TEXT_MUTED),
                                ],
                                spacing=4
                            )
                        ),
                        ft.Container(height=4),
                        ft.Container(
                            padding=10,
                            bgcolor=SURFACE_CONTAINER,
                            border_radius=8,
                            content=ft.Column(
                                controls=[
                                    ft.Text("1. PC 브라우저로 drive.google.com (또는 script.google.com) 접속", size=11, color=TEXT_PRIMARY),
                                    ft.Text("2. '+ 새로 만들기' -> '더보기' -> 'Google Apps Script' 생성", size=11, color=TEXT_PRIMARY),
                                    ft.Text("3. 기존 내용을 지우고 아래 스크립트 코드 전체 붙여넣기", size=11, color=TEXT_PRIMARY),
                                    ft.Text("4. 우측 상단 파란색 [배포] -> [새 배포] 클릭", size=11, color=TEXT_PRIMARY),
                                    ft.Text("   • 유형: [웹 앱(Web App)] 선택", size=11, color=ACCENT_BLUE),
                                    ft.Text("   • 다음 사용자 권한으로 실행: '나(내 이메일)'", size=11, color=TEXT_PRIMARY),
                                    ft.Text("   • 액세스 권한: '모든 사용자(Anyone)' 선택 (필수!)", size=11, color=PROFIT_GREEN, weight=ft.FontWeight.BOLD),
                                    ft.Text("5. [배포] 클릭 후 발급된 '웹 앱 URL' 복사 -> 앱에 붙여넣기 끝!", size=11, color=TEXT_PRIMARY),
                                ],
                                spacing=4
                            )
                        ),
                        ft.Container(height=4),
                        ft.Text("Google Apps Script 소스 코드 (길게 눌러 복사 가능):", size=11, color=TEXT_MUTED, weight=ft.FontWeight.BOLD),
                        ft.TextField(
                            value=script_code,
                            multiline=True,
                            min_lines=4,
                            max_lines=6,
                            read_only=True,
                            text_size=10,
                            border_color=BORDER_COLOR,
                            color=TEXT_PRIMARY,
                            content_padding=ft.Padding.all(8)
                        ),
                        ft.FilledButton(
                            content=ft.Row([
                                ft.Icon(ft.Icons.CONTENT_COPY, size=15),
                                ft.Text("스크립트 코드 전체 클립보드 복사", size=12, weight=ft.FontWeight.BOLD)
                            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                            style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK, shape=ft.RoundedRectangleBorder(radius=8)),
                            width=380,
                            on_click=lambda _: (copy_text_to_clipboard(app.page, script_code), show_toast(app.page, "Google Apps Script 코드가 복사되었습니다!"))
                        ),
                        ft.OutlinedButton(
                            content=ft.Row([
                                ft.Icon(ft.Icons.OPEN_IN_BROWSER, size=15, color=ACCENT_BLUE),
                                ft.Text("Google Apps Script 에디터 바로 열기", size=12, color=ACCENT_BLUE)
                            ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                            style=ft.ButtonStyle(side=ft.BorderSide(1, ACCENT_BLUE), shape=ft.RoundedRectangleBorder(radius=8)),
                            width=380,
                            url="https://script.google.com/home/start"
                        )
                    ],
                    spacing=6,
                    scroll=ft.ScrollMode.AUTO
                )
            ),
            actions=[
                ft.TextButton("닫기", on_click=lambda _: app.page.pop_dialog())
            ],
            bgcolor=SURFACE_CARD,
            shape=ft.RoundedRectangleBorder(radius=14)
        )
        app.page.show_dialog(guide_dlg)

    cloud_sync_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CLOUD_SYNC_ROUNDED, color=ACCENT_BLUE, size=20),
                            ft.Text("Google Drive 클라우드 실시간 동기화", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ],
                        spacing=6
                    ),
                    ft.Text(
                        "폰과 태블릿 등 여러 기기에서 동일한 구글 드라이브 폴더('JongJongTrader')를 통해 계좌 내역을 실시간으로 자동 동기화합니다.",
                        size=11,
                        color=TEXT_SECONDARY
                    ),
                    ft.Container(height=2),
                    sync_control_box,
                    ft.Container(height=2),
                    ft.Row(
                        controls=[
                            sync_url_field,
                            ft.FilledButton(
                                "적용",
                                style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK, shape=ft.RoundedRectangleBorder(radius=8)),
                                on_click=handle_save_url
                            ),
                            ft.OutlinedButton(
                                "테스트",
                                style=ft.ButtonStyle(side=ft.BorderSide(1, ACCENT_BLUE), shape=ft.RoundedRectangleBorder(radius=8)),
                                on_click=handle_test_conn
                            )
                        ],
                        spacing=6
                    ),
                    sync_status_text,
                    sync_loading,
                    ft.Container(height=2),
                    ft.Row(
                        controls=[
                            ft.FilledButton(
                                content=ft.Row([ft.Icon(ft.Icons.SYNC, size=15), ft.Text("지금 즉시 동기화", size=12, weight=ft.FontWeight.BOLD)], spacing=4),
                                style=ft.ButtonStyle(bgcolor=PROFIT_GREEN, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding.symmetric(vertical=10)),
                                expand=True,
                                on_click=handle_sync_now
                            ),
                            ft.OutlinedButton(
                                content=ft.Row([ft.Icon(ft.Icons.CLOUD_UPLOAD_OUTLINED, size=15, color=TEXT_PRIMARY), ft.Text("드라이브로 올리기", size=11, color=TEXT_PRIMARY)], spacing=4),
                                style=ft.ButtonStyle(side=ft.BorderSide(1, BORDER_COLOR), shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding.symmetric(vertical=10)),
                                expand=True,
                                tooltip="현재 기기의 계좌를 구글 드라이브에 강제 덮어쓰기 백업",
                                on_click=handle_force_upload
                            ),
                            ft.OutlinedButton(
                                content=ft.Row([ft.Icon(ft.Icons.CLOUD_DOWNLOAD_OUTLINED, size=15, color=TEXT_PRIMARY), ft.Text("드라이브에서 받기", size=11, color=TEXT_PRIMARY)], spacing=4),
                                style=ft.ButtonStyle(side=ft.BorderSide(1, BORDER_COLOR), shape=ft.RoundedRectangleBorder(radius=8), padding=ft.Padding.symmetric(vertical=10)),
                                expand=True,
                                tooltip="구글 드라이브의 계좌를 기기로 내려받아 적용 (기존 로컬 데이터는 자동 백업)",
                                on_click=handle_force_download
                            ),
                        ],
                        spacing=6
                    ),
                    ft.OutlinedButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.HELP_OUTLINE, size=15, color=ACCENT_BLUE),
                            ft.Text("1분 만에 끝내는 구글 드라이브 연동 가이드 & 스크립트 복사", size=11.5, color=ACCENT_BLUE, weight=ft.FontWeight.W_500)
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                        style=ft.ButtonStyle(
                            side=ft.BorderSide(1, ACCENT_BLUE),
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.Padding.symmetric(vertical=9)
                        ),
                        width=380,
                        on_click=open_gas_guide_dialog
                    )
                ],
                spacing=8
            )
        )
    )

    # 3. 환율 설정 카드
    rate_field = ft.TextField(
        label="기준 환율 (1 USD = N 원)",
        value=f"{app.exchange_rate:.0f}",
        keyboard_type=ft.KeyboardType.NUMBER,
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=13,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        expand=True
    )

    def handle_save_rate(e):
        try:
            app.exchange_rate = set_exchange_rate(float(rate_field.value.strip()))
            show_toast(app.page, f"기준 환율이 {app.exchange_rate:,.0f}원으로 변경되었습니다.")
            app.reload_data()
        except Exception:
            show_toast(app.page, "올바른 환율 숫자를 입력하세요.", is_error=True)

    rate_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CURRENCY_EXCHANGE, color=PROFIT_GREEN, size=20),
                            ft.Text("기준 환율 설정", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ],
                        spacing=6
                    ),
                    ft.Text("홈 화면 및 계좌 상세에서 달러 자산을 원화로 환산할 때 적용되는 기준 환율입니다.", size=11, color=TEXT_SECONDARY),
                    ft.Container(height=4),
                    ft.Row(
                        controls=[
                            rate_field,
                            ft.FilledButton(
                                "적용",
                                style=ft.ButtonStyle(bgcolor=PROFIT_GREEN, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=8)),
                                on_click=handle_save_rate
                            )
                        ],
                        spacing=8
                    )
                ],
                spacing=8
            )
        )
    )

    # 3. 버그 리포트 (Bug Report) 카드
    mailto_url = make_bug_report_mailto()

    bug_report_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.BUG_REPORT_OUTLINED, color=LOSS_RED, size=20),
                            ft.Text("버그 리포트 & 피드백 (Bug Report)", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ],
                        spacing=6
                    ),
                    ft.Text(
                        "앱 사용 중 오류가 발생했거나 개선 사항이 있으시면 언제든 메일을 보내주세요.\n"
                        "버튼을 누르면 스마트폰 메일 앱이 열리며 수신인과 양식이 자동 입력됩니다.",
                        size=11,
                        color=TEXT_SECONDARY
                    ),
                    ft.Container(height=4),
                    ft.FilledButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.EMAIL_OUTLINED, size=16),
                            ft.Text("Bug Report 메일 작성하기", size=13, weight=ft.FontWeight.BOLD)
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                        style=ft.ButtonStyle(
                            bgcolor=LOSS_RED,
                            color=ft.Colors.WHITE,
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.Padding.symmetric(vertical=12)
                        ),
                        width=380,
                        url=mailto_url,
                        on_click=lambda _: show_toast(app.page, "메일 작성 화면으로 이동합니다.")
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(vertical=2, horizontal=4),
                        content=ft.Text(
                            "• 직접 전송 시 수신인: wprkfgur@hotmail.com (길게 눌러 복사 가능)",
                            size=11,
                            color=TEXT_MUTED,
                            selectable=True
                        )
                    )
                ],
                spacing=8
            )
        )
    )

    # 4. 로컬 시세 DB 캐시 상태 및 동기화 카드
    soxl_min, soxl_max = get_db_date_range('SOXL')
    tqqq_min, tqqq_max = get_db_date_range('TQQQ')
    soxl_status = f"{soxl_min} ~ {soxl_max}" if soxl_min else "미구축"
    tqqq_status = f"{tqqq_min} ~ {tqqq_max}" if tqqq_min else "미구축"

    db_sync_loading = ft.ProgressBar(visible=False, color=ACCENT_BLUE)
    db_status_text = ft.Text(f"• SOXL: {soxl_status}\n• TQQQ: {tqqq_status}", size=11, color=TEXT_MUTED)

    def handle_sync_market_db(e):
        db_sync_loading.visible = True
        db_sync_loading.update()
        try:
            today_s = datetime.now().strftime('%Y-%m-%d')
            fetch_market_data('SOXL', '2019-01-01', today_s)
            fetch_market_data('TQQQ', '2019-01-01', today_s)
            s_min, s_max = get_db_date_range('SOXL')
            t_min, t_max = get_db_date_range('TQQQ')
            db_status_text.value = f"• SOXL: {s_min} ~ {s_max}\n• TQQQ: {t_min} ~ {t_max}"
            db_status_text.update()
            show_toast(app.page, "SOXL, TQQQ 로컬 시세 DB가 최신으로 동기화되었습니다!")
        except Exception as ex:
            show_toast(app.page, f"시세 DB 동기화 실패: {ex}", is_error=True)
        finally:
            db_sync_loading.visible = False
            db_sync_loading.update()

    cache_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.STORAGE_ROUNDED, color=ACCENT_BLUE, size=20),
                            ft.Text("로컬 시세 DB 캐시 (초고속 로딩)", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ],
                        spacing=6
                    ),
                    ft.Text("SOXL, TQQQ 시세를 내부 DB에 영구 보존하여 백테스트와 계좌 조회를 네트워크 지연 없이 0.01초 만에 실행합니다.", size=11, color=TEXT_SECONDARY),
                    db_status_text,
                    db_sync_loading,
                    ft.Container(height=2),
                    ft.OutlinedButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SYNC, size=15, color=ACCENT_BLUE),
                            ft.Text("최신 시세 수동 동기화", size=12, color=ACCENT_BLUE)
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                        style=ft.ButtonStyle(
                            side=ft.BorderSide(1, ACCENT_BLUE),
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.Padding.symmetric(vertical=10)
                        ),
                        width=380,
                        on_click=handle_sync_market_db
                    )
                ],
                spacing=8
            )
        )
    )

    # 5. 추후 확장 예정 설정 안내 카드
    future_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.AUTO_AWESOME, color=RESERVE_AMBER, size=20),
                            ft.Text("향후 추가 예정 설정", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ],
                        spacing=6
                    ),
                    ft.Text("다음 업데이트에서 다양한 개인화 및 자동화 설정이 제공될 예정입니다.", size=11, color=TEXT_SECONDARY),
                    ft.Container(height=4),
                    ft.Row([ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED, size=16, color=TEXT_MUTED), ft.Text("미국 프리마켓 장전 목표가 도달 알림", size=12, color=TEXT_MUTED)], spacing=8),
                    ft.Row([ft.Icon(ft.Icons.API, size=16, color=TEXT_MUTED), ft.Text("증권사 Open API 연동 및 자동 주문 전송", size=12, color=TEXT_MUTED)], spacing=8),
                    ft.Row([ft.Icon(ft.Icons.WIDGETS_OUTLINED, size=16, color=TEXT_MUTED), ft.Text("안드로이드 바탕화면 실시간 잔고 위젯", size=12, color=TEXT_MUTED)], spacing=8),
                ],
                spacing=6
            )
        )
    )

    # 5-2. 버전 확인 및 GitHub Releases 원클릭 자동 업데이트 카드
    update_cfg = get_update_config()
    saved_update_url = update_cfg.get("apk_update_url") or update_cfg.get("apk_drive_url") or DEFAULT_UPDATE_CHANNEL_URL
    if "drive.google.com" in str(saved_update_url):
        saved_update_url = DEFAULT_UPDATE_CHANNEL_URL

    update_url_field = ft.TextField(
        label="배포 GitHub 저장소 / 채널 링크",
        value=saved_update_url,
        hint_text=DEFAULT_UPDATE_CHANNEL_URL,
        label_style=ft.TextStyle(size=11, color=TEXT_SECONDARY),
        border_color=BORDER_COLOR,
        focused_border_color=ACCENT_BLUE,
        color=TEXT_PRIMARY,
        text_size=11,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        expand=True
    )

    update_status_text = ft.Text(
        f"현재 설치 버전: v{APP_VERSION} (최신 ARM64 배포판)",
        size=11,
        color=TEXT_MUTED
    )

    def handle_save_update_url(e):
        url_val = update_url_field.value.strip() or DEFAULT_UPDATE_CHANNEL_URL
        update_url_field.value = url_val
        cfg = get_update_config()
        cfg["apk_update_url"] = url_val
        save_update_config(cfg)
        show_toast(app.page, "업데이트 채널 링크가 저장되었습니다.")
        update_status_text.value = f"현재 버전: v{APP_VERSION} • GitHub 채널 연동 완료"
        app.page.update()

    def handle_reset_update_url(e):
        update_url_field.value = DEFAULT_UPDATE_CHANNEL_URL
        cfg = get_update_config()
        cfg["apk_update_url"] = DEFAULT_UPDATE_CHANNEL_URL
        save_update_config(cfg)
        show_toast(app.page, "기본 GitHub 배포 채널로 초기화되었습니다.")
        update_status_text.value = f"현재 버전: v{APP_VERSION} • GitHub 기본 채널 연결됨"
        app.page.update()

    def handle_check_and_update(e):
        url_val = update_url_field.value.strip() or DEFAULT_UPDATE_CHANNEL_URL
        download_fallback_url = parse_download_url(url_val)

        update_btn.disabled = True
        update_btn.content = ft.Row([
            ft.ProgressRing(width=16, height=16, stroke_width=2, color=ft.Colors.BLACK),
            ft.Text("최신 버전 확인 중...", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8)
        update_btn.update()

        def _worker():
            info = check_remote_version_info(url_val)
            update_btn.disabled = False
            update_btn.content = ft.Row([
                ft.Icon(ft.Icons.SYSTEM_UPDATE_ROUNDED, size=18, color=ft.Colors.BLACK),
                ft.Text("최신 버전 확인 및 업데이트", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8)
            update_btn.update()

            download_target_url = info.get("download_url") or download_fallback_url

            if info.get("status") == "success":
                cfg = get_update_config()
                cfg["apk_update_url"] = url_val
                cfg["last_check_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_update_config(cfg)
                update_status_text.value = f"설치 버전: v{APP_VERSION} • 최근 확인: {cfg['last_check_time']} (GitHub 연동)"
                update_status_text.update()

                notes_preview = info.get("release_notes", "")
                notes_ctrl = None
                if notes_preview:
                    clean_notes = notes_preview.replace("#", "").strip()[:180]
                    notes_ctrl = ft.Container(
                        padding=8,
                        bgcolor=ft.Colors.with_opacity(0.08, ACCENT_BLUE),
                        border_radius=6,
                        content=ft.Text(f"📋 업데이트 요약:\n{clean_notes}...", size=10, color=TEXT_SECONDARY)
                    )

                if not info.get("is_newer"):
                    # 1. 이미 최신 버전인 경우 (불필요한 대용량 다운로드 방지)
                    dialog_items = [
                        ft.Container(
                            padding=12,
                            bgcolor=ft.Colors.with_opacity(0.12, PROFIT_GREEN),
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, PROFIT_GREEN)),
                            border_radius=8,
                            content=ft.Text(
                                f"현재 이미 가장 최신 버전(v{APP_VERSION})을 사용하고 계십니다!\n새 버전이 없어 불필요한 데이터 다운로드를 방지했습니다.",
                                size=12,
                                weight=ft.FontWeight.W_500,
                                color=PROFIT_GREEN
                            )
                        ),
                        ft.Container(height=4),
                        ft.Row([ft.Text("• 현재 설치 버전:", size=11, color=TEXT_MUTED), ft.Text(f"v{APP_VERSION} (최신)", size=11, color=TEXT_PRIMARY, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• 릴리즈 제목:", size=11, color=TEXT_MUTED), ft.Text(str(info.get('release_name', '최신 릴리즈'))[:22], size=11, color=TEXT_PRIMARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• GitHub 배포일:", size=11, color=TEXT_MUTED), ft.Text(info.get('remote_date_str', APP_BUILD_DATE_STR), size=11, color=TEXT_PRIMARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• 배포 파일 크기:", size=11, color=TEXT_MUTED), ft.Text(f"{info.get('remote_size_mb', 0)} MB", size=11, color=TEXT_PRIMARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ]
                    if notes_ctrl:
                        dialog_items.append(notes_ctrl)
                    dialog_items.extend([
                        ft.Divider(color=BORDER_COLOR, height=1),
                        ft.Text("※ 앱을 초기화하거나 재설치할 목적이 아니라면 다시 다운로드하실 필요가 없습니다.", size=10, color=TEXT_MUTED)
                    ])

                    dlg = ft.AlertDialog(
                        modal=True,
                        title=ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, color=PROFIT_GREEN, size=22),
                            ft.Text("최신 버전 사용 중", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ], spacing=8),
                        content=ft.Container(
                            width=360,
                            content=ft.Column(
                                controls=dialog_items,
                                spacing=6,
                                tight=True
                            )
                        ),
                        actions=[
                            ft.TextButton("확인 (닫기)", on_click=lambda _: app.page.pop_dialog()),
                            ft.TextButton(
                                "강제 재다운로드",
                                url=download_target_url,
                                style=ft.ButtonStyle(color=TEXT_MUTED),
                                on_click=lambda _: (app.page.pop_dialog(), trigger_apk_download(download_target_url, app.page), show_toast(app.page, "GitHub에서 최신 APK 다운로드를 시작합니다..."))
                            )
                        ],
                        actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        bgcolor=SURFACE_CARD,
                        shape=ft.RoundedRectangleBorder(radius=14)
                    )
                    app.page.show_dialog(dlg)
                else:
                    # 2. 새로운 최신 버전이 있는 경우 (다운로드 확인 팝업)
                    dialog_items = [
                        ft.Container(
                            padding=12,
                            bgcolor=ft.Colors.with_opacity(0.12, ACCENT_BLUE),
                            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ACCENT_BLUE)),
                            border_radius=8,
                            content=ft.Text(
                                "GitHub Releases에 새로운 배포 버전이 등록되었습니다!\n지금 바로 업데이트하시겠습니까?",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                color=ACCENT_BLUE
                            )
                        ),
                        ft.Container(height=4),
                        ft.Row([ft.Text("• 현재 설치 버전:", size=11, color=TEXT_MUTED), ft.Text(f"v{APP_VERSION}", size=11, color=TEXT_SECONDARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• 최신 배포 버전:", size=11, color=TEXT_MUTED), ft.Text(f"v{info.get('remote_version') or '최신'}", size=11, color=PROFIT_GREEN, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• 릴리즈 제목:", size=11, color=TEXT_MUTED), ft.Text(str(info.get('release_name', '최신 릴리즈'))[:22], size=11, color=TEXT_PRIMARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• 배포 일시:", size=11, color=TEXT_MUTED), ft.Text(info.get('remote_date_str', '최신'), size=11, color=TEXT_PRIMARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([ft.Text("• 파일 크기:", size=11, color=TEXT_MUTED), ft.Text(f"{info.get('remote_size_mb', 0)} MB", size=11, color=TEXT_PRIMARY)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ]
                    if notes_ctrl:
                        dialog_items.append(notes_ctrl)
                    dialog_items.extend([
                        ft.Divider(color=BORDER_COLOR, height=1),
                        ft.Text("※ 다운로드 완료 후 상단 알림을 터치하면 기존 계좌 데이터를 유지한 채 바로 업데이트됩니다.", size=10, color=TEXT_MUTED)
                    ])

                    dlg = ft.AlertDialog(
                        modal=True,
                        title=ft.Row([
                            ft.Icon(ft.Icons.NEW_RELEASES_ROUNDED, color=ACCENT_BLUE, size=22),
                            ft.Text("새로운 업데이트 발견! 🚀", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ], spacing=8),
                        content=ft.Container(
                            width=360,
                            content=ft.Column(
                                controls=dialog_items,
                                spacing=6,
                                tight=True
                            )
                        ),
                        actions=[
                            ft.TextButton("나중에", on_click=lambda _: app.page.pop_dialog()),
                            ft.FilledButton(
                                "🚀 지금 업데이트 다운로드",
                                url=download_target_url,
                                style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK),
                                on_click=lambda _: (app.page.pop_dialog(), trigger_apk_download(download_target_url, app.page), show_toast(app.page, "GitHub에서 최신 APK 다운로드를 시작합니다..."))
                            )
                        ],
                        actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        bgcolor=SURFACE_CARD,
                        shape=ft.RoundedRectangleBorder(radius=14)
                    )
                    app.page.show_dialog(dlg)
            elif info.get("status") == "no_release":
                # 3. 릴리즈가 등록되지 않은 경우
                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, color=ACCENT_BLUE, size=22),
                        ft.Text("GitHub 릴리즈 미등록", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                    ], spacing=8),
                    content=ft.Container(
                        width=360,
                        content=ft.Column(
                            controls=[
                                ft.Text(info.get("message", "GitHub 저장소에 등록된 릴리즈가 없습니다."), size=12, color=TEXT_SECONDARY),
                                ft.Container(height=4),
                                ft.Text(f"저장소: {info.get('download_url')}", size=11, color=TEXT_MUTED)
                            ],
                            spacing=6,
                            tight=True
                        )
                    ),
                    actions=[
                        ft.TextButton("닫기", on_click=lambda _: app.page.pop_dialog()),
                        ft.FilledButton(
                            "저장소 열기",
                            url=info.get('download_url', DEFAULT_RELEASES_WEB_URL),
                            style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK),
                            on_click=lambda _: (app.page.pop_dialog(), trigger_apk_download(info.get('download_url', DEFAULT_RELEASES_WEB_URL), app.page))
                        )
                    ],
                    actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    bgcolor=SURFACE_CARD,
                    shape=ft.RoundedRectangleBorder(radius=14)
                )
                app.page.show_dialog(dlg)
            else:
                # 4. 네트워크 에러 등으로 확인 실패한 경우
                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Row([
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=RESERVE_AMBER, size=22),
                        ft.Text("버전 확인 실패", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                    ], spacing=8),
                    content=ft.Container(
                        width=360,
                        content=ft.Column(
                            controls=[
                                ft.Text(f"GitHub 서버 연결에 실패했습니다.\n사유: {info.get('error', '네트워크 오류')}", size=12, color=TEXT_SECONDARY),
                                ft.Container(height=4),
                                ft.Text("직접 다운로드를 시도하시겠습니까?", size=11, color=TEXT_MUTED)
                            ],
                            spacing=6,
                            tight=True
                        )
                    ),
                    actions=[
                        ft.TextButton("닫기", on_click=lambda _: app.page.pop_dialog()),
                        ft.FilledButton(
                            "직접 다운로드 시도",
                            url=download_target_url,
                            style=ft.ButtonStyle(bgcolor=ACCENT_BLUE, color=ft.Colors.BLACK),
                            on_click=lambda _: (app.page.pop_dialog(), trigger_apk_download(download_target_url, app.page), show_toast(app.page, "최신 APK 다운로드를 시작합니다..."))
                        )
                    ],
                    actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    bgcolor=SURFACE_CARD,
                    shape=ft.RoundedRectangleBorder(radius=14)
                )
                app.page.show_dialog(dlg)

        threading.Thread(target=_worker, daemon=True).start()

    update_btn = ft.FilledButton(
        content=ft.Row([
            ft.Icon(ft.Icons.SYSTEM_UPDATE_ROUNDED, size=18, color=ft.Colors.BLACK),
            ft.Text("최신 버전 확인 및 업데이트", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK)
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
        style=ft.ButtonStyle(
            bgcolor=ACCENT_BLUE,
            shape=ft.RoundedRectangleBorder(radius=10),
            padding=ft.Padding.symmetric(vertical=13, horizontal=14)
        ),
        expand=True,
        on_click=handle_check_and_update
    )

    app_update_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Row([
                                ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, color=ACCENT_BLUE, size=20),
                                ft.Text("버전 관리 및 GitHub Releases 자동 업데이트", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                            ], spacing=6),
                            ft.Container(
                                content=ft.Text(f"v{APP_VERSION}", size=11, color=PROFIT_GREEN, weight=ft.FontWeight.BOLD),
                                bgcolor=ft.Colors.with_opacity(0.15, PROFIT_GREEN),
                                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                                border_radius=6
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    # 공식 GitHub Releases 연동 상태 뱃지
                    ft.Container(
                        bgcolor=ft.Colors.with_opacity(0.1, PROFIT_GREEN),
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, PROFIT_GREEN)),
                        border_radius=8,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        content=ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE_ROUNDED, size=16, color=PROFIT_GREEN),
                            ft.Text(
                                "GitHub Releases 공식 배포 채널 연결됨 (jj_invest)",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=PROFIT_GREEN,
                                expand=True
                            )
                        ], spacing=8)
                    ),
                    ft.Text(
                        "버튼을 누르면 먼저 GitHub Releases의 최신 배포본과 현재 버전을 비교합니다. 이미 최신 버전이면 다운로드를 방지하고 팝업으로 안내하며, 새 릴리즈가 등록되었을 때만 안전하게 다운로드합니다.",
                        size=11,
                        color=TEXT_SECONDARY
                    ),
                    ft.Container(height=2),
                    # 원클릭 자동 업데이트 실행 버튼
                    update_btn,
                    update_status_text,
                    ft.Divider(color=BORDER_COLOR, height=1),
                    # 고급 설정: GitHub 링크 확인 및 수동 변경
                    ft.ExpansionTile(
                        title=ft.Text("배포 채널(GitHub 저장소) 확인 및 수동 변경 (선택사항)", size=11, color=TEXT_MUTED),
                        dense=True,
                        controls_padding=ft.Padding.only(top=4, bottom=6),
                        controls=[
                            ft.Row(
                                controls=[
                                    update_url_field,
                                    ft.IconButton(
                                        icon=ft.Icons.SAVE,
                                        icon_color=ACCENT_BLUE,
                                        tooltip="링크 저장",
                                        on_click=handle_save_update_url
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.RESTART_ALT,
                                        icon_color=TEXT_MUTED,
                                        tooltip="기본 링크로 초기화",
                                        on_click=handle_reset_update_url
                                    )
                                ],
                                spacing=2
                            ),
                            ft.Text(
                                "※ GitHub Releases(wprkfgur-dotcom/jj_invest/releases)에 새 APK가 등록되면 앱에서 즉시 감지하여 업데이트할 수 있습니다.",
                                size=10,
                                color=TEXT_MUTED
                            )
                        ]
                    )
                ],
                spacing=8
            )
        )
    )


    # 6. 앱 정보 및 개발자 크레딧 카드
    app_info_card = ft.Container(
        padding=16,
        bgcolor=SURFACE_CARD,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=ACCENT_BLUE),
                        ft.Text(f"종종 투자 모바일 (JongJong Mobile) v{APP_VERSION}", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ],
                    spacing=8
                ),
                ft.Divider(color=BORDER_COLOR, height=1),
                # 프로젝트 크레딧 (역할별 시각적 위계 적용)
                ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.12, ACCENT_BLUE),
                    border=ft.Border.all(1, ft.Colors.with_opacity(0.35, ACCENT_BLUE)),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                    content=ft.Row(
                        controls=[
                            ft.Row([
                                ft.Icon(ft.Icons.CODE_ROUNDED, size=18, color=ACCENT_BLUE),
                                ft.Text("App Development:", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ], spacing=6),
                            ft.Container(
                                content=ft.Text("이혁", size=13.5, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
                                bgcolor=ACCENT_BLUE,
                                padding=ft.Padding.symmetric(horizontal=9, vertical=3),
                                border_radius=6
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    content=ft.Row(
                        controls=[
                            ft.Row([
                                ft.Icon(ft.Icons.ANALYTICS_OUTLINED, size=15, color=TEXT_SECONDARY),
                                ft.Text("Logic Design:", size=12, weight=ft.FontWeight.W_600, color=TEXT_SECONDARY),
                            ], spacing=6),
                            ft.Text("최용민", size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=1),
                    content=ft.Row(
                        controls=[
                            ft.Row([
                                ft.Icon(ft.Icons.COFFEE_ROUNDED, size=13, color=TEXT_MUTED),
                                ft.Text("Do Nothing:", size=11, color=TEXT_MUTED),
                            ], spacing=6),
                            ft.Text("이종필, 윤석배", size=11, color=TEXT_MUTED)
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ),
                ft.Divider(color=BORDER_COLOR, height=1),
                ft.Text("엔진: Python 3.12 & Flutter (Flet 1.0.2) • 데이터: data/accounts.json, data/market_data.db", size=10, color=TEXT_MUTED),
            ],
            spacing=8
        )
    )

    return ft.ListView(
        controls=[
            export_card,
            ft.Container(height=6),
            cloud_sync_card,
            ft.Container(height=6),
            rate_card,
            ft.Container(height=6),
            cache_card,
            ft.Container(height=6),
            bug_report_card,
            ft.Container(height=6),
            app_update_card,
            ft.Container(height=6),
            future_card,
            ft.Container(height=6),
            app_info_card,
            ft.Container(height=20)
        ],
        spacing=8,
        expand=True
    )

    # =================================================================
    # 모달 다이얼로그 (계좌 추가, 계좌 설정, 계좌 삭제, Undo)
    # =================================================================
