# app/task_handlers/task1_simple.py
"""
Task 1 – 단순 조회
"""
from __future__ import annotations

import re, math, datetime as dt
from functools import lru_cache
from typing import List, Dict

import pandas as pd
import yfinance as yf

from app.ticker_lookup import to_ticker
from app.data_fetcher import get_price_on_date, get_volume_top, _download, _slice_single
from app.universe import (
    KOSPI_TICKERS, KOSDAQ_TICKERS, GLOBAL_TICKERS,
    NAME_BY_TICKER, KOSPI_MAP, KOSDAQ_MAP,
)
from app.utils import _is_zero_volume

# ──────────────────────────────
FIELD_MAP = {"종가": "Close", "시가": "Open", "고가": "High", "저가": "Low", "등락률": "%Change"}
TICK2NAME: Dict[str, str] = {v: k for k, v in {**KOSPI_MAP, **KOSDAQ_MAP}.items()}

_LOOKBACK_DAYS = 7                      # 지난 7 일 안에서 직전 거래일 탐색
# ──────────────────────────────
# 0. 유틸
_PARTICLE_CUT = re.compile(r"[의은는이가를]\s*$")
_MARKET_PREFIX = re.compile(r"\b(KOSPI|KOSDAQ)\b\s*에서?")

_BDAY = pd.tseries.offsets.BDay(1)

def _prev_bday(date: str) -> str:
    return (pd.Timestamp(date) - _BDAY).strftime("%Y-%m-%d")

