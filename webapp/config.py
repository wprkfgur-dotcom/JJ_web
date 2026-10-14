"""
JJ Invest 웹 서버 설정/공유 객체 (경로, 코어 모듈 sys.path 등록, 매니저 싱글턴)
"""
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "web" / "static"
TEMPLATE_DIR = BASE_DIR / "web" / "templates"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# data 디렉터리 및 accounts.json 초기 확인
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
ACCOUNTS_JSON = DATA_DIR / "accounts.json"
ACCOUNTS_EXAMPLE = DATA_DIR / "accounts.example.json"

if not ACCOUNTS_JSON.exists() and ACCOUNTS_EXAMPLE.exists():
    try:
        shutil.copy(ACCOUNTS_EXAMPLE, ACCOUNTS_JSON)
        print(f"[*] 예시 계좌 데이터 복사 완료: {ACCOUNTS_JSON}")
    except Exception as e:
        print(f"[!] 계좌 예시 데이터 복사 실패: {e}")

# 코어 모듈은 sys.path 등록 이후에 임포트해야 한다.
from core.account_manager import AccountManager  # noqa: E402
from core.user_manager import UserManager  # noqa: E402

DEFAULT_OWNER = "huxley"  # 비로그인 요청의 기본 소유자 (기존 동작 유지)

am = AccountManager(filepath=str(ACCOUNTS_JSON))
um = UserManager()
