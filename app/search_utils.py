# app/search_utils.py (리팩토링 완료)
from __future__ import annotations
from typing import Dict, List, Iterable, Tuple
import pandas as pd
import numpy as np
import datetime as dt

from app.data_fetcher import _download, _next_day
from app.universe import NAME_BY_TICKER, KOSPI_TICKERS, KOSDAQ_TICKERS
from app.utils import _holiday_msg, _prev_bday, _next_day, _universe
from app.ticker_lookup import to_ticker

ALL = KOSPI_TICKERS + KOSDAQ_TICKERS

# ────────────────────────── 1. 가격/거래량 조건 기반 필터 ──────────────────────────
def search_by_pct_change_range(df: pd.DataFrame, from_date: str, to_date: str, cond: dict, tickers: list[str]) -> list[str]:
    min_, max_ = cond.get("min"), cond.get("max")
    out = []

    for t in tickers:
        try:
            p1 = df.loc[pd.to_datetime(from_date), (t, "Close")]
            p2 = df.loc[pd.to_datetime(to_date),   (t, "Close")]
            vol = df.loc[pd.to_datetime(to_date), (t, "Volume")]
        except KeyError:
            continue
        if any(pd.isna(x) or x == 0 for x in (p1, p2, vol)):
            continue
        change = (p2 / p1 - 1) * 100
        if (min_ is not None and change < min_) or (max_ is not None and change > max_):
            continue
        out.append(t)

    return out

def search_by_consecutive_change(df: pd.DataFrame, from_date: str, to_date: str, cond: dict, tickers: list[str]) -> list[str]:
    direction = cond.get("direction", "up")
    count = cond.get("count", 3)
    out = []
    sliced = df.loc[pd.to_datetime(from_date):pd.to_datetime(to_date)]

    for t in tickers:
        try:
            close = sliced[(t, "Close")].dropna()
            vol = df.loc[pd.to_datetime(to_date), (t, "Volume")]
        except KeyError:
            continue
        if len(close) < count or pd.isna(vol) or vol == 0:
            continue
        diff = close.diff().iloc[1:]
        cmp = diff > 0 if direction == "up" else diff < 0
        if cmp.rolling(count).apply(all).any():
            out.append(t)
    return out

def search_cross_count_by_stock(name: str, from_date: str, to_date: str, side: str) -> str:
    g, d = count_crosses(from_date, to_date, name)
    if side == "golden":
        return f"{name}에서 {from_date}부터 {to_date}까지 골든크로스가 발생한 횟수는 {g}번입니다."
    elif side == "dead":
        return f"{name}에서 {from_date}부터 {to_date}까지 데드크로스가 발생한 횟수는 {d}번입니다."
    elif side == "both":
        return f"{name}에서 {from_date}부터 {to_date}까지 데드크로스는 {d}번, 골든크로스는 {g}번 발생했습니다."
    else:
        return f"{name}에서 {from_date}부터 {to_date}까지 골든크로스 {g}번, 데드크로스 {d}번 발생했습니다."

def search_cross_dates_by_condition(df: pd.DataFrame, from_date: str, to_date: str, side: str, tickers: list[str]) -> list[str]:
    window_short, window_long = 5, 20
    out = []

    for t in tickers:
        if (t, "Close") not in df.columns:
            continue
        close = df[t, "Close"].dropna().loc[from_date:to_date]
        if len(close) < window_long:
            continue
        ma_short = close.rolling(window=window_short).mean()
        ma_long  = close.rolling(window=window_long).mean()
        prev_diff = None

        for i in range(len(close)):
            if pd.isna(ma_short.iloc[i]) or pd.isna(ma_long.iloc[i]):
                continue
            diff = ma_short.iloc[i] - ma_long.iloc[i]
            if prev_diff is not None:
                if side == "golden" and prev_diff < 0 and diff > 0:
                    out.append(t)
                    break
                if side == "dead" and prev_diff > 0 and diff < 0:
                    out.append(t)
                    break
            prev_diff = diff
    return out

ALL = KOSPI_TICKERS + KOSDAQ_TICKERS

# ───────────────────────────────────────────────
def compute_rsi(series: pd.Series, date: str, window: int = 14) -> float | None:
    date = pd.to_datetime(date)
    series = series.dropna()
    if date not in series.index:
        return None
    end_loc = series.index.get_loc(date)
    if end_loc < window:
        return None
    window_series = series.iloc[end_loc - window : end_loc + 1]
    delta = window_series.diff().iloc[1:]
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.mean()
    avg_loss = loss.mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ───────────────────────────────────────────────
