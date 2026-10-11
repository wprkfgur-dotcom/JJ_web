"""
앱 일반 설정(환율 등) 영구 저장 모듈

data/app_settings.json 파일에 사용자 설정을 저장하여 앱 재시작 후에도 유지합니다.
"""
import os
import sys
import json
from typing import Any, Dict

if os.environ.get("FLET_APP_STORAGE_DATA"):
    BASE_DIR = os.environ.get("FLET_APP_STORAGE_DATA")
elif getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "app_settings.json")

DEFAULT_EXCHANGE_RATE = 1380.0  # 기본 USD/KRW 환율

DEFAULT_SETTINGS: Dict[str, Any] = {
    "exchange_rate": DEFAULT_EXCHANGE_RATE,
}


def load_settings(path: str = SETTINGS_FILE) -> Dict[str, Any]:
    """설정 파일을 읽습니다. 파일이 없거나 손상된 경우 기본값을 반환합니다."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update(data)
    except Exception as e:
        print(f"[AppSettings] 설정 로드 실패: {e}")
    return settings


def save_settings(settings: Dict[str, Any], path: str = SETTINGS_FILE) -> None:
    """설정 파일을 저장합니다."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[AppSettings] 설정 저장 실패: {e}")


def get_exchange_rate(path: str = SETTINGS_FILE) -> float:
    """저장된 기준 환율(1 USD = N 원)을 반환합니다."""
    try:
        rate = float(load_settings(path).get("exchange_rate", DEFAULT_EXCHANGE_RATE))
        return rate if rate > 0 else DEFAULT_EXCHANGE_RATE
    except (TypeError, ValueError):
        return DEFAULT_EXCHANGE_RATE


def set_exchange_rate(rate: float, path: str = SETTINGS_FILE) -> float:
    """기준 환율을 저장합니다. 0 이하 값은 ValueError를 발생시킵니다."""
    rate = float(rate)
    if rate <= 0:
        raise ValueError("환율은 0보다 커야 합니다.")
    settings = load_settings(path)
    settings["exchange_rate"] = rate
    save_settings(settings, path)
    return rate
