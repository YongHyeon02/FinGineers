# app/task_handlers/task4_ambiguous.py
"""
Task 4 Handler — 모호한 의미 해석
"""
from __future__ import annotations

import datetime as dt
from typing import List

import pandas as pd

from app.parsers import parse_ambiguous, AmbiguousQuery
from app.data_fetcher import get_price_series
from app.indicators import pct_change, max_drawdown
from app.utils import trading_day_offset, fmt_price
from app.ticker_lookup import NAME_BY_TICKER, KOSPI_TICKERS, KOSDAQ_TICKERS

_ALL_TICKERS: List[str] = KOSPI_TICKERS + KOSDAQ_TICKERS

# ───────────── Helper ─────────────
def _rank(series: pd.Series, n: int) -> pd.Series:
    return series.sort_values(ascending=False).head(n)

def _build_reply(q: AmbiguousQuery, ranked: pd.Series) -> str:
    header = (
        f"최근 {q.period_days}일 기준 "
        + ("상승률 TOP" if q.intent == "top_gainers" else "고점 대비 낙폭 TOP")
        + f" {q.top_n} 종목"
    )
    lines = [
        f"{i+1}. {NAME_BY_TICKER.get(sym, sym)} ({fmt_price(val, is_pct=True)})"
        for i, (sym, val) in enumerate(ranked.items())
    ]
    return header + "\\n" + "\\n".join(lines)

# ───────────── Entry ─────────────
def handle(question: str) -> str:
    q = parse_ambiguous(question)
    if not q:
        return "질문을 이해하지 못했습니다. (Task 4)"

    end_d = trading_day_offset(dt.date.today(), -1)
    start_d = trading_day_offset(end_d, -(q.period_days - 1))

    price = get_price_series(_ALL_TICKERS, start_d, end_d)
    if price.empty:
        return "해당 기간 데이터가 없습니다."

    if q.intent == "top_gainers":
        metric = pct_change(price["Close"])
    else:
        metric = max_drawdown(price["High"], price["Low"])

    ranked = _rank(metric, q.top_n)
    return _build_reply(q, ranked)
