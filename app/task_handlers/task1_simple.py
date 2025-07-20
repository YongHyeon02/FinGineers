# app/task_handlers/task1_simple.py
"""
Task 1 – 단순 조회
"""
from __future__ import annotations

import re, math, datetime as dt
from functools import lru_cache
from typing import List, Dict, Tuple

import pandas as pd
import yfinance as yf

from app.ticker_lookup import to_ticker, TickerInfo
from app.data_fetcher import get_price_on_date, get_volume_top, _download, _slice_single
from app.universe import (
    KOSPI_TICKERS, KOSDAQ_TICKERS, GLOBAL_TICKERS,
    NAME_BY_TICKER, KOSPI_MAP, KOSDAQ_MAP,
)
from app.utils import _is_zero_volume, _holiday_msg, _BDAY, _universe, _prev_bday, _next_day, _find_prev_close

# ──────────────────────────────
FIELD_MAP = {"종가": "Close", "시가": "Open", "고가": "High", "저가": "Low", "등락률": "%Change"}
TICK2NAME: Dict[str, str] = {v: k for k, v in {**KOSPI_MAP, **KOSDAQ_MAP}.items()}

                   # 지난 7 일 안에서 직전 거래일 탐색


# ─────────────────────────── 1. 가격/등락률 ───────────────────────────
def _answer_price(params: dict) -> str:
    raw_name   = params["tickers"][0]
    date   = params["date"]
    field_ko = params["metrics"][0]          # 종가·시가·고가·저가·등락률 중 하나
    if (msg := _holiday_msg(date)):
        return msg
    info: TickerInfo = to_ticker(raw_name, with_name = True)
    ticker, off_name = info.ticker, info.name

    # 가격 데이터가 없는 주식(거래정지) → 0 처리
    if field_ko == "등락률":
        try:
            p_today = get_price_on_date(ticker, date, "Close")
            _, p_prev = _find_prev_close(ticker, date)
            if not p_prev or not p_today:
                return f"{date}에 {off_name}의 등락률 데이터를 찾을 수 없습니다"
            pct = (p_today - p_prev) / p_prev * 100
            value = f"{pct:+.2f}%"
            return f"{date}에 {off_name}의 등락률은 {value} 입니다."
        except Exception:
            return f"{date}에 {off_name}의 등락률 데이터를 찾을 수 없습니다"

    field = FIELD_MAP[field_ko]
    try:
        price = get_price_on_date(ticker, date, field)
        vol   = get_price_on_date(ticker, date, "Volume")
    except Exception:
        price, vol = None, None
    if price in (None, 0):
        return f"{date}에 {off_name}의 {field_ko} 데이터를 찾을 수 없습니다"
    if vol in (None, 0) or price in (None, 0):
        return f"{date}에 {off_name}은(는) 거래되지 않았습니다."
    value = f"{price:,.0f}원"
    return f"{date}에 {off_name}의 {field_ko}은(는) {value} 입니다."

def _answer_index(date: str, market: str, ticker: str) -> str:
    msg = _holiday_msg(date)
    if msg:
        return msg
    try:
        val = get_price_on_date(ticker, date, "Close")
    except Exception:
        val = None
    if not val:
        return f"{date}에 {market} 지수 데이터가 없습니다."
    return f"{date}에 {market} 지수는 {val:,.2f} 입니다."

def _answer_kospi_index(date: str)  -> str: return _answer_index(date, "KOSPI",  "^KS11")
def _answer_kosdaq_index(date: str) -> str: return _answer_index(date, "KOSDAQ", "^KQ11")

# 거래대금
def _answer_total_trading_value(date: str, market: str | None) -> str:
    if msg := _holiday_msg(date):
        return msg
    tickers = _universe(market)
    market_txt = market if market else "전체 시장"
    df = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df.empty:
        return f"{date}에 {market_txt} 거래대금 데이터가 없습니다"
    total = 0
    for t in GLOBAL_TICKERS:
        try:
            sub = _slice_single(df, t)
            price, vol = sub["Close"].iloc[0], sub["Volume"].iloc[0]
            if not pd.isna(price) and not pd.isna(vol):
                total += price * vol
        except Exception:
            continue
    if not total:
        return f"{date}에 {market_txt} 거래대금 데이터가 없습니다"
    
    value = f"{int(total):,}원"
    return f"{date}에 {market_txt} 거래대금은 {value} 입니다."

