from __future__ import annotations
import pandas as pd
import datetime as dt
import numpy as np
from typing import Any, Iterable, List, Tuple

from app.universe import KOSPI_TICKERS, KOSDAQ_TICKERS, NAME_BY_TICKER
from app.data_fetcher import _download, _next_day
from app.ticker_lookup import to_ticker
from app.utils import _prev_bday

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
        if (ticker, "Volume") not in df.columns or df[ticker, "Volume"].get(date, 0) == 0:
            continue
        close = df[ticker, "Adj Close"].dropna()
        rsi = compute_rsi(close, date, window)
        if rsi is None:
            continue
        if "min" in cond and rsi < cond["min"]:
            continue
        if "max" in cond and rsi > cond["max"]:
            continue
        result.append((ticker, rsi))

    result.sort(key=lambda x: -abs(x[1]))
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

    result.sort(key=lambda x: -abs(x[1]))
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

    result.sort(key=lambda x: -abs(x[1]))
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

def three_pattern_dates(
    ticker: str,
    pattern: str,
    date_from: str,
    date_to: str,
) -> str:
    """단일 종목 구간 내 발생일 리스트업"""
    occ = _scan_three_pattern(pattern, date_from, date_to, [ticker])
    if not occ:
        return (f"{NAME_BY_TICKER.get(ticker, ticker)}은(는) {date_from}~{date_to} 기간에 {pattern} 패턴이 없습니다.")
    dates = ", ".join(d for _, d in occ)
    return (f"{NAME_BY_TICKER.get(ticker, ticker)} ({date_from}~{date_to}) {pattern} 발생일은 {dates}입니다.")

def three_pattern_counts(
    ticker: str,
    pattern: str,
    date_from: str,
    date_to: str,
) -> str:
    occ = _scan_three_pattern(pattern, date_from, date_to, [ticker])
    counts = len(occ)
    return (f"{NAME_BY_TICKER.get(ticker, ticker)} ({date_from}~{date_to}) {pattern} 발생 횟수는 {counts}입니다.")

def three_pattern_tickers(
    pattern: str,
    date_from: str,
    date_to: str,
    market: str,
) -> str:
    """구간 내 패턴이 최소 1회라도 나온 종목 리스트업"""
    pool = (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        ALL
    )
    market_txt = market if market else "전체 시장"
    hit_codes: list[str] = []
    for tk in pool:
        # 티커별로 소규모 DF만 다운로드 → 메모리·누락 문제 최소화
        if _scan_three_pattern(pattern, date_from, date_to, [tk]):
            hit_codes.append(tk)
    if not hit_codes:
        return f"{date_from}~{date_to} 기간에 {market_txt}에서 {pattern} 패턴이 관측된 종목이 없습니다."
    names = [NAME_BY_TICKER.get(tk, tk) for tk in sorted(hit_codes)]
    return (f"{date_from}~{date_to} 기간에 {market_txt}에서 {pattern} 발생 종목은 다음과 같습니다.\n" + ", ".join(names))