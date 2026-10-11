"""
인증(Auth) 및 관리자 회원 관리 라우터
"""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from ..config import am, um
from ..schemas import LoginRequest, RegisterRequest
from ..utils import (
    default_role,
    default_role_label,
    get_current_user,
    require_admin,
    user_account_ids,
)

router = APIRouter()


def _full_user_payload(user: dict, **extra) -> dict:
    """로그인/세션 확인 응답에 공통으로 쓰이는 사용자 정보"""
    return {
        "username": user["username"],
        "email": user.get("email", ""),
        "name": user["name"],
        "role": default_role(user),
        "role_label": default_role_label(user),
        "linked_accounts": user_account_ids(user["username"]),
        **extra,
    }


@router.post("/api/auth/register")
async def register(req: RegisterRequest):
    """신규 회원가입: 이메일, ID, PW만 입력받아 100,000회 PBKDF2 단방향 암호화 보관"""
    try:
        user = um.register_user(email=req.email, username=req.username, password=req.password)
        token = um.create_session(user["username"])
        return {
            "success": True,
            "token": token,
            "user": {
                "username": user["username"],
                "email": user["email"],
                "name": user["name"],
                "role": user.get("role", "user"),
                "role_label": user.get("role_label", "일반회원"),
                "created_at": user["created_at"],
            },
            "message": f"환영합니다! {user['name']}님 회원가입이 완료되었습니다.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[Register Error] {e}")
        raise HTTPException(status_code=500, detail="회원가입 처리 중 오류가 발생했습니다.")


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    """사용자 로그인 처리 (단방향 해시 검증 및 세션 토큰 발급)"""
    user = um.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    token = um.create_session(user["username"])
    return {
        "success": True,
        "token": token,
        "user": _full_user_payload(user, login_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    }


@router.get("/api/auth/me")
async def check_current_user(request: Request):
    """현재 로그인 세션 검증 및 사용자별 연동 계좌 상태 확인"""
    user = get_current_user(request)
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "user": _full_user_payload(user)}


@router.post("/api/auth/logout")
async def logout(request: Request):
    """로그아웃 처리 (세션 무효화)"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if token:
        um.delete_session(token)
    return {"success": True, "message": "성공적으로 로그아웃되었습니다."}


# -------------------------------------------------------------------
# 관리자 전용 회원 관리
# -------------------------------------------------------------------
@router.get("/api/admin/users")
async def admin_list_users(request: Request):
    """전체 회원 목록 조회 (관리자 전용: ID, 이메일, 회원 구분만 반환, PW는 비노출)"""
    require_admin(request)
    users = um.list_users()
    return {"success": True, "users": users, "total_count": len(users)}


@router.delete("/api/admin/users/{target_username}")
async def admin_delete_user(target_username: str, request: Request):
    """회원 계정 삭제 (관리자 전용: 본인/최고관리자 삭제 불가, 계좌 데이터 동시 정리)"""
    curr = require_admin(request)
    try:
        um.delete_user(target_username, curr["username"])
        del_acc_count = am.delete_accounts_by_owner(target_username)
        return {
            "success": True,
            "message": f"'{target_username}' 회원이 성공적으로 삭제되었습니다. (연동 계좌 {del_acc_count}개 정리됨)",
            "deleted_username": target_username,
            "deleted_accounts_count": del_acc_count,
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원 삭제 중 오류가 발생했습니다: {str(e)}")
