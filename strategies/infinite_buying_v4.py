"""
=====================================================================
라오어 무한매수법 V4.0 전략 모듈 (Infinite Buying Method V4.0)
=====================================================================
공식 방법론 문서 완벽 반영:
1. 일반 모드 (소진 전):
   - 회차 T값 동적 관리: 1회매수(+1), 절반매수(+0.5), 쿼터매도(T*0.75), 지정가매도 후 매수((T*0.25)+1 or +0.5)
   - 1회 매수 시도액: 잔금 / (분할수 - T)
   - 별지점(★): TQQQ (15 - 0.75*T)%, SOXL (20 - T)%
   - 전반전(T < 분할수/2): 0.5회분 별지점 LOC + 0.5회분 평단 LOC 매수
   - 후반전(T >= 분할수/2): 1회분 별지점 LOC 매수
   - 매도: 보유량의 1/4 별지점 LOC 매도 (쿼터매도) + 3/4 지정가 매도(TQQQ +15%, SOXL +20%)
   - 보유량 0 도달 시 사이클 종료 및 복리 리셋

2. 소진후 리버스 모드 (T > 39 또는 매수 불가 시):
   - 첫날: 매수 없음, 보유량의 1/20 종가(MOC) 무조건 매도, T = T * 0.95
   - 둘째날 이후:
     - 별지점: 직전 5거래일 종가 평균(SMA 5)
     - 매도: 보유량의 1/20 별지점 LOC 매도 (체결 시 T = T * 0.95)
     - 매수: 총 잔금의 1/4(쿼터매수) 별지점 아래 LOC 매수 (체결 시 T = T + (40-T)*0.25)
     - 잔금/4로 1주 매수 불가 시 MOC 매도로 현금 확보
   - 종료 및 일반모드 복귀: 종가가 평단 대비 TQQQ -15% 초과, SOXL -20% 초과로 회복 시 일반모드로 복귀
"""
import pandas as pd
import numpy as np
from .base import BaseStrategy


