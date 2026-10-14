"""
미국 주식 시장(NYSE / NASDAQ) 개장일 및 영업일(Trading Days) 캘린더 모듈
주말(토/일) 및 미국 연방/증시 공휴일(New Year, MLK, Presidents' Day, Good Friday,
Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving, Christmas)을 정확히 판별합니다.
"""
import datetime
from typing import Set


def calc_easter(year: int) -> datetime.date:
    """
    그레고리력 기준 부활절(Easter Sunday) 날짜 계산 (알고리즘: Anonymous Gregorian / Meeus)
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def get_nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """
    특정 연도, 월의 n번째 특정 요일 반환 (0=월요일, 1=화요일, ..., 6=일요일)
    """
    first_day = datetime.date(year, month, 1)
    first_weekday = first_day.weekday()
    day = 1 + (weekday - first_weekday) % 7 + (n - 1) * 7
    return datetime.date(year, month, day)


def get_last_weekday(year: int, month: int, weekday: int) -> datetime.date:
    """
    특정 연도, 월의 마지막 특정 요일 반환
    """
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    last_day = next_month - datetime.timedelta(days=1)
    diff = (last_day.weekday() - weekday) % 7
    return last_day - datetime.timedelta(days=diff)


def get_us_market_holidays(year: int) -> Set[datetime.date]:
    """
    해당 연도의 미국 증시 공식 휴장일(NYSE / NASDAQ Holidays) 목록을 반환합니다.
    """
    holidays = set()

    # 1. New Year's Day (1월 1일 - 일요일이면 1월 2일 대체 휴장, 토요일이면 전년도 12월 31일)
    ny = datetime.date(year, 1, 1)
    if ny.weekday() == 6:
        holidays.add(datetime.date(year, 1, 2))
    elif ny.weekday() != 5:
        holidays.add(ny)

    # 2. Martin Luther King Jr. Day (1월 3번째 월요일)
    holidays.add(get_nth_weekday(year, 1, 0, 3))

    # 3. Washington's Birthday / Presidents' Day (2월 3번째 월요일)
    holidays.add(get_nth_weekday(year, 2, 0, 3))

    # 4. Good Friday (성금요일: 부활절 2일 전 금요일)
    easter = calc_easter(year)
    good_friday = easter - datetime.timedelta(days=2)
    holidays.add(good_friday)

    # 5. Memorial Day (5월 마지막 월요일)
    holidays.add(get_last_weekday(year, 5, 0))

    # 6. Juneteenth National Independence Day (6월 19일, 2021년부터 제정)
    if year >= 2021:
        june19 = datetime.date(year, 6, 19)
        if june19.weekday() == 5:
            holidays.add(datetime.date(year, 6, 18))
        elif june19.weekday() == 6:
            holidays.add(datetime.date(year, 6, 20))
        else:
            holidays.add(june19)

    # 7. Independence Day (7월 4일 - 토요일이면 7월 3일, 일요일이면 7월 5일 대체 휴장)
    july4 = datetime.date(year, 7, 4)
    if july4.weekday() == 5:
        holidays.add(datetime.date(year, 7, 3))
    elif july4.weekday() == 6:
        holidays.add(datetime.date(year, 7, 5))
    else:
        holidays.add(july4)

    # 8. Labor Day (9월 첫 번째 월요일)
    holidays.add(get_nth_weekday(year, 9, 0, 1))

    # 9. Thanksgiving Day (11월 4번째 목요일)
    holidays.add(get_nth_weekday(year, 11, 3, 4))

    # 10. Christmas Day (12월 25일 - 토요일이면 12월 24일, 일요일이면 12월 26일 대체 휴장)
    dec25 = datetime.date(year, 12, 25)
    if dec25.weekday() == 5:
        holidays.add(datetime.date(year, 12, 24))
    elif dec25.weekday() == 6:
        holidays.add(datetime.date(year, 12, 26))
    else:
        holidays.add(dec25)

    return holidays


def is_us_trading_day(d: datetime.date) -> bool:
    """
    주어진 날짜가 미국 증시 개장일(영업일)인지 확인합니다.
    (주말 또는 공휴일이면 False)
    """
    if d.weekday() >= 5:  # 5=토요일, 6=일요일
        return False
    holidays = get_us_market_holidays(d.year)
    return d not in holidays


def get_next_trading_day(d: datetime.date) -> datetime.date:
    """
    주어진 날짜의 바로 다음 미국 증시 영업일(개장일)을 반환합니다.
    (주말 및 미국 공휴일을 자동으로 건너뜁니다)
    """
    curr = d + datetime.timedelta(days=1)
    while not is_us_trading_day(curr):
        curr += datetime.timedelta(days=1)
    return curr


def get_prev_trading_day(d: datetime.date) -> datetime.date:
    """
    주어진 날짜의 바로 이전 미국 증시 영업일(개장일)을 반환합니다.
    """
    curr = d - datetime.timedelta(days=1)
    while not is_us_trading_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr


def parse_date(date_val) -> datetime.date:
    """
    문자열('YYYY-MM-DD') 또는 datetime 객체를 datetime.date 객체로 변환합니다.
    """
    if isinstance(date_val, datetime.date):
        return date_val
    if isinstance(date_val, datetime.datetime):
        return date_val.date()
    if isinstance(date_val, str):
        return datetime.datetime.strptime(date_val.strip()[:10], '%Y-%m-%d').date()
    raise ValueError(f"지원하지 않는 날짜 포맷입니다: {date_val}")
