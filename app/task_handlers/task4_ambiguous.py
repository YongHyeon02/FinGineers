# app/task_handlers/task4_ambiguous.py
"""
Task 4 – 모호 질의 해석(최근 급등주·고점 대비 낙폭 등)
"""
from __future__ import annotations
import datetime as dt
from typing import List, Dict

import pandas as pd
from app.parsers import AmbiguousQuery
# from app.parsers import parse_ambiguous, AmbiguousQuery
from app.data_fetcher import get_price_series, _PREFETCH_END, _PREFETCH_START
from app.indicators import pct_change, max_drawdown
from app.utils import trading_day_offset, fmt_price
from app.universe import (
    NAME_BY_TICKER, KOSPI_TICKERS, KOSDAQ_TICKERS,
)

_ALL_TICKERS: List[str] = KOSPI_TICKERS + KOSDAQ_TICKERS


# ───────────────────── 내부 유틸 ─────────────────────
def _metric(price: Dict[str, pd.DataFrame], q: AmbiguousQuery) -> pd.Series:
    """의도(intent)에 맞는 지표 Series 반환"""
    if q.intent == "top_gainers":
        close = price.get("Close")
        if close is None or close.empty:
            raise ValueError("Close 데이터 없음")
        return pct_change(close)          # ↑% (양수 ↑)
    else:  # off_peak
        high, low = price.get("High"), price.get("Low")
        if any(x is None or x.empty for x in (high, low)):
            raise ValueError("High/Low 데이터 없음")
        return max_drawdown(high, low)    # 음수 (낙폭 ↑ → 값은 더 작음)


def _rank(series: pd.Series, n: int, intent: str) -> pd.Series:
    """intent에 따라 정렬 방향 결정"""
    ascending = intent != "top_gainers"   # 낙폭은 음수 절댓값 큰 순
    return series.sort_values(ascending=ascending).head(n)


def _build_reply(q: AmbiguousQuery, ranked: pd.Series) -> str:
    title = (
        f"최근 {q.period_days}일 기준 "
        + ("상승률 TOP" if q.intent == "top_gainers" else "고점 대비 낙폭 TOP")
        + f" {q.top_n} 종목"
    )
    body = "\n".join(
        f"{i+1}. {NAME_BY_TICKER.get(t, t)} ({fmt_price(v, is_pct=True)})"
        for i, (t, v) in enumerate(ranked.items())
    )
    return f"{title}\n{body}"


# ───────────────────── 메인 엔트리 ─────────────────────
def handle(question: str) -> str:
    # q = parse_ambiguous(question)
    if not q:
        return "질문을 이해하지 못했습니다. (Task 4)"

    # end_d   = trading_day_offset(dt.date.today(), -1)                 # 어제(직전 영업일)
    end_d = _PREFETCH_END
    start_d = trading_day_offset(end_d, -(q.period_days - 1))         # 기간 첫날

    price = get_price_series(_ALL_TICKERS, start_d, end_d)
    if not price or price.get("Close", pd.DataFrame()).empty:
        return "해당 기간 데이터가 없습니다."

    try:
        series = _metric(price, q)
    except ValueError:
        return "해당 기간 데이터가 없습니다."

    # (선택) threshold_pct 필터
    if q.threshold_pct:
        if q.intent == "top_gainers":
            series = series[series >= q.threshold_pct]
        else:
            series = series[series <= -abs(q.threshold_pct)]

    if series.empty:
        return "해당 조건을 만족하는 종목이 없습니다."

    ranked = _rank(series, q.top_n, q.intent)
    return _build_reply(q, ranked)
