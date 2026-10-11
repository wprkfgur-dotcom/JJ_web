"""
=====================================================================
종종이 & 무한매수 주식 매매 시스템 - 공통 UI 위젯 모듈 (mobile.widgets)
=====================================================================
모바일 UI 전반에서 반복적으로 사용되는 카드, 메트릭 타일, 섹션 헤더,
뱃지(Pill), 확인 다이얼로그, Empty State 등을 표준화하여 제공합니다.
"""

from typing import Callable, Optional, Union
import flet as ft

from mobile.theme import (
    SURFACE_CARD,
    SURFACE_CONTAINER,
    BORDER_COLOR,
    ACCENT_BLUE,
    LOSS_RED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
)


def build_card(
    content: ft.Control,
    padding: Union[int, float, ft.Padding] = 14,
    radius: int = 14,
    elevation: int = 2,
    border_color: str = BORDER_COLOR,
    bg_color: str = SURFACE_CARD,
    on_click: Optional[Callable] = None,
    expand: bool = False,
) -> ft.Card:
    """
    일관된 둥근 모서리, 배경색, 그림자 및 테두리를 갖춘 표준 카드를 반환합니다.
    on_click 콜백 지정 시 터치 가능한 인터랙티브 카드로 작동합니다.
    """
    pad = padding if isinstance(padding, ft.Padding) else ft.Padding.all(padding)
    container_kwargs = {
        "content": content,
        "padding": pad,
        "border_radius": radius,
    }
    if border_color:
        container_kwargs["border"] = ft.Border.all(1, border_color)
    if on_click is not None:
        container_kwargs["on_click"] = on_click

    return ft.Card(
        bgcolor=bg_color,
        elevation=elevation,
        shape=ft.RoundedRectangleBorder(radius=radius),
        content=ft.Container(**container_kwargs),
        expand=expand,
    )


def build_metric_tile(
    title: str,
    value: str,
    subtext: Optional[str] = None,
    icon: Optional[str] = None,
    icon_color: str = ACCENT_BLUE,
    value_color: str = TEXT_PRIMARY,
    title_color: str = TEXT_SECONDARY,
    subtext_color: str = TEXT_MUTED,
    bg_color: str = SURFACE_CARD,
    border_color: str = BORDER_COLOR,
    radius: int = 10,
    padding: int = 10,
    expand: bool = True,
) -> ft.Container:
    """
    핵심 수치(KPI)를 직관적으로 나타내는 표준 메트릭 박스를 생성합니다.
    (홈 탭의 4대 지표, 계좌 상세의 예수금/보유량/수익률 타일 등)
    """
    row_controls = []
    if icon:
        row_controls.append(ft.Icon(icon, size=15, color=icon_color))
    row_controls.append(ft.Text(title, size=11, color=title_color))

    col_controls = [
        ft.Row(controls=row_controls, spacing=4),
        ft.Container(height=2),
        ft.Text(value, size=14, weight=ft.FontWeight.BOLD, color=value_color),
    ]
    if subtext:
        col_controls.append(ft.Text(subtext, size=10, color=subtext_color))

    return ft.Container(
        bgcolor=bg_color,
        border=ft.Border.all(1, border_color) if border_color else None,
        border_radius=radius,
        padding=padding,
        content=ft.Column(controls=col_controls, spacing=1),
        expand=expand,
    )


def build_section_header(
    title: str,
    subtitle: Optional[str] = None,
    icon: Optional[str] = None,
    icon_color: str = ACCENT_BLUE,
    title_color: str = TEXT_PRIMARY,
    title_size: int = 13,
    action: Optional[ft.Control] = None,
) -> ft.Row:
    """
    아이콘, 제목, 서브텍스트 및 우측 액션(버튼/뱃지 등)이 포함된 섹션 헤더를 생성합니다.
    """
    left_controls = []
    if icon:
        left_controls.append(ft.Icon(icon, size=17, color=icon_color))
    left_controls.append(
        ft.Text(title, size=title_size, weight=ft.FontWeight.BOLD, color=title_color)
    )

    right_control = action
    if right_control is None and subtitle:
        right_control = ft.Text(subtitle, size=10, color=TEXT_MUTED)

    controls = [ft.Row(left_controls, spacing=6)]
    if right_control:
        controls.append(right_control)

    return ft.Row(
        controls=controls,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN if right_control else ft.MainAxisAlignment.START,
    )


