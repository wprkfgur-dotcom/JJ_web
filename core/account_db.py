"""
=====================================================================
SQLite3 기반 계좌 및 매매기록 데이터베이스 모듈 (Account Database Engine)
- WAL(Write-Ahead Logging) 모드를 통한 동시성 및 ACID 트랜잭션 보장
- accounts, adjustments, trade_records 테이블 분리 정규화
- 기존 accounts.json 데이터 무손실 자동 마이그레이션 지원
=====================================================================
"""
import os
import json
import sqlite3
from typing import List, Dict, Any, Optional

def get_connection(db_path: str) -> sqlite3.Connection:
    """WAL 모드와 외래키가 활성화된 SQLite 연결 반환"""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str):
    """테이블 스키마 생성 및 인덱스 초기화"""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with get_connection(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            strategy TEXT,
            ticker TEXT,
            start_date TEXT,
            initial_seed REAL,
            reserve_ratio REAL,
            memo TEXT,
            created_at TEXT,
            current_date TEXT,
            operational_state TEXT,
            current_cash REAL,
            current_holdings INTEGER,
            total_asset REAL,
            current_price REAL,
            last_applied_adj REAL,
            manual_mode TEXT,
            auto_trade_json TEXT,
            order_table_json TEXT,
            strategy_params_json TEXT
        );

        CREATE TABLE IF NOT EXISTS adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            type TEXT,
            amount REAL,
            date TEXT,
            reason TEXT,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_adj_account ON adjustments(account_id);

        CREATE TABLE IF NOT EXISTS trade_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            t INTEGER,
            close REAL,
            chg REAL,
            mode TEXT,
            r INTEGER,
            buy_qty INTEGER,
            buy_price REAL,
            s REAL,
            u REAL,
            sold INTEGER,
            w TEXT,
            x REAL,
            z REAL,
            profit REAL,
            sell_qty INTEGER,
            cash REAL,
            hold INTEGER,
            asset REAL,
            ar REAL,
            ak REAL,
            memo TEXT,
            extra_json TEXT,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(account_id, trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_tr_acc_date ON trade_records(account_id, trade_date);
        """)
        try:
            conn.execute("ALTER TABLE accounts ADD COLUMN strategy_params_json TEXT")
        except Exception:
            pass

def migrate_from_json_if_needed(json_path: str, db_path: str) -> bool:
    """
    accounts.db 가 비어 있고 accounts.json 이 존재하면 100% 무손실 마이그레이션 수행
    """
    init_db(db_path)
    if not os.path.exists(json_path):
        return False

    with get_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM accounts")
        count = cur.fetchone()[0]
        if count > 0:
            return False  # 이미 SQLite 데이터가 존재함

    # JSON 데이터 로드 및 마이그레이션
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
        if not accounts:
            return False

        save_all_accounts(accounts, db_path)
        print(f"[SQLite Migration] {len(accounts)}개 계좌를 {db_path}로 마이그레이션 완료!")
        return True
    except Exception as e:
        print(f"[SQLite Migration Error] {e}")
        return False

def load_all_accounts(db_path: str) -> List[Dict[str, Any]]:
    """SQLite DB에서 모든 계좌와 그에 속한 매매기록, 입출금 내역을 로드"""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts ORDER BY created_at ASC")
        acc_rows = cur.fetchall()
        accounts = []

        for a in acc_rows:
            acc_id = a["id"]
            
            # 1. auto_trade 및 order_table 복원
            auto_trade = {}
            if a["auto_trade_json"]:
                try:
                    auto_trade = json.loads(a["auto_trade_json"])
                except Exception:
                    pass

            order_table = {}
            if a["order_table_json"]:
                try:
                    order_table = json.loads(a["order_table_json"])
                except Exception:
                    pass

            # 2. adjustments 로드
            cur.execute("SELECT type, amount, date, reason FROM adjustments WHERE account_id = ? ORDER BY date ASC, id ASC", (acc_id,))
            adj_rows = cur.fetchall()
            adjustments = [
                {
                    "type": adj["type"],
                    "amount": adj["amount"],
                    "date": adj["date"],
                    "reason": adj["reason"] or ""
                }
                for adj in adj_rows
            ]

            # 3. trade_records 로드
            cur.execute("SELECT * FROM trade_records WHERE account_id = ? ORDER BY trade_date ASC, t ASC", (acc_id,))
            tr_rows = cur.fetchall()
            trade_records = []
            for tr in tr_rows:
                extra = {}
                if tr["extra_json"]:
                    try:
                        extra = json.loads(tr["extra_json"])
                    except Exception:
                        pass

                rec = {
                    "t": tr["t"],
                    "Date": tr["trade_date"],
                    "Close": tr["close"],
                    "Chg": tr["chg"],
                    "Mode": tr["mode"],
                    "R": tr["r"],
                    "BuyQty": tr["buy_qty"],
                    "BuyPrice": tr["buy_price"],
                    "S": tr["s"],
                    "U": tr["u"],
                    "Sold": bool(tr["sold"]),
                    "W": tr["w"],
                    "X": tr["x"],
                    "Z": tr["z"],
                    "Profit": tr["profit"],
                    "SellQty": tr["sell_qty"],
                    "Cash": tr["cash"],
                    "Hold": tr["hold"],
                    "Asset": tr["asset"],
                    "AR": tr["ar"],
                    "AK": tr["ak"],
                    "Memo": tr["memo"] or "",
                    **extra
                }
                trade_records.append(rec)

            # strategy_params 복원
            strategy_params = {}
            if "strategy_params_json" in a.keys() and a["strategy_params_json"]:
                try:
                    strategy_params = json.loads(a["strategy_params_json"])
                except Exception:
                    pass

            acc_dict = {
                "id": acc_id,
                "owner": a["owner"],
                "name": a["name"],
                "strategy": a["strategy"],
                "ticker": a["ticker"],
                "start_date": a["start_date"],
                "initial_seed": a["initial_seed"],
                "reserve_ratio": a["reserve_ratio"],
                "memo": a["memo"] or "",
                "created_at": a["created_at"],
                "current_date": a["current_date"],
                "operational_state": a["operational_state"],
                "current_cash": a["current_cash"],
                "current_holdings": a["current_holdings"],
                "total_asset": a["total_asset"],
                "current_price": a["current_price"],
                "last_applied_adj": a["last_applied_adj"] or 0.0,
                "manual_mode": a["manual_mode"],
                "auto_trade": auto_trade,
                "order_table": order_table,
                "strategy_params": strategy_params,
                "adjustments": adjustments,
                "trade_records": trade_records
            }
            accounts.append(acc_dict)

        return accounts

def save_all_accounts(accounts: List[Dict[str, Any]], db_path: str):
    """
    단일 SQLite 트랜잭션 내에서 모든 계좌, 입출금, 매매기록을 원자적(Atomically)으로 저장
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        cur = conn.cursor()
        
        existing_acc_ids = set()
        for acc in accounts:
            acc_id = acc["id"]
            existing_acc_ids.add(acc_id)

            auto_trade_json = json.dumps(acc.get("auto_trade", {}), ensure_ascii=False) if acc.get("auto_trade") else None
            order_table_json = json.dumps(acc.get("order_table", {}), ensure_ascii=False) if acc.get("order_table") else None
            strategy_params_json = json.dumps(acc.get("strategy_params", {}), ensure_ascii=False) if acc.get("strategy_params") else None

            # 1. Account Upsert
            cur.execute("""
            INSERT INTO accounts (
                id, owner, name, strategy, ticker, start_date, initial_seed, reserve_ratio,
                memo, created_at, current_date, operational_state, current_cash, current_holdings,
                total_asset, current_price, last_applied_adj, manual_mode, auto_trade_json, order_table_json, strategy_params_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner = excluded.owner,
                name = excluded.name,
                strategy = excluded.strategy,
                ticker = excluded.ticker,
                start_date = excluded.start_date,
                initial_seed = excluded.initial_seed,
                reserve_ratio = excluded.reserve_ratio,
                memo = excluded.memo,
                created_at = excluded.created_at,
                current_date = excluded.current_date,
                operational_state = excluded.operational_state,
                current_cash = excluded.current_cash,
                current_holdings = excluded.current_holdings,
                total_asset = excluded.total_asset,
                current_price = excluded.current_price,
                last_applied_adj = excluded.last_applied_adj,
                manual_mode = excluded.manual_mode,
                auto_trade_json = excluded.auto_trade_json,
                order_table_json = excluded.order_table_json,
                strategy_params_json = excluded.strategy_params_json;
            """, (
                acc_id,
                acc.get("owner", "huxley"),
                acc.get("name", ""),
                acc.get("strategy", ""),
                acc.get("ticker", "SOXL"),
                acc.get("start_date", ""),
                float(acc.get("initial_seed", 0.0)),
                float(acc.get("reserve_ratio", 0.05)),
                acc.get("memo", ""),
                acc.get("created_at", ""),
                acc.get("current_date", ""),
                acc.get("operational_state", "WAITING_FOR_FILL"),
                float(acc.get("current_cash", 0.0)),
                int(acc.get("current_holdings", 0)),
                float(acc.get("total_asset", 0.0)),
                float(acc.get("current_price", 0.0)),
                float(acc.get("last_applied_adj", 0.0)),
                acc.get("manual_mode"),
                auto_trade_json,
                order_table_json,
                strategy_params_json
            ))

            # 2. Adjustments 교체
            cur.execute("DELETE FROM adjustments WHERE account_id = ?", (acc_id,))
            for adj in acc.get("adjustments", []):
                cur.execute("""
                INSERT INTO adjustments (account_id, type, amount, date, reason)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    acc_id,
                    adj.get("type", "DEPOSIT"),
                    float(adj.get("amount", 0.0)),
                    adj.get("date", ""),
                    adj.get("reason", "")
                ))

            # 3. Trade Records 교체
            cur.execute("DELETE FROM trade_records WHERE account_id = ?", (acc_id,))
            for tr in acc.get("trade_records", []):
                # Standard fields vs extra fields
                standard_keys = {
                    "t", "Date", "Close", "Chg", "Mode", "R", "BuyQty", "BuyPrice",
                    "S", "U", "Sold", "W", "X", "Z", "Profit", "SellQty", "Cash",
                    "Hold", "Asset", "AR", "AK", "Memo"
                }
                extra = {k: v for k, v in tr.items() if k not in standard_keys}
                extra_json = json.dumps(extra, ensure_ascii=False) if extra else None

                cur.execute("""
                INSERT INTO trade_records (
                    account_id, trade_date, t, close, chg, mode, r, buy_qty, buy_price,
                    s, u, sold, w, x, z, profit, sell_qty, cash, hold, asset, ar, ak, memo, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    acc_id,
                    str(tr.get("Date", "")),
                    int(tr.get("t", 0)) if tr.get("t") is not None else None,
                    float(tr.get("Close", 0.0)) if tr.get("Close") is not None else None,
                    float(tr.get("Chg", 0.0)) if tr.get("Chg") is not None else None,
                    str(tr.get("Mode", "Normal")),
                    int(tr.get("R", 0)) if tr.get("R") is not None else 0,
                    int(tr.get("BuyQty", tr.get("R", 0))) if (tr.get("BuyQty") is not None or tr.get("R") is not None) else 0,
                    float(tr.get("BuyPrice", 0.0)) if tr.get("BuyPrice") is not None else None,
                    float(tr.get("S", 0.0)) if tr.get("S") is not None else None,
                    float(tr.get("U", 0.0)) if tr.get("U") is not None else None,
                    1 if tr.get("Sold") else 0,
                    str(tr.get("W")) if tr.get("W") else None,
                    float(tr.get("X")) if tr.get("X") is not None else None,
                    float(tr.get("Z")) if tr.get("Z") is not None else None,
                    float(tr.get("Profit")) if tr.get("Profit") is not None else None,
                    int(tr.get("SellQty", 0)) if tr.get("SellQty") is not None else 0,
                    float(tr.get("Cash", 0.0)) if tr.get("Cash") is not None else None,
                    int(tr.get("Hold", 0)) if tr.get("Hold") is not None else 0,
                    float(tr.get("Asset", 0.0)) if tr.get("Asset") is not None else None,
                    float(tr.get("AR", 0.0)) if tr.get("AR") is not None else None,
                    float(tr.get("AK", 0.0)) if tr.get("AK") is not None else None,
                    str(tr.get("Memo", "")),
                    extra_json
                ))

        # 삭제된 계좌가 있다면 SQLite에서도 제거
        if existing_acc_ids:
            placeholders = ",".join("?" for _ in existing_acc_ids)
            cur.execute(f"DELETE FROM accounts WHERE id NOT IN ({placeholders})", list(existing_acc_ids))
        else:
            cur.execute("DELETE FROM accounts")