def detect_rsi(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    window = cond.get("window", 14)
    min_, max_ = cond.get("min"), cond.get("max")
    out = []

    for ticker in tickers:
        if (ticker, "Volume") not in df.columns:
            continue
        vol = df[ticker, "Volume"]
        if date not in vol or vol[date] == 0:
            continue

        close = df[ticker, "Adj Close"].dropna()
        rsi = compute_rsi(close, date, window)
        if rsi is None:
            continue
        if min_ is not None and rsi < min_:
            continue
        if max_ is not None and rsi > max_:
            continue
        out.append(ticker)

    return out


# ───────────────────────────────────────────────
def detect_volume_spike(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    window = cond.get("window", 20)
    threshold = cond.get("volume_ratio", {}).get("min", 0)
    out = []

    for ticker in tickers:
        if (ticker, "Adj Close") not in df.columns:
            continue
        vol = df[ticker, "Volume"].dropna()
        if date not in vol:
            continue
        hist = vol.loc[:date]
        if len(hist) < window:
            continue
        past = hist.iloc[-window:]
        avg = past.mean()
        today = vol.loc[date]
        if pd.isna(avg) or avg == 0:
            continue
        ratio = today / avg * 100 - 100
        if ratio >= threshold:
            out.append(ticker)

    return out

# ───────────────────────────────────────────────
def detect_ma_break(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    window = cond.get("window", 20)
    threshold = cond.get("diff_pct", {}).get("min", 0)
    out = []

    for ticker in tickers:    
        if (ticker, "Adj Close") not in df.columns:
            continue
        close = df[ticker, "Adj Close"].dropna()
        if date not in close or len(close) < window:
            continue
        ma = close.loc[:date].iloc[-window:].mean()
        price = close.loc[date]
        if ma == 0 or pd.isna(price):
            continue
        pct_diff = (price - ma) / ma * 100
        if pct_diff >= threshold:
            out.append(ticker)

    return out

# ───────────────────────────────────────────────
def detect_bollinger_touch(df: pd.DataFrame, date: str, band: str, tickers: list[str]) -> list[str]:
    window = 20
    std_mul = 2
    out = []

    for ticker in tickers:
        if (ticker, "Adj Close") not in df.columns:
            continue
        close = df[ticker, "Adj Close"].dropna()
        if date not in close or len(close) < window:
            continue
        hist = close.loc[:date]        
        if len(hist) < window:
            continue
        ma = hist.iloc[-window:].mean()
        std = hist.iloc[-window:].std()
        upper = ma + std_mul * std
        lower = ma - std_mul * std
        price = close.loc[date]
        if band == "upper" and price >= upper:
            out.append(ticker)
        elif band == "lower" and price <= lower:
            out.append(ticker)
    return out

# ───────────────────────────────────────────────
def count_crosses(from_date: str, to_date: str, target: str) -> tuple[int, int]:
    code = to_ticker(target)
    if code is None:
        return -1, -1
    start = (pd.Timestamp(from_date) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(to_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download((code,), start=start, end=end)
    close = df[code, "Adj Close"].dropna()
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    delta = ma5 - ma20
    prev_sign = delta.shift(1).apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
    curr_sign = delta.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
    cross_dates = (prev_sign * curr_sign < 0)
    golden = 0
    dead = 0
    for d in cross_dates.index:
        if from_date <= d.strftime("%Y-%m-%d") <= to_date:
            if prev_sign[d] < 0 and curr_sign[d] > 0:
                golden += 1
            elif prev_sign[d] > 0 and curr_sign[d] < 0:
                dead += 1
    return golden, dead


# ───────────────────────────────────────────────────────────
# ⑤ 캔들스틱 패턴: 3-연속 양봉/음봉 (‘적삼병’ / ‘흑삼병’)
# ───────────────────────────────────────────────────────────
def _slice_three(sr: pd.Series, loc: int) -> Tuple[pd.Series, pd.Series] | None:
    """loc(정수 인덱스) 포함해 직전 2일·당일 총 3거래일을 반환"""
    if loc < 2:
        return None
    return sr.iloc[loc - 2 : loc + 1]

def _white(open_s, close_s) -> bool:
    # 3연속 양봉 + 종가 지속 상승
    return bool((close_s > open_s).all() and np.diff(close_s).min() > 0)

def _black(open_s, close_s) -> bool:
    # 3연속 음봉 + 종가 지속 하락
    return bool((close_s < open_s).all() and np.diff(close_s).max() < 0)

def _scan_three_pattern(
    pattern: str,
    start: str,
    end: str,
    tickers: Iterable[str] | None = None,
) -> List[Tuple[str, str]]:
    """
    - pattern: "적삼병" | "흑삼병"
    - 반환: [(ticker, 'YYYY-MM-DD'), ...]
    """
    if tickers is None or not tickers:
        tickers = tuple(ALL)

    df = _download(tuple(tickers),start=start, end=_next_day(end), interval="1d")
    if df.empty or not isinstance(df.columns, pd.MultiIndex):
        return []
    occurs: list[Tuple[str, str]] = []
    for t in df.columns.levels[0]:
        try:
            op = df[t, "Open"].dropna()
            cl = df[t, "Adj Close"].dropna()
        except KeyError:
            continue

        # ── 연속 3거래일 슬라이딩 ──────────────────────────
        for idx in range(2, len(op)):
            sub_o = _slice_three(op, idx)
            sub_c = _slice_three(cl, idx)
            if sub_o is None or sub_c is None:
                continue            # 자료 부족

            if (pattern == "적삼병" and _white(sub_o, sub_c)) or \
               (pattern == "흑삼병" and _black(sub_o, sub_c)):
                occurs.append((t, str(op.index[idx].date())))
    return occurs

def three_pattern_dates(ticker: str, pattern: str, date_from: str, date_to: str) -> str:
    occ = _scan_three_pattern(pattern, date_from, date_to, [ticker])
    if not occ:
        return (f"{NAME_BY_TICKER.get(ticker, ticker)}은(는) {date_from}~{date_to} 기간에 {pattern} 패턴이 없습니다.")
    dates = ", ".join(d for _, d in occ)
    return (f"{NAME_BY_TICKER.get(ticker, ticker)} ({date_from}~{date_to}) {pattern} 발생일은 {dates}입니다.")

def three_pattern_counts(ticker: str, pattern: str, date_from: str, date_to: str) -> str:
    occ = _scan_three_pattern(pattern, date_from, date_to, [ticker])
    counts = len(occ)
    return (f"{NAME_BY_TICKER.get(ticker, ticker)} ({date_from}~{date_to}) {pattern} 발생 횟수는 {counts}입니다.")

def check_three_pattern_occurrence(df: pd.DataFrame, pattern: str, date_from: str, date_to: str, ticker: str) -> bool:
    """
    주어진 df에 대해, 특정 ticker가 구간 내에 지정한 패턴을 최소 1회 만족하는지 여부 반환
    - pattern: "적삼병" or "흑삼병"
    """
    try:
        op = df[ticker, "Open"].dropna().loc[date_from:date_to]
        cl = df[ticker, "Adj Close"].dropna().loc[date_from:date_to]
    except KeyError:
        return False

    for idx in range(2, len(op)):
        sub_o = _slice_three(op, idx)
        sub_c = _slice_three(cl, idx)
        if sub_o is None or sub_c is None:
            continue

        if pattern == "적삼병" and _white(sub_o, sub_c):
            return True
        elif pattern == "흑삼병" and _black(sub_o, sub_c):
            return True

    return False

def three_pattern_tickers( df: pd.DataFrame, pattern: str, date_from: str, date_to: str, tickers: list[str],) -> list[str]:
    result = []
    for t in tickers:
        if (t, "Open") not in df.columns or (t, "Adj Close") not in df.columns:
            continue
        if check_three_pattern_occurrence(df, pattern, date_from, date_to, t):
            result.append(t)
    return result

def search_by_price_close(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    try:
        today = df.loc[pd.to_datetime(date)]
    except KeyError:
        return []

    min_, max_ = cond.get("min"), cond.get("max")
    result = []
    for t in tickers:
        if (t, "Close") not in today or (t, "Volume") not in today:
            continue
        close = today[(t, "Close")]
        volume = today[(t, "Volume")]
        if pd.isna(close) or volume == 0:
            continue
        if (min_ is not None and close < min_) or (max_ is not None and close > max_):
            continue
        result.append(t)
    return result

def search_by_volume(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    try:
        today = df.loc[pd.to_datetime(date)]
    except KeyError:
        return []

    min_, max_ = cond.get("min"), cond.get("max")
    result = []
    for t in tickers:
        if (t, "Volume") not in today:
            continue
        vol = today.get((t, "Volume"))
        if pd.isna(vol) or vol == 0:
            continue
        if (min_ is not None and vol < min_) or (max_ is not None and vol > max_):
            continue
        result.append(t)
    return result

def search_by_pct_change(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    try:
        today = df.loc[pd.to_datetime(date)]
        yest = df.loc[pd.to_datetime(_prev_bday(date))]
    except KeyError:
        return []

    dmin, dmax = cond.get("min"), cond.get("max")
    result = []
    for t in tickers:
        if (t, "Close") not in today or (t, "Close") not in yest or (t, "Volume") not in today:
            continue
        c1 = today[(t, "Close")]
        c0 = yest[(t, "Close")]
        vol = today[(t, "Volume")]
        if pd.isna(c0) or pd.isna(c1) or c0 == 0 or vol == 0:
            continue
        pct = (c1 - c0) / c0 * 100
        if (dmin is not None and pct < dmin) or (dmax is not None and pct > dmax):
            continue
        result.append(t)
    return result

def search_by_volume_pct(df: pd.DataFrame, date: str, cond: dict, tickers: list[str]) -> list[str]:
    try:
        today = df.loc[pd.to_datetime(date)]
        yest = df.loc[pd.to_datetime(_prev_bday(date))]
    except KeyError:
        return []

    vmin, vmax = cond.get("min"), cond.get("max")
    result = []
    for t in tickers:
        if (t, "Volume") not in today or (t, "Volume") not in yest:
            continue
        v1 = today[(t, "Volume")]
        v0 = yest[(t, "Volume")]
        if pd.isna(v0) or pd.isna(v1) or v0 == 0:
            continue
        pct = (v1 - v0) / v0 * 100
        if (vmin is not None and pct < vmin) or (vmax is not None and pct > vmax):
            continue
        result.append(t)
    return result


# ────────────────────────── 2. 52주 신고가/신저가 & 고점 대비 ──────────────────────────
def _window_slice(sr: pd.Series, date: str, period_days: int) -> pd.Series:
    """date 포함, 과거 period_days 만큼 슬라이스(데이터 부족 시 가능한 범위)"""
    idx = sr.index.get_loc(pd.to_datetime(date))
    start = max(0, idx - period_days + 1)
    return sr.iloc[start : idx + 1]

def detect_52w_high_break(
    df: pd.DataFrame, date: str, period_days: int, tickers: list[str]
) -> list[str]:
    out = []
    for t in tickers:
        if (t, "Close") not in df.columns or (t, "Volume") not in df.columns:
            continue
        today_price = df.loc[pd.to_datetime(date), (t, "Close")]
        vol = df.loc[pd.to_datetime(date), (t, "Volume")]
        if pd.isna(today_price) or vol == 0:
            continue
        hist = df[t, "Close"].dropna()
        if date not in hist.index:
            continue
        window = _window_slice(hist, date, period_days)
        if window.empty:
            continue
        if today_price >= window.max():
            out.append(t)
    return out

def detect_52w_low(
    df: pd.DataFrame, date: str, period_days: int, tickers: list[str]
) -> list[str]:
    out = []
    for t in tickers:
        if (t, "Close") not in df.columns or (t, "Volume") not in df.columns:
            continue
        today_price = df.loc[pd.to_datetime(date), (t, "Close")]
        vol = df.loc[pd.to_datetime(date), (t, "Volume")]
        if pd.isna(today_price) or vol == 0:
            continue
        hist = df[t, "Close"].dropna()
        if date not in hist.index:
            continue
        window = _window_slice(hist, date, period_days)
        if window.empty:
            continue
        if today_price <= window.min():
            out.append(t)
    return out

def detect_off_peak(
    df: pd.DataFrame, date: str, period_days: int, drop_pct: float, tickers: list[str]
) -> list[str]:
    out = []
    for t in tickers:
        if (t, "Close") not in df.columns or (t, "Volume") not in df.columns:
            continue
        today_price = df.loc[pd.to_datetime(date), (t, "Close")]
        vol = df.loc[pd.to_datetime(date), (t, "Volume")]
        if pd.isna(today_price) or vol == 0:
            continue
        hist = df[t, "Close"].dropna()
        if date not in hist.index:
            continue
        window = _window_slice(hist, date, period_days)
        if window.empty:
            continue
        peak = window.max()
        if peak == 0:
            continue
        pct_down = (peak - today_price) / peak * 100
        if pct_down >= drop_pct:
            out.append(t)
    return out


# ────────────────────────── 3. 갭 상승, 갭 하락 ──────────────────────────
def search_by_gap_pct(df: pd.DataFrame, date: str, cond: dict,
                      tickers: list[str]) -> list[str]:
    """
    (Open_today − Close_prev) / Close_prev × 100  ← ‘갭 %’
    cond = {"min": 5}  → min 이상   (갭상승)
            {"max": -5} → max 이하 (갭하락)
    """
    try:
        today = df.loc[pd.to_datetime(date)]
        prev  = df.loc[pd.to_datetime(_prev_bday(date))]
    except KeyError:
        return []

    gmin, gmax = cond.get("min"), cond.get("max")
    out = []
    for t in tickers:
        if (t, "Open") not in today or (t, "Close") not in prev \
           or (t, "Volume") not in today:
            continue
        o = today[(t, "Open")]
        c = prev[(t, "Close")]
        v = today[(t, "Volume")]
        if any(pd.isna(x) or x == 0 for x in (o, c, v)):
            continue
        gap = (o - c) / c * 100
        if (gmin is not None and gap < gmin) or (gmax is not None and gap > gmax):
            continue
        out.append(t)
    return out