def build_badge(
    text: str,
    color: str = ACCENT_BLUE,
    bg_opacity: float = 0.15,
    text_size: int = 11,
    font_weight: ft.FontWeight = ft.FontWeight.BOLD,
    radius: int = 4,
    padding_h: int = 6,
    padding_v: int = 2,
) -> ft.Container:
    """
    티커 태그, 모드 표시, 상태 알림 등을 위한 필(Pill) 스타일 뱃지를 반환합니다.
    """
    return ft.Container(
        content=ft.Text(text, size=text_size, color=color, weight=font_weight),
        bgcolor=ft.Colors.with_opacity(bg_opacity, color),
        padding=ft.Padding.symmetric(horizontal=padding_h, vertical=padding_v),
        border_radius=radius,
    )


def build_confirm_dialog(
    title: str,
    content: Union[str, ft.Control],
    on_confirm: Callable,
    on_cancel: Optional[Callable] = None,
    confirm_text: str = "확인",
    cancel_text: str = "취소",
    is_danger: bool = False,
    icon: Optional[str] = None,
    page: Optional[ft.Page] = None,
) -> ft.AlertDialog:
    """
    삭제, 취소, 초기화 등 확인이 필요한 모달 대화상자(AlertDialog)를 표준 규격으로 반환합니다.
    """
    icon_color = LOSS_RED if is_danger else ACCENT_BLUE
    btn_bgcolor = LOSS_RED if is_danger else ACCENT_BLUE
    btn_textcolor = ft.Colors.WHITE if is_danger else ft.Colors.BLACK

    dlg_icon = icon or (ft.Icons.WARNING_AMBER_ROUNDED if is_danger else ft.Icons.HELP_OUTLINE)

    def cancel_wrapper(e):
        if page:
            page.pop_dialog()
        if on_cancel:
            on_cancel(e)

    body_content = ft.Text(content, size=13, color=TEXT_SECONDARY) if isinstance(content, str) else content

    return ft.AlertDialog(
        title=ft.Row(
            controls=[
                ft.Icon(dlg_icon, color=icon_color),
                ft.Text(title, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
            ],
            spacing=8,
        ),
        content=body_content,
        actions=[
            ft.TextButton(cancel_text, on_click=cancel_wrapper),
            ft.FilledButton(
                confirm_text,
                style=ft.ButtonStyle(bgcolor=btn_bgcolor, color=btn_textcolor),
                on_click=on_confirm,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        bgcolor=SURFACE_CARD,
    )


def build_empty_state(
    icon: str = ft.Icons.SAVINGS_OUTLINED,
    title: str = "데이터가 없습니다",
    subtitle: Optional[str] = None,
    action_button: Optional[ft.Control] = None,
    top_padding: int = 80,
) -> ft.Column:
    """
    등록된 데이터나 목록이 비어있을 때 안내하는 일관된 빈 상태(Empty State) 화면을 생성합니다.
    """
    controls = [
        ft.Container(height=top_padding),
        ft.Icon(icon, size=64, color=TEXT_MUTED),
        ft.Text(title, size=16, weight=ft.FontWeight.W_600, color=TEXT_SECONDARY),
    ]
    if subtitle:
        controls.append(
            ft.Text(
                subtitle,
                size=13,
                color=TEXT_MUTED,
                text_align=ft.TextAlign.CENTER,
            )
        )
    if action_button:
        controls.extend([ft.Container(height=16), action_button])

    return ft.Column(
        controls=controls,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )
