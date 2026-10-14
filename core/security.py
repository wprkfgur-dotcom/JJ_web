"""
=====================================================================
보안 암호화 모듈 (Security & Encryption)
- 증권사 Open API App Key 및 App Secret 안전 암호화/복호화
- cryptography.fernet.Fernet 기반 대칭키 암호화
- 서버 로컬 data/.secret_key 파일에 마스터 키 격리 보관
=====================================================================
"""
import os
import base64
from typing import Optional
from cryptography.fernet import Fernet

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SECRET_KEY_PATH = os.path.join(DATA_DIR, ".secret_key")


def _get_or_create_master_key() -> bytes:
    """마스터 암호화 키를 안전하게 로드하거나 최초 1회 생성"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_KEY_PATH):
        try:
            with open(SECRET_KEY_PATH, "rb") as f:
                key = f.read().strip()
                if len(key) == 44:  # Fernet key standard length
                    return key
        except Exception:
            pass

    # 신규 32바이트 url-safe base64 키 생성
    new_key = Fernet.generate_key()
    try:
        with open(SECRET_KEY_PATH, "wb") as f:
            f.write(new_key)
        # Linux / Ubuntu 환경 권한 축소 (600)
        try:
            os.chmod(SECRET_KEY_PATH, 0o600)
        except Exception:
            pass
    except Exception as e:
        print(f"마스터 암호화 키 저장 실패: {e}")
    return new_key


_cipher_suite: Optional[Fernet] = None


def _get_cipher() -> Fernet:
    global _cipher_suite
    if _cipher_suite is None:
        key = _get_or_create_master_key()
        _cipher_suite = Fernet(key)
    return _cipher_suite


def encrypt_credential(text: str) -> str:
    """민감 문자열(App Key / Secret)을 Fernet 암호화하여 Base64 문자열로 반환"""
    if not text:
        return ""
    cipher = _get_cipher()
    token = cipher.encrypt(text.strip().encode("utf-8"))
    return token.decode("utf-8")


def decrypt_credential(cipher_text: str) -> str:
    """암호화된 Base64 문자열을 복호화하여 원문 반환"""
    if not cipher_text:
        return ""
    try:
        cipher = _get_cipher()
        raw = cipher.decrypt(cipher_text.strip().encode("utf-8"))
        return raw.decode("utf-8")
    except Exception as e:
        print(f"복호화 실패: {e}")
        return ""


def mask_credential(text: str) -> str:
    """민감 문자열 마스킹 (예: PSIJ8r...eDGl)"""
    if not text:
        return ""
    s = text.strip()
    if len(s) <= 8:
        return "********"
    return f"{s[:6]}...{s[-4:]}"
