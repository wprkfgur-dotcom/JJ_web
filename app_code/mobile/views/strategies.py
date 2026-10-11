"""
투자 전략 가이드 탭 뷰 (mobile.views.strategies)

종종이 기본전략, 라오어 무한매수법 v4.0, 라오어 밸류리밸런싱 VR 5.0 및 3대 전략 비교표 렌더링.
"""
import flet as ft

from mobile.theme import (
    SURFACE_CARD, BORDER_COLOR, ACCENT_BLUE, PROFIT_GREEN,
    RESERVE_AMBER, VR_PURPLE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED
)
from mobile.widgets import build_card, build_section_header


def make_section_title(icon, title, color):
    return build_section_header(title=title, icon=icon, icon_color=color, title_size=13)


def make_bullet_point(title, desc):
    return ft.Column([
        ft.Text(f"• {title}", size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
        ft.Container(
            padding=ft.Padding.only(left=12),
            content=ft.Text(desc, size=11, color=TEXT_SECONDARY)
        )
    ], spacing=2)


def make_comparison_row(title, v1, v2, v3):
    return ft.Container(
        padding=ft.Padding.symmetric(vertical=6),
        border=ft.Border(bottom=ft.BorderSide(1, BORDER_COLOR)),
        content=ft.Row([
            ft.Text(title, size=11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED, width=65),
            ft.Text(v1, size=10, color=PROFIT_GREEN, expand=1),
            ft.Text(v2, size=10, color=RESERVE_AMBER, expand=1),
            ft.Text(v3, size=10, color=VR_PURPLE, expand=1),
        ], spacing=4)
    )


def build_strategies_view() -> ft.Control:
    """투자 전략 가이드 탭(ListView) 컴포넌트를 빌드합니다."""
    # 1. 헤더 카드
    header_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=3,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.LIGHTBULB, color=ACCENT_BLUE, size=22),
                        ft.Text("투자 전략 가이드", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=8),
                    ft.Container(height=2),
                    ft.Text(
                        "미국 3배 레버리지 ETF(SOXL, TQQQ 등)의 극심한 변동성을 역이용하여, "
                        "시장 예측과 인간의 감정(공포·탐욕)을 배제하고 수학적 분할 매매와 기계적 원칙으로 "
                        "안정적이고 지속적인 우상향 복리 수익을 달성하는 2대 핵심 시스템입니다.",
                        size=12,
                        color=TEXT_SECONDARY
                    )
                ],
                spacing=4
            )
        )
    )

    # 2. 종종이 기본전략 카드
    jongjong_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Container(
                            content=ft.Text("전략 1", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
                            bgcolor=PROFIT_GREEN,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                            border_radius=6
                        ),
                        ft.Text("종종이 기본전략 (JongJong)", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=8),
                    ft.Container(height=4),
                    ft.Text("3단계 시장 모드(8/7/5 분할) & 조각별 100% 독립 운영 시스템", size=12, color=PROFIT_GREEN, weight=ft.FontWeight.W_500),
                    ft.Divider(color=BORDER_COLOR, height=1),

                    make_section_title(ft.Icons.AUTO_GRAPH, "핵심 운용 철학", PROFIT_GREEN),
                    ft.Text(
                        "레버리지 ETF의 추세와 변동성을 3단계 시장 모드(Normal/Safe/Riskoff)로 자동 진단하고, "
                        "모드별로 차등 분할 매수합니다. 매수 체결된 각 조각(Lot)은 전체 평단가에 묶이지 않고 "
                        "각각 고유 매입가와 목표가를 가진 '100% 독립 조각'으로 운영되며, 목표가 도달 시 개별 익절하고 "
                        "10거래일 내 미익절 시 기계적으로 시간손절(MOC)하여 시드 고착을 완벽 차단합니다.",
                        size=11, color=TEXT_SECONDARY
                    ),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.SPEED, "3단계 시장 모드 & 차등 분할 전략", PROFIT_GREEN),
                    make_bullet_point(
                        "Normal 모드 (일반 상승/횡보장, 8분할)",
                        "가용 시드(AR)를 8등분(AR / 8.0)하여 매일 LOC 매수 주문을 제출합니다. "
                        "목표 익절 수익률은 +2.75%이며, 정상 변동성 밴드(±12.8%) 내에서 적극적으로 수익을 창출합니다."
                    ),
                    make_bullet_point(
                        "Safe 모드 (단기 급락 감지 / 안전 모드, 7분할)",
                        "주가가 20일 이평선(MA20)을 하회한 상태에서 -3% 이상 급락하거나 단기 -8% 이상 급락 시 자동 발동합니다. "
                        "가용 시드를 7등분(AR / 7.0)하여 매수하고, 목표 익절률을 +0.25%로 극도로 낮추어 원금 방어 및 신속한 본전 탈출에 집중합니다."
                    ),
                    make_bullet_point(
                        "Riskoff 모드 (위험 회피 / 추세 붕괴, 5분할)",
                        "전일 급락 Flag 경고가 발생했거나 고점 대비 위험 낙폭에 도달했을 때 발동합니다. "
                        "가용 시드를 5등분(AR / 5.0)으로 초긴축 방어 운용하며, 전일 종가 대비 -5.5% 이하 저가에서만 매수하여 목표 익절률 +0.70%로 자산을 지킵니다."
                    ),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.VIEW_QUILT, "조각(Lot)별 100% 독립 운영 메커니즘", PROFIT_GREEN),
                    make_bullet_point(
                        "조각별 개별 목표가 익절 (독립 체결)",
                        "매일 매수한 주식은 다른 날짜 매수분과 물타기(합산)되지 않고, 각각의 고유 매입단가(S)와 개별 목표가(U)를 갖는 독자적 조각으로 살아있습니다. "
                        "당일 종가가 특정 조각의 목표가에 도달하면 해당 조각만 단독 익절 매도되어 현금이 즉시 회수됩니다."
                    ),
                    make_bullet_point(
                        "10거래일 기계적 시간손절 (10-Day Time Cut / MOC)",
                        "매수 후 10거래일이 경과하도록 목표가에 도달하지 못한 조각은 10일째 장 마감(MOC)에 기계적으로 전량 시장가 매도(손절)합니다. "
                        "이를 통해 하락장에 물량이 영구 고착되는 것을 막고, 회수된 현금으로 바닥 구간에서 새로운 조각을 매수하여 가파른 복리 반등을 만듭니다."
                    ),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.SCHEDULE_SEND, "당일 5분할 비선형 LOC 예약 매수", PROFIT_GREEN),
                    make_bullet_point(
                        "수학적 곡률(Curvature 0.7) 5분할 주문",
                        "당일 매수 예정 예산(P = AR / 모드별분할수)을 5개의 LOC 호가로 비선형 분할하여, "
                        "주가가 깊게 하락할수록 기하급수적으로 더 많은 수량이 체결되도록 설계된 스마트 주문표입니다."
                    ),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.ACCOUNT_BALANCE_WALLET, "위기준비금(AK, 5%) & Risk-Off 병합 시스템", PROFIT_GREEN),
                    make_bullet_point(
                        "위기준비금(AK, 5%) 평상시 엄격 격리 보관",
                        "전체 자본의 5%는 비상금으로 완전히 분리하여 평상시(Normal/Safe) 매수에는 절대 투입하지 않고 안전 금고에 보존합니다."
                    ),
                    make_bullet_point(
                        "Risk-Off 진입 시 위기준비금 전액 병합",
                        "시장 급락으로 Risk-Off 모드가 시작되는 당일, 그동안 쌓인 모든 위기준비금을 실가동 시드(AR)와 가용 현금에 100% 병합하여 저점 분할매수 실탄으로 전진 배치합니다."
                    ),
                    make_bullet_point(
                        "10거래일 복리 정산 및 재적립",
                        "매 10거래일마다 누적 실현손익을 정산하여 5%는 위기준비금으로 적립하고, 95%는 실가동 시드(AR)에 합산하여 원금을 키우는 복리 시스템이 자동 가동됩니다."
                    ),
                ],
                spacing=8
            )
        )
    )

    # 3. 라오어 무한매수법 v4.0 카드
    infinite_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Container(
                            content=ft.Text("전략 2", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
                            bgcolor=RESERVE_AMBER,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                            border_radius=6
                        ),
                        ft.Text("라오어 무한매수법 v4.0", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=8),
                    ft.Container(height=4),
                    ft.Text("매일 40분할 기계적 루틴 매수 & 사이클당 10% 확정 익절", size=12, color=RESERVE_AMBER, weight=ft.FontWeight.W_500),
                    ft.Divider(color=BORDER_COLOR, height=1),

                    make_section_title(ft.Icons.ACCESS_TIME, "핵심 운용 철학", RESERVE_AMBER),
                    ft.Text(
                        "정해진 원금을 40분할하여 매일 밤 LOC(Limit-on-Close) 주문을 제출, "
                        "시장 상승/하락에 상관없이 1일 1회 정해진 규칙대로 매매하여 사이클당 +10% 수익을 확정 짓는 직장인 최적화 전략입니다.",
                        size=11, color=TEXT_SECONDARY
                    ),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.LOOKS_ONE, "전반전 (1회차 ~ 20회차)", RESERVE_AMBER),
                    make_bullet_point("0.5회분 LOC 평단 매수", "종가가 내 평단가 이하일 때만 체결되어 평단가를 적극적으로 낮춥니다."),
                    make_bullet_point("0.5회분 LOC 큰수 매수", "종가가 평단가 * 1.05 이하일 때 체결되도록 하여 무조건 1회분 매수를 채웁니다."),
                    make_bullet_point("전량 +10% 지정가 매도", "보유 중인 모든 수량을 평단가 +10% 가격에 매일 지정가 매도 주문을 걸어둡니다."),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.LOOKS_TWO, "후반전 (21회차 ~ 40회차)", RESERVE_AMBER),
                    make_bullet_point("0.5회분만 보수적 매수", "원금 소진을 늦추기 위해 매일 0.5회분만 평단가 이하 LOC로 매수하고, 나머지 0.5회분은 현금을 보존합니다."),
                    make_bullet_point("본전 탈출 및 분할 매도", "평단가 +5%~+10% 구간에서 보유 수량을 분할 매도하여 안전하게 사이클을 마무리합니다."),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.REFRESH, "쿼터 손절 및 리셋 룰", RESERVE_AMBER),
                    make_bullet_point("40회차 소진 시 대응", "40회차까지 익절하지 못했을 경우, 보유 주식의 25%(1/4)를 기계적으로 손절하여 새로운 매수 시드를 창출하고 사이클을 연장합니다.")
                ],
                spacing=8
            )
        )
    )

    # 4. 라오어 밸류리밸런싱 VR 5.0 카드
    vr_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Container(
                            content=ft.Text("전략 3", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            bgcolor=VR_PURPLE,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                            border_radius=6
                        ),
                        ft.Text("라오어 밸류리밸런싱 VR 5.0", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=8),
                    ft.Container(height=4),
                    ft.Text("2주 사이클 밸류 밴드(±15%) & 풀(Pool) 기반 자동 리밸런싱", size=12, color=VR_PURPLE, weight=ft.FontWeight.W_500),
                    ft.Divider(color=BORDER_COLOR, height=1),

                    make_section_title(ft.Icons.AUTO_AWESOME, "핵심 운용 철학", VR_PURPLE),
                    ft.Text(
                        "목표 평가액 가이드라인 곡선 V를 설정하고, 2주(10거래일)마다 증권사에 기간예약 주문을 걸어두어 "
                        "주가가 상하단 밴드(V ±15%)를 벗어날 때만 기계적으로 매수/매도하여 밴드로 복귀시키는 중장기 레버리지 자산배분 전략입니다.",
                        size=11, color=TEXT_SECONDARY
                    ),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.CALENDAR_MONTH, "2주(10거래일) 사이클 & V 갱신 공식", VR_PURPLE),
                    make_bullet_point("V 갱신 공식", "다음 V = 현재 V + (Pool / G) ± (적립금 or 인출금)"),
                    make_bullet_point("G(기울기) 인자", "G=10(기본/적립·거치) ~ G=20(인출식/보수적)으로 V의 상승 속도를 조절합니다."),
                    make_bullet_point("현금 풀(Pool)", "하락장에서 든든한 매수 방패 역할을 하며, 상승 익절 시 수익금을 흡수하여 현금을 비축합니다."),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.SWAP_VERT, "2주치 예약 주문 (상·하단 밴드)", VR_PURPLE),
                    make_bullet_point("하단 밴드 매수 (V * 0.85)", "주가 하락 시 P_buy = V_min / n 가격에 순차 매수하여 Pool을 소진하고 주식 비중을 늘립니다."),
                    make_bullet_point("상단 밴드 매도 (V * 1.15)", "주가 급등 시 P_sell = V_max / n 가격에 분할 익절하여 확정 수익을 Pool로 회수합니다."),
                    ft.Container(height=4),

                    make_section_title(ft.Icons.SAVINGS, "운용 유형별 Pool 한도", VR_PURPLE),
                    make_bullet_point("적립식 VR", "2주마다 적립금 추가 투입 + 사이클당 Pool의 75%까지 매수 사용"),
                    make_bullet_point("거치식 VR", "원금 일시 거치 + 사이클당 Pool의 50%까지 매수 사용"),
                    make_bullet_point("인출식 VR", "2주마다 생활비 인출 + 사이클당 Pool의 25%까지 보수적 매수 사용")
                ],
                spacing=8
            )
        )
    )

    # 5. 전략 비교 매트릭스 카드
    comparison_card = ft.Card(
        bgcolor=SURFACE_CARD,
        elevation=2,
        shape=ft.RoundedRectangleBorder(radius=14),
        content=ft.Container(
            padding=16,
            content=ft.Column(
                controls=[
                    ft.Row([
                        ft.Icon(ft.Icons.COMPARE_ARROWS, color=ACCENT_BLUE, size=18),
                        ft.Text("3대 투자 전략 한눈에 비교", size=14, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                    ], spacing=6),
                    ft.Container(height=4),
                    ft.Row([
                        ft.Text("구분", size=11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED, width=65),
                        ft.Text("종종이 기본", size=10.5, weight=ft.FontWeight.BOLD, color=PROFIT_GREEN, expand=1),
                        ft.Text("무한매수 v4", size=10.5, weight=ft.FontWeight.BOLD, color=RESERVE_AMBER, expand=1),
                        ft.Text("VR 5.0", size=10.5, weight=ft.FontWeight.BOLD, color=VR_PURPLE, expand=1),
                    ], spacing=4),
                    ft.Divider(color=BORDER_COLOR, height=1),
                    make_comparison_row("주요 대상", "SOXL 등 3X", "TQQQ/SOXL", "TQQQ/QLD 3X/2X"),
                    make_comparison_row("매매 주기", "매일 밤 LOC", "매일 밤 LOC", "2주(10일) 1회 예약"),
                    make_comparison_row("시드 분할", "8/7/5 분할", "40분할 고정", "V ±15% 밴드 분할"),
                    make_comparison_row("조각 운용", "조각별 독립 익절", "전체 평단 통합", "전체 밸류 밴드"),
                    make_comparison_row("현금 관리", "위기준비금 5%", "전액 시드 소진", "Pool 현금 (15~50%)"),
                    make_comparison_row("목표 수익", "0.25% ~ 2.75%", "사이클당 +10%", "밴드 상단 돌파 익절"),
                    make_comparison_row("손절 원칙", "10일 MOC 청산", "40회차 쿼터손절", "원칙적 손절 없음"),
                    make_comparison_row("추천 성향", "고변동성 공략", "정형화된 루틴", "게으른 장기 투자"),
                ],
                spacing=2
            )
        )
    )

    return ft.ListView(
        controls=[
            header_card,
            ft.Container(height=6),
            jongjong_card,
            ft.Container(height=6),
            infinite_card,
            ft.Container(height=6),
            vr_card,
            ft.Container(height=6),
            comparison_card,
            ft.Container(height=24)
        ],
        spacing=8,
        expand=True
    )
