# app/signal_utils.py
from __future__ import annotations

import pandas as pd
import datetime as dt

from app.universe import KOSPI_TICKERS, KOSDAQ_TICKERS, NAME_BY_TICKER
from app.data_fetcher import _download
from app.ticker_lookup import to_ticker
from app.task_handlers.task1_simple import _prev_bday, _next_day

ALL = KOSPI_TICKERS + KOSDAQ_TICKERS

# ─────────────────────────────────────────────────────
def compute_rsi(series: pd.Series, date: str, window: int = 14) -> float | None:
    date = pd.to_datetime(date)
    series = series.dropna()
    
    # 해당 날짜까지 포함한 window+1개 추출 (diff 때문에 하나 더 필요)
    if date not in series.index:
        return None
    
    end_loc = series.index.get_loc(date)
    if end_loc < window:
        return None  # 충분한 길이 없음

    window_series = series.iloc[end_loc - window : end_loc + 1]
    
    delta = window_series.diff().iloc[1:]  # 첫 NaN 제외
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.mean()
    avg_loss = loss.mean()

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ─────────────────────────────────────────────────────
def detect_rsi(signal_type: str, date: str, threshold: float) -> str:
    start = (pd.Timestamp(date) - pd.tseries.offsets.BDay(20)).strftime("%Y-%m-%d")
    nxt = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=nxt)
    result = []
    tickers = sorted(set(k[0] for k in df.columns))
    for ticker in tickers:
        close = df[ticker, "Adj Close"].dropna()
        rsi = compute_rsi(close, date)        
        if rsi is None:
            continue
        if signal_type == "RSI_OVERBOUGHT" and rsi >= threshold:
            result.append((ticker, rsi))
        elif signal_type == "RSI_OVERSOLD" and rsi <= threshold:
            result.append((ticker, rsi))

    result.sort(key=lambda x: -x[1])
    return ", ".join(f"{NAME_BY_TICKER.get(t, t)}(RSI:{v:.1f})" for t, v in result) if result else "조건에 맞는 종목 없음"

# ─────────────────────────────────────────────────────
def detect_volume_spike(date: str, threshold: float, window: int = 20) -> str:
    start = (pd.Timestamp(date) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    result = []
    for ticker in df.columns.levels[0]:
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
            result.append((ticker, ratio))

    result.sort(key=lambda x: -x[1])
    return ", ".join(f"{NAME_BY_TICKER.get(t, t)}({r:.0f}%)" for t, r in result) if result else "조건에 맞는 종목 없음"

# ─────────────────────────────────────────────────────
def detect_ma_break(signal_type: str, date: str, threshold: float) -> str:
    ma_len = int(signal_type[2:signal_type.index("_")])
    start = (pd.Timestamp(date) - pd.Timedelta(days=ma_len * 3)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    result = []
    for ticker in df.columns.levels[0]:
        close = df[ticker, "Adj Close"].dropna()
        if date not in close or len(close) < ma_len:
            continue
        window = close.loc[:date].iloc[-ma_len:]
        ma = window.mean()
        price = close.loc[date]
        ratio = (price - ma) / ma * 100
        if ratio >= threshold:
            result.append((ticker, ratio))

    result.sort(key=lambda x: -x[1])
    return ", ".join(f"{NAME_BY_TICKER.get(t, t)}({r:.2f}%)" for t, r in result) if result else "조건에 맞는 종목 없음"

# ─────────────────────────────────────────────────────
def detect_bollinger_touch(signal_type: str, date: str) -> str:
    start = (pd.Timestamp(date) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    result = []
    for ticker in df.columns.levels[0]:
        close = df[ticker, "Adj Close"].dropna()
        if date not in close or len(close) < 20:
            continue
        window = close.loc[:date].iloc[-20:]
        ma20 = window.mean()
        std20 = window.std()
        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20
        price = close.loc[date]

        if signal_type == "BOLLINGER_UPPER" and price >= upper:
            result.append(ticker)
        elif signal_type == "BOLLINGER_LOWER" and price <= lower:
            result.append(ticker)

    return ", ".join(NAME_BY_TICKER.get(t, t) for t in result) if result else "조건에 맞는 종목 없음"

# ─────────────────────────────────────────────────────
def count_crosses(signal_type: str, from_date: str, to_date: str, target: str) -> str:
    code = to_ticker(target)
    if code is None:
        return f"[ERROR] 티커 조회 실패: {target}"

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

    crosses = []
    for d in cross_dates.index:
        if from_date <= d.strftime("%Y-%m-%d") <= to_date:
            if prev_sign[d] < 0 and curr_sign[d] > 0:
                crosses.append("골든크로스")
            elif prev_sign[d] > 0 and curr_sign[d] < 0:
                crosses.append("데드크로스")

    golden = crosses.count("골든크로스")
    dead = crosses.count("데드크로스")

    return f"{golden}번" if "GOLDEN" in signal_type else f"{dead}번"

# ─────────────────────────────────────────────────────
def list_crossed_stocks(signal_type: str, from_date: str, to_date: str) -> str:
    start = (pd.Timestamp(from_date) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(to_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    crossed = []
    for ticker in df.columns.levels[0]:
        close = df[ticker, "Adj Close"].dropna()
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()

        delta = ma5 - ma20
        prev_sign = delta.shift(1).apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        curr_sign = delta.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        cross_dates = (prev_sign * curr_sign < 0)

        found = False
        for d in cross_dates.index:
            if from_date <= d.strftime("%Y-%m-%d") <= to_date:
                if "GOLDEN" in signal_type and prev_sign[d] < 0 and curr_sign[d] > 0:
                    found = True
                elif "DEAD" in signal_type and prev_sign[d] > 0 and curr_sign[d] < 0:
                    found = True
        if found:
            crossed.append(NAME_BY_TICKER.get(ticker, ticker))

    return ", ".join(sorted(crossed)) if crossed else "조건에 맞는 종목 없음"