def _next_day(date: str) -> str:
    return (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

def _weekend_msg(date: str, suffix: str) -> str | None:
    """주말(토/일)인 경우 메시지 반환, 평일이면 None"""
    wd = pd.Timestamp(date).weekday()
    if wd == 5:
        return f"토요일 {suffix}"
    if wd == 6:
        return f"일요일 {suffix}"
    return None

# ─────────────────────────── 1. 가격/등락률 ───────────────────────────
def _answer_price(params: dict) -> str:
    name   = params["tickers"][0]
    date   = params["date"]
    field_ko = params["metrics"][0]          # 종가·시가·고가·저가·등락률 중 하나

    wk = _weekend_msg(date, f"({field_ko} 데이터 없음)")
    if wk:
        return wk

    ticker = to_ticker(name)
    # 가격 데이터가 없는 주식(거래정지) → 0 처리
    if field_ko == "등락률":
        prev, today = _prev_bday(date), date
        try:
            p_today = get_price_on_date(ticker, today, "Close")
            p_prev  = get_price_on_date(ticker, prev,  "Close")
            if p_today in (None, 0) or p_prev in (None, 0):
                return f"{date} 등락률 데이터 없음"
            pct = (p_today - p_prev) / p_prev * 100
            return f"{pct:+.2f}%"
        except Exception:
            return f"{date} 등락률 데이터 없음"

    field = FIELD_MAP[field_ko]
    try:
        price = get_price_on_date(ticker, date, field)
        vol   = get_price_on_date(ticker, date, "Volume")
    except Exception:
        price, vol = None, None

    if vol in (None, 0) or price in (None, 0):
        return "0원" if ticker.endswith((".KS", ".KQ")) else "0USD"

    unit = "원" if ticker.endswith((".KS", ".KQ")) else "USD"
    return f"{price:,.0f}{unit}"


# ─────────────────────────── 2. 상승/하락/거래 종목 수 ───────────────────────────
def _universe(market: str|None) -> List[str]:
    return (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )

def _updown_count(date: str, market: str|None, direction: str) -> str:
    """direction ∈ {'상승','하락'}"""
    tickers = _universe(market)
    prev = _prev_bday(date)
    nxt  = _next_day(date)
    df = _download(tuple(tickers), start=prev, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"

    inc = 0
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if _is_zero_volume(sub, idx=1):
                continue
            if len(sub) >= 2 and "Close" in sub.columns:
                pc, tc = sub["Close"].iloc[0], sub["Close"].iloc[1]
                if pd.isna(pc) or pd.isna(tc):
                    continue
                if (tc > pc and direction == "상승") or (tc < pc and direction == "하락"):
                    inc += 1
        except KeyError:
            continue
    return f"{inc:,}개" if inc else f"{date} 데이터 없음"

def _traded_count(date: str, market: str) -> str:
    tickers = _universe(market)
    nxt = _next_day(date)
    df = _download(tuple(tickers), start=date, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"
    cnt = sum(
        1
        for t in tickers
        if not pd.isna((sub := _slice_single(df, t))["Volume"].iloc[0])
        and sub["Volume"].iloc[0] > 0
    )
    return f"{cnt:,}개"

# ─────────────────────────── 3. 시장 순위 ───────────────────────────
def _answer_volume_top(date: str, market: str|None, n: int) -> str:
    tickers = _universe(market)
    top = get_volume_top(tickers, date, n)
    if not top.any():
        return f"{date} 데이터 없음"
    if n == 1:
        t, v = top.index[0], int(top.iloc[0])
        return f"{TICK2NAME.get(t, t)} ({v:,}주)"
    names = [TICK2NAME.get(t, t) for t in top.index[:n]]
    return ", ".join(names)

def _answer_top_mover(date: str, market: str|None, direction: str, n: int) -> str:
    tickers = _universe(market)
    start = (pd.Timestamp(date) - pd.Timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    nxt   = _next_day(date)
    df = _download(tuple(tickers), start=start, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"

    pct: Dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if date not in sub.index or _is_zero_volume(sub):
                continue
            today_c = sub.loc[date, "Close"]
            prev_ser = sub.loc[:date, "Close"].iloc[:-1].dropna()
            if prev_ser.empty:
                continue
            prev_c = prev_ser.iloc[-1]
            if today_c and prev_c:
                pct[t] = (today_c - prev_c) / prev_c * 100
        except Exception:
            continue
    if not pct:
        return f"{date} 데이터 없음"

    rank = sorted(pct.items(), key=lambda x: x[1], reverse=(direction == "상승률"))[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in rank)

def _answer_top_price(date: str, market: str|None, n: int) -> str:
    tickers = _universe(market)
    nxt = _next_day(date)
    df = _download(tuple(tickers), start=date, end=nxt, interval="1d")
    closes = {
        t: sub["Close"].iloc[0]
        for t in tickers
        if (sub := _slice_single(df, t)).empty is False
        and not _is_zero_volume(sub)
        and not pd.isna(sub["Close"].iloc[0])
    }
    if not closes:
        return f"{date} 데이터 없음"
    top = sorted(closes.items(), key=lambda x: x[1], reverse=True)[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in top)

def _answer_kospi_index(date: str) -> str:
    return _index_close(date, "^KS11")

def _answer_kosdaq_index(date: str) -> str:
    return _index_close(date, "^KQ11")

def _index_close(date: str, ticker: str) -> str:
    try:
        val = get_price_on_date(ticker, date, "Close")
        return f"{val:,.2f}" if val else f"{date} 데이터 없음"
    except Exception:
        return f"{date} 데이터 없음"

def _answer_total_trading_value(date: str) -> str:
    nxt = _next_day(date)
    df = _download(tuple(GLOBAL_TICKERS), start=date, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"
    total = 0
    for t in GLOBAL_TICKERS:
        try:
            sub = _slice_single(df, t)
            price, vol = sub["Close"].iloc[0], sub["Volume"].iloc[0]
            if not pd.isna(price) and not pd.isna(vol):
                total += price * vol
        except Exception:
            continue
    return f"{int(total):,}원" if total else f"{date} 데이터 없음"


# ─────────────────────────── 메인 엔트리 ───────────────────────────
def handle(_: str, p: dict) -> str:
    """
    Router 로부터 (원본질문, params) 을 받는다.
    원본 질문은 로그·후행 질문 생성용으로만 사용하므로
    여기선 params 만 쓰면 된다.
    """
    task = p["task"]

    # 1) 단순가격/지수/거래대금
    if task == "단순조회":
        metric = p["metrics"][0]
        if metric in {"종가","시가","고가","저가","등락률"}:
            return _answer_price(p)
        if metric == "지수":
            mkt = p.get("market")
            if mkt == "KOSPI":
                return _answer_kospi_index(p["date"])
            if mkt == "KOSDAQ":
                return _answer_kosdaq_index(p["date"])
            return "KOSPI와 KOSDAQ 중 시장을 지정해주세요."
        if metric == "거래대금" and not p.get("tickers"):
            return _answer_total_trading_value(p["date"])
        return "지원하지 않는 지표입니다."

    # 2) 종목 수
    if task == "상승종목수":
        return _updown_count(p["date"], p.get("market"), "상승")
    if task == "하락종목수":
        return _updown_count(p["date"], p.get("market"), "하락")
    if task == "거래종목수":
        return _traded_count(p["date"], p["market"])

    # 3) 시장순위
    if task == "시장순위":
        metric = p["metrics"][0]
        n = p.get("rank_n") or 1
        if metric == "거래량":
            return _answer_volume_top(p["date"], p.get("market"), n)
        if metric in ("상승률","하락률"):
            return _answer_top_mover(p["date"], p.get("market"), metric, n)
        if metric == "가격":
            return _answer_top_price(p["date"], p.get("market"), n)
        return "지원하지 않는 지표입니다."

    return "질문을 이해하지 못했습니다."