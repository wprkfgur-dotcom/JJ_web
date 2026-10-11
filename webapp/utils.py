"""
공통 유틸리티: JSON 직렬화 클리너, 증시 상태, 인증/소유권 헬퍼
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request

from .config import DEFAULT_OWNER, am, um


def sanitize_for_json(val: Any) -> Any:
    """NumPy, Pandas, NaN, Infinity 등을 표준 JSON 직렬화 가능 객체로 변환"""
    if val is None:
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, datetime)):
        has_time = hasattr(val, "hour") and (val.hour or val.minute)
        return val.strftime("%Y-%m-%d %H:%M:%S") if has_time else val.strftime("%Y-%m-%d")
    if isinstance(val, pd.DataFrame):
        return sanitize_for_json(val.to_dict(orient="records"))
    if isinstance(val, pd.Series):
        return sanitize_for_json(val.to_dict())
    if isinstance(val, dict):
        return {str(k): sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, np.ndarray, set)):
        return [sanitize_for_json(x) for x in val]
    return val


def get_market_status() -> dict:
    """미국 증시 장 상태(개장/폐장/프리마켓) 및 각국 현재 시각 반환"""
    utc_now = datetime.now(timezone.utc)
    kst_now = utc_now + timedelta(hours=9)
    et_now = utc_now - timedelta(hours=4)  # 미국 동부시간(EDT) 기준 대략 산출

    et_hour = et_now.hour + et_now.minute / 60.0

    if et_now.weekday() >= 5:
        status, badge = "휴장 (주말)", "closed"
    elif 9.5 <= et_hour < 16.0:
        status, badge = "정규장 진행 중", "open"
    elif 4.0 <= et_hour < 9.5:
        status, badge = "프리마켓 (장전)", "pre"
    elif 16.0 <= et_hour < 20.0:
        status, badge = "애프터마켓 (장후)", "after"
    else:
        status, badge = "장 마감", "closed"

    fmt = "%Y-%m-%d %H:%M:%S"
    return {
        "status": status,
        "badge": badge,
        "kst": kst_now.strftime(fmt),
        "et": et_now.strftime(fmt),
        "utc": utc_now.strftime(fmt),
    }


# -------------------------------------------------------------------
# 인증 / 소유권
# -------------------------------------------------------------------
def get_current_user(request: Request) -> Optional[dict]:
    """요청 헤더(Bearer) 또는 쿼리 파라미터에서 세션 토큰을 검증하여 현재 회원 정보 반환"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip()
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        return None
    return um.get_user_by_token(token)


def current_username(request: Request) -> str:
    """현재 로그인 회원의 소문자 ID (비로그인 시 기본 소유자)"""
    user = get_current_user(request)
    return user["username"].lower() if user else DEFAULT_OWNER


def require_admin(request: Request) -> dict:
    """관리자 권한 검증 (실패 시 403)"""
    user = get_current_user(request)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자(Admin) 권한이 필요한 기능입니다.")
    return user


def get_owned_account(acc_id: str, request: Request, forbidden_msg: str) -> dict:
    """계좌 조회 + 소유자 검증 (없으면 404, 타인 계좌면 403)"""
    target = next((a for a in am.load_accounts() if a["id"] == acc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Account not found")
    if target.get("owner", DEFAULT_OWNER).lower() != current_username(request):
        raise HTTPException(status_code=403, detail=forbidden_msg)
    return target


def user_account_ids(username: str) -> list:
    """해당 회원이 소유한 계좌 ID 목록"""
    return [
        a["id"] for a in am.load_accounts()
        if a.get("owner", DEFAULT_OWNER).lower() == username.lower()
    ]


def default_role(user: dict) -> str:
    return user.get("role", "admin" if user["username"].lower() == DEFAULT_OWNER else "user")


def default_role_label(user: dict) -> str:
    return user.get("role_label", "관리자" if user["username"].lower() == DEFAULT_OWNER else "일반회원")
