"""
계좌(Accounts) 라우터: 목록/상세/CRUD/운용(진행·정산·입출금·되돌리기)
"""
from fastapi import APIRouter, HTTPException, Request

from core.telegram_notifier import notify_order_generation
from core.market_cache import get_cached_close, set_cached_close
from core.meritz_client import MeritzClient
from core.security import decrypt_credential

from ..config import DEFAULT_OWNER, am
from ..schemas import (
    AdjustmentRequest,
    CreateAccountRequest,
    SettlementRequest,
    UpdateAccountRequest,
    AccountBrokerConfigRequest,
    EditTradeRecordRequest,
    StrategyParamsRequest,
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
        "season_info": details.get("season_info")
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

    # 일자별 총 자산 추이 (Daily Total Asset Trend) 집계 (X축: 거래일자, Y축: 총자산)
    all_dates = set()
    acc_records_map = {}
    for acc in user_accounts:
        recs = acc.get("trade_records", [])
        rec_dict = {}
        for r in recs:
            d = str(r.get("Date", ""))[:10]
            if d:
                all_dates.add(d)
                try:
                    rec_dict[d] = float(r.get("Asset", 0.0))
                except (ValueError, TypeError):
                    rec_dict[d] = 0.0
        acc_records_map[acc["id"]] = {
            "start_date": str(acc.get("start_date", ""))[:10],
            "initial_seed": float(acc.get("initial_seed", 0.0)),
            "records": rec_dict
        }

    daily_trend = []
    if all_dates:
        sorted_dates = sorted(list(all_dates))
        latest_acc_asset = {acc["id"]: 0.0 for acc in user_accounts}
        for d in sorted_dates:
            day_total = 0.0
            for acc in user_accounts:
                acc_info = acc_records_map[acc["id"]]
                if d in acc_info["records"]:
                    latest_acc_asset[acc["id"]] = acc_info["records"][d]
                elif latest_acc_asset[acc["id"]] == 0.0 and d >= acc_info["start_date"]:
                    latest_acc_asset[acc["id"]] = acc_info["initial_seed"]
                day_total += latest_acc_asset[acc["id"]]
            daily_trend.append({"date": d, "asset": round(day_total, 2)})

    return {
        "portfolio": {
            "total_asset": round(total_asset, 2),
            "total_cash": round(total_cash, 2),
            "total_seed": round(total_seed, 2),
            "total_profit": round(total_profit, 2),
            "return_pct": overall_pct,
            "account_count": len(processed),
            "owner": owner,
            "daily_trend": daily_trend,
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
    acc_copy["strategy_params"] = am.get_account_strategy_params(acc_id)
    if "auto_trade" in acc_copy and isinstance(acc_copy["auto_trade"], dict):
        sanitized_at = dict(acc_copy["auto_trade"])
        sanitized_at.pop("app_key_enc", None)
        sanitized_at.pop("app_secret_enc", None)
        acc_copy["auto_trade"] = sanitized_at
    return sanitize_for_json({
        "account": acc_copy,
        "details": details_clean,
        "summary": details_clean,
        "orders": {
            "buy_orders": details_clean.get("buy_orders", []),
            "sell_orders": details_clean.get("sell_orders", []),
            "netting_info": details_clean.get("netting_info", {}),
        },
        "season_info": details_clean.get("season_info"),
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


@router.get("/{acc_id}/settlement-preview")
async def get_settlement_preview(acc_id: str, request: Request):
    """
    일일 마감 정산(종가 & 체결 입력) 팝업 시 종가, 매수량, 매도량을 자동 계산하여 프리뷰 제공.
    1) 종가: 시스템 전역 캐시(메리츠/야후/정산 등 누군가 1회라도 확인한 종가)를 최우선 제공.
    2) 체결량: 메리츠 OpenAPI 연동 계좌면 당일 실체결 내역 조회, 미연동 시 당일 주문표 기반 예상 체결량 산출.
    3) 사용자가 최종 확인 후 자유롭게 수정 가능.
    """
    target = get_owned_account(acc_id, request, "본인의 계좌만 조회할 수 있습니다.")
    ticker = target.get("ticker", "SOXL").upper().strip()
    target_date = target.get("current_date")

    # 계좌 상세 계산 (주문표 및 슬롯)
    details = am.compute_account_details(target)

    # 1. 종가 조회 (전역 캐시 최우선 -> 세부 계산 시세)
    cached = get_cached_close(ticker, target_date)
    if not cached:
        cached = get_cached_close(ticker)

    close_price = None
    close_source = "실시간 시세"
    close_updated_at = None

    if cached and cached.get("close_price"):
        close_price = float(cached["close_price"])
        close_source = f"전역 캐시 ({cached.get('source', '시스템')})"
        close_updated_at = cached.get("updated_at")
    else:
        close_price = float(details.get("current_price", 0.0) or 0.0)
        close_source = "당일 계산 시세"
        if close_price > 0:
            set_cached_close(ticker, close_price, date_str=target_date, source="계좌 시세 자동감지")

    # 2. 체결 매수량 / 매도량 자동 산출
    suggested_buy_qty = 0
    suggested_sell_qty = 0
    suggested_memo = ""
    is_api_filled = False

    # 2-A. 메리츠 OpenAPI 연동 계좌인 경우 실제 체결 내역 조회 시도
    auto_cfg = target.get("auto_trade", {})
    if auto_cfg.get("enabled") and auto_cfg.get("broker") == "meritz" and auto_cfg.get("app_key_enc") and auto_cfg.get("app_secret_enc"):
        try:
            client = MeritzClient(config_path="/dev/null")
            client.config = {
                "app_key": decrypt_credential(auto_cfg["app_key_enc"]),
                "app_secret": decrypt_credential(auto_cfg["app_secret_enc"]),
                "is_simulation": False,
                "enabled": True
            }
            ord_res = client.get_today_orders()
            if ord_res.get("success"):
                cq_buy = 0
                cq_sell = 0
                for o in ord_res.get("orders", []):
                    cq = int(float(o.get("cntg_qty") or o.get("ccld_qty") or 0))
                    side_cd = str(o.get("seln_byov_clcd") or o.get("sll_buy_dvs_cd") or "")
                    if cq > 0:
                        if side_cd in ("02", "BUY", "2"):
                            cq_buy += cq
                        elif side_cd in ("01", "SELL", "1"):
                            cq_sell += cq
                if cq_buy > 0 or cq_sell > 0:
                    suggested_buy_qty = cq_buy
                    suggested_sell_qty = cq_sell
                    suggested_memo = f"메리츠 OpenAPI 실체결 조회 (매수 {cq_buy}주, 매도 {cq_sell}주)"
                    is_api_filled = True
        except Exception as ex:
            print(f"[SettlementPreview] 메리츠 실체결 조회 안내: {ex}")

    # 2-B. 메리츠 실체결이 없거나 미연동인 경우 주문표 기반 예상 체결량 산출
    if not is_api_filled:
        orders = details.get("orders", {}).get("orders", [])
        buy_orders = [o for o in orders if o.get("side") == "BUY"]
        if buy_orders:
            fillable_buys = 0
            for bo in buy_orders:
                limit_p = float(bo.get("limit_price") or 0.0)
                if close_price > 0 and close_price <= limit_p:
                    fillable_buys += int(bo.get("order_qty") or 0)
            suggested_buy_qty = fillable_buys if fillable_buys > 0 else int(buy_orders[0].get("order_qty") or 0)

        sell_orders = [o for o in orders if o.get("side") == "SELL"]
        if sell_orders:
            fillable_sells = 0
            for so in sell_orders:
                target_u = float(so.get("target_price") or so.get("limit_price") or 0.0)
                if close_price > 0 and close_price >= target_u:
                    fillable_sells += int(so.get("order_qty") or 0)
            suggested_sell_qty = fillable_sells

        suggested_memo = "당일 주문표 기준 자동 추천"

    return {
        "success": True,
        "account_id": acc_id,
        "account_name": target.get("name"),
        "ticker": ticker,
        "target_date": target_date,
        "close_price": close_price,
        "close_source": close_source,
        "close_updated_at": close_updated_at,
        "suggested_buy_qty": suggested_buy_qty,
        "suggested_sell_qty": suggested_sell_qty,
        "suggested_memo": suggested_memo,
        "is_api_filled": is_api_filled
    }


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


@router.post("/{acc_id}/trade-records/edit")
async def edit_account_trade_record(acc_id: str, req: EditTradeRecordRequest, request: Request):
    """매매일지 특정 거래일 기록 수정 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 수정할 수 있습니다.")
    fields = {}
    if req.close_price is not None:
        fields["Close"] = float(req.close_price)
        fields["BuyPrice"] = float(req.close_price)
    if req.buy_qty is not None:
        fields["BuyQty"] = int(req.buy_qty)
        fields["R"] = int(req.buy_qty)
    if req.sell_qty is not None:
        fields["SellQty"] = int(req.sell_qty)
    if req.mode is not None:
        fields["Mode"] = req.mode.strip().capitalize()
    if req.memo is not None:
        fields["Memo"] = req.memo

    ok = am.update_trade_record(acc_id, req.date.strip(), fields)
    if not ok:
        raise HTTPException(status_code=400, detail="기록 수정에 실패했거나 거래일을 찾을 수 없습니다.")
    return {"success": True, "message": "매매 기록이 성공적으로 수정되었습니다."}


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


@router.get("/{acc_id}/strategy-params")
async def get_account_strategy_params(acc_id: str, request: Request):
    """계좌별 전략 파라미터 조회 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 조회할 수 있습니다.")
    params = am.get_account_strategy_params(acc_id)
    if params is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "strategy_params": params}


@router.post("/{acc_id}/strategy-params")
async def update_account_strategy_params(acc_id: str, req: StrategyParamsRequest, request: Request):
    """계좌별 전략 파라미터(보유일수, 위기준비율, 수수료율, 모드별 익절률/분할수) 설정 (소유자 검증)"""
    get_owned_account(acc_id, request, "본인의 계좌만 수정할 수 있습니다.")
    try:
        updated = am.save_account_strategy_params(acc_id, req.dict())
        return {"success": True, "strategy_params": updated}
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex))


