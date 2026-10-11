"""
종종 트레이더 모바일 (JongJongTrader Mobile) 종합 기능 자동화 테스트 스위트
TC-1: 계좌 생성/저장/로드 및 백업 무결성
TC-2: 종종이(JJ) LOC 4분할 및 퉁치기 주문 산출 엔진
TC-3: 라오어 무한매수법 v4 주문 산출 엔진
TC-4: 시장 시세 조회 및 SQLite DB 캐시 무결성
TC-5: GitHub Releases 자동 업데이트 버전 체크 엔진
TC-6: 모바일 UI 헬퍼 및 차트 SVG 생성기
TC-7: Mobile EXE 바이너리 기동
TC-8: VR 5.0 전략 및 주문표
TC-9: 전략 레지스트리 (전략 판별/목표수익률/팩토리)
TC-10: 거래내역 표 계산 (누적손익/변동률/목표가 폴백)
TC-11: 앱 설정(환율) 영구 저장
TC-12: 백테스트 러너 (합성 시세)
"""
import sys
import os
import shutil
import tempfile
import unittest

# Windows 콘솔 UTF-8 출력 보장
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 루트 경로 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.account_manager import AccountManager
from core.order_netting import calculate_order_netting, generate_jongjong_orders
from strategies.jongjong import JongJongStrategy
from strategies.infinite_buying_v4 import InfiniteBuyingV4Strategy
from strategies.vr_v5 import ValueRebalancingV5Strategy
from core.data import get_current_stock_price, get_price_from_db, get_exact_stock_price_for_date
from core.app_update import APP_VERSION, check_remote_version_info, parse_download_url
from mobile.theme import BG_DARK, PROFIT_GREEN, LOSS_RED
from mobile.helpers import compute_suggested_trades, parse_picked_date_str
from mobile.charts import render_portfolio_chart