class InfiniteBuyingV4Strategy(BaseStrategy):
    """
    라오어 무한매수법 V4.0 전략 클래스 (일반모드 + 리버스모드)
    """

    def __init__(self,
                 ticker: str = 'SOXL',
                 initial_capital: float = 200000.0,
                 divisions: int = 40,
                 fee_rate: float = 0.0005,
                 sec_fee: float = 0.0000278,
                 name: str = "무한매수법 v4.0"):
        super().__init__(name=name, initial_capital=initial_capital,
                         fee_rate=fee_rate, sec_fee=sec_fee)
        self.ticker = str(ticker).upper()
        self.divisions = int(divisions)

    def calculate_star_pct(self, t_val: float) -> float:
        """
        현재 회차(T)에 따른 별%를 계산합니다.
        """
        is_soxl = ('SOXL' in self.ticker)
        if self.divisions == 20:
            pct = (20.0 - 2.0 * t_val) if is_soxl else (15.0 - 1.5 * t_val)
        else:  # 40분할 기본
            pct = (20.0 - t_val) if is_soxl else (15.0 - 0.75 * t_val)
        return pct / 100.0

    def run(self, df_data: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
        df_period = df_data[(df_data['Date'] >= pd.Timestamp(start_date)) &
                            (df_data['Date'] <= pd.Timestamp(end_date))].copy().reset_index(drop=True)

        if len(df_period) == 0:
            raise ValueError(f"지정한 기간({start_date} ~ {end_date})에 '{self.ticker}' 거래 데이터가 없습니다.")

        is_soxl = ('SOXL' in self.ticker)
        limit_target_pct = 0.20 if is_soxl else 0.15          # 지정가 매도 목표: SOXL +20%, TQQQ +15%
        reverse_exit_pct = -0.20 if is_soxl else -0.15         # 리버스모드 종료 회복 기준: SOXL -20%, TQQQ -15%
        div_count = float(self.divisions)
        half_div = div_count / 2.0

        # 상태 변수 초기화
        cash = self.initial_capital
        hold = 0
        avg_price = 0.0
        T = 0.0
        mode = 'NORMAL'          # 'NORMAL' or 'REVERSE'
        reverse_day = 0          # 리버스모드 경과일수
        records = []

        # 시세 데이터 배열 준비
        dates = df_period['Date'].values
        closes = df_period['Close'].values
        highs = df_period['High'].values if 'High' in df_period.columns else closes

        for i in range(len(df_period)):
            d = dates[i]
            close_p = closes[i]
            high_p = highs[i]
            prev_close = closes[i - 1] if i > 0 else close_p

            day_profit = 0.0
            day_buy_qty = 0
            day_sell_qty = 0

            # -------------------------------------------------------------
            # [A] 일반모드 소진 여부 사전 검사 -> 리버스모드 전환 판별
            # -------------------------------------------------------------
            if mode == 'NORMAL':
                # 소진 조건: T가 분할수-1을 초과했거나 (40분할 시 T > 39), 매수가 불가능한 경우
                if T > (div_count - 1.0) and hold > 0:
                    mode = 'REVERSE'
                    reverse_day = 1
                elif hold > 0:
                    current_budget = cash / max(div_count - T, 1.0)
                    if current_budget < prev_close and cash < prev_close:
                        mode = 'REVERSE'
                        reverse_day = 1

            # -------------------------------------------------------------
            # [B] 당일 매매 실행
            # -------------------------------------------------------------
            if mode == 'NORMAL':
                # ==========================
                # 1. 일반 모드 매매
                # ==========================
                # (1) 1회 매수 시도액 산출
                if hold == 0 or T <= 0.0:
                    budget = cash / div_count
                else:
                    budget = cash / max(div_count - T, 1.0)

                # (2) 별지점 산출
                if hold > 0 and avg_price > 0:
                    star_pct = self.calculate_star_pct(T)
                    star_point = round(avg_price * (1.0 + star_pct), 2)
                else:
                    star_point = prev_close

                # (3) 매도 주문 처리
                shares_sold_limit = 0
                shares_sold_quarter = 0

                if hold > 0:
                    # ① 쿼터 매도 (보유량의 1/4 별지점 LOC 매도)
                    quarter_qty = int(hold / 4)
                    # ② 지정가 매도 (나머지 3/4 수량 평단 +15% / +20% 지정가 매도)
                    limit_qty = hold - quarter_qty
                    limit_price = round(avg_price * (1.0 + limit_target_pct), 2)

                    # 지정가 매도 체결 여부 (장중 High >= 지정가 목표)
                    if high_p >= limit_price and limit_qty > 0:
                        gross_limit = limit_price * limit_qty
                        fee_limit = gross_limit * (self.fee_rate + self.sec_fee)
                        net_limit = gross_limit - fee_limit
                        day_profit += (limit_price - avg_price) * limit_qty - fee_limit
                        cash += net_limit
                        shares_sold_limit = limit_qty

                    # 쿼터 매도 체결 여부 (종가 Close >= 별지점)
                    if close_p >= star_point and quarter_qty > 0:
                        gross_quarter = close_p * quarter_qty
                        fee_quarter = gross_quarter * (self.fee_rate + self.sec_fee)
                        net_quarter = gross_quarter - fee_quarter
                        day_profit += (close_p - avg_price) * quarter_qty - fee_quarter
                        cash += net_quarter
                        shares_sold_quarter = quarter_qty

                # 매도 후 남은 수량
                hold_after_sell = hold - shares_sold_limit - shares_sold_quarter

                # 매도에 따른 T값 변화
                t_after_sell = T
                if shares_sold_quarter > 0 and hold_after_sell > 0:
                    t_after_sell = t_after_sell * 0.75

                # (4) 매수 주문 처리
                buy_qty = 0
                bought_full = False
                bought_half = False

                if hold == 0 or (hold_after_sell == 0 and shares_sold_limit == 0 and shares_sold_quarter == 0):
                    # [처음 매수]: 현재 보유량이 0인 새 사이클 시작일
                    first_buy_cap = int(budget / close_p) if close_p > 0 else 0
                    cost = first_buy_cap * close_p * (1.0 + self.fee_rate)
                    if cost <= cash and first_buy_cap > 0:
                        buy_qty = first_buy_cap
                        bought_full = True
                elif t_after_sell < half_div:
                    # [전반전 매수]: 0.5회분 별지점 LOC + 0.5회분 평단 LOC
                    buy_p_star = max(star_point - 0.01, 0.01)
                    budget_half = budget * 0.5
                    qty_star = int(budget_half / buy_p_star) if buy_p_star > 0 else 0
                    qty_avg = int(budget_half / avg_price) if avg_price > 0 else 0

                    # 별지점 LOC 체결 검사 (Close <= 별지점 - 0.01)
                    fill_star = (close_p <= buy_p_star and qty_star > 0)
                    # 평단 LOC 체결 검사 (Close <= 평단)
                    fill_avg = (close_p <= avg_price and qty_avg > 0)

                    total_req_qty = (qty_star if fill_star else 0) + (qty_avg if fill_avg else 0)
                    total_cost = total_req_qty * close_p * (1.0 + self.fee_rate)

                    if total_cost <= cash and total_req_qty > 0:
                        buy_qty = total_req_qty
                        if fill_star and fill_avg:
                            bought_full = True
                        elif fill_star or fill_avg:
                            bought_half = True
                    elif fill_star:
                        single_cost = qty_star * close_p * (1.0 + self.fee_rate)
                        if single_cost <= cash and qty_star > 0:
                            buy_qty = qty_star
                            bought_half = True
                else:
                    # [후반전 매수]: 1회분 전체 별지점 LOC 매수
                    buy_p_star = max(star_point - 0.01, 0.01)
                    qty_star = int(budget / buy_p_star) if buy_p_star > 0 else 0

                    # 별지점 LOC 체결 검사
                    if close_p <= buy_p_star and qty_star > 0:
                        total_cost = qty_star * close_p * (1.0 + self.fee_rate)
                        if total_cost <= cash:
                            buy_qty = qty_star
                            bought_full = True

                # 매수 체결 반영 및 T값 갱신
                day_buy_qty = buy_qty
                day_sell_qty = shares_sold_limit + shares_sold_quarter

                if buy_qty > 0:
                    buy_cost = buy_qty * close_p * (1.0 + self.fee_rate)
                    cash -= buy_cost
                    new_total_hold = hold_after_sell + buy_qty
                    if hold_after_sell > 0:
                        avg_price = (avg_price * hold_after_sell + close_p * buy_qty) / new_total_hold
                    else:
                        avg_price = close_p
                    hold = new_total_hold

                    # T값 갱신: 지정가 매도 후 LOC 매수인지 일반 매수인지 분기
                    if shares_sold_limit > 0:
                        # 지정가매도 후 loc 매수되는 경우: (직전T * 0.25 + 1.0) or (직전T * 0.25 + 0.5)
                        T = (T * 0.25 + 1.0) if bought_full else (T * 0.25 + 0.5)
                    else:
                        if bought_full:
                            T = t_after_sell + 1.0
                        elif bought_half:
                            T = t_after_sell + 0.5
                        else:
                            T = t_after_sell
                else:
                    hold = hold_after_sell
                    T = t_after_sell
                    if hold == 0:
                        avg_price = 0.0
                        T = 0.0

            else:
                # ==========================
                # 2. 소진후 리버스 모드 매매
                # ==========================
                # 별지점: 직전 5거래일 종가의 단순 이동평균(SMA 5, 오늘 이전 5거래일)
                sma5_closes = closes[max(0, i-5):i] if i > 0 else np.array([close_p])
                star_point = float(np.mean(sma5_closes))
                divisor = 10 if self.divisions == 20 else 20

                if reverse_day == 1:
                    # [리버스 첫날]: 매수 없음, 보유량의 1/20(40분할) or 1/10(20분할) 무조건 MOC 매도
                    moc_qty = int(hold / divisor)
                    if moc_qty > 0:
                        day_sell_qty += moc_qty
                        gross_sell = close_p * moc_qty
                        fee_sell = gross_sell * (self.fee_rate + self.sec_fee)
                        net_sell = gross_sell - fee_sell
                        day_profit += (close_p - avg_price) * moc_qty - fee_sell
                        cash += net_sell
                        hold -= moc_qty
                        T = T * (0.9 if self.divisions == 20 else 0.95)

                    reverse_day = 2
                else:
                    # [리버스 둘째날 이후]
                    # (1) 별지점 LOC 매도 (보유량의 1/20 or 1/10)
                    rev_sell_qty = int(hold / divisor)
                    if close_p >= star_point and rev_sell_qty > 0:
                        day_sell_qty += rev_sell_qty
                        gross_sell = close_p * rev_sell_qty
                        fee_sell = gross_sell * (self.fee_rate + self.sec_fee)
                        net_sell = gross_sell - fee_sell
                        day_profit += (close_p - avg_price) * rev_sell_qty - fee_sell
                        cash += net_sell
                        hold -= rev_sell_qty
                        T = T * (0.9 if self.divisions == 20 else 0.95)

                    # (2) 쿼터 매수: 총 잔금의 1/4 금액만큼 별지점 아래(star_point - 0.01)에서 매수 시도
                    quarter_budget = cash / 4.0
                    buy_target_p = max(star_point - 0.01, 0.01)

                    # 잔금/4로 1주 매수가 불가능한 경우 -> 비상 MOC 매도로 현금 확보
                    if quarter_budget < buy_target_p and hold > 0:
                        moc_qty = max(1, int(hold / divisor))
                        moc_qty = min(moc_qty, hold)
                        day_sell_qty += moc_qty
                        gross_sell = close_p * moc_qty
                        fee_sell = gross_sell * (self.fee_rate + self.sec_fee)
                        net_sell = gross_sell - fee_sell
                        day_profit += (close_p - avg_price) * moc_qty - fee_sell
                        cash += net_sell
                        hold -= moc_qty
                        T = T * (0.9 if self.divisions == 20 else 0.95)
                        quarter_budget = cash / 4.0

                    # 쿼터 매수 LOC 체결 검사 (Close <= 별지점 - 0.01)
                    if close_p <= buy_target_p:
                        rev_buy_qty = int(quarter_budget / buy_target_p)
                        cost = rev_buy_qty * close_p * (1.0 + self.fee_rate)
                        if cost <= cash and rev_buy_qty > 0:
                            day_buy_qty += rev_buy_qty
                            cash -= cost
                            new_hold = hold + rev_buy_qty
                            avg_price = (avg_price * hold + close_p * rev_buy_qty) / new_hold
                            hold = new_hold
                            T = T + (div_count - T) * 0.25

                    reverse_day += 1

                # 리버스모드 종료 및 일반모드 복귀 검사
                # 종가가 평단 대비 회복선(SOXL -20%, TQQQ -15%) 초과 시 일반모드로 복귀
                if avg_price > 0 and (close_p / avg_price - 1.0) > reverse_exit_pct:
                    mode = 'NORMAL'
                    reverse_day = 0

            # -------------------------------------------------------------
            # [C] 당일 기말 자산 평가 및 레코드 기록
            # -------------------------------------------------------------
            curr_equity = hold * close_p
            curr_asset = cash + curr_equity

            records.append({
                'Date': d,
                'Close': close_p,
                'Cash': cash,
                'Hold': hold,
                'AvgPrice': avg_price,
                'Asset': curr_asset,
                'T': T,
                'Mode': mode,
                'Profit': day_profit,
                'BuyQty': day_buy_qty,
                'SellQty': day_sell_qty
            })

        df_res = pd.DataFrame(records)
        df_res['DD'] = self.compute_drawdown(df_res['Asset'], self.initial_capital)
        return df_res
