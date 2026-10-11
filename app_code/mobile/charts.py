"""??? ? ?? ??? (?? SVG Base64 ??)."""
import base64
from datetime import datetime, timedelta
import pandas as pd



# =====================================================================
# =====================================================================
# 차트 렌더링 헬퍼 (초경량 고성능 순수 벡터 SVG Base64 변환)
# 모바일 환경에서 100% 무결점 동작하며, InteractiveViewer에서 무한 확대해도 선명합니다.
# =====================================================================
def render_portfolio_chart(accounts_data: list, total_portfolio_asset: float):
    """
    전체 계좌의 통합 자산 추이 그래프를 고해상도 순수 벡터 SVG로 생성하여 base64 URI 및 데이터 배열을 반환합니다.
    (InteractiveViewer에서 부드럽게 좌우 이동 및 무손실 확대 가능, 롱프레스 시 수치 확인 가능)
    """
    try:
        width = 650
        height = 260
        pad_left = 65
        pad_right = 25
        pad_top = 25
        pad_bottom = 40
        
        chart_w = width - pad_left - pad_right
        chart_h = height - pad_top - pad_bottom

        all_series = []
        for d in accounts_data:
            df = d.get('df_res')
            if df is not None and not df.empty and 'Asset' in df.columns:
                s = df.set_index('Date')['Asset']
                all_series.append(s)

        if all_series:
            combined_df = pd.concat(all_series, axis=1).ffill().fillna(0.0)
            total_series = combined_df.sum(axis=1)
            dates = [pd.to_datetime(d).strftime('%m/%d') for d in total_series.index]
            vals = [float(v) for v in total_series.values]
        else:
            now = datetime.now()
            dates = [(now - timedelta(days=4-i)).strftime('%m/%d') for i in range(5)]
            vals = [float(total_portfolio_asset)] * 5

        min_val = min(vals) if vals else 0.0
        max_val = max(vals) if vals else 1000.0
        if min_val == max_val:
            min_val = max(0.0, min_val * 0.9)
            max_val = max_val * 1.1 if max_val > 0 else 1000.0

        val_range = max_val - min_val if max_val > min_val else 1.0
        n = len(vals)

        points = []
        for i, v in enumerate(vals):
            x = pad_left + (i / max(1, n - 1)) * chart_w
            y = pad_top + chart_h - ((v - min_val) / val_range) * chart_h
            points.append((x, y))

        path_d = f"M {points[0][0]:.1f} {points[0][1]:.1f}"
        for pt in points[1:]:
            path_d += f" L {pt[0]:.1f} {pt[1]:.1f}"

        fill_d = path_d + f" L {points[-1][0]:.1f} {pad_top + chart_h:.1f} L {points[0][0]:.1f} {pad_top + chart_h:.1f} Z"

        grid_lines = []
        for step in [0.0, 0.5, 1.0]:
            gy = pad_top + chart_h * (1.0 - step)
            gval = min_val + step * val_range
            grid_lines.append(f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width - pad_right}" y2="{gy:.1f}" stroke="#2A344A" stroke-dasharray="3,3" stroke-width="1"/>')
            grid_lines.append(f'<text x="{pad_left - 8}" y="{gy + 4:.1f}" fill="#94A3B8" font-size="10" text-anchor="end">${gval:,.0f}</text>')

        x_labels = []
        indices = [0, n // 2, n - 1] if n >= 3 else list(range(n))
        for idx in sorted(list(set(indices))):
            px = points[idx][0]
            dt = dates[idx]
            x_labels.append(f'<text x="{px:.1f}" y="{height - 12}" fill="#94A3B8" font-size="10" text-anchor="middle">{dt}</text>')

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">
  <defs>
    <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#3B82F6" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#3B82F6" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" fill="#1E2536" rx="8"/>
  {''.join(grid_lines)}
  <path d="{fill_d}" fill="url(#blueGrad)"/>
  <path d="{path_d}" fill="none" stroke="#3B82F6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  {''.join(x_labels)}
</svg>'''

        b64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
        return f"data:image/svg+xml;base64,{b64}", dates, vals
    except Exception as ex:
        print(f"Portfolio chart render error: {ex}")
        return "", [], []


def render_multi_backtest_chart(series_list: list, ticker: str):
    """
    복수 전략(종종이, 무한매수, 단순보유 등)의 백테스트 자산 비교 차트를 고해상도 순수 벡터 SVG로 생성합니다.
    Returns: (chart_b64, dates, valid_series)
    """
    try:
        width = 650
        height = 260
        pad_left = 65
        pad_right = 25
        pad_top = 40
        pad_bottom = 40

        chart_w = width - pad_left - pad_right
        chart_h = height - pad_top - pad_bottom

        valid_series = [s for s in series_list if s.get('vals')]
        if not valid_series:
            return "", [], []

        # 날짜 축 (가장 긴 시리즈 기준)
        longest_s = max(valid_series, key=lambda s: len(s.get('dates', [])))
        dates = longest_s.get('dates', [])
        n = len(dates)

        # 전체 전략의 min, max 산출
        all_vals = []
        for s in valid_series:
            all_vals.extend(s['vals'])

        min_val = min(all_vals) if all_vals else 0.0
        max_val = max(all_vals) if all_vals else 1000.0
        if min_val == max_val:
            min_val = max(0.0, min_val * 0.9)
            max_val = max_val * 1.1 if max_val > 0 else 1000.0

        val_range = max_val - min_val if max_val > min_val else 1.0

        # Y축 격자선
        grid_lines = []
        for step in [0.0, 0.5, 1.0]:
            gy = pad_top + chart_h * (1.0 - step)
            gval = min_val + step * val_range
            grid_lines.append(f'<line x1="{pad_left}" y1="{gy:.1f}" x2="{width - pad_right}" y2="{gy:.1f}" stroke="#2A344A" stroke-dasharray="3,3" stroke-width="1"/>')
            grid_lines.append(f'<text x="{pad_left - 8}" y="{gy + 4:.1f}" fill="#94A3B8" font-size="10" text-anchor="end">${gval:,.0f}</text>')

        # 각 전략별 선 그리기
        paths_svg = []
        for idx, s in enumerate(valid_series):
            vals = s['vals']
            col = s.get('color', '#10B981')
            is_dash = s.get('dash', False)
            m = len(vals)
            if m == 0:
                continue

            pts = []
            for i, v in enumerate(vals):
                x = pad_left + (i / max(1, m - 1)) * chart_w
                y = pad_top + chart_h - ((v - min_val) / val_range) * chart_h
                pts.append((x, y))

            path_d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
            for pt in pts[1:]:
                path_d += f" L {pt[0]:.1f} {pt[1]:.1f}"

            dash_attr = 'stroke-dasharray="4,4"' if is_dash else ''
            stroke_w = "2.0" if is_dash else "2.5"

            fill_svg = ""
            if len(valid_series) == 1 and not is_dash:
                fill_d = path_d + f" L {pts[-1][0]:.1f} {pad_top + chart_h:.1f} L {pts[0][0]:.1f} {pad_top + chart_h:.1f} Z"
                fill_svg = f'<path d="{fill_d}" fill="{col}" fill-opacity="0.18"/>'

            paths_svg.append(f'{fill_svg}<path d="{path_d}" fill="none" stroke="{col}" stroke-width="{stroke_w}" {dash_attr} stroke-linecap="round" stroke-linejoin="round"/>')

        # X축 날짜 레이블
        x_labels = []
        indices = [0, n // 4, n // 2, (3 * n) // 4, n - 1] if n >= 5 else list(range(n))
        for i_idx in sorted(list(set(indices))):
            if i_idx < n:
                px = pad_left + (i_idx / max(1, n - 1)) * chart_w
                dt_str = dates[i_idx]
                x_labels.append(f'<text x="{px:.1f}" y="{height - 12}" fill="#94A3B8" font-size="10" text-anchor="middle">{dt_str}</text>')

        # 상단 범례 (Legend)
        legend_items = []
        cur_x = pad_left + 10
        for s in valid_series:
            col = s.get('color', '#10B981')
            name = s.get('name', '')
            is_dash = s.get('dash', False)
            dash_attr = 'stroke-dasharray="3,3"' if is_dash else ''
            legend_items.append(f'''
            <g transform="translate({cur_x}, 18)">
              <line x1="0" y1="0" x2="16" y2="0" stroke="{col}" stroke-width="2.5" {dash_attr}/>
              <circle cx="8" cy="0" r="3" fill="{col}"/>
              <text x="22" y="4" fill="#E2E8F0" font-size="10" font-weight="bold">{name}</text>
            </g>
            ''')
            cur_x += len(name) * 8 + 65

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">
  <rect width="{width}" height="{height}" fill="#1E2536" rx="8"/>
  {''.join(grid_lines)}
  {''.join(paths_svg)}
  {''.join(legend_items)}
  {''.join(x_labels)}
</svg>'''

        b64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
        return f"data:image/svg+xml;base64,{b64}", dates, valid_series
    except Exception as ex:
        print(f"Multi-chart render error: {ex}")
        return "", [], []


def render_backtest_chart(df_strat: pd.DataFrame, df_bnh: pd.DataFrame, strat_name: str, ticker: str) -> str:
    """
    단일 전략 하위 호환성 래퍼 함수
    """
    series_list = []
    if df_strat is not None and not df_strat.empty and 'Asset' in df_strat.columns:
        series_list.append({
            'name': strat_name,
            'color': '#10B981',
            'dash': False,
            'dates': [pd.to_datetime(d).strftime('%y/%m' if len(df_strat) > 365 else '%m/%d') for d in df_strat['Date']],
            'vals': df_strat['Asset'].values.tolist()
        })
    if df_bnh is not None and not df_bnh.empty and 'Asset' in df_bnh.columns:
        series_list.append({
            'name': f"{ticker} 단순보유",
            'color': '#94A3B8',
            'dash': True,
            'dates': [pd.to_datetime(d).strftime('%y/%m' if len(df_bnh) > 365 else '%m/%d') for d in df_bnh['Date']],
            'vals': df_bnh['Asset'].values.tolist()
        })
    chart_b64, _, _ = render_multi_backtest_chart(series_list, ticker)
    return chart_b64