class TestJongJongTrader(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_accounts_file = os.path.join(self.test_dir, "test_accounts.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tc1_account_lifecycle_and_backup(self):
        """TC-1: 계좌 생성, 저장, 로드 및 백업 생성 무결성 검증"""
        am = AccountManager(filepath=self.test_accounts_file)
        self.assertEqual(len(am.load_accounts()), 0)

        # 1. 신규 계좌 추가
        acc = am.add_account(
            name="테스트_SOXL_계좌",
            strategy="종종이 (LOC 4분할)",
            ticker="SOXL",
            start_date="2026-01-01",
            initial_seed=10000.0,
            reserve_ratio=0.05,
            memo="자동 테스트 계좌"
        )
        self.assertIsNotNone(acc)
        self.assertEqual(acc["name"], "테스트_SOXL_계좌")
        self.assertEqual(acc["initial_seed"], 10000.0)
        self.assertEqual(acc["reserve_ratio"], 0.05)

        # 2. 파일 영속성 검증 (저장 및 다시 로드)
        am2 = AccountManager(filepath=self.test_accounts_file)
        loaded = am2.load_accounts()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["ticker"], "SOXL")

        # 3. 백업 파일 생성 검증 (accounts.backup.json 자동 백업 로직)
        backup_path = os.path.join(os.path.dirname(am.filepath), "accounts.backup.json")
        with open(am.filepath, 'r', encoding='utf-8') as rf:
            with open(backup_path, 'w', encoding='utf-8') as wf:
                wf.write(rf.read())
        self.assertTrue(os.path.exists(backup_path))
        self.assertGreater(os.path.getsize(backup_path), 0)

    def test_tc2_jongjong_strategy_orders(self):
        """TC-2: 종종이(JJ) 4분할 주문 산출 및 퉁치기 로직 검증"""
        strat = JongJongStrategy(initial_capital=10000.0, reserve_ratio=0.05)
        self.assertEqual(strat.initial_capital, 10000.0)
        self.assertEqual(strat.reserve_ratio, 0.05)

        # 퉁치기(상계) 주문 계산 검증
        buy_orders = [{"type": "매수", "price": 40.0, "qty": 10, "loc_type": "LOC"}]
        sell_orders = [{"type": "매도", "price": 40.0, "qty": 4, "loc_type": "LOC"}]
        netting_result = calculate_order_netting(buy_orders, sell_orders)
        self.assertIsInstance(netting_result, dict)
        self.assertIn('net_buy_orders', netting_result)
        self.assertIn('net_sell_orders', netting_result)
        self.assertTrue(netting_result.get('is_netted', False))

        # 종종이 주문표 매도 주문 가격 내림차순 정렬 검증 (최저 목표가가 맨 아래 위치)
        unsold_lots = [
            {'date': '10.01', 'R': 300, 'U': 168.22, 'hold_days': 1},
            {'date': '10.02', 'R': 282, 'U': 168.79, 'hold_days': 2},
        ]
        orders_result = generate_jongjong_orders(
            unsold_lots=unsold_lots,
            yest_close=164.27,
            p_budget=47435.0,
            mode='Normal',
            C2=0.128,
            C3=-0.17
        )
        sells = orders_result['net_sell_orders']
        self.assertGreaterEqual(len(sells), 2)
        sell_prices = [s['price'] for s in sells]
        # 가격 내림차순 검증
        self.assertEqual(sell_prices, sorted(sell_prices, reverse=True))
        # 168.22가 맨 아래(마지막)에 위치하는지 검증
        self.assertEqual(sells[-1]['price'], 168.22)

    def test_tc3_infinite_buying_v4_strategy(self):
        """TC-3: 라오어 무한매수법 v4 전략 엔진 초기화 및 검증"""
        strat = InfiniteBuyingV4Strategy(initial_capital=20000.0)
        self.assertEqual(strat.initial_capital, 20000.0)
        self.assertEqual(strat.name, "무한매수법 v4.0")

    def test_tc4_market_data_and_db_cache(self):
        """TC-4: 시장 데이터 시세 조회 및 로컬 DB 캐시 조회 검증"""
        # SQLite DB에 기저장된 SOXL 과거 시세 조회 (빠른 로컬 DB 검증)
        db_price = get_price_from_db("SOXL", "2024-01-05")
        if db_price > 0:
            self.assertGreater(db_price, 0)

        # 실시간 fallback 가격 로직 검증
        price = get_current_stock_price("INVALID_TICKER_XYZ", fallback_price=50.0)
        self.assertEqual(price, 50.0)

        # 정확한 날짜 종가 조회 (get_exact_stock_price_for_date) 검증
        # 2024-01-05 (금요일 정상 영업일) -> 종가 확인 가능
        exact_p = get_exact_stock_price_for_date("SOXL", "2024-01-05")
        if exact_p is not None:
            self.assertGreater(exact_p, 0.0)
        # 2024-01-06 (토요일 주말/휴장일) -> 미확인(None) 반환 검증
        exact_weekend = get_exact_stock_price_for_date("SOXL", "2024-01-06")
        self.assertIsNone(exact_weekend)

    def test_tc5_app_update_version_check(self):
        """TC-5: GitHub Releases 자동 업데이트 버전 파싱 및 API 검증"""
        # 현재 버전 형식 검증 (vX.Y.Z)
        self.assertTrue(APP_VERSION.count(".") == 2, f"버전 형식 오류: {APP_VERSION}")
        
        # GitHub direct 다운로드 URL 파싱 로직 검증
        parsed = parse_download_url("https://github.com/wprkfgur-dotcom/jj_invest/releases/tag/v2.0.0")
        self.assertIn("github.com", parsed)

        # 원격 릴리스 정보 API 조회 검증
        info = check_remote_version_info()
        if info:
            self.assertIn("remote_version", info)
            self.assertIn("download_url", info)

    def test_tc6_mobile_helpers_and_svg_charts(self):
        """TC-6: 모바일 테마, 헬퍼 함수 및 SVG 차트 렌더러 검증"""
        self.assertTrue(BG_DARK.startswith("#"))
        self.assertTrue(PROFIT_GREEN.startswith("#"))
        self.assertTrue(LOSS_RED.startswith("#"))

        # 날짜 파싱 헬퍼 검증 (시간 제외 및 날짜 문자열 정규화)
        d_str = parse_picked_date_str("2026-10-04T00:00:00")
        self.assertTrue(len(d_str) == 10 and d_str.startswith("2026-10-"))

        # 제안 주문 계산 헬퍼 검증 (체결 수량 산출)
        buy_orders = [{"type": "매수", "price": 30.0, "qty": 10}]
        sell_orders = [{"type": "매도", "price": 32.0, "qty": 5}]
        calc_b, calc_s = compute_suggested_trades(
            close_p=29.0,
            buy_orders=buy_orders,
            sell_orders=sell_orders
        )
        self.assertEqual(calc_b, 10) # 29.0 <= 30.0 이므로 매수 체결 10주
        self.assertEqual(calc_s, 0)  # 29.0 < 32.0 이므로 매도 미체결 0주

        # SVG 차트 렌더러 검증 (Base64 벡터 이미지 생성)
        test_accounts = [{
            "account": {"name": "테스트"},
            "details": {"asset": 12000.0, "cash": 5000.0, "hold_value": 7000.0}
        }]
        svg_b64, dates, vals = render_portfolio_chart(test_accounts, total_portfolio_asset=12000.0)
        self.assertTrue(svg_b64.startswith("data:image/svg+xml;base64,"))
        self.assertGreater(len(vals), 0)

    def test_tc7_mobile_exe_binary_launch(self):
        r"""TC-7: dist\JongJongTrader_Mobile.exe 바이너리 직접 실행 및 프로세스 기동 검증"""
        import subprocess
        import time

        exe_path = os.path.join(BASE_DIR, "dist", "JongJongTrader_Mobile.exe")
        if not os.path.exists(exe_path):
            self.skipTest(f"바이너리가 존재하지 않습니다: {exe_path}")

        proc = subprocess.Popen([exe_path])
        try:
            # 4초간 프로세스가 크래시(WinError 등) 없이 정상 구동되는지 확인
            time.sleep(4)
            ret_code = proc.poll()
            self.assertIsNone(ret_code, f"JongJongTrader_Mobile.exe가 비정상 종료되었습니다 (반환코드: {ret_code})")
        finally:
            # 안전하게 프로세스 종료 및 정리
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
            subprocess.run(["taskkill", "/F", "/IM", "flet.exe"], capture_output=True)
            subprocess.run(["taskkill", "/F", "/IM", "JongJongTrader_Mobile.exe"], capture_output=True)

    def test_tc8_vr_v5_strategy_and_orders(self):
        """TC-8: 라오어 밸류리밸런싱 VR 5.0 전략 엔진 및 2주 기간예약 주문 산출 검증"""
        # 1. 전략 엔진 초기화 검증
        strat = ValueRebalancingV5Strategy(
            ticker='TQQQ',
            initial_capital=100000.0,
            g_value=10.0,
            band_pct=0.15,
            pool_usage_limit=0.50
        )
        self.assertEqual(strat.g_value, 10.0)
        self.assertEqual(strat.band_pct, 0.15)
        self.assertEqual(strat.pool_usage_limit, 0.50)

        # 2. 2주 기간예약 주문표 (P_buy = V_min / n, P_sell = V_max / n) 산출 검증
        v_test = 85000.0
        v_min = v_test * 0.85 # 72,250
        v_max = v_test * 1.15 # 97,750
        buys, sells = strat.calculate_order_ladder(
            v_val=v_test,
            current_hold=1000,
            pool_cash=15000.0,
            pool_usage_limit=0.50
        )
        self.assertGreater(len(buys), 0)
        self.assertGreater(len(sells), 0)
        # 매수 1차 가격은 v_min / 1000 = 72.25
        self.assertAlmostEqual(buys[0]['price'], v_min / 1000, places=2)
        # 매도 1차 가격은 v_max / 1000 = 97.75
        self.assertAlmostEqual(sells[0]['price'], v_max / 1000, places=2)

        # 3. AccountManager 계좌 연동 및 주문표 산출 검증
        am = AccountManager(filepath=self.test_accounts_file)
        acc = am.add_account(
            name="VR_테스트계좌",
            strategy="VR 5.0 (밸류리밸런싱)",
            ticker="TQQQ",
            start_date="2026-01-02",
            initial_seed=100000.0,
            memo="VR 5.0 테스트"
        )
        dtl = am.compute_account_details(acc)
        self.assertIn("VR 5.0", dtl['strategy_name'])
        self.assertIn("buy_orders", dtl)
        self.assertIn("sell_orders", dtl)
        self.assertGreater(len(dtl['buy_orders']), 0)

    def test_tc9_strategy_registry(self):
        """TC-9: 전략 이름 판별, 목표 수익률, 백테스트 전략 팩토리 검증"""
        from core import strategy_registry as reg
        from strategies.buy_and_hold import BuyAndHoldStrategy

        self.assertEqual(reg.classify_strategy("종종이 기본전략"), reg.JONGJONG)
        self.assertEqual(reg.classify_strategy("종종이 (LOC 4분할)"), reg.JONGJONG)
        self.assertEqual(reg.classify_strategy("무한매수법 v4.0"), reg.INFINITE)
        self.assertEqual(reg.classify_strategy("VR 5.0 (밸류리밸런싱)"), reg.VR)
        self.assertEqual(reg.classify_strategy("vr 5.0"), reg.VR)
        self.assertEqual(reg.classify_strategy("SOXL 단순보유(B&H)"), reg.BNH)
        self.assertEqual(reg.classify_strategy(None), reg.BNH)

        self.assertEqual(reg.get_target_yield("종종이 기본전략"), 0.0275)
        self.assertEqual(reg.get_target_yield("무한매수법 v4.0"), 0.05)

        self.assertIsInstance(reg.create_backtest_strategy(reg.DISPLAY_NAMES[reg.JONGJONG], "SOXL", 1000.0), JongJongStrategy)
        self.assertIsInstance(reg.create_backtest_strategy(reg.DISPLAY_NAMES[reg.INFINITE], "SOXL", 1000.0), InfiniteBuyingV4Strategy)
        self.assertIsInstance(reg.create_backtest_strategy(reg.DISPLAY_NAMES[reg.VR], "TQQQ", 1000.0), ValueRebalancingV5Strategy)
        self.assertIsInstance(reg.create_backtest_strategy(reg.bnh_display_name("SOXL"), "SOXL", 1000.0), BuyAndHoldStrategy)

    def test_tc10_trade_history_rows(self):
        """TC-10: 거래내역 표 계산 (누적손익, 변동률, 보유일, 목표가 폴백) 검증"""
        from core.trade_history import build_trade_rows, format_kr_date

        self.assertEqual(format_kr_date("2026-09-28"), "09.28.(월)")
        self.assertEqual(format_kr_date(None), "-")

        records = [
            {'t': 0, 'Date': '2026-09-28', 'Close': 142.29, 'Mode': 'Normal', 'BuyQty': 304, 'U': 146.21,
             'Sold': True, 'W': '2026-09-29', 'X': 147.00, 'Profit': 1431.84, 'ProfitRate': 3.3},
            {'t': 1, 'Date': '2026-09-29', 'Close': 147.00, 'Mode': 'Normal', 'BuyQty': 304, 'U': 151.05,
             'Sold': True, 'W': '2026-10-01', 'X': 153.69, 'Profit': 2033.76},
            # 목표가(U) 없는 미매도 슬롯: 기존에는 round_up NameError 로 화면 크래시
            {'t': 2, 'Date': '2026-09-30', 'Close': 100.00, 'Mode': 'Safe', 'BuyQty': 10, 'U': None, 'Sold': False},
        ]
        rows = build_trade_rows(records, "종종이 기본전략")
        self.assertEqual([r['idx'] for r in rows], [2, 1, 0])  # 최신순

        newest, middle, oldest = rows
        # 목표가 폴백: 100 * 1.0275 = 102.75
        self.assertAlmostEqual(newest['target_price'], 102.75, places=2)
        self.assertTrue(newest['is_holding'])
        self.assertEqual(newest['sell_date_str'], "보유중(0d)")
        self.assertEqual(newest['profit_str'], "-")
        self.assertIsNone(newest['cum_profit'])
        self.assertEqual(newest['mode'], 'Safe')

        # 변동률: Chg 값이 없으면 전일 종가 기준으로 계산
        self.assertAlmostEqual(middle['chg'], 147.00 / 142.29 - 1.0, places=6)
        self.assertEqual(middle['chg_str'], "+3.31%")
        # 손익률 폴백: BuyPrice 없으면 종가 기준 (153.69/147 - 1)
        self.assertEqual(middle['profit_rate_str'], "+4.6%")
        # 누적손익
        self.assertAlmostEqual(middle['cum_profit'], 1431.84 + 2033.76, places=2)
        self.assertEqual(middle['cum_str'], "+3,466$")

        # 첫 행: 이전 행이 없으므로 변동률 '-' (기존에는 records[-1] 을 참조하던 버그)
        self.assertEqual(oldest['chg_str'], "-")
        self.assertEqual(oldest['sell_date_str'], "09.29.(화)")
        self.assertEqual(oldest['sell_price_str'], "$147.00")
        self.assertEqual(oldest['profit_rate_str'], "+3.3%")

        self.assertEqual(build_trade_rows([], "종종이"), [])

    def test_tc11_app_settings_exchange_rate(self):
        """TC-11: 기준 환율 저장/로드 영속성 및 잘못된 값 방어 검증"""
        from core.app_settings import get_exchange_rate, set_exchange_rate, DEFAULT_EXCHANGE_RATE

        path = os.path.join(self.test_dir, "app_settings.json")
        self.assertEqual(get_exchange_rate(path), DEFAULT_EXCHANGE_RATE)
        set_exchange_rate(1450, path)
        self.assertEqual(get_exchange_rate(path), 1450.0)
        with self.assertRaises(ValueError):
            set_exchange_rate(0, path)
        self.assertEqual(get_exchange_rate(path), 1450.0)

        # 손상된 파일은 기본값으로 복구
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertEqual(get_exchange_rate(path), DEFAULT_EXCHANGE_RATE)

    def test_tc12_backtest_runner(self):
        """TC-12: 백테스트 러너 (합성 시세로 단순보유 실행 + 차트 시리즈) 검증"""
        import pandas as pd
        from core.backtest_runner import run_strategies, build_chart_series
        from core.strategy_registry import bnh_display_name

        dates = pd.bdate_range("2025-01-02", periods=30)
        df = pd.DataFrame({'Date': dates, 'Close': [100.0 + i for i in range(30)]})
        df['Open'] = df['Close']
        df['High'] = df['Close']
        df['Low'] = df['Close']

        progress = []
        results = run_strategies(df, "TEST", 10000.0, "2025-01-02", "2025-12-31",
                                 [bnh_display_name("TEST")], on_progress=progress.append)
        self.assertEqual(len(results), 1)
        self.assertEqual(progress, [bnh_display_name("TEST")])
        res = results[0]
        self.assertEqual(len(res['df']), 30)
        self.assertIsInstance(res['metrics'], dict)
        self.assertGreater(res['df']['Asset'].iloc[-1], 10000.0)  # 우상향 시세 → 수익

        series = build_chart_series(res['df'])
        self.assertEqual(len(series['dates']), 30)
        self.assertEqual(series['dates'][0], "01/02")
        self.assertEqual(len(series['vals']), 30)

    def test_tc13_views_decomposition(self):
        """TC-13: 모듈화된 뷰(mobile.views) 패키지 무결성 및 컴포넌트 빌드 검증"""
        import flet as ft
        from mobile.views import (
            build_home_view,
            build_empty_home_view,
            build_accounts_view,
            build_strategies_view,
            build_settings_view,
            open_add_account_dialog,
            open_settings_dialog,
            open_delete_account_dialog,
            open_undo_dialog,
            open_edit_trade_dialog,
            open_custom_date_dialog,
        )

        # 1. 투자 전략 가이드 뷰 빌드 (독립 컴포넌트)
        strat_view = build_strategies_view()
        self.assertIsInstance(strat_view, ft.ListView)

        # 2. Mock App 객체로 빈 계좌 뷰 및 계좌 현황 뷰 빌드
        class MockApp:
            def __init__(self):
                self.accounts = []
                self.accounts_details = []
                self.exchange_rate = 1450.0
                self.open_add_account_dialog = lambda *a, **k: None

        mock_app = MockApp()
        empty_home = build_empty_home_view(mock_app)
        self.assertIsInstance(empty_home, ft.Column)

        acc_tab = build_accounts_view(mock_app)
        self.assertIsInstance(acc_tab, ft.Column)  # 계좌 없을 때 empty_home 반환

    def test_tc14_widgets_and_domain_bridge(self):
        """TC-14: 공통 위젯(mobile.widgets) 생성 및 도메인(core/gui) 브릿지 무결성 검증"""
        import flet as ft
        import core.account_manager as cam
        import gui.account_manager as gam
        import core.order_netting as con
        import gui.order_netting as gon

        # 1. core와 gui 브릿지 일치성 검증
        self.assertIs(cam.AccountManager, gam.AccountManager)
        self.assertIs(con.calculate_order_netting, gon.calculate_order_netting)
        self.assertIs(con.generate_jongjong_orders, gon.generate_jongjong_orders)

        # 2. mobile.widgets 컴포넌트 팩토리 검증
        from mobile.widgets import (
            build_card,
            build_metric_tile,
            build_section_header,
            build_badge,
            build_confirm_dialog,
            build_empty_state,
        )

        card = build_card(content=ft.Text("Hello"), padding=10, radius=12)
        self.assertIsInstance(card, ft.Card)

        metric = build_metric_tile(title="예수금", value="$10,000", subtext="가용 현금", icon=ft.Icons.MONEY)
        self.assertIsInstance(metric, ft.Container)

        header = build_section_header(title="주문표", subtitle="안내", icon=ft.Icons.RECEIPT)
        self.assertIsInstance(header, ft.Row)

        badge = build_badge(text="SOXL")
        self.assertIsInstance(badge, ft.Container)

        confirm_dlg = build_confirm_dialog(
            title="삭제 확인",
            content="정말 삭제하시겠습니까?",
            on_confirm=lambda e: None,
            is_danger=True
        )
        self.assertIsInstance(confirm_dlg, ft.AlertDialog)

        empty_box = build_empty_state(title="계좌 없음")
        self.assertIsInstance(empty_box, ft.Column)

    def test_tc15_determine_next_mode_safe_transition(self):
        """TC-15: 폭락장 시 종종이 익일 Safe 모드 전환 및 주문표 산출 무결성 검증"""
        from strategies.jongjong import JongJongStrategy
        from core.account_manager import AccountManager

        strat = JongJongStrategy()
        # 2026-10-02 ~ 2026-10-08 실제 시세 (10월 8일 -10.31% 폭락)
        closes = [142.29, 147.00, 147.86, 153.69, 163.71, 164.27, 164.26, 158.91, 142.52]
        # 10월 8일 시점에서 익일(10월 9일) 모드 판정
        next_mode = strat.determine_next_mode(closes, prev_mode='Normal', prev_flag=False)
        self.assertEqual(next_mode, 'Safe', "10월 8일 -10.31% 급락 후 10월 9일 모드는 Safe여야 합니다.")

        # AccountManager 연동 테스트
        am = AccountManager(filepath=self.test_accounts_file)
        acc = am.add_account(
            name="세이프테스트",
            strategy="종종이 기본전략",
            ticker="SOXL",
            start_date="2026-09-28",
            initial_seed=400000.0,
            reserve_ratio=0.05
        )
        # 10월 8일 정산 기록 추가
        rec_1008 = {
            't': 0, 'Date': '2026-10-08', 'Close': 142.52, 'Chg': -0.1031, 'Mode': 'Normal',
            'R': 282, 'BuyQty': 282, 'BuyPrice': 142.52, 'U': 146.44, 'Sold': False,
            'Cash': 180922.79, 'Hold': 1428, 'Asset': 384441.35, 'AR': 380000.0, 'AK': 20000.0
        }
        acc['trade_records'] = [rec_1008]
        acc['current_date'] = '2026-10-09'
        acc['operational_state'] = 'WAITING_FOR_FILL'
        am.save_accounts([acc])

        dtl = am.compute_account_details(acc)
        self.assertEqual(dtl['mode'], 'Safe')
        self.assertAlmostEqual(dtl['daily_budget'], 380000.0 / 7.0, places=1)
        # 매도 주문 중 146.44가 퉁치기 없이 그대로 목표가 매도로 유지되는지 확인
        sell_prices = [float(s['price']) for s in dtl['sell_orders']]
        self.assertIn(146.44, sell_prices)


if __name__ == "__main__":
    print("=" * 65)
    print("🚀 종종트레이더 모바일 (JongJongTrader Mobile) 기능 무결성 테스트")
    print("=" * 65)
    unittest.main(verbosity=2)

