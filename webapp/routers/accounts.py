"""
계좌(Accounts) 라우터: 목록/상세/CRUD/운용(진행·정산·입출금·되돌리기)
"""
from fastapi import APIRouter, HTTPException, Request

from core.telegram_notifier import notify_order_generation

from ..config import DEFAULT_OWNER, am
from ..schemas import (
    AdjustmentRequest,
    CreateAccountRequest,
    SettlementRequest,
    UpdateAccountRequest,
    AccountBrokerConfigRequest,
)
from ..utils import current_username, get_owned_account, sanitize_for_json

router = APIRouter(prefix="/api/accounts")


def _pick(details: dict, key: str, fallback):
    """compute_account_details 결과값이 None 이면 fallback 사용"""
    val = details.get(key)
    return fallback if val is None else val


def _summarize_account(acc: dict, owner: str):
    """계좌 1건을 목록 카드용 요약으로 변환한다.

    Returns:
        (요약 dict, 반올림 전 총자산, 반올림 전 현금, 시드) - 포트폴리오 합계는 반올림 전 값으로 누적한다.
    계산 실패 시 예외를 전파한다.
    """
    details = am.compute_account_details(acc)

    seed = float(details.get("net_invested") or details.get("initial_seed") or acc.get("initial_seed", 0.0))
    asset = float(_pick(details, "current_asset", acc.get("total_asset", seed)))
    cash = float(_pick(details, "current_cash", acc.get("current_cash", seed)))
    hold = int(_pick(details, "current_hold", acc.get("current_holdings", 0)))
    price = float(_pick(details, "current_price", acc.get("current_price", 0.0)))
    profit = float(_pick(details, "total_profit", asset - seed))
    default_pct = ((asset / seed - 1.0) * 100) if seed > 0 else 0.0
    return_pct = float(_pick(details, "total_return_pct", default_pct))

    buy_orders = details.get("buy_orders", [])
    sell_orders = details.get("sell_orders", [])

    item = {
        "id": acc["id"],
        "owner": acc.get("owner", owner),
        "is_my_account": True,
        "name": acc["name"],
        "ticker": acc["ticker"],
        "strategy": acc["strategy"],
        "start_date": acc.get("start_date", ""),
        "current_date": details.get("current_date") or acc.get("current_date", ""),
        "operational_state": details.get("operational_state") or acc.get("operational_state", "WAITING_FOR_FILL"),
        "initial_seed": seed,
        "reserve_ratio": float(acc.get("reserve_ratio", 0.05)),
        "memo": acc.get("memo", ""),
        "total_asset": round(asset, 2),
        "current_cash": round(cash, 2),
        "current_holdings": hold,
        "current_price": round(price, 2),
        "total_profit": round(profit, 2),
        "return_pct": round(return_pct, 2),
        "mode": str(details.get("mode") or "Normal"),
        "pending_sell_count": int(details.get("pending_sell_count", 0)),
        "records_count": len(acc.get("trade_records", [])),
        "has_orders": bool(buy_orders or sell_orders),
        "buy_orders": buy_orders,
        "sell_orders": sell_orders,
        "auto_trade": {
            "enabled": bool(acc.get("auto_trade", {}).get("enabled", False)),
            "broker": acc.get("auto_trade", {}).get("broker", "meritz"),
            "has_credentials": bool(acc.get("auto_trade", {}).get("app_key_enc")),
            "app_key_masked": acc.get("auto_trade", {}).get("app_key_masked", ""),
            "last_status": acc.get("auto_trade", {}).get("last_status", ""),
            "last_message": acc.get("auto_trade", {}).get("last_message", "")
        },
    }
    return item, asset, cash, seed


def _fallback_summary(acc: dict, owner: str) -> dict:
    """계산 실패 시 시드 기준의 안전한 기본 요약 (포트폴리오 합계에는 포함하지 않음)"""
    seed = float(acc.get("initial_seed", 0.0))
    return {
        "id": acc["id"],
        "owner": acc.get("owner", owner),
        "is_my_account": True,
        "name": acc["name"],
        "ticker": acc["ticker"],
        "strategy": acc["strategy"],
        "initial_seed": seed,
        "total_asset": seed,
        "current_cash": seed,
        "current_holdings": 0,
        "current_price": 0.0,
        "total_profit": 0.0,
        "return_pct": 0.0,
        "mode": "Normal",
        "operational_state": "WAITING_FOR_FILL",
        "records_count": len(acc.get("trade_records", [])),
    }


