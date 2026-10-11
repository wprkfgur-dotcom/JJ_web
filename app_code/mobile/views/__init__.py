"""
모바일 뷰 패키지 (mobile.views)
각 탭별 화면 컴포넌트 및 모달 대화상자를 모듈화하여 관리합니다.
"""

from mobile.views.home import build_home_view, build_empty_home_view, on_home_chart_inspect
from mobile.views.accounts import build_accounts_view
from mobile.views.account_detail import build_account_detail_view
from mobile.views.backtest import build_backtest_view
from mobile.views.strategies import build_strategies_view
from mobile.views.settings import build_settings_view
from mobile.views.dialogs import (
    open_add_account_dialog,
    open_settings_dialog,
    open_delete_account_dialog,
    open_undo_dialog,
    open_edit_trade_dialog,
    open_custom_date_dialog,
)

__all__ = [
    "build_home_view",
    "build_empty_home_view",
    "on_home_chart_inspect",
    "build_accounts_view",
    "build_account_detail_view",
    "build_backtest_view",
    "build_strategies_view",
    "build_settings_view",
    "open_add_account_dialog",
    "open_settings_dialog",
    "open_delete_account_dialog",
    "open_undo_dialog",
    "open_edit_trade_dialog",
    "open_custom_date_dialog",
]
