"""
계좌 관리 및 자산 입출금(세금 인출 등) 영속성 관리 모듈 (Account Manager)
데이터 파일(data/accounts.json)을 통해 사용자의 계좌 정보 및 일일 실매매 기록을 영구 보존합니다.
미국 증시 개장일 캘린더를 연동하여 Next Day(다음 거래일) 진행, 당일 종가 및 체결 정산,
일지 수정 및 마지막 거래일 삭제(Undo) 기능을 제공합니다.
"""
import sys
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

if os.environ.get("FLET_APP_STORAGE_DATA"):
    # Flet 모바일 (Android/iOS) 전용 영구 저장소 디렉터리
    BASE_DIR = os.environ.get("FLET_APP_STORAGE_DATA")
elif getattr(sys, 'frozen', False):
    # PyInstaller 실행 파일(.exe)이 위치한 실제 폴더 기준
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")


class AccountManager:
    """
    다중 계좌 생성, 조회, 삭제, 입출금 관리 및 일일 실매매 운용(Next Day / 체결 정산 / Undo) 관리 클래스
    """

    def __init__(self, filepath: str = ACCOUNTS_FILE):
        self.filepath = filepath
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            # 처음 시작 시 계좌가 없는 상태로 초기화
            self.save_accounts([])

    def load_accounts(self) -> list:
        try:
            if not os.path.exists(self.filepath):
                return []
            with open(self.filepath, 'r', encoding='utf-8') as f:
                accounts = json.load(f)
            # 미매도 슬롯의 실현손익 및 매도정보 정제 (한 행은 하나의 슬롯)
            for acc in accounts:
                for r in acc.get('trade_records', []):
                    if not r.get('Sold', False):
                        r['Profit'] = None
                        r['ProfitRate'] = None
                        r['W'] = None
                        r['X'] = None
            return accounts
        except Exception as e:
            print(f"계좌 파일 로드 중 오류: {e}")
            return []

    def save_accounts(self, accounts: list, skip_cloud_sync: bool = False):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)
        if not skip_cloud_sync:
            try:
                from core.cloud_sync import trigger_async_upload
                trigger_async_upload(accounts)
            except Exception:
                pass

    def add_account(self, name: str, strategy: str, ticker: str, start_date: str, initial_seed: float, memo: str = "",
                    trade_records: list = None, adjustments: list = None, current_date: str = None, operational_state: str = None,
                    reserve_ratio: float = 0.05) -> dict:
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
            'current_price': float(last_rec.get('Close', 0.0)) if last_rec else 0.0
        }
        accounts.append(new_acc)
        self.save_accounts(accounts)
        return new_acc

    def update_account_settings(self, acc_id: str, name: str = None, reserve_ratio: float = None, memo: str = None, initial_seed: float = None) -> dict:
        """
        계좌의 기본 설정(별칭, 위기준비금 비율, 메모, 초기 시드)을 수정합니다.
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
            target['initial_seed'] = float(initial_seed)
            if not target.get('trade_records'):
                target['current_cash'] = float(initial_seed)
                target['total_asset'] = float(initial_seed)

        if reserve_ratio is not None or initial_seed is not None:
            cur_r = float(target.get('reserve_ratio', 0.05))
            cur_s = float(target.get('initial_seed', 100000.0))
            if target.get('trade_records'):
                target['trade_records'][-1]['AK'] = round(cur_s * cur_r, 2)
                target['trade_records'][-1]['AR'] = round(cur_s * (1.0 - cur_r), 2)

        self.save_accounts(accounts)
        return target

    def delete_account(self, acc_id: str) -> bool:
        accounts = self.load_accounts()
        filtered = [a for a in accounts if a['id'] != acc_id]
        if len(filtered) != len(accounts):
            self.save_accounts(filtered)
            return True
        return False

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
        계좌에 현금 입금(DEPOSIT) 또는 출금(WITHDRAW, 예: 세금 납부)을 기록합니다.
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

        fee_rate = 0.001
        sec_fee = 0.0000278

        # 1. 매도 체결 정산
        sell_q = int(sell_qty)
        sell_p = round(float(sell_price), 2) if sell_price is not None and sell_price > 0 else close_p
        net_sell_proceeds = 0.0
        total_profit = 0.0
        shares_to_sell = sell_q

        if shares_to_sell > 0:
            unsold_lots = [r for r in records if r.get('R', 0) > 0 and not r.get('Sold', False)]
            t_yield = 0.0275 if '종종이' in acc.get('strategy', '') else 0.05

            def get_lot_u(lot):
                raw_u = lot.get('U')
                if raw_u is not None and not pd.isna(raw_u):
                    return float(raw_u)
                bp = float(lot.get('BuyPrice', lot.get('Close', close_p)))
                return round_up(bp * (1.0 + t_yield), 2)

            # 슬롯 매도 우선순위 정렬 (만기 및 목표가 도달 익절 우선, 낮은 목표가 순)
            def get_sort_key(lot):
                u_val = get_lot_u(lot)
                h_days = len(records) - 1 - int(lot.get('t', 0))
                is_moc = (h_days >= 10)
                is_target_reached = (close_p >= u_val - 1e-4)
                priority = 0 if (is_target_reached or is_moc) else 1
                return (priority, u_val)

            sorted_unsold_lots = sorted(unsold_lots, key=get_sort_key)

            for lot in sorted_unsold_lots:
                if shares_to_sell <= 0:
                    break
                u_val = get_lot_u(lot)
                h_days = len(records) - 1 - int(lot.get('t', 0))
                is_moc = (h_days >= 10)
                is_target_reached = (close_p >= u_val - 1e-4)

                # 종종이 전략 보호: 목표가 미도달 및 만기 미도달 슬롯은 보호
                if not is_target_reached and not is_moc and '종종이' in acc.get('strategy', ''):
                    continue

                lot_r = int(lot['R'])
                if lot_r <= shares_to_sell:
                    lot['Sold'] = True
                    lot['W'] = curr_d_str
                    lot['X'] = sell_p
                    gross_s = sell_p * lot_r
                    net_s = gross_s - gross_s * (fee_rate + sec_fee)
                    lot['Z'] = round(net_s, 2)
                    p_amt = net_s - float(lot.get('S', 0.0))
                    lot['Profit'] = round(p_amt, 2)
                    bp = float(lot.get('BuyPrice', lot.get('Close', 1.0)))
                    lot['ProfitRate'] = round((sell_p / bp - 1.0) * 100.0, 2) if bp > 0 else 0.0
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
        buy_p = round(float(buy_price), 2) if buy_price is not None and buy_price > 0 else close_p
        gross_b = buy_p * buy_q
        b_fee = gross_b * fee_rate
        s_amt = round(gross_b + b_fee, 2)
        target_yield = 0.0275 if '종종이' in acc.get('strategy', '') else 0.05
        u_target = round_up(buy_p * (1.0 + target_yield), 2) if buy_q > 0 else None

        # 3. 신규 잔고 산출
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
            'BuyPrice': buy_p,
            'S': s_amt,
            'U': u_target,
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
        acc['operational_state'] = 'DAY_COMPLETED'  # 장 마감 정산 완료 상태
        self.save_accounts(accounts)
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
                profit = float(row.get('Profit', 0.0))
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
            strat = JongJongStrategy(initial_capital=initial_seed)
            unsold_mask = (df_res['R'] > 0) & (~df_res['Sold'])
            unsold_df = df_res[unsold_mask]
            unsold_lots = []
            for _, r_lot in unsold_df.iterrows():
                h_days = len(df_res) - 1 - int(r_lot.get('t', 0))
                d_str = r_lot['Date'].strftime('%m.%d') if hasattr(r_lot['Date'], 'strftime') else str(r_lot['Date'])
                u_p = r_lot.get('U')
                if u_p is None or pd.isna(u_p):
                    u_p = round_up(float(r_lot['Close']) * (1.0 + strat.target_yields.get(r_lot.get('Mode', 'Normal'), 0.0275)), 2)
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

            target_yield = strat.target_yields.get(mode, 0.0275)
            div = strat.div_rounds.get(mode, 8.0)
            reserve_ratio = float(acc.get('reserve_ratio', 0.05))
            if len(last_row) > 0 and 'AR' in last_row and 'AK' in last_row:
                ar_val = round(float(last_row['AR']), 2)
                ak_val = round(float(last_row['AK']), 2)
            else:
                ar_val = round(initial_seed * (1.0 - reserve_ratio), 2)
                ak_val = round(initial_seed * reserve_ratio, 2)
            budget = min(ar_val / div, final_cash) if final_cash >= (ar_val / div) else final_cash
            budget = max(0.0, budget)

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
            'df_res': df_res,
            'adjustments': adjustments
        }