@router.get("")
async def list_accounts(request: Request):
    """현재 로그인한 회원의 계좌 목록 및 포트폴리오 요약 반환 (회원별 독립 격리)"""
    owner = current_username(request)
    user_accounts = [
        acc for acc in am.load_accounts()
        if acc.get("owner", DEFAULT_OWNER).lower() == owner
    ]

    processed, total_asset, total_cash, total_seed = [], 0.0, 0.0, 0.0
    for acc in user_accounts:
        try:
            item, asset, cash, seed = _summarize_account(acc, owner)
        except Exception as e:
            print(f"계좌 [{acc.get('name')}] 계산 실패: {e}")
            processed.append(_fallback_summary(acc, owner))
            continue
        total_asset += asset
        total_cash += cash
        total_seed += seed
        processed.append(item)

    total_profit = total_asset - total_seed
    overall_pct = round(total_profit / total_seed * 100, 2) if total_seed > 0 else 0.0
    return {
        "portfolio": {
            "total_asset": round(total_asset, 2),
            "total_cash": round(total_cash, 2),
            "total_seed": round(total_seed, 2),
            "total_profit": round(total_profit, 2),
            "return_pct": overall_pct,
            "account_count": len(processed),
            "owner": owner,
        },
        "accounts": processed,
    }


@router.get("/{acc_id}")
async def get_account_detail(acc_id: str, request: Request):
    """특정 계좌의 주문표, 미매도 슬롯, 매매일지, 입출금 상세 내역 반환 (회원별 격리)"""
    target = get_owned_account(acc_id, request, "본인의 계좌 정보만 열람할 수 있습니다.")

    details = am.compute_account_details(target)
    # df_res 는 대용량 DataFrame 이므로 응답 크기 절약 및 안전한 JSON 직렬화를 위해 제외
    details_clean = {k: v for k, v in details.items() if k != "df_res"}

    trade_records = target.get("trade_records", [])
    acc_copy = dict(target)
    acc_copy["mode"] = details_clean.get("mode", "Normal")
    return sanitize_for_json({
        "account": acc_copy,
        "details": details_clean,
        "summary": details_clean,
        "orders": {
            "buy_orders": details_clean.get("buy_orders", []),
            "sell_orders": details_clean.get("sell_orders", []),
            "netting_info": details_clean.get("netting_info", {}),
        },
        "unsold_lots": details_clean.get("unsold_lots", []),
        "trade_records": trade_records[-100:],
        "adjustments": target.get("adjustments", []),
    })


@router.post("")
async def create_account(req: CreateAccountRequest, request: Request):
    """신규 계좌 생성 (현재 로그인한 회원 소유로 등록)"""
    new_acc = am.add_account(
        name=req.name,
        strategy=req.strategy,
        ticker=req.ticker,
        start_date=req.start_date,
        initial_seed=req.initial_seed,
        memo=req.memo or "",
        reserve_ratio=req.reserve_ratio,
        owner=current_username(request),
    )
    return {"success": True, "account": new_acc}


@router.put("/{acc_id}")
async def update_account(acc_id: str, req: UpdateAccountRequest, request: Request):
    """계좌 설정(명칭, 위기준비금 비율, 메모 등) 수정 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 수정할 수 있습니다.")

    updated = am.update_account_settings(
        acc_id=acc_id,
        name=req.name,
        reserve_ratio=req.reserve_ratio,
        memo=req.memo,
        initial_seed=req.initial_seed,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "account": updated}


@router.delete("/{acc_id}")
async def delete_account(acc_id: str, request: Request):
    """계좌 삭제 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 삭제할 수 있습니다.")

    if not am.delete_account(acc_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "deleted_id": acc_id}


def _notify_orders(res: dict) -> None:
    """(예약) 매수/매도 주문표 생성 시 텔레그램 알림 자동 발송 (실패해도 진행 결과에는 영향 없음)"""
    try:
        details = am.compute_account_details(res)
        notify_order_generation(
            account_name=res.get("name", "투자계좌"),
            ticker=res.get("ticker", "SOXL"),
            trade_date=str(details.get("target_order_date") or res.get("current_date", "")),
            mode=str(details.get("mode", "Normal")),
            buy_orders=details.get("buy_orders", []),
            sell_orders=details.get("sell_orders", []),
            netting_info=details.get("netting_info"),
            total_asset=float(details.get("current_asset", 0.0)),
            cash=float(details.get("current_cash", 0.0)),
        )
    except Exception as ex:
        print(f"[Telegram Alert Error] {ex}")


@router.post("/{acc_id}/advance-day")
async def advance_account_day(acc_id: str, request: Request):
    """계좌 운용 날짜를 다음 미국 개장일로 진행 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 운용할 수 있습니다.")

    res = am.advance_next_day(acc_id)
    if not res:
        raise HTTPException(status_code=404, detail="Account not found")

    _notify_orders(res)
    return {"success": True, "account": res}


@router.post("/{acc_id}/close-settlement")
async def record_close_settlement(acc_id: str, req: SettlementRequest, request: Request):
    """미국 장마감 후 당일 종가 및 체결 수량 입력 정산 (소유자 검증)"""
    target = get_owned_account(acc_id, request, "본인의 계좌만 정산할 수 있습니다.")

    mode = req.mode
    if not mode:
        details = am.compute_account_details(target)
        mode = details.get("mode", "Normal")

    res = am.record_daily_close(
        acc_id=acc_id,
        close_price=req.close_price,
        buy_qty=req.buy_qty,
        buy_price=req.buy_price,
        sell_qty=req.sell_qty,
        sell_price=req.sell_price,
        memo=req.memo or "",
        trade_date=req.trade_date,
        mode=mode,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Account not found or settlement failed")
    return {"success": True, "account": res}


@router.post("/{acc_id}/adjustment")
async def add_account_adjustment(acc_id: str, req: AdjustmentRequest, request: Request):
    """계좌 입금 또는 출금 기록 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 입출금 기록이 가능합니다.")

    ok = am.add_adjustment(
        acc_id=acc_id,
        adj_type=req.type,
        amount=req.amount,
        date_str=req.date,
        reason=req.reason or "",
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True}


