"""
계좌 관리 및 자산 입출금 영속성 관리 모듈 (Account Manager) - 하위 호환성 브릿지
코어 로직은 core.account_manager 로 이관되었습니다.
"""
from core.account_manager import (
    AccountManager,
    BASE_DIR,
    DATA_DIR,
    ACCOUNTS_FILE,
)

__all__ = [
    "AccountManager",
    "BASE_DIR",
    "DATA_DIR",
    "ACCOUNTS_FILE",
]
