import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import pandas as pd
import numpy as np
from core.data import fetch_market_data
from strategies.jongjong import JongJongStrategy, excel_round, round_down, round_up, safe_round4
from core.metrics import calculate_metrics, build_comparison_table, calculate_yearly_stats


class JongJongReserveMergedStrategy(JongJongStrategy):
    """
    위기준비금(AK) 격리 보관 후 Risk-Off 모드 진입 시 전액 투자금(AR & Cash)에 병합하는 전략
    
    variant:
      - 'standard': Risk-Off 진입 시 AK 전액 병합(AK=0). 이후 복리 주기에서 수익 시 AK 재적립(기존 복리 수식).
      - 'no_deduct_on_loss': 손실 시 AK를 깎지 않고(수익 시에만 적립) Risk-Off 때만 병합.
      - 'pause_reinvest_in_riskoff': Risk-Off 진행 중에는 AK 적립을 중단(100% AR 복리), Normal/Safe 복귀 후 재적립.
    """
    def __init__(self,
                 initial_capital: float = 200000.0,
                 reserve_ratio: float = 0.05,
                 fee_rate: float = 0.0005,
                 sec_fee: float = 0.0000278,
                 max_hold_days: int = 10,
                 reinvest_cycle: int = 10,
                 order_split_count: int = 5,
                 order_curvature: float = 0.7,
                 range_normal: float = 0.128,
                 range_crash: float = -0.17,
                 div_rounds: dict = None,
                 target_yields: dict = None,
                 risk_dd_threshold: float = -0.08,
                 risk_drop_threshold: float = -0.15,
                 risk_buy_offset: float = -0.055,
                 variant: str = 'standard',
                 name: str = "종종이(Risk-Off 병합)"):
        super().__init__(
            initial_capital=initial_capital,
            reserve_ratio=reserve_ratio,
            fee_rate=fee_rate,
            sec_fee=sec_fee,
            max_hold_days=max_hold_days,
            reinvest_cycle=reinvest_cycle,
            order_split_count=order_split_count,
            order_curvature=order_curvature,
            range_normal=range_normal,
            range_crash=range_crash,
            div_rounds=div_rounds,
            target_yields=target_yields,
            risk_dd_threshold=risk_dd_threshold,
            risk_drop_threshold=risk_drop_threshold,
            risk_buy_offset=risk_buy_offset,
            name=name
        )
        self.variant = variant

    def run(self, df_data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        df = self.prepare_indicators(df_data, start_date)
        valid_indices = df[(df['Date'] >= pd.Timestamp(start_date)) & (df['Date'] <= pd.Timestamp(end_date))].index
        if len(valid_indices) == 0:
            raise ValueError(f"지정한 기간({start_date} ~ {end_date})에 유효 거래일이 없습니다.")

        start_idx = valid_indices[0]
        end_idx = valid_indices[-1]

        M2 = self.initial_capital
        M3 = self.max_hold_days
        M4 = self.reserve_ratio
        O2 = self.risk_dd_threshold
        O3 = self.risk_drop_threshold
        O4 = self.risk_buy_offset
        C2 = self.range_normal
        C3 = self.range_crash
        C4 = self.order_split_count
        C6 = self.order_curvature
        T2 = self.fee_rate
        T3 = self.sec_fee

        records = []

        ak_vault = M2 * M4
        trading_cash = M2 - ak_vault
        ar_val = M2 - ak_vault

        for t in range(end_idx - start_idx + 1):
            db_idx = start_idx + t
            d = df.loc[db_idx, 'Date']
            close_p = df.loc[db_idx, 'Close']
            yest_close = df.loc[db_idx - 1, 'Close'] if db_idx > 0 else close_p
            chg = close_p / yest_close - 1.0 if t > 0 else 0.0

            # [Step A] 당일 최종 모드 확정
            if t == 0:
                mode = df.loc[db_idx, 'DB_Mode']
            else:
                mode = 'Riskoff' if records[t-1]['Flag'] else df.loc[db_idx, 'DB_Mode']

            prev_mode = records[t-1]['Mode'] if t > 0 else 'Normal'
            prev_ar = records[t-1]['AR'] if t > 0 else ar_val
            prev_ak = records[t-1]['AK'] if t > 0 else ak_vault
            prev_cash = records[t-1]['Cash'] if t > 0 else trading_cash
            prev_hold = records[t-1]['Hold'] if t > 0 else 0

            # [Step B] 10거래일 주기 복리 시드(AR) 및 위기준비금(AK) 동시 갱신
            if t == 0:
                ak_val = ak_vault
                ar_val = M2 - ak_val
                curr_cash_before_trade = trading_cash
            elif (t >= (self.reinvest_cycle * 2) and self.reinvest_cycle > 0 and t % self.reinvest_cycle == 0):
                pf = sum(records[k]['Profit'] for k in range(t - (self.reinvest_cycle * 2), t - self.reinvest_cycle))
                
                if self.variant == 'pause_reinvest_in_riskoff' and mode == 'Riskoff':
                    # Risk-off 기간에는 AK 적립 중단, 100% AR 복리
                    ak_diff = 0.0
                    ar_diff = pf
                elif self.variant == 'no_deduct_on_loss' and pf < 0:
                    # 손실 시에는 AK 보전 (0% 손실 분담)
                    ak_diff = 0.0
                    ar_diff = pf
                else:
                    deduct_reserve = M4 if (prev_ak + pf > 0) else 0.0
                    ak_diff = pf * deduct_reserve
                    ar_diff = pf * (1.0 - deduct_reserve)

                ak_val = prev_ak + ak_diff
                ar_val = prev_ar + ar_diff
                curr_cash_before_trade = prev_cash - ak_diff
            else:
                ak_val = prev_ak
                ar_val = prev_ar
                curr_cash_before_trade = prev_cash

            # [Step B-2: 핵심 신규 로직] Risk-Off 모드가 '시작'되는 시점 트리거
            riskoff_started = (mode == 'Riskoff' and prev_mode != 'Riskoff')
            if riskoff_started and ak_val > 0:
                merged_ak = ak_val
                ar_val += merged_ak
                curr_cash_before_trade += merged_ak
                ak_val = 0.0
            else:
                merged_ak = 0.0

            # [Step C] 당일 매수예정금(P) 산출
            div = self.div_rounds[mode]
            p_budget = ar_val / div if t == 0 else min(ar_val / div, curr_cash_before_trade)

            # [Step D] 일일 LOC 예약 주문표 산출
            unsold = [rec for rec in records if rec['R'] > 0 and not rec['Sold']]
            moc_lots = [rec for rec in unsold if (t - rec['t']) == M3]
            loc_lots = [rec for rec in unsold if (t - rec['t']) < M3]

            AV7 = sum(rec['R'] for rec in moc_lots)
            has_moc = len(moc_lots) > 0
            AU1 = max(0.0, p_budget)
            AU2 = yest_close
            is_normal = (mode == 'Normal')
            is_riskoff = (mode == 'Riskoff')

            BB3 = excel_round(AU2 * (1.0 + C2), 2)
            AU3, AV3 = None, 0
            if len(loc_lots) > 0:
                min_u = min(rec['U'] for rec in loc_lots)
                if is_normal and BB3 >= min_u:
                    AU3 = min_u
                    for rec in loc_lots:
                        if rec['U'] == min_u:
                            AV3 = rec['R']
                            break

            a_val = C2 if is_normal else (O4 if is_riskoff else 0.0)
            if is_normal and AU3 is not None and AU3 <= AU2 * (1.0 + a_val):
                AY2 = safe_round4(AU3 - 0.01)
            else:
                AY2 = safe_round4(AU2 * (1.0 + a_val) - 0.01)

            AZ2 = int(AU1 / AY2) if AY2 > 0 else 0
            BB2 = safe_round4(AU2 * (1.0 + a_val)) if ((not is_normal) and has_moc) else AU3
            BC2 = int(AU1 / BB2) if (is_normal and BB2 is not None and BB2 > 0) else 0
            AY3 = safe_round4(AU2 * (1.0 - C2))

            if AU3 is not None and (BB3 - AY3) != 0:
                AY4 = excel_round((AY2 - AY3) / (BB3 - AY3) * (C4 - 2) + 1.0, 0) - 1
            else:
                AY4 = C4 - 1
            BB4 = C4 - 2 - AY4

            # 하단 매수 호가 배열
            ay_list = [AY2]
            if AY4 - 1 > 0:
                for i_seq in range(AY4 - 1):
                    if AY4 - 2 == 0:
                        ay_list.append(None)
                    else:
                        denom = AY3 + ((AY4 - 2.0 - i_seq) / (AY4 - 2.0)) ** C6 * (AY2 - AY3)
                        val = round_down(AU1 / (AU1 / denom), 2) if (AU1 > 0 and denom > 0) else None
                        ay_list.append(val)

            az_list = [AZ2 - AV7]
            for k in range(1, len(ay_list)):
                if ay_list[k] is None or ay_list[k-1] is None or ay_list[k] <= 0 or ay_list[k-1] <= 0:
                    az_list.append(None)
                else:
                    az_list.append(int(AU1 / ay_list[k]) - int(AU1 / ay_list[k-1]))

            if any(x is None for x in ay_list):
                AZ4 = 1
                ay_valid = [AY2] if (AZ2 - AV7) != 0 else []
            else:
                AZ4 = len(ay_list)
                ay_valid = [ay_list[k] for k in range(len(ay_list)) if az_list[k] != 0]

            # 상단 호가 배열
            bb_list, bc_list = [], []
            if AU3 is not None or has_moc:
                bb_list.append(BB2)
                bc_list.append(AV3 + AV7 - BC2)
            if AU3 is not None and BB4 - 1 > 0:
                for i_seq in range(BB4 - 1):
                    if BB4 - 2 == 0:
                        bb_list.append(None)
                        bc_list.append(None)
                    else:
                        denom = BB3 - ((BB4 - 2.0 - i_seq) / (BB4 - 2.0)) ** C6 * (BB3 - BB2)
                        val = round_down(AU1 / (AU1 / denom), 2) if (AU1 > 0 and denom > 0) else None
                        prev_p = bb_list[-1]
                        bb_list.append(val)
                        if val is None or prev_p is None or val <= 0 or prev_p <= 0:
                            bc_list.append(None)
                        else:
                            bc_list.append(int(AU1 / prev_p) - int(AU1 / val))

            if any(x is None for x in bb_list):
                BC4 = 1
                bb_valid = [bb_list[0]] if (len(bc_list) > 0 and bc_list[0] is not None and bc_list[0] != 0 and bb_list[0] is not None) else []
            else:
                BC4 = len(bb_list)
                bb_valid = [bb_list[k] for k in range(len(bb_list)) if bc_list[k] != 0 and bb_list[k] is not None]

            BE3 = round(round_down(AU1 / (AV3 + 1.0), 2) + 0.01, 2) if AV3 > 0 else None
            BE4 = safe_round4(AU2 * (1.0 + C3))
            BF4 = excel_round(AU1 / BE4, 0) if BE4 > 0 else 0

            be_candidates = list(ay_valid) + list(bb_valid)
            if BE3 is not None and AY3 <= BE3 <= BB3:
                be_candidates.append(BE3)
            if AZ4 == 1:
                be_candidates.append(AY3)
            if BC4 == 1:
                be_candidates.append(BB3)
            BE_col = sorted(be_candidates, reverse=True)

            BF_col = []
            for p in BE_col:
                b_cond = 0 if ((not is_normal) and (BB2 is not None and BB2 <= p)) else 1
                a_calc = (int(AU1 / p) if p > 0 else 0) * b_cond * (1 if p < BB3 else 0) - AV7 - (AV3 if (AU3 is not None and p >= AU3) else 0)
                if AU3 is not None and p >= AU3 and a_calc > 0:
                    bf_val = (int(AU1 / (p - 0.01)) if (p - 0.01) > 0 else 0) - AV7 - AV3
                else:
                    bf_val = a_calc
                BF_col.append(bf_val)

            BH_orders = []
            for k in range(len(BE_col)):
                p, bf = BE_col[k], BF_col[k]
                bf_prev = BF_col[k-1] if k > 0 else None
                bf_next = BF_col[k+1] if k + 1 < len(BE_col) else 0
                p_next = BE_col[k+1] if k + 1 < len(BE_col) else None

                if bf > 0:
                    if bf_prev is not None and bf_prev == 0:
                        continue
                    deduct = 0.01 if (AU3 is not None and p >= AU3 and p != BB2) else 0.0
                    ord_q = bf - (bf_prev if (bf_prev is not None and bf_prev > 0) else 0)
                    if ord_q != 0:
                        BH_orders.append(("매수", safe_round4(p - deduct), ord_q))
                elif bf < 0:
                    add = 0.01 if (p_next is not None and p == p_next and bf < 0 and bf_next > 0) else 0.0
                    ord_q = (bf_next if bf_next < 0 else 0) - bf
                    if ord_q != 0:
                        BH_orders.append(("매도", safe_round4(p + add), ord_q))

            # [Step E] 장 마감 후 종가(close_p) 기준 체결 정산
            BQ3 = close_p
            buy_filled = sum(q for ord_t, p, q in BH_orders if ord_t == "매수" and p >= BQ3)
            sell_filled = sum(q for ord_t, p, q in BH_orders if ord_t == "매도" and q > 0 and p <= BQ3)
            auto_buy_qty = (buy_filled - sell_filled) + (AV3 if (AU3 is not None and AU3 <= BQ3) else 0) + AV7 + (BF4 if BE4 > BQ3 else 0)
            r_buy = max(0, int(auto_buy_qty))

            sell_proceeds, shares_sold_today = 0.0, 0
            for rec in unsold:
                if (t - rec['t']) == M3 or close_p >= rec['U']:
                    rec['Sold'] = True
                    rec['D'] = t - rec['t']
                    rec['W'] = d
                    rec['X'] = close_p
                    gross_sell = close_p * rec['R']
                    sell_fee = gross_sell * (T2 + T3)
                    net_sell = gross_sell - sell_fee
                    rec['Z'] = net_sell
                    rec['Profit'] = net_sell - rec['S']
                    sell_proceeds += net_sell
                    shares_sold_today += rec['R']

            gross_buy = close_p * r_buy
            buy_fee = gross_buy * T2
            s_amt = gross_buy + buy_fee
            u_target = round_up(close_p * (1.0 + self.target_yields[mode]), 2) if r_buy > 0 else None

            curr_cash = curr_cash_before_trade - s_amt + sell_proceeds
            curr_hold = prev_hold + r_buy - shares_sold_today
            
            curr_asset = curr_cash + close_p * curr_hold + ak_val

            max_asset_so_far = max([M2] + [rec['Asset'] for rec in records] + [curr_asset])
            dd = curr_asset / max_asset_so_far - 1.0

            prev_n = 0 if t == 0 else records[t-1]['N']
            n_val = 15 if (t >= M3 and records[t-M3]['R'] > 0 and records[t-M3]['W'] == d) else max(0, prev_n - 1)
            o_val = 1 if (t > 0 and chg < O3 and dd < O2) else 0
            stable = df.loc[db_idx, 'G']
            prev_flag = False if t == 0 else records[t-1]['Flag']
            as_val = False if stable else ((n_val > 0 and o_val > 0) or prev_flag)

            records.append({
                't': t, 'Date': d, 'Close': close_p, 'Chg': chg, 'Mode': mode,
                'P': p_budget, 'Q': int(p_budget / close_p) if p_budget > 0 else 0,
                'R': r_buy, 'S': s_amt, 'U': u_target, 'D': None,
                'Sold': False, 'W': None, 'X': None, 'Z': 0.0, 'Profit': 0.0,
                'Cash': curr_cash, 'Hold': curr_hold, 'Asset': curr_asset, 'DD': dd,
                'AR': ar_val, 'AK': ak_val, 'N': n_val, 'O': o_val, 'Flag': as_val,
                'MergedAK': merged_ak
            })

        df_res = pd.DataFrame(records)
        df_res['DD'] = self.compute_drawdown(df_res['Asset'], self.initial_capital)
        return df_res


def run_comprehensive():
    start_date = "2011-03-01"
    end_date = "2026-09-30"
    capital = 100000.0

    for ticker in ["SOXL", "TQQQ"]:
        print("\n" + "#"*80)
        print(f" ### [{ticker}] {start_date} ~ {end_date} 백테스트 비교 분석 ###")
        print("#"*80)
        df_market = fetch_market_data(ticker, start_date, end_date, warmup_days=60)

        strat_orig = JongJongStrategy(initial_capital=capital, name="1. 종종이 (기존)")
        strat_v1 = JongJongReserveMergedStrategy(initial_capital=capital, variant='standard', name="2. 종종이 (Risk-Off 전액병합)")
        strat_v2 = JongJongReserveMergedStrategy(initial_capital=capital, variant='no_deduct_on_loss', name="3. 종종이 (병합+손실시AK보전)")
        strat_v3 = JongJongReserveMergedStrategy(initial_capital=capital, variant='pause_reinvest_in_riskoff', name="4. 종종이 (병합+RiskOff중적립일시정지)")

        df_orig = strat_orig.run(df_market, start_date, end_date)
        df_v1 = strat_v1.run(df_market, start_date, end_date)
        df_v2 = strat_v2.run(df_market, start_date, end_date)
        df_v3 = strat_v3.run(df_market, start_date, end_date)

        results_dict = {
            strat_orig.name: (df_orig, capital),
            strat_v1.name: (df_v1, capital),
            strat_v2.name: (df_v2, capital),
            strat_v3.name: (df_v3, capital),
        }

        comp_df = build_comparison_table(results_dict)
        print(comp_df.to_string(index=False))


if __name__ == "__main__":
    run_comprehensive()
