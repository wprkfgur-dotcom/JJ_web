"""
Pydantic 요청 스키마
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class CreateAccountRequest(BaseModel):
    name: str = Field(..., example="SOXL 종종이 1호")
    strategy: str = Field(..., example="종종이 기본전략")
    ticker: str = Field(..., example="SOXL")
    start_date: str = Field(..., example="2026-01-02")
    initial_seed: float = Field(..., example=100000.0)
    reserve_ratio: float = Field(default=0.05, example=0.05)
    memo: Optional[str] = Field(default="")


class UpdateAccountRequest(BaseModel):
    name: Optional[str] = None
    reserve_ratio: Optional[float] = None
    memo: Optional[str] = None
    initial_seed: Optional[float] = None


class SettlementRequest(BaseModel):
    close_price: float = Field(..., example=50.25)
    buy_qty: int = Field(default=0)
    buy_price: Optional[float] = None
    sell_qty: int = Field(default=0)
    sell_price: Optional[float] = None
    memo: Optional[str] = ""
    trade_date: Optional[str] = None
    mode: Optional[str] = None


class AdjustmentRequest(BaseModel):
    type: str = Field(..., example="DEPOSIT")  # "DEPOSIT" or "WITHDRAW"
    amount: float = Field(..., example=5000.0)
    date: str = Field(..., example="2026-10-10")
    reason: Optional[str] = ""


class BacktestRequest(BaseModel):
    ticker: str = Field(default="SOXL")
    capital: float = Field(default=100000.0)
    start_date: str = Field(default="2023-01-03")
    end_date: str = Field(default="2026-10-09")
    strategies: List[str] = Field(default=["종종이 기본전략", "무한매수법 v4.0", "SOXL 단순보유(B&H)"])
    use_adj_close: bool = Field(default=True)


class RegisterRequest(BaseModel):
    email: str = Field(..., example="user@example.com")
    username: str = Field(..., example="myid")
    password: str = Field(..., example="mypassword")


class LoginRequest(BaseModel):
    username: str = Field(..., example="myid")
    password: str = Field(..., example="mypassword")


class TelegramConfigRequest(BaseModel):
    bot_token: str = Field(default="", example="123456789:ABCdef...")
    chat_id: str = Field(default="", example="123456789")
    enabled: bool = Field(default=True)
    notify_on_orders: bool = Field(default=True)


class TelegramTestRequest(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None


class MeritzConfigRequest(BaseModel):
    app_key: str = Field(default="", example="발급받은_App_Key")
    app_secret: str = Field(default="", example="발급받은_App_Secret")
    is_simulation: bool = Field(default=True)
    enabled: bool = Field(default=True)


class MeritzTestRequest(BaseModel):
    app_key: Optional[str] = None
    app_secret: Optional[str] = None


class MeritzOrderExecuteRequest(BaseModel):
    account_id: str
    symbol: Optional[str] = None
    dry_run: Optional[bool] = None


class AccountBrokerConfigRequest(BaseModel):
    broker: str = Field(default="meritz", example="meritz")  # "meritz", "kiwoom", "kis"
    enabled: bool = Field(default=False)
    notify_telegram: bool = Field(default=True)
    app_key: Optional[str] = Field(default=None)
    app_secret: Optional[str] = Field(default=None)


class SchedulerConfigRequest(BaseModel):
    enabled: bool = Field(default=True)
    order_time: str = Field(default="20:20", example="20:20")
    settle_time: str = Field(default="05:10", example="05:10")



