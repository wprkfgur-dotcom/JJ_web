"""
=====================================================================
사용자 인증 및 보안 관리 모듈 (User Manager)
- PBKDF2-HMAC-SHA256 (100,000회 반복 + 128비트 솔트) 단방향 암호화
- 원문 비밀번호 복호화 불가 (관리자/개발자도 조회 불가)
- 세션 토큰 관리 및 회원별 계좌 격리
=====================================================================
"""
import os
import json
import secrets
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")


def hash_password(password: str) -> str:
    """
    단방향 솔트 암호화 (PBKDF2-HMAC-SHA256 100,000회 반복)
    솔트(salt)와 해시(hash)를 결합하여 저장하므로 개발자/서버 관리자도 원문 복호화 불가.
    """
    salt = secrets.token_hex(16)  # 32글자 랜덤 16바이트 솔트
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        bytes.fromhex(salt),
        100_000
    ).hex()
    return f"{salt}:{key}"


def verify_password(password: str, hashed_str: str) -> bool:
    """
    비밀번호 검증 (Timing Attack 방지 compare_digest 사용)
    """
    try:
        if not hashed_str or ':' not in hashed_str:
            return False
        salt, key = hashed_str.split(':', 1)
        new_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            bytes.fromhex(salt),
            100_000
        ).hex()
        return secrets.compare_digest(key, new_key)
    except Exception:
        return False


class UserManager:
    def __init__(self, users_filepath: str = USERS_FILE, sessions_filepath: str = SESSIONS_FILE):
        self.users_file = users_filepath
        self.sessions_file = sessions_filepath
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.users_file), exist_ok=True)
        if not os.path.exists(self.users_file):
            self.save_users({})
        self._init_default_huxley()
        self._load_sessions()

    def _init_default_huxley(self):
        """기존 huxley 관리자 계정이 없으면 안전하게 암호화하여 초기화"""
        users = self.load_users()
        if "huxley" not in users:
            users["huxley"] = {
                "username": "huxley",
                "email": "huxley@oracle.server",
                "password_hash": hash_password("lee0320"),
                "name": "Huxley",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.save_users(users)
            print("[UserManager] 기본 huxley 계정 암호화 생성 완료.")

    def load_users(self) -> Dict[str, Any]:
        try:
            if not os.path.exists(self.users_file):
                return {}
            with open(self.users_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[UserManager] 사용자 파일 로드 오류: {e}")
            return {}

    def save_users(self, users: Dict[str, Any]):
        tmp_file = f"{self.users_file}.tmp"
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, self.users_file)

    def _load_sessions(self):
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'r', encoding='utf-8') as f:
                    self._memory_sessions = json.load(f)
        except Exception:
            self._memory_sessions = {}

    def _save_sessions(self):
        try:
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(self._memory_sessions, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def register_user(self, email: str, username: str, password: str) -> Dict[str, Any]:
        """
        신규 회원가입: 이메일, ID, PW만 입력받아 검증 후 암호화 저장
        """
        email_clean = email.strip().lower()
        uname_clean = username.strip().lower()
        pwd = password.strip()

        # 유효성 검사
        if not email_clean or not re.match(r"[^@]+@[^@]+\.[^@]+", email_clean):
            raise ValueError("올바른 이메일 형식을 입력해주세요.")

        if not uname_clean or len(uname_clean) < 3 or len(uname_clean) > 20:
            raise ValueError("아이디는 3자 이상 20자 이하이어야 합니다.")

        if not re.match(r"^[a-zA-Z0-9_]+$", uname_clean):
            raise ValueError("아이디는 영문, 숫자, 밑줄(_)만 사용할 수 있습니다.")

        if len(pwd) < 4:
            raise ValueError("비밀번호는 최소 4자 이상이어야 합니다.")

        users = self.load_users()

        # 중복 검사
        if uname_clean in users:
            raise ValueError("이미 존재하는 아이디입니다. 다른 아이디를 사용해주세요.")

        for u in users.values():
            if u.get("email", "").lower() == email_clean:
                raise ValueError("이미 등록된 이메일 주소입니다.")

        # 비밀번호 단방향 암호화 후 저장
        user_record = {
            "username": uname_clean,
            "email": email_clean,
            "password_hash": hash_password(pwd),
            "name": username.strip(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        users[uname_clean] = user_record
        self.save_users(users)

        return {
            "username": uname_clean,
            "email": email_clean,
            "name": username.strip(),
            "created_at": user_record["created_at"]
        }

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        사용자 로그인 검증
        """
        uname_clean = username.strip().lower()
        pwd = password.strip()

        users = self.load_users()
        user = users.get(uname_clean)
        if not user:
            # 이메일로도 로그인 허용
            for u in users.values():
                if u.get("email", "").lower() == uname_clean:
                    user = u
                    uname_clean = u["username"]
                    break

        if not user:
            return None

        # 단방향 해시 검증
        if not verify_password(pwd, user.get("password_hash", "")):
            return None

        return {
            "username": uname_clean,
            "email": user.get("email", ""),
            "name": user.get("name", uname_clean),
            "created_at": user.get("created_at", "")
        }

    def create_session(self, username: str) -> str:
        """암호학적으로 안전한 64자리 세션 토큰 생성 (30일 유효)"""
        token = "jj_" + secrets.token_hex(32)
        expire_dt = datetime.now() + timedelta(days=30)
        self._memory_sessions[token] = {
            "username": username,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": expire_dt.strftime("%Y-%m-%d %H:%M:%S")
        }
        self._save_sessions()
        return token

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """토큰으로 현재 사용자 정보 조회 및 만료 확인"""
        if not token:
            return None
        sess = self._memory_sessions.get(token)
        if not sess:
            return None

        exp_str = sess.get("expires_at")
        if exp_str:
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > exp_dt:
                    del self._memory_sessions[token]
                    self._save_sessions()
                    return None
            except Exception:
                pass

        users = self.load_users()
        u = users.get(sess["username"])
        if not u:
            return None

        return {
            "username": u["username"],
            "email": u.get("email", ""),
            "name": u.get("name", u["username"]),
            "created_at": u.get("created_at", "")
        }

    def delete_session(self, token: str):
        if token in self._memory_sessions:
            del self._memory_sessions[token]
            self._save_sessions()