@router.post("/{acc_id}/undo")
async def undo_last_trade(acc_id: str, request: Request):
    """마지막 거래일 기록 취소 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 취소(Undo)할 수 있습니다.")

    if not am.delete_last_trade_record(acc_id):
        raise HTTPException(status_code=400, detail="Cannot undo last record")
    return {"success": True}


@router.get("/{acc_id}/broker")
async def get_account_broker(acc_id: str, request: Request):
    """계좌별 자동매매 브로커 설정 조회 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 브로커 설정 조회가 가능합니다.")
    cfg = am.get_account_broker_config(acc_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "config": cfg}


@router.post("/{acc_id}/broker")
async def save_account_broker(acc_id: str, req: AccountBrokerConfigRequest, request: Request):
    """계좌별 자동매매 On/Off 및 브로커 선택 저장 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 브로커 설정 저장이 가능합니다.")
    broker_name = (req.broker or "meritz").lower().strip()

    if broker_name in ("kiwoom", "kis"):
        # 키움증권 / 한국투자증권은 구현 예정
        cfg = am.save_account_broker_config(
            acc_id=acc_id,
            broker=broker_name,
            enabled=req.enabled,
            notify_telegram=req.notify_telegram,
            check_status="PENDING",
            check_message="구현 예정입니다."
        )
        return {
            "success": True,
            "message": f"{'키움증권' if broker_name == 'kiwoom' else '한국투자증권'}은 구현 예정입니다.",
            "config": cfg,
            "is_pending": True
        }

    cfg = am.save_account_broker_config(
        acc_id=acc_id,
        broker=broker_name,
        enabled=req.enabled,
        notify_telegram=req.notify_telegram
    )
    return {"success": True, "message": "자동매매 설정이 저장되었습니다.", "config": cfg}


@router.post("/{acc_id}/broker/check-save")
async def check_and_save_broker(acc_id: str, req: AccountBrokerConfigRequest, request: Request):
    """
    증권사 Open API 연동 검증 및 검증 성공 시 키 암호화 안전 저장 (Check & Save)
    """
    target = get_owned_account(acc_id, request, "본인의 계좌만 브로커 연동 설정이 가능합니다.")
    broker_name = (req.broker or "meritz").lower().strip()

    # 1. 키움 / 한국투자증권 선택 시
    if broker_name in ("kiwoom", "kis"):
        broker_kr = "키움증권" if broker_name == "kiwoom" else "한국투자증권"
        return {
            "success": False,
            "message": f"'{broker_kr}' 연동은 현재 구현 예정입니다.",
            "is_pending": True
        }

    # 2. 메리츠증권 Open API 검증
    if broker_name == "meritz":
        from core.meritz_client import MeritzClient
        from core.security import decrypt_credential

        app_key = (req.app_key or "").strip()
        app_secret = (req.app_secret or "").strip()

        # 새로 입력되지 않고 기존 등록된 키가 있는 경우 복호화하여 테스트 지원
        cur_cfg = target.get("auto_trade", {})
        if not app_key and cur_cfg.get("app_key_enc"):
            app_key = decrypt_credential(cur_cfg.get("app_key_enc", ""))
        if not app_secret and cur_cfg.get("app_secret_enc"):
            app_secret = decrypt_credential(cur_cfg.get("app_secret_enc", ""))

        if not app_key or not app_secret:
            raise HTTPException(
                status_code=400,
                detail="메리츠증권 APP KEY와 APP SECRET을 모두 입력해 주세요."
            )

        # 실제 메리츠 Open API(토큰 발급 + 해외주식 잔고조회) 호출 검증
        ok, msg, data = MeritzClient.verify_credentials(app_key=app_key, app_secret=app_secret)
        if not ok:
            return {
                "success": False,
                "message": msg
            }

        clean_success_msg = "메리츠증권 Open API 연동 검증이 완료되었습니다."

        # 검증 성공 시 대칭키 암호화하여 영구 저장
        saved_cfg = am.save_account_broker_config(
            acc_id=acc_id,
            broker="meritz",
            enabled=req.enabled,
            notify_telegram=req.notify_telegram,
            app_key=app_key,
            app_secret=app_secret,
            check_status="SUCCESS",
            check_message=clean_success_msg
        )

        return {
            "success": True,
            "message": clean_success_msg,
            "config": saved_cfg
        }

    raise HTTPException(status_code=400, detail="지원되지 않는 증권사입니다.")

