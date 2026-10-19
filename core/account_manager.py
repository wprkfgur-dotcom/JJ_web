"""
계좌 관리 및 자산 입출금(세금 인출 등) 영속성 관리 모듈 (Account Manager)
데이터 파일(data/accounts.json)을 통해 사용자의 계좌 정보 및 일일 실매매 기록을 영구 보존합니다.
미국 증시 개장일 캘린더를 연동하여 Next Day(다음 거래일) 진행, 당일 종가 및 체결 정산,
일지 수정 및 마지막 거래일 삭제(Undo) 기능을 제공합니다.
"""
import os
import json
import uuid
from datetime import datetime
import pandas as pd

from strategies.jongjong import JongJongStrategy, round_up
from strategies.infinite_buying_v4 import InfiniteBuyingV4Strategy
from strategies.vr_v5 import ValueRebalancingV5Strategy
from core.order_netting import calculate_order_netting, generate_jongjong_orders
from core.market_calendar import get_next_trading_day, parse_date
from core.strategy_registry import get_target_yield
from core.market_cache import set_cached_close, get_cached_close

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
ACCOUNTS_DB_FILE = os.path.join(DATA_DIR, "accounts.db")


class AccountManager:
    """
    다중 계좌 생성, 조회, 삭제, 입출금 관리 및 일일 실매매 운용(Next Day / 체결 정산 / Undo) 관리 클래스
    SQLite3 (WAL 모드) 엔진 기반으로 동작하며, JSON 백업을 동시 유지합니다.
    """

    def __init__(self, filepath: str = ACCOUNTS_FILE, db_path: str = ACCOUNTS_DB_FILE):
        self.filepath = filepath
        self.db_path = db_path
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        from core.account_db import init_db, migrate_from_json_if_needed
        init_db(self.db_path)
        # 기존 accounts.json 데이터가 존재하면 SQLite로 무손실 마이그레이션
        migrate_from_json_if_needed(self.filepath, self.db_path)

    def load_accounts(self) -> list:
        try:
            from core.account_db import load_all_accounts
            accounts = load_all_accounts(self.db_path)
            # 미매도 슬롯의 실현손익 및 매도정보 정제 및 잔고/시드 동기화
            updated = False
            for acc in accounts:
                for r in acc.get('trade_records', []):
                    if not r.get('Sold', False):
                        r['Profit'] = None
                        r['ProfitRate'] = None
                        r['W'] = None
                        r['X'] = None
                if self.sync_account_balances(acc):
                    updated = True
            if updated:
                self.save_accounts(accounts)
            return accounts
        except Exception as e:
            print(f"계좌 DB 로드 중 오류: {e}")
            # 폴백: JSON 로드
            try:
                if os.path.exists(self.filepath):
                    with open(self.filepath, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception:
                pass
            return []

    def sync_account_balances(self, target: dict) -> bool:
        """
        계좌의 초기 시드(initial_seed) 및 입출금 내역(adjustments)을 바탕으로
        현재 현금(current_cash), 총 평가자산(total_asset), 실투자원금(AR), 위기준비금(AK)을
        실시간으로 완벽하게 동기화합니다.
        """
        changed = False
        initial_seed = float(target.get('initial_seed', 100000.0))
        reserve_ratio = float(target.get('reserve_ratio', 0.05))
        adjustments = target.get('adjustments', [])
        records = target.get('trade_records', [])

        total_deposited = sum(float(a.get('amount', 0.0)) for a in adjustments if a.get('type') == 'DEPOSIT')
        total_withdrawn = sum(float(a.get('amount', 0.0)) for a in adjustments if a.get('type') == 'WITHDRAW')
        net_adj = total_deposited - total_withdrawn

        effective_capital = initial_seed + net_adj
        cur_ar = round(effective_capital * (1.0 - reserve_ratio), 2)
        cur_ak = round(effective_capital * reserve_ratio, 2)

        last_applied = float(target.get('last_applied_adj', 0.0))
        unapplied = round(net_adj - last_applied, 2)

        if unapplied != 0.0:
            target['current_cash'] = round(float(target.get('current_cash', initial_seed)) + unapplied, 2)
            target['total_asset'] = round(float(target.get('total_asset', initial_seed)) + unapplied, 2)
            if records:
                last_r = records[-1]
                last_r['Cash'] = round(float(last_r.get('Cash', 0.0)) + unapplied, 2)
                c_p = float(last_r.get('Close', 0.0))
                h = int(last_r.get('Hold', 0))
                last_r['Asset'] = round(float(last_r['Cash']) + c_p * h, 2)
                target['total_asset'] = last_r['Asset']
                target['current_cash'] = last_r['Cash']
            target['last_applied_adj'] = net_adj
            changed = True

        if records:
            last_r = records[-1]
            if last_r.get('AR') != cur_ar or last_r.get('AK') != cur_ak:
                last_r['AR'] = cur_ar
                last_r['AK'] = cur_ak
                changed = True
            c_p = float(last_r.get('Close', 0.0))
            h = int(last_r.get('Hold', 0))
            expected_asset = round(float(last_r.get('Cash', 0.0)) + c_p * h, 2)
            if last_r.get('Asset') != expected_asset:
                last_r['Asset'] = expected_asset
                target['total_asset'] = expected_asset
                changed = True
            target['current_cash'] = float(last_r.get('Cash', 0.0))
            target['current_holdings'] = h
            target['current_price'] = c_p
        else:
            if target.get('current_cash') != effective_capital:
                target['current_cash'] = effective_capital
                target['total_asset'] = effective_capital
                changed = True

        return changed

    def save_accounts(self, accounts: list):
        """계좌 및 거래 일지 데이터를 SQLite3 데이터베이스에 원자적(ACID)으로 저장 및 JSON 자동 백업"""
        from core.account_db import save_all_accounts

        # 1. Primary 저장소: SQLite3 (WAL 모드 트랜잭션)
        save_all_accounts(accounts, self.db_path)

        # 2. Secondary 저장소: 안전한 JSON 자동 백업
        try:
            tmp_file = f"{self.filepath}.tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.filepath)
            backup_file = self.filepath.replace("accounts.json", "accounts.backup.json")
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            print(f"[JSON Backup Warning] {ex}")

    def add_account(self, name: str, strategy: str, ticker: str, start_date: str, initial_seed: float, memo: str = "",
                    trade_records: list = None, adjustments: list = None, current_date: str = None, operational_state: str = None,
                    reserve_ratio: float = 0.05, owner: str = "huxley") -> dict:
        accounts = self.load_accounts()
        acc_id = f"acc_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}"
        
        last_rec = trade_records[-1] if (trade_records and len(trade_records) > 0) else None
        curr_d = current_date or (last_rec['Date'] if last_rec else start_date.strip())
        
        # 신규 계좌는 장전 주문 대기('WAITING_FOR_FILL'), 기존 기록 복원 시에는 'DAY_COMPLETED' 기본값
        if operational_state is None:
            op_state = 'DAY_COMPLETED' if (trade_records and len(trade_records) > 0) else 'WAITING_FOR_FILL'
        else:
            op_state = operational_state

        new_acc = {
            'id': acc_id,
            'owner': (owner or 'huxley').strip().lower(),
            'name': name.strip(),
            'strategy': strategy.strip(),
            'ticker': ticker.strip().upper(),
            'start_date': start_date.strip(),
            'initial_seed': float(initial_seed),
            'reserve_ratio': float(reserve_ratio),   # 위기준비금 비율 (기본 0.05 = 5%)
            'memo': memo.strip(),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'adjustments': adjustments or [],        # 입금 및 출금(세금 등) 이력
            'trade_records': trade_records or [],    # 일일 실매매 기록 일지
            'current_date': curr_d,
            'operational_state': op_state,           # 'WAITING_FOR_FILL' (장전 주문대기) or 'DAY_COMPLETED' (마감정산완료)
            'current_cash': float(last_rec.get('Cash', initial_seed)) if last_rec else float(initial_seed),
            'current_holdings': int(last_rec.get('Hold', 0)) if last_rec else 0,
            'total_asset': float(last_rec.get('Asset', initial_seed)) if last_rec else float(initial_seed),
            'current_price': float(last_rec.get('Close', 0.0)) if last_rec else 0.0,
            'last_applied_adj': 0.0
        }
        self.sync_account_balances(new_acc)
        accounts.append(new_acc)
        self.save_accounts(accounts)
        return new_acc

    def update_account_settings(self, acc_id: str, name: str = None, reserve_ratio: float = None, memo: str = None, initial_seed: float = None) -> dict:
        """
        계좌의 기본 설정(별칭, 위기준비금 비율, 메모, 초기 시드)을 수정합니다.
        시드 변경 시 잔고 및 주문표 연동을 즉시 갱신합니다.
        """
        accounts = self.load_accounts()
        target = next((a for a in accounts if a['id'] == acc_id), None)
        if not target:
            return None

        if name is not None:
            target['name'] = name.strip()
        if reserve_ratio is not None:
            target['reserve_ratio'] = max(0.0, min(1.0, float(reserve_ratio)))
        if memo is not None:
            target['memo'] = memo.strip()
        if initial_seed is not None and float(initial_seed) > 0:
            old_seed = float(target.get('initial_seed', initial_seed))
            new_seed = float(initial_seed)
            seed_diff = round(new_seed - old_seed, 2)
            target['initial_seed'] = new_seed
            if seed_diff != 0.0:
                target['current_cash'] = round(float(target.get('current_cash', 0.0)) + seed_diff, 2)
                target['total_asset'] = round(float(target.get('total_asset', 0.0)) + seed_diff, 2)
                if target.get('trade_records'):
                    last_r = target['trade_records'][-1]
                    last_r['Cash'] = round(float(last_r.get('Cash', 0.0)) + seed_diff, 2)
                    c_p = float(last_r.get('Close', 0.0))
                    h = int(last_r.get('Hold', 0))
                    last_r['Asset'] = round(float(last_r['Cash']) + c_p * h, 2)
                    target['total_asset'] = last_r['Asset']
                    target['current_cash'] = last_r['Cash']

        self.sync_account_balances(target)
        self.save_accounts(accounts)
        return target

    def delete_account(self, acc_id: str) -> bool:
        accounts = self.load_accounts()
        filtered = [a for a in accounts if a['id'] != acc_id]
        if len(filtered) != len(accounts):
            self.save_accounts(filtered)
            return True
        return False

    def get_account_broker_config(self, acc_id: str) -> dict:
        """
        계좌별 자동매매 브로커 설정 안전 조회 (암호화된 시크릿 키는 제외하고 마스킹된 정보만 반환)
        """
        accounts = self.load_accounts()
        target = next((a for a in accounts if a['id'] == acc_id), None)
        if not target:
            return None

        cfg = target.get('auto_trade', {})
        has_creds = bool(cfg.get('app_key_enc') and cfg.get('app_secret_enc'))
        return {
            'account_id': acc_id,
            'account_name': target.get('name'),
            'ticker': target.get('ticker'),
            'enabled': bool(cfg.get('enabled', False)),
            'broker': cfg.get('broker', 'meritz'),
            'notify_telegram': bool(cfg.get('notify_telegram', True)),
            'has_credentials': has_creds,
            'app_key_masked': cfg.get('app_key_masked', ''),
            'last_checked_at': cfg.get('last_checked_at'),
            'last_status': cfg.get('last_status'),
            'last_message': cfg.get('last_message', '')
        }

    def save_account_broker_config(self, acc_id: str, broker: str, enabled: bool,
                                   notify_telegram: bool = True,
                                   app_key: str = None, app_secret: str = None,
                                   check_status: str = "SUCCESS", check_message: str = "") -> dict:
        """
        계좌별 자동매매 브로커 설정 저장.
        제공된 App Key와 App Secret을 대칭키로 안전하게 암호화하여 계좌에 영구 저장합니다.
        """
        from core.security import encrypt_credential, mask_credential

        accounts = self.load_accounts()
        target = next((a for a in accounts if a['id'] == acc_id), None)
        if not target:
            return None

        cur_cfg = target.setdefault('auto_trade', {})
        app_key_enc = cur_cfg.get('app_key_enc', '')
        app_secret_enc = cur_cfg.get('app_secret_enc', '')
        app_key_masked = cur_cfg.get('app_key_masked', '')

        # 새로운 키가 입력된 경우 암호화하여 갱신
        if app_key and app_key.strip():
            app_key_enc = encrypt_credential(app_key.strip())
            app_key_masked = mask_credential(app_key.strip())
        if app_secret and app_secret.strip():
            app_secret_enc = encrypt_credential(app_secret.strip())

        target['auto_trade'] = {
            'enabled': bool(enabled),
            'broker': broker.lower().strip() if broker else 'meritz',
            'notify_telegram': bool(notify_telegram),
            'app_key_enc': app_key_enc,
            'app_secret_enc': app_secret_enc,
            'app_key_masked': app_key_masked,
            'last_checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_status': check_status,
            'last_message': check_message
        }

        self.save_accounts(accounts)
        return self.get_account_broker_config(acc_id)

    def get_account_strategy_params(self, acc_id: str) -> dict:
        """
        계좌별 전략 설정 파라미터 조회 (기본값 제공)
        """
        accounts = self.load_accounts()
        target = next((a for a in accounts if a['id'] == acc_id), None)
        if not target:
            return None
        params = target.get('strategy_params') or {}
        return {
            'max_hold_days': int(params.get('max_hold_days', 10)),
            'reserve_ratio': float(params.get('reserve_ratio', target.get('reserve_ratio', 0.05))),
            'fee_rate': float(params.get('fee_rate', 0.0)),
            'normal_target_yield': float(params.get('normal_target_yield', 0.0275)),
            'normal_splits': float(params.get('normal_splits', 8.0)),
            'safe_target_yield': float(params.get('safe_target_yield', 0.0025)),
            'safe_splits': float(params.get('safe_splits', 7.0)),
            'riskoff_target_yield': float(params.get('riskoff_target_yield', 0.0070)),
            'riskoff_splits': float(params.get('riskoff_splits', 5.0))
        }

    def save_account_strategy_params(self, acc_id: str, params: dict) -> dict:
        """
        계좌별 전략 파라미터(보유일수, 위기준비율, 수수료율, 모드별 목표수익률 및 분할수)를 저장합니다.
        """
        accounts = self.load_accounts()
        target = next((a for a in accounts if a['id'] == acc_id), None)
        if not target:
            raise ValueError(f"계좌 ID {acc_id}를 찾을 수 없습니다.")

        clean_params = {
            'max_hold_days': int(params.get('max_hold_days', 10)),
            'reserve_ratio': float(params.get('reserve_ratio', 0.05)),
            'fee_rate': float(params.get('fee_rate', 0.0)),
            'normal_target_yield': float(params.get('normal_target_yield', 0.0275)),
            'normal_splits': float(params.get('normal_splits', 8.0)),
            'safe_target_yield': float(params.get('safe_target_yield', 0.0025)),
            'safe_splits': float(params.get('safe_splits', 7.0)),
            'riskoff_target_yield': float(params.get('riskoff_target_yield', 0.0070)),
            'riskoff_splits': float(params.get('riskoff_splits', 5.0))
        }

        target['strategy_params'] = clean_params
        target['reserve_ratio'] = clean_params['reserve_ratio']
        self.sync_account_balances(target)
        self.save_accounts(accounts)
        return clean_params

    def export_trade_records_csv(self, acc_id: str, file_path: str) -> bool:
        """
        계좌의 매매 일지(trade_records) 및 상세 지표를 CSV 파일로 저장합니다.
        메타데이터(Ticker, Strategy, InitialSeed 등)를 포함하여 나중에 새 계좌 생성 시
        그대로 불러와 이어갈 수 있도록 지원합니다.
        """
        accounts = self.load_accounts()
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return False

        details = self.compute_account_details(acc)
        df_res = details.get('df_res')
        if df_res is None or df_res.empty:
            return False

        df_export = df_res.copy()
        df_export['AccountName'] = acc.get('name', '')
        df_export['Ticker'] = acc.get('ticker', '')
        df_export['Strategy'] = acc.get('strategy', '')
        df_export['InitialSeed'] = acc.get('initial_seed', 0.0)

        df_export.to_csv(file_path, index=False, encoding='utf-8-sig')
        return True

    def parse_trade_records_csv(self, file_path: str) -> dict:
        """
        CSV 파일을 읽어 계좌 메타데이터와 정규화된 trade_records 목록을 추출합니다.
        영문 헤더 및 한국어 엑셀 헤더(거래일자, 종가, 매수량 등)를 모두 자동 호환합니다.
        """
        encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']
        df = None
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, encoding=enc)
                break
            except Exception:
                continue

        if df is None or df.empty:
            raise ValueError("CSV 파일을 읽을 수 없거나 데이터가 비어 있습니다.")

        col_map = {
            '날짜': 'Date', '일자': 'Date', '거래일자': 'Date', 'date': 'Date',
            '종가': 'Close', 'close': 'Close',
            '변동률': 'Chg', '등락률': 'Chg', 'chg': 'Chg',
            '모드': 'Mode', '구분모드': 'Mode', 'mode': 'Mode',
            '매수량': 'BuyQty', '매수수량': 'BuyQty', 'r': 'R', 'buyqty': 'BuyQty',
            '매수가': 'BuyPrice', '매수단가': 'BuyPrice', '체결단가': 'BuyPrice', 'buyprice': 'BuyPrice',
            '매수금액': 'S', 's': 'S',
            '목표가': 'U', 'u': 'U',
            '매도여부': 'Sold', '청산여부': 'Sold', 'sold': 'Sold',
            '매도일': 'W', '청산일': 'W', '매도일자': 'W', 'w': 'W',
            '매도가': 'X', '매도단가': 'X', '청산가': 'X', 'x': 'X',
            '매도량': 'SellQty', '매도수량': 'SellQty', '청산수량': 'SellQty', 'y': 'SellQty', 'sellqty': 'SellQty',
            '매도금액': 'Z', '청산금액': 'Z', 'z': 'Z',
            '손익금액': 'Profit', '실현손익': 'Profit', '손익': 'Profit', 'profit': 'Profit',
            '예수금': 'Cash', '현금': 'Cash', '보유현금': 'Cash', 'cash': 'Cash',
            '보유량': 'Hold', '보유수량': 'Hold', 'hold': 'Hold',
            '총자산': 'Asset', '평가금': 'Asset', '총평가자산': 'Asset', 'asset': 'Asset',
            '메모': 'Memo', '비고': 'Memo', 'memo': 'Memo',
            '슬롯상태': 'StatusText', '상태': 'StatusText', 'statustext': 'StatusText',
            'tag': 'Tag',
            '종목': 'Ticker', 'ticker': 'Ticker',
            '전략': 'Strategy', 'strategy': 'Strategy',
            '초기시드': 'InitialSeed', 'initialseed': 'InitialSeed',
            '계좌명': 'AccountName', 'accountname': 'AccountName'
        }

        renamed = {}
        for c in df.columns:
            s_c = str(c).strip()
            low_c = s_c.lower()
            if s_c in col_map:
                renamed[c] = col_map[s_c]
            elif low_c in col_map:
                renamed[c] = col_map[low_c]
        df = df.rename(columns=renamed)

        if 'Date' not in df.columns:
            raise ValueError("CSV 파일에 날짜(Date/거래일자) 열이 존재하지 않습니다.")

        ticker = 'SOXL'
        if 'Ticker' in df.columns and not df['Ticker'].isna().all():
            ticker = str(df['Ticker'].dropna().iloc[0]).strip().upper()
        elif 'SOXL' in file_path.upper():
            ticker = 'SOXL'
        elif 'TQQQ' in file_path.upper():
            ticker = 'TQQQ'

        strategy = '종종이 기본전략'
        if 'Strategy' in df.columns and not df['Strategy'].isna().all():
            strategy = str(df['Strategy'].dropna().iloc[0]).strip()
        elif '종종' in file_path:
            strategy = '종종이 기본전략'
        elif '무한' in file_path:
            strategy = '무한매수법 v4.0'
        elif 'VR' in file_path.upper():
            strategy = 'VR 5.0'

        initial_seed = 150000.0
        if 'InitialSeed' in df.columns and not df['InitialSeed'].isna().all():
            initial_seed = float(df['InitialSeed'].dropna().iloc[0])
        elif 'Cash' in df.columns and not pd.isna(df['Cash'].iloc[0]):
            initial_seed = float(df['Cash'].iloc[0])
        elif 'Asset' in df.columns and not pd.isna(df['Asset'].iloc[0]):
            initial_seed = float(df['Asset'].iloc[0])

        account_name = f"{ticker} 복원 계좌"
        if 'AccountName' in df.columns and not df['AccountName'].isna().all():
            account_name = str(df['AccountName'].dropna().iloc[0]).strip()
        else:
            base = os.path.splitext(os.path.basename(file_path))[0]
            clean_base = base.replace('_매매기록', '').replace('_trade_records', '')
            if clean_base:
                account_name = clean_base

        records = []
        for idx, row in df.iterrows():
            d_val = str(row['Date'])[:10]
            close_v = float(row.get('Close', 0.0)) if not pd.isna(row.get('Close')) else 0.0
            r_v = int(row.get('R', row.get('BuyQty', 0))) if not pd.isna(row.get('R', row.get('BuyQty', 0))) else 0
            buy_p = float(row.get('BuyPrice', close_v)) if not pd.isna(row.get('BuyPrice')) else close_v
            s_v = float(row.get('S', 0.0)) if not pd.isna(row.get('S')) else round(buy_p * r_v * 1.001, 2)
            u_v = float(row['U']) if ('U' in row and not pd.isna(row['U']) and float(row['U']) > 0) else None

            w_raw = row.get('W')
            sold_raw = row.get('Sold')
            is_sold = False
            w_val = None
            if w_raw is not None and not pd.isna(w_raw) and str(w_raw).strip() not in ('', '-', 'None', 'nan'):
                is_sold = True
                w_val = str(w_raw)[:10]
            elif sold_raw is True or str(sold_raw).lower() in ('true', '1'):
                is_sold = True
                w_val = str(w_raw)[:10] if (w_raw is not None and not pd.isna(w_raw)) else d_val

            x_v = float(row['X']) if ('X' in row and not pd.isna(row['X']) and float(row['X']) > 0) else None
            z_v = float(row['Z']) if ('Z' in row and not pd.isna(row['Z'])) else 0.0
            profit_v = float(row['Profit']) if ('Profit' in row and not pd.isna(row['Profit'])) else (None if not is_sold else 0.0)
            sell_q = int(row.get('SellQty', 0)) if not pd.isna(row.get('SellQty')) else 0
            cash_v = float(row.get('Cash', 0.0)) if not pd.isna(row.get('Cash')) else 0.0
            hold_v = int(row.get('Hold', 0)) if not pd.isna(row.get('Hold')) else 0
            asset_v = float(row.get('Asset', 0.0)) if not pd.isna(row.get('Asset')) else round(cash_v + hold_v * close_v, 2)

            rec = {
                't': idx,
                'Date': d_val,
                'Close': close_v,
                'Chg': float(row.get('Chg', 0.0)) if not pd.isna(row.get('Chg')) else 0.0,
                'Mode': str(row.get('Mode', 'Normal')),
                'R': r_v,
                'BuyQty': r_v,
                'BuyPrice': buy_p,
                'S': s_v,
                'U': u_v,
                'Sold': is_sold,
                'W': w_val,
                'X': x_v,
                'Z': z_v,
                'Profit': profit_v,
                'SellQty': sell_q,
                'Cash': cash_v,
                'Hold': hold_v,
                'Asset': asset_v,
                'AR': float(row.get('AR', 0.0)) if not pd.isna(row.get('AR')) else initial_seed,
                'AK': float(row.get('AK', 0.0)) if not pd.isna(row.get('AK')) else 0.0,
                'Memo': str(row.get('Memo', '')) if not pd.isna(row.get('Memo')) else '',
                'StatusText': str(row.get('StatusText', '')) if not pd.isna(row.get('StatusText')) else '',
                'Tag': str(row.get('Tag', 'tag_normal')) if not pd.isna(row.get('Tag')) else 'tag_normal'
            }
            records.append(rec)

        return {
            'account_name': account_name,
            'ticker': ticker,
            'strategy': strategy,
            'initial_seed': initial_seed,
            'start_date': records[0]['Date'] if records else datetime.now().strftime('%Y-%m-%d'),
            'current_date': records[-1]['Date'] if records else datetime.now().strftime('%Y-%m-%d'),
            'current_cash': records[-1]['Cash'] if records else initial_seed,
            'current_hold': records[-1]['Hold'] if records else 0,
            'total_asset': records[-1]['Asset'] if records else initial_seed,
            'current_price': records[-1]['Close'] if records else 0.0,
            'trade_records': records,
            'record_count': len(records)
        }

    def add_adjustment(self, acc_id: str, adj_type: str, amount: float, date_str: str, reason: str = "") -> bool:
        """
        계좌에 현금 입금(DEPOSIT) 또는 출금(WITHDRAW, 예: 세금 납부)을 기록하고,
        예수금/총자산/실투자원금(AR) 및 당일 매수/매도 주문표를 즉시 재계산하여 업데이트합니다.
        """
        accounts = self.load_accounts()
        target = None
        for a in accounts:
            if a['id'] == acc_id:
                target = a
                break

        if not target:
            return False

        adj_entry = {
            'id': f"adj_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}",
            'type': adj_type.upper(),  # 'WITHDRAW' or 'DEPOSIT'
            'amount': float(amount),
            'date': date_str.strip(),
            'reason': reason.strip(),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        target.setdefault('adjustments', []).append(adj_entry)
        self.sync_account_balances(target)

        # 잔액/AR 변경에 따른 당일 매수/매도 주문표 즉시 재계산 및 갱신
        details = self.compute_account_details(target)
        target['order_table'] = details.get('orders', {})

        self.save_accounts(accounts)
        return True

    def delete_adjustment(self, acc_id: str, adj_id: str) -> bool:
        """
        계좌의 특정 입출금 내역을 삭제하고,
        예수금/총자산/실투자원금(AR) 롤백 및 당일 매수/매도 주문표를 즉시 재계산하여 업데이트합니다.
        """
        accounts = self.load_accounts()
        target = next((a for a in accounts if a['id'] == acc_id), None)
        if not target:
            return False

        adjs = target.get('adjustments', [])
        found_idx = None
        for i, a in enumerate(adjs):
            if str(a.get('id', '')) == str(adj_id):
                found_idx = i
                break

        if found_idx is None:
            return False

        removed = adjs.pop(found_idx)
        print(f"[AccountManager] 입출금 기록 삭제: 계좌={target.get('name')}, type={removed.get('type')}, amount={removed.get('amount')}, date={removed.get('date')}")

        # 잔액 및 자산 롤백 동기화
        self.sync_account_balances(target)

        # 잔액/AR 변경에 따른 당일 매수/매도 주문표 즉시 재계산 및 갱신
        details = self.compute_account_details(target)
        target['order_table'] = details.get('orders', {})

        self.save_accounts(accounts)
        return True

    def advance_next_day(self, acc_id: str) -> dict:
        """
        계좌의 운용 날짜를 다음 미국 증시 개장일(영업일)로 진행시킵니다.
        (주말 및 미국 공휴일을 자동으로 건너뜁니다)
        """
        accounts = self.load_accounts()
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return None

        records = acc.get('trade_records', [])
        base_d_str = acc.get('current_date')
        if not base_d_str:
            base_d_str = records[-1]['Date'] if records else acc.get('start_date', '2026-01-02')

        curr_d = parse_date(base_d_str)
        next_d = get_next_trading_day(curr_d)
        next_d_str = next_d.strftime('%Y-%m-%d')

        acc['current_date'] = next_d_str
        if records:
            last_r = records[-1]
            acc['current_cash'] = float(last_r.get('Cash', acc.get('current_cash', 0.0)))
            acc['current_holdings'] = int(last_r.get('Hold', acc.get('current_holdings', 0)))
            acc['current_price'] = float(last_r.get('Close', acc.get('current_price', 0.0)))
            acc['total_asset'] = float(last_r.get('Asset', acc.get('total_asset', 0.0)))
        acc['operational_state'] = 'WAITING_FOR_FILL'  # 미국 장전 - LOC 주문 대기 상태
        self.save_accounts(accounts)
        return acc

    def record_daily_close(self, acc_id: str, close_price: float, buy_qty: int = 0, buy_price: float = None,
                           sell_qty: int = 0, sell_price: float = None, memo: str = "", trade_date: str = None,
                           mode: str = None) -> dict:
        """
        미국 주식 시장 마감 후 당일 종가와 실제 체결 수량을 기록하고 계좌 잔고 및 일지를 갱신합니다.
        한 행은 하나의 슬롯(Lot)에 대한 정보를 담으며, 체결된 슬롯의 매도일/매도가/손익/손익률이 갱신됩니다.
        """
        accounts = self.load_accounts()
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return None

        records = acc.setdefault('trade_records', [])
        curr_d_str = trade_date.strip() if (trade_date and str(trade_date).strip()) else acc.get('current_date')
        if not curr_d_str:
            curr_d_str = records[-1]['Date'] if records else acc.get('start_date', '2026-01-02')

        # 이미 해당 날짜의 기록이 존재하면 덮어쓰고, 없으면 새로 추가
        existing_idx = None
        for i, r in enumerate(records):
            if r.get('Date') == curr_d_str:
                existing_idx = i
                break

        prev_rec = records[existing_idx - 1] if (existing_idx is not None and existing_idx > 0) else (records[-1] if (existing_idx is None and records) else None)

        prev_cash = float(prev_rec['Cash']) if prev_rec else float(acc['initial_seed'])
        prev_hold = int(prev_rec['Hold']) if prev_rec else 0
        prev_close = float(prev_rec['Close']) if prev_rec else float(close_price)
        reserve_ratio = float(acc.get('reserve_ratio', 0.05))
        init_seed = float(acc.get('initial_seed', 100000.0))
        cur_ar = round(init_seed * (1.0 - reserve_ratio), 2)
        cur_ak = round(init_seed * reserve_ratio, 2)

        close_p = round(float(close_price), 2)
        chg = (close_p / prev_close - 1.0) if prev_close > 0 else 0.0

        if not mode:
            mode = prev_rec.get('Mode', 'Normal') if prev_rec else 'Normal'

        strat_params = acc.get('strategy_params') or {}
        fee_rate = float(strat_params.get('fee_rate', 0.00044))
        sec_fee = 0.0000278
        max_hold = int(strat_params.get('max_hold_days', 10))

        # 1. 매도 체결 정산
        # 당일 시점(today_t) 기준 미매도 슬롯 및 만기 도달(h_days >= max_hold) 슬롯 산출
        today_t = existing_idx if existing_idx is not None else len(records)
        unsold_lots = [r for r in records if r.get('R', 0) > 0 and not r.get('Sold', False)]
        moc_shares = sum(int(l.get('R', 0)) for l in unsold_lots if (today_t - int(l.get('t', 0))) >= max_hold)

        sell_q = int(sell_qty)
        # 종종이 전략: 10영업일 만기 도달 슬롯(MOC)은 매도 수량에 무조건 포함하여 강제 손절/청산
        if '종종이' in acc.get('strategy', '') and moc_shares > 0:
            sell_q = max(sell_q, moc_shares)

        sell_p = round(float(sell_price), 2) if sell_price is not None and sell_price > 0 else close_p
        net_sell_proceeds = 0.0
        total_profit = 0.0
        shares_to_sell = sell_q

        if shares_to_sell > 0:
            def get_lot_u(lot):
                bp = float(lot.get('BuyPrice', lot.get('Close', close_p)))
                lot_mode = str(lot.get('Mode', 'Normal')).capitalize()
                lot_yield = get_target_yield(acc.get('strategy'), lot_mode)
                return round_up(bp * (1.0 + lot_yield), 2)

            # 슬롯 매도 우선순위 정렬 (만기 및 목표가 도달 익절 우선, 낮은 목표가 순)
            def get_sort_key(lot):
                u_val = get_lot_u(lot)
                h_days = today_t - int(lot.get('t', 0))
                is_moc = (h_days >= max_hold)
                is_target_reached = (close_p >= u_val - 1e-4)
                priority = 0 if (is_target_reached or is_moc) else 1
                return (priority, u_val)

            sorted_unsold_lots = sorted(unsold_lots, key=get_sort_key)

            for lot in sorted_unsold_lots:
                if shares_to_sell <= 0:
                    break
                u_val = get_lot_u(lot)
                h_days = today_t - int(lot.get('t', 0))
                is_moc = (h_days >= max_hold)
                is_target_reached = (close_p >= u_val - 1e-4)

                # 종종이 전략 보호: 목표가 미도달 및 만기 미도달 슬롯은 보호
                if not is_target_reached and not is_moc and '종종이' in acc.get('strategy', ''):
                    continue

                lot_r = int(lot['R'])
                if lot_r <= shares_to_sell:
                    lot['Sold'] = True
                    lot['W'] = curr_d_str
                    lot['X'] = close_p  # 기록은 당일 종가를 기록
                    gross_s = sell_p * lot_r
                    net_s = gross_s - gross_s * (fee_rate + sec_fee)  # 예수금 반영 시 실제 수수료/제비용 공제
                    lot['Z'] = round(net_s, 2)
                    p_amt = net_s - float(lot.get('S', 0.0))
                    lot['Profit'] = round(p_amt, 2)
                    bp = float(lot.get('BuyPrice', lot.get('Close', 1.0)))
                    lot['ProfitRate'] = round((close_p / bp - 1.0) * 100.0, 2) if bp > 0 else 0.0
                    lot['HoldDays'] = h_days
                    total_profit += p_amt
                    net_sell_proceeds += net_s
                    shares_to_sell -= lot_r
                else:
                    # 부분 매도 시 슬롯 차감
                    sold_part = shares_to_sell
                    lot['R'] = lot_r - sold_part
                    gross_s = sell_p * sold_part
                    net_s = gross_s - gross_s * (fee_rate + sec_fee)
                    net_sell_proceeds += net_s
                    shares_to_sell = 0
                    break

        # 2. 매수 체결 정산
        buy_q = int(buy_qty)
        # 기록은 당일 종가(close_p)를 기록하고, 예수금에는 실제 수수료 포함 금액으로 반영
        record_buy_p = close_p
        exec_buy_p = round(float(buy_price), 2) if buy_price is not None and buy_price > 0 else close_p
        gross_b = exec_buy_p * buy_q
        b_fee = gross_b * fee_rate
        s_amt = round(gross_b + b_fee, 2)  # 예수금 차감 시 수수료 포함

        target_yield = get_target_yield(acc.get('strategy'), mode)
        u_target = round_up(record_buy_p * (1.0 + target_yield), 2) if buy_q > 0 else None

        # 3. 신규 잔고 산출 (예수금에 실제 수수료 반영)
        new_cash = round(max(0.0, prev_cash - s_amt + net_sell_proceeds), 2)
        new_hold = max(0, prev_hold + buy_q - sell_q)
        new_asset = round(new_cash + close_p * new_hold, 2)

        # 4. 상태 텍스트
        if buy_q > 0 and sell_q > 0:
            profit_str = f"+${total_profit:,.0f}" if total_profit >= 0 else f"-${abs(total_profit):,.0f}"
            status_text = f"🟢 매수({buy_q:,}주) / 🔴 익절({sell_q:,}주, {profit_str})" if total_profit >= 0 else f"🟢 매수({buy_q:,}주) / 🔵 손절({sell_q:,}주, {profit_str})"
            tag = 'tag_profit_pos' if total_profit >= 0 else 'tag_profit_neg'
        elif buy_q > 0:
            status_text = f"🟢 매도 대기 ({buy_q:,}주 / 보유 0일차)"
            tag = 'tag_active'
        elif sell_q > 0:
            status_text = f"🔴 익절 완료 (+${total_profit:,.2f})" if total_profit >= 0 else f"🔵 손절 완료 (-${abs(total_profit):,.2f})"
            tag = 'tag_profit_pos' if total_profit >= 0 else 'tag_profit_neg'
        else:
            status_text = "⚪ 체결 없음 (관망)"
            tag = 'tag_normal'

        new_entry = {
            't': len(records) if existing_idx is None else existing_idx,
            'Date': curr_d_str,
            'Close': close_p,
            'Chg': round(chg, 4),
            'Mode': mode,
            'R': buy_q,
            'BuyQty': buy_q,
            'BuyPrice': record_buy_p,  # 매매 일지 기록은 종가(Close)
            'S': s_amt,
            'U': u_target,  # 종가 기준 목표가
            'Sold': False,
            'W': None,
            'X': None,
            'Z': 0.0,
            'Profit': None,
            'ProfitRate': None,
            'SellQty': sell_q,
            'Cash': new_cash,
            'Hold': new_hold,
            'Asset': new_asset,
            'AR': cur_ar,
            'AK': cur_ak,
            'Memo': memo,
            'StatusText': status_text,
            'Tag': tag
        }

        if existing_idx is not None:
            records[existing_idx] = new_entry
        else:
            records.append(new_entry)

        acc['current_date'] = curr_d_str
        acc['current_cash'] = new_cash
        acc['current_holdings'] = new_hold
        acc['total_asset'] = new_asset
        acc['current_price'] = close_p
        acc['operational_state'] = 'DAY_COMPLETED'  # 장 마감 정산 완료 상태
        self.save_accounts(accounts)

        # 시스템 전역 종가 변수에 등록 (모든 사용자/계좌가 즉시 공유)
        try:
            acc_name = acc.get('name', '사용자')
            set_cached_close(acc.get('ticker', 'SOXL'), close_p, date_str=curr_d_str, source=f"정산 입력 ({acc_name})")
        except Exception as ex:
            print(f"[AccountManager] 전역 종가 캐시 등록 안내: {ex}")

        return acc

    def delete_last_day_record(self, acc_id: str) -> bool:
        """
        가장 최근 거래일의 기록을 삭제하고 이전 날짜로 계좌 상태를 되돌립니다 (Undo 기능).
        해당 거래일에 매도되었던 슬롯들도 미매도(Sold=False) 상태로 복구됩니다.
        """
        accounts = self.load_accounts()
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return False

        records = acc.get('trade_records', [])
        if not records:
            return False

        removed = records.pop()
        removed_d = removed.get('Date')

        # 이 날짜에 청산되었던 이전 슬롯 복구
        for r in records:
            if r.get('W') == removed_d:
                r['Sold'] = False
                r['W'] = None
                r['X'] = None
                r['Z'] = 0.0
                r['Profit'] = 0.0

        if records:
            acc['current_date'] = records[-1]['Date']
            acc['operational_state'] = 'DAY_COMPLETED'
        else:
            acc['current_date'] = acc.get('start_date', '2026-01-02')
            acc['operational_state'] = 'WAITING_FOR_FILL'

        self.save_accounts(accounts)
        return True

    delete_last_trade_record = delete_last_day_record

    def update_trade_record(self, acc_id: str, date_str: str, updated_fields: dict) -> bool:
        """
        특정 거래일의 기록을 수정하고 이후 누적 잔고(Cash, Hold, Asset)를 재계산합니다.
        """
        accounts = self.load_accounts()
        acc = next((a for a in accounts if a['id'] == acc_id), None)
        if not acc:
            return False

        records = acc.get('trade_records', [])
        target_idx = None
        for i, r in enumerate(records):
            if r.get('Date') == date_str:
                target_idx = i
                break

        if target_idx is None:
            return False

        records[target_idx].update(updated_fields)

        # 잔고 및 슬롯 상태 재계산
        for i in range(len(records)):
            r = records[i]
            prev = records[i - 1] if i > 0 else None
            p_cash = float(prev['Cash']) if prev else float(acc['initial_seed'])
            p_hold = int(prev['Hold']) if prev else 0
            b_q = int(r.get('BuyQty', r.get('R', 0)))
            s_q = int(r.get('SellQty', 0))
            c_p = float(r['Close'])
            b_fee = c_p * b_q * 0.001
            s_amt = c_p * b_q + b_fee
            z_amt = float(r.get('Z', 0.0))
            if z_amt == 0.0 and s_q > 0:
                z_amt = c_p * s_q * (1.0 - 0.0010278)
            r_cash = round(max(0.0, p_cash - s_amt + z_amt), 2)
            r_hold = max(0, p_hold + b_q - s_q)
            r['Cash'] = r_cash
            r['Hold'] = r_hold
            r['Asset'] = round(r_cash + c_p * r_hold, 2)

        self.save_accounts(accounts)
        return True

    def compute_account_details(self, acc: dict, df_market: pd.DataFrame = None) -> dict:
        """
        계좌의 실시간 자산 현황, 오늘의 주문표, 매매 기록을 산출합니다.
        영구 보존된 trade_records가 존재하면 이를 기반으로 운용하며,
        최초 실행 시에만 과거 시뮬레이션을 통해 trade_records를 초기화합니다.
        """
        self.sync_account_balances(acc)
        ticker = acc['ticker']
        strategy_name = acc['strategy']
        start_date = acc['start_date']
        initial_seed = float(acc['initial_seed'])
        adjustments = acc.get('adjustments', [])

        # 입출금 내역 일자별 정리
        adj_by_date = {}
        total_withdrawn = 0.0
        total_deposited = 0.0
        for adj in adjustments:
            d = adj['date']
            amt = float(adj['amount'])
            if adj['type'] == 'WITHDRAW':
                total_withdrawn += amt
                adj_by_date[d] = adj_by_date.get(d, 0.0) - amt
            else:
                total_deposited += amt
                adj_by_date[d] = adj_by_date.get(d, 0.0) + amt

        effective_capital = initial_seed + total_deposited - total_withdrawn
        records = acc.get('trade_records', [])

        # 1. DataFrame 생성 (trade_records가 없는 신규 계좌는 깨끗한 상태 유지)
        if records:
            df_res = pd.DataFrame(records)
            df_res['Date'] = pd.to_datetime(df_res['Date'])
        else:
            df_res = pd.DataFrame(columns=[
                'Date', 'Close', 'Chg', 'Mode', 'R', 'BuyQty', 'BuyPrice', 'S', 'U',
                'Sold', 'W', 'X', 'Z', 'Profit', 'SellQty', 'Cash', 'Hold', 'Asset',
                'AR', 'AK', 'Memo', 'StatusText', 'Tag', 'IsActive'
            ])

        # 기말 지표 계산
        if not df_res.empty:
            last_row = df_res.iloc[-1]
            last_completed_date = last_row['Date'].strftime('%Y-%m-%d')
            latest_close = float(last_row['Close'])
            hold_shares = int(last_row['Hold'])
            final_cash = float(last_row['Cash'])
            final_asset = float(last_row['Asset'])
            avg_price = float(last_row.get('AvgPrice', 0.0))
            if avg_price == 0.0 and hold_shares > 0:
                avg_price = latest_close
        else:
            last_completed_date = start_date
            latest_close = float(df_market.iloc[-1]['Close']) if (df_market is not None and not df_market.empty) else 0.0
            if latest_close <= 0.0:
                try:
                    from core.data import get_stock_price_for_date, get_price_from_db
                    p_db = get_stock_price_for_date(ticker, start_date)
                    if p_db > 0:
                        latest_close = p_db
                    else:
                        latest_close = get_price_from_db(ticker, start_date)
                except Exception:
                    pass
            hold_shares = 0
            final_cash = initial_seed
            final_asset = initial_seed
            avg_price = 0.0
            last_row = {}

        # 매도 대기 수 및 액티브 슬롯 판별
        pending_sell_count = 0
        tags = []
        status_texts = []
        is_actives = []
        buy_qtys = []

        if '종종이' in strategy_name and not df_res.empty:
            unsold_mask = (df_res['R'] > 0) & (~df_res['Sold'])
            pending_sell_count = int(unsold_mask.sum()) if hold_shares > 0 else 0

            for idx, row in df_res.iterrows():
                r = int(row.get('R', 0))
                sold = bool(row.get('Sold', False))
                raw_profit = row.get('Profit')
                profit = float(raw_profit) if (raw_profit is not None and not pd.isna(raw_profit)) else 0.0
                buy_qtys.append(r)

                if r > 0 and not sold:
                    hold_days = len(df_res) - 1 - int(row.get('t', idx))
                    is_actives.append(True)
                    tags.append('tag_active')
                    status_texts.append(f"🟢 매도 대기 ({r:,}주 / 보유 {hold_days}일차)")
                elif profit > 0.01:
                    is_actives.append(False)
                    tags.append('tag_profit_pos')
                    status_texts.append(f"🔴 익절 완료 (+${profit:,.0f})")
                elif profit < -0.01:
                    is_actives.append(False)
                    tags.append('tag_profit_neg')
                    status_texts.append(f"🔵 손절 완료 (-${abs(profit):,.0f})")
                elif r > 0 and sold:
                    is_actives.append(False)
                    tags.append('tag_normal')
                    status_texts.append("⚪ 매수분 청산됨")
                else:
                    is_actives.append(False)
                    tags.append('tag_normal')
                    status_texts.append("관망/대기")

            df_res['IsActive'] = is_actives
            df_res['Tag'] = tags
            df_res['StatusText'] = status_texts
            df_res['BuyQty'] = buy_qtys
        elif not df_res.empty:
            for idx, row in df_res.iterrows():
                is_actives.append(False)
                tags.append('tag_normal')
                status_texts.append("관망/대기")
                buy_qtys.append(0)

            df_res['IsActive'] = is_actives
            df_res['Tag'] = tags
            df_res['StatusText'] = status_texts
            df_res['BuyQty'] = buy_qtys

        net_invested = initial_seed + total_deposited - total_withdrawn
        total_profit = final_asset - net_invested
        total_return_pct = (total_profit / net_invested * 100.0) if net_invested > 0 else 0.0

        # 3. 주문표 산출 기준일 및 주문 생성
        op_state = acc.get('operational_state', 'WAITING_FOR_FILL' if not records else 'DAY_COMPLETED')
        current_date_str = acc.get('current_date', last_completed_date)

        target_order_date = current_date_str
        if op_state == 'WAITING_FOR_FILL':
            display_status = f"{target_order_date} (미국 장전 - 주문 대기 중)"
        else:
            display_status = f"{current_date_str} (장 마감 정산 완료)"

        sell_orders = []
        buy_orders = []
        net_result = {}
        unsold_lots = []

        if '종종이' in strategy_name:
            params = acc.get('strategy_params') or {}
            res_ratio = float(params.get('reserve_ratio', acc.get('reserve_ratio', 0.05)))
            max_hold = int(params.get('max_hold_days', 10))
            fee_r = float(params.get('fee_rate', 0.0))
            target_yields = {
                'Normal': float(params.get('normal_target_yield', 0.0275)),
                'Safe': float(params.get('safe_target_yield', 0.0025)),
                'Riskoff': float(params.get('riskoff_target_yield', 0.0070))
            }
            div_rounds = {
                'Normal': float(params.get('normal_splits', 8.0)),
                'Safe': float(params.get('safe_splits', 7.0)),
                'Riskoff': float(params.get('riskoff_splits', 5.0))
            }
            strat = JongJongStrategy(
                initial_capital=initial_seed,
                reserve_ratio=res_ratio,
                max_hold_days=max_hold,
                fee_rate=fee_r,
                target_yields=target_yields,
                div_rounds=div_rounds
            )
            unsold_mask = (df_res['R'] > 0) & (~df_res['Sold'])
            unsold_df = df_res[unsold_mask]
            unsold_lots = []
            target_t = len(df_res)
            for _, r_lot in unsold_df.iterrows():
                h_days = target_t - int(r_lot.get('t', 0))
                d_str = r_lot['Date'].strftime('%m.%d') if hasattr(r_lot['Date'], 'strftime') else str(r_lot['Date'])
                lot_mode = str(r_lot.get('Mode', 'Normal')).capitalize()
                close_p = float(r_lot['Close'])
                buy_p = float(r_lot.get('BuyPrice', close_p))
                target_yield = strat.target_yields.get(lot_mode, 0.0275)
                u_p = round_up(buy_p * (1.0 + target_yield), 2)
                unsold_lots.append({
                    'date': d_str,
                    'R': int(r_lot['R']),
                    'U': float(u_p),
                    'hold_days': h_days,
                    't': int(r_lot.get('t', 0))
                })

            # 목표 운용일(target_order_date)의 시장 모드(Normal / Safe / Riskoff) 정밀 판별
            if acc.get('manual_mode'):
                mode = acc['manual_mode']
            else:
                try:
                    from core.data import get_cached_candles_from_db
                    # 1. 과거 시세 확보 (로컬 DB + trade_records 결합)
                    closes_dict = {}
                    df_cached = get_cached_candles_from_db(ticker, '2020-01-01', target_order_date)
                    if not df_cached.empty:
                        for _, crow in df_cached.iterrows():
                            d_key = crow['Date'].strftime('%Y-%m-%d') if hasattr(crow['Date'], 'strftime') else str(crow['Date'])[:10]
                            closes_dict[d_key] = float(crow['Close'])

                    for r in records:
                        r_d = str(r.get('Date', ''))[:10]
                        if r_d and r.get('Close') is not None:
                            closes_dict[r_d] = float(r['Close'])

                    # 오늘(target_order_date) 장전이므로 오늘 이전(< target_order_date)의 마감된 거래일 종가만 시간순 추출
                    valid_dates = sorted([d for d in closes_dict.keys() if d < target_order_date])
                    closes_series = [closes_dict[d] for d in valid_dates]

                    prev_mode = str(last_row.get('Mode', 'Normal')) if len(last_row) > 0 else 'Normal'
                    prev_flag = bool(last_row.get('Flag', False)) if len(last_row) > 0 else False

                    if len(closes_series) >= 3:
                        mode = strat.determine_next_mode(
                            closes_series=closes_series,
                            prev_mode=prev_mode,
                            prev_flag=prev_flag
                        )
                    else:
                        mode = prev_mode
                except Exception as ex:
                    print(f"[{ticker}] 익일 모드 정밀 판정 안내 (fallback 사용): {ex}")
                    mode = str(last_row.get('Mode', 'Normal')) if len(last_row) > 0 else 'Normal'

            # 10거래일 시즌 사이클 분석 및 잔여 예산 계산
            total_recs = len(records)
            season_number = (total_recs // 10) + 1
            season_day = (total_recs % 10) + 1  # 1 ~ 10일차
            season_start_idx = (total_recs // 10) * 10
            season_records = records[season_start_idx:]

            target_yield = strat.target_yields.get(mode, 0.0275)
            reserve_ratio = float(acc.get('reserve_ratio', 0.05))
            ar_val = round(effective_capital * (1.0 - reserve_ratio), 2)
            ak_val = round(effective_capital * reserve_ratio, 2)

            normal_splits = float(strat.div_rounds.get('Normal', 8.0))
            safe_splits = float(strat.div_rounds.get('Safe', 7.0))
            riskoff_splits = float(strat.div_rounds.get('Riskoff', 5.0))

            normal_p = round(ar_val / normal_splits, 2)
            safe_p = round(ar_val / safe_splits, 2)
            riskoff_p = round(ar_val / riskoff_splits, 2)

            current_mode_p = safe_p if mode == 'Safe' else (riskoff_p if mode == 'Riskoff' else normal_p)

            # 이번 시즌에 이미 매수 집행된 1회분 배정금 누적액
            season_used_budget = 0.0
            for r in season_records:
                if int(r.get('BuyQty', r.get('R', 0))) > 0:
                    r_mode = str(r.get('Mode', 'Normal'))
                    r_div = safe_splits if r_mode == 'Safe' else (riskoff_splits if r_mode == 'Riskoff' else normal_splits)
                    season_used_budget += (ar_val / r_div)

            season_used_budget = round(season_used_budget, 2)
            season_remaining_budget = max(0.0, round(ar_val - season_used_budget, 2))

            # 당일 매수 예정금 (budget):
            # Normal로 7일 보낸 후 Safe 전환 시 남은 1회분만 매수, 잔여 예산 소진 시 9~10일차 매수 불가(0원)
            budget = min(current_mode_p, season_remaining_budget)
            budget = max(0.0, round(budget, 2))

            season_info = {
                'season_number': season_number,
                'season_day': season_day,
                'total_days_in_season': 10,
                'season_ar': ar_val,
                'season_ak': ak_val,
                'normal_splits': int(normal_splits),
                'safe_splits': int(safe_splits),
                'riskoff_splits': int(riskoff_splits),
                'normal_p': normal_p,
                'safe_p': safe_p,
                'riskoff_p': riskoff_p,
                'current_mode': mode,
                'current_mode_p': current_mode_p,
                'season_used_budget': season_used_budget,
                'season_remaining_budget': season_remaining_budget,
                'daily_p_budget': budget,
                'is_budget_exhausted': bool(budget <= 0.0)
            }

            net_result = generate_jongjong_orders(
                unsold_lots=unsold_lots,
                yest_close=latest_close if latest_close > 0 else 100.0,
                p_budget=budget,
                mode=mode,
                C2=strat.range_normal,
                C3=strat.range_crash,
                C4=strat.order_split_count,
                C6=strat.order_curvature,
                target_yield=target_yield
            )
            sell_orders = net_result['net_sell_orders']
            buy_orders = net_result['net_buy_orders']
        elif 'VR' in strategy_name.upper():
            reserve_ratio = 0.0
            ar_val = initial_seed
            ak_val = 0.0
            g_val = float(acc.get('g_value', 10.0))
            band_pct = float(acc.get('band_pct', 0.15))
            pool_usage_limit = float(acc.get('pool_usage_limit', 0.50))
            num_recs = len(df_res)
            day_in_cycle = (num_recs % 10) + 1
            mode = f"2주 {day_in_cycle}/10일차"

            v_val = float(acc.get('v_value', 0.0))
            if v_val <= 0.0:
                v_val = (hold_shares * latest_close) if (hold_shares > 0 and latest_close > 0) else (initial_seed * 0.85)

            strat = ValueRebalancingV5Strategy(
                ticker=ticker,
                initial_capital=initial_seed,
                g_value=g_val,
                band_pct=band_pct,
                pool_usage_limit=pool_usage_limit
            )
            buy_orders, sell_orders = strat.calculate_order_ladder(
                v_val=v_val,
                current_hold=hold_shares,
                pool_cash=final_cash,
                pool_usage_limit=pool_usage_limit,
                current_price=latest_close,
                max_orders=15
            )
            budget = max(0.0, final_cash * pool_usage_limit)
            net_result = {
                'is_netted': False,
                'summary_text': f"⚡ [VR 5.0 2주 예약] V: ${v_val:,.2f} | 밴드: ${v_val*(1-band_pct):,.2f} ~ ${v_val*(1+band_pct):,.2f} | 가용 Pool: ${budget:,.2f}"
            }
        else:
            # 3-C. 무한매수법 v4.0 (Infinite Buying V4.0)
            reserve_ratio = 0.0
            ar_val = initial_seed
            ak_val = 0.0
            strat = InfiniteBuyingV4Strategy(ticker=ticker, initial_capital=initial_seed, divisions=40)

            t_val = float(last_row.get('T', 0.0)) if (len(last_row) > 0 and 'T' in last_row) else 0.0
            raw_mode = str(last_row.get('Mode', 'NORMAL')) if (len(last_row) > 0 and 'Mode' in last_row) else 'NORMAL'
            mode = f"일반 (T={t_val:.1f}/40)" if raw_mode.upper() == 'NORMAL' else f"리버스 (T={t_val:.1f})"

            div_count = 40.0
            half_div = div_count / 2.0
            is_soxl = ('SOXL' in ticker.upper())
            limit_target_pct = 0.20 if is_soxl else 0.15

            if hold_shares == 0 or t_val <= 0.0:
                budget = final_cash / div_count
            else:
                budget = final_cash / max(div_count - t_val, 1.0)
            budget = max(0.0, budget)

            # 별지점 계산
            if hold_shares > 0 and avg_price > 0:
                star_pct = strat.calculate_star_pct(t_val)
                star_point = round(avg_price * (1.0 + star_pct), 2)
            else:
                star_point = latest_close

            raw_sell_orders = []
            raw_buy_orders = []

            # 매도 주문 산출
            if hold_shares > 0:
                quarter_qty = int(hold_shares / 4)
                limit_qty = hold_shares - quarter_qty
                limit_price = round(avg_price * (1.0 + limit_target_pct), 2) if avg_price > 0 else round(latest_close * (1.0 + limit_target_pct), 2)

                if quarter_qty > 0:
                    raw_sell_orders.append({
                        'price': max(0.01, star_point),
                        'qty': quarter_qty,
                        'stage': '쿼터 매도 (LOC)',
                        'type': 'LOC 매도'
                    })
                if limit_qty > 0:
                    raw_sell_orders.append({
                        'price': max(0.01, limit_price),
                        'qty': limit_qty,
                        'stage': f'지정가 매도 (+{int(limit_target_pct*100)}%)',
                        'type': '지정가 매도'
                    })

            # 매수 주문 산출
            if hold_shares == 0 or t_val <= 0.0:
                init_qty = int(budget / latest_close) if latest_close > 0 else 0
                if init_qty > 0:
                    raw_buy_orders.append({
                        'price': latest_close,
                        'qty': init_qty,
                        'stage': '1회분 LOC 매수',
                        'type': 'LOC 매수'
                    })
            elif t_val < half_div:
                # 전반전: 0.5회분 별지점 LOC + 0.5회분 평단 LOC
                buy_p_star = max(round(star_point - 0.01, 2), 0.01)
                buy_p_avg = max(round(avg_price, 2), 0.01) if avg_price > 0 else latest_close
                budget_half = budget * 0.5

                qty_star = int(budget_half / buy_p_star) if buy_p_star > 0 else 0
                qty_avg = int(budget_half / buy_p_avg) if buy_p_avg > 0 else 0

                if qty_star > 0:
                    raw_buy_orders.append({
                        'price': buy_p_star,
                        'qty': qty_star,
                        'stage': '별지점 LOC 매수 (0.5회)',
                        'type': 'LOC 매수'
                    })
                if qty_avg > 0:
                    raw_buy_orders.append({
                        'price': buy_p_avg,
                        'qty': qty_avg,
                        'stage': '평단 LOC 매수 (0.5회)',
                        'type': 'LOC 매수'
                    })
            else:
                # 후반전: 1회분 전체 별지점 LOC
                buy_p_star = max(round(star_point - 0.01, 2), 0.01)
                qty_star = int(budget / buy_p_star) if buy_p_star > 0 else 0
                if qty_star > 0:
                    raw_buy_orders.append({
                        'price': buy_p_star,
                        'qty': qty_star,
                        'stage': '별지점 LOC 매수 (1회)',
                        'type': 'LOC 매수'
                    })

            net_result = calculate_order_netting(raw_buy_orders, raw_sell_orders)
            sell_orders = net_result['net_sell_orders']
            buy_orders = net_result['net_buy_orders']

        return {
            'account_id': acc['id'],
            'account_name': acc['name'],
            'strategy_name': strategy_name,
            'ticker': ticker,
            'start_date': start_date,
            'initial_seed': initial_seed,
            'reserve_ratio': reserve_ratio,
            'ar_val': ar_val,
            'ak_val': ak_val,
            'daily_budget': budget,
            'memo': acc.get('memo', ''),
            'latest_date': last_completed_date,
            'current_date': current_date_str,
            'target_order_date': target_order_date,
            'operational_state': op_state,
            'display_status': display_status,
            'current_price': latest_close,
            'current_cash': final_cash,
            'current_hold': hold_shares,
            'pending_sell_count': pending_sell_count,
            'avg_price': avg_price,
            'current_asset': final_asset,
            'total_deposited': total_deposited,
            'total_withdrawn': total_withdrawn,
            'net_invested': net_invested,
            'total_profit': total_profit,
            'total_return_pct': total_return_pct,
            'mode': mode,
            'sell_orders': sell_orders,
            'buy_orders': buy_orders,
            'unsold_lots': unsold_lots,
            'netting_info': net_result,
            'season_info': season_info if 'season_info' in locals() else None,
            'df_res': df_res,
            'adjustments': adjustments
        }

    def delete_accounts_by_owner(self, owner_username: str) -> int:
        """특정 사용자가 소유한 모든 계좌 삭제 (회원 탈퇴/관리자 삭제 시)"""
        owner_clean = owner_username.strip().lower()
        accounts = self.load_accounts()
        remaining = [
            a for a in accounts
            if a.get('owner', 'huxley').lower() != owner_clean
        ]
        deleted_count = len(accounts) - len(remaining)
        if deleted_count > 0:
            self.save_accounts(remaining)
        return deleted_count
