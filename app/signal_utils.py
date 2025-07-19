from __future__ import annotations
import pandas as pd
import datetime as dt

from app.universe import KOSPI_TICKERS, KOSDAQ_TICKERS, NAME_BY_TICKER
from app.data_fetcher import _download
from app.ticker_lookup import to_ticker

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
def detect_rsi(date: str, cond: dict) -> str:
    window = cond.get("window", 14)
    start = (pd.Timestamp(date) - pd.tseries.offsets.BDay(window * 2)).strftime("%Y-%m-%d")
    nxt = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=nxt)

    result = []
    for ticker in sorted(set(k[0] for k in df.columns)):
        close = df[ticker, "Adj Close"].dropna()
        rsi = compute_rsi(close, date, window)
        if rsi is None:
            continue
        if "min" in cond and rsi < cond["min"]:
            continue
        if "max" in cond and rsi > cond["max"]:
            continue
        result.append((ticker, rsi))

    result.sort(key=lambda x: -x[1])
    names = [f"{NAME_BY_TICKER.get(t, t)}(RSI:{v:.1f})" for t, v in result]

    if not names:
        return "조건에 맞는 종목 없음"

    if "min" in cond:
        cond_text = f"RSI가 {cond['min']} 이상인"
    elif "max" in cond:
        cond_text = f"RSI가 {cond['max']} 이하인"
    else:
        cond_text = "RSI 조건에 맞는"

    return f"{date}에 {cond_text} 종목은 다음과 같습니다.\n{', '.join(names)}"

# ───────────────────────────────────────────────
def detect_volume_spike(date: str, cond: dict) -> str:
    window = cond.get("window", 20)
    threshold = cond.get("volume_ratio", {}).get("min", 0)
    start = (pd.Timestamp(date) - pd.Timedelta(days=window * 2)).strftime("%Y-%m-%d")
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
    names = [f"{NAME_BY_TICKER.get(t, t)}({r:.0f}%)" for t, r in result]

    if not names:
        return "조건에 맞는 종목 없음"

    return f"{date}에 거래량이 {window}일 평균 대비 {threshold}% 이상 급증한 종목은 다음과 같습니다.\n{', '.join(names)}"

# ───────────────────────────────────────────────
def detect_ma_break(date: str, cond: dict) -> str:
    window = cond["window"]
    threshold = cond["diff_pct"]["min"]
    start = (pd.Timestamp(date) - pd.Timedelta(days=window * 3)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    result = []
    for ticker in df.columns.levels[0]:
        close = df[ticker, "Adj Close"].dropna()
        if date not in close or len(close) < window:
            continue
        ma = close.loc[:date].iloc[-window:].mean()
        price = close.loc[date]
        pct_diff = (price - ma) / ma * 100
        if pct_diff >= threshold:
            result.append((ticker, pct_diff))

    result.sort(key=lambda x: -x[1])
    names = [f"{NAME_BY_TICKER.get(t, t)}({r:.2f}%)" for t, r in result]

    if not names:
        return "조건에 맞는 종목 없음"

    return f"{date}에 종가가 {window}일 이동평균보다 {threshold}% 이상 높은 종목은 다음과 같습니다.\n{', '.join(names)}"

# ───────────────────────────────────────────────
def detect_bollinger_touch(date: str, cond: dict) -> str:
    start = (pd.Timestamp(date) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    band = cond.get("band")
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

        if band == "upper" and price >= upper:
            result.append(ticker)
        elif band == "lower" and price <= lower:
            result.append(ticker)
            
    if not result:
        return "조건에 맞는 종목 없음"

    band_kr = "상단" if band == "upper" else "하단" if band == "lower" else ""
    names = [NAME_BY_TICKER.get(t, t) for t in result]
    return f"{date}에 볼린저 밴드 {band_kr}에 터치한 종목은 다음과 같습니다.\n{', '.join(names)}"

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

# ───────────────────────────────────────────────
def list_crossed_stocks(from_date: str, to_date: str, cond: dict) -> list[str]:
    side = cond.get("side")
    start = (pd.Timestamp(from_date) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(to_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    df = _download(tuple(ALL), start=start, end=end)

    result = []
    for ticker in df.columns.levels[0]:
        close = df[ticker, "Adj Close"].dropna()
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        delta = ma5 - ma20
        prev_sign = delta.shift(1).apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        curr_sign = delta.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
        cross_dates = (prev_sign * curr_sign < 0)

        for d in cross_dates.index:
            if from_date <= d.strftime("%Y-%m-%d") <= to_date:
                if side == "golden" and prev_sign[d] < 0 and curr_sign[d] > 0:
                    result.append(NAME_BY_TICKER.get(ticker, ticker))
                    break
                elif side == "dead" and prev_sign[d] > 0 and curr_sign[d] < 0:
                    result.append(NAME_BY_TICKER.get(ticker, ticker))
                    break
    return sorted(result)