# ─────────────────────────── 2. 상승/하락/거래 종목 수 ───────────────────────────
def _updown_count(date: str, market: str|None, direction: str) -> int | None:
    """direction ∈ {'상승','하락'}"""
    tickers = _universe(market)
    df = _download(tuple(tickers), start=date, end=date, interval="1d") # 당일만
    if df.empty:
        return None

    inc = 0
    for t in tickers:
        try:
            today_c =   _slice_single(df, t)["Close"].iloc[0]
            vol =       _slice_single(df, t)["Volume"].iloc[0]
            if pd.isna(today_c) or pd.isna(vol) or vol == 0:
                continue
            _, prev_c = _find_prev_close(t, date)
            if not prev_c:
                continue
            if (today_c > prev_c and direction == "상승") or (today_c < prev_c and direction == "하락"):
                inc += 1
        except KeyError:
            continue
    return inc

def _traded_count(date: str, market: str) -> str:
    tickers = _universe(market)
    df = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df.empty:
        return None
    cnt = 0
    for t in tickers:
        try:
            sub = _slice_single(df, t)          # df에 없으면 KeyError
        except KeyError:
            continue                            # 데이터 미존재 → 패스

        if "Volume" not in sub.columns:
            continue
        v = sub["Volume"].iloc[0]
        if pd.isna(v) or v == 0:
            continue
        cnt += 1

    return cnt

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
    df_today = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df_today.empty:
        return f"{date} 데이터 없음"

    pct: Dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df_today, t)
            today_c = sub["Close"].iloc[0]
            vol     = sub["Volume"].iloc[0]
            if pd.isna(today_c) or pd.isna(vol) or vol == 0:
                continue
            _, prev_c = _find_prev_close(t, date)
            if prev_c is None or pd.isna(prev_c) or prev_c == 0:
                continue
            change = (today_c - prev_c) / prev_c * 100
            if pd.isna(change) or math.isinf(change):
                continue
            pct[t] = change
        except Exception:
            continue
    if not pct:
        return f"{date} 데이터 없음"

    rank = sorted(pct.items(), key=lambda x: x[1], reverse=(direction == "상승률"))[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in rank)

def _answer_top_price(date: str, market: str|None, n: int) -> str:
    tickers = _universe(market)
    df = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"
    closes: dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df, t)        # 티커 없으면 KeyError
        except KeyError:
            continue                           # 데이터 미존재 → 패스

        if sub.empty or _is_zero_volume(sub):
            continue
        close_val = sub["Close"].iloc[0] if "Close" in sub.columns else None
        if pd.isna(close_val):
            continue
        closes[t] = float(close_val)
    if not closes:
        return f"{date} 데이터 없음"
    top = sorted(closes.items(), key=lambda x: x[1], reverse=True)[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in top)




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
            return _answer_total_trading_value(p["date"],p.get("market"))
        return f"지원하지 않는 지표입니다."

    # 2) 종목 수
    if task in ("상승종목수", "하락종목수", "거래종목수"):
        msg = _holiday_msg(p["date"])
        if msg:
            return msg
        market = p.get("market")
        market_txt = f"{market}에서 " if market else ""
        if task == "상승종목수":
            cnt = _updown_count(p["date"], market, "상승")
            return f"{p['date']}에 {market_txt}상승한 종목은 {cnt:,}개 입니다." if cnt is not None else f"{p['date']}의 데이터가 없습니다."
        if task == "하락종목수":
            cnt = _updown_count(p["date"], market, "하락")
            return f"{p['date']}에 {market_txt}하락한 종목은 {cnt:,}개 입니다." if cnt is not None else f"{p['date']}의 데이터가 없습니다."
        if task == "거래종목수":
            cnt = _traded_count(p["date"], market)
            return f"{p['date']}에 {market_txt}거래된 종목은 {cnt:,}개 입니다." if cnt is not None else f"{p['date']}의 데이터가 없습니다."

    # 3) 시장순위
    if task == "시장순위":
        msg = _holiday_msg(p["date"])
        if msg:
            return msg
        metric = p["metrics"][0]            # 거래량·상승률·하락률·가격
        n      = p.get("rank_n") or 1
        market = p.get("market")
        market_txt = f"{market}에서 " if market else ""

        if metric == "거래량":
            names = _answer_volume_top(p["date"], market, n)
        elif metric in ("상승률", "하락률"):
            names = _answer_top_mover(p["date"], market, metric, n)
        elif metric == "가격":
            names = _answer_top_price(p["date"], market, n)
        else:
            return f"지원하지 않는 지표입니다."

        if "데이터 없음" in names:
            return f"{p['date']}에 데이터가 없습니다."
        if n == 1:
            return f"{p['date']}에 {market_txt}{metric}이(가) 가장 높은 종목은 {names} 입니다."
        return (
            f"{p['date']}에 {market_txt}{metric} 상위 {n}개 종목은 다음과 같습니다.\n"
            f"{names}"
        )

    return "질문을 이해하지 못했습니다."