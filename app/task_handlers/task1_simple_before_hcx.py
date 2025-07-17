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

# ──────────────────────────────
# 1. 가격 & 등락률 답변
# ──────────────────────────────

def _extract_price_components(q: str):
    m_date  = re.search(r"(\d{4}-\d{2}-\d{2})", q)
    m_field = re.search(r"(종가|시가|고가|저가|등락률)", q)
    if not (m_date and m_field):
        raise ValueError("날짜·필드 파싱 실패")

    date, field_ko = m_date.group(1), m_field.group(1)
    raw  = _PARTICLE_CUT.sub("", _MARKET_PREFIX.sub("", q[: m_date.start()]).strip())
    name = raw.split()[-1]
    return name, date, field_ko


def _answer_price(q: str) -> str:
    name, date, field_ko = _extract_price_components(q)

    wk = _weekend_msg(date, f"({field_ko} 데이터 없음)")
    if wk:
        return wk
    
    field = FIELD_MAP[field_ko]

    # ▶ 1차: yfinance 직통
    ticker = to_ticker(name)
    try:
        price = get_price_on_date(ticker, date, field)
    except Exception:
        price = None
    
    # if price is None:
    #     return f"해당 날짜 {field_ko} 데이터 없음"
        
    vol = get_price_on_date(ticker, date, "Volume")
    if vol in (None, 0) or (isinstance(vol, float) and math.isnan(vol)):
        # 시가/고가/저가/종가 → 0원, 등락률 → 0%
        return "0원" if field_ko != "등락률" else "0%"
    
    if field_ko == "등락률":
        prev     = _prev_bday(date)
        today_c  = get_price_on_date(ticker, date, "Close")
        prev_c   = get_price_on_date(ticker, prev, "Close")
        today_vol = get_price_on_date(ticker, date, "Volume")
        prev_vol  = get_price_on_date(ticker, prev, "Volume")

        if (
            today_c in (None, 0) or
            prev_c in (None, 0) or
            (isinstance(prev_c, float) and math.isnan(prev_c))
        ):
            return f"{date} 등락률 데이터 없음"
        if any(v in (None, 0) or (isinstance(v, float) and math.isnan(v)) for v in (today_vol, prev_vol)):
            return f"{date} 등락률 데이터 없음"

        pct = (today_c - prev_c) / prev_c * 100.0
        return f"{pct:+.2f}%"

    unit = "원" if ticker.endswith((".KS", ".KQ")) else "USD"
    return f"{price:,.0f}{unit}"

# ──────────────────────────────
# 2. 거래량 TOP N
# ──────────────────────────────

def _answer_volume(m: re.Match) -> str:
    date   = m.group(1)                                    # 필수 ① 날짜
    market = m.group(2)                                    # 필수 ② 시장(KOSPI|KOSDAQ|None)
    n_str  = m.group(3) if m.lastindex and m.lastindex >= 3 else None  # 선택 ③ N
    n = int(n_str) if n_str else 1

    wk = _weekend_msg(date, "(거래량 데이터 없음)")
    if wk:
        return wk
    
    uni = (
        KOSPI_TICKERS if market == "KOSPI" else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )

    top = get_volume_top(uni, date, n)
    if n == 1:
        t, vol = next(top.items())
        return f"{TICK2NAME.get(t, t)} ({int(vol):,}주)"
    names = [TICK2NAME.get(t, t) for t in top.index[:n]]
    return ", ".join(names)
# ──────────────────────────────
# 3. 시장 통계 / 순위 (yfinance only)
# ──────────────────────────────

_CHUNK = 250  # yfinance URL 길이 / 속도 균형 기준


def _download_two_days(date: str, tickers: List[str]) -> pd.DataFrame:
    prev = _prev_bday(date)
    nxt  = _next_day(date)
    return _download(tuple(tickers), start=prev, end=nxt, interval="1d")


def _updown_count_yf(date: str, market: str | None, direction: str) -> str:
    tickers = (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )

    df = _download_two_days(date, tickers)
    if df.empty:
        return f"{date} 데이터 없음"

    inc = 0
    for t in df.columns.get_level_values(0).unique():
        try:
            sub = _slice_single(df, t)
            if _is_zero_volume(sub, idx=1):
                continue
        except KeyError:
            continue
        if len(sub) < 2 or "Close" not in sub.columns:
            continue
        prev_c, today_c = sub["Close"].iloc[0], sub["Close"].iloc[1]
        if pd.isna(prev_c) or pd.isna(today_c):
            continue
        if (today_c > prev_c and direction == "상승") or (
            today_c < prev_c and direction == "하락"):
            inc += 1
    return f"{inc:,}개" if inc else f"{date} 데이터 없음"


def _answer_updown_count(m: re.Match) -> str:
    date, market, direction = m.groups()
    wk = _weekend_msg(date, "(데이터 없음)")
    if wk:
        return wk
    return _updown_count_yf(date, market, direction)


# — Top mover (상승률·하락률 TOP N) —

def _answer_top_mover(m: re.Match) -> str:
    date, market, direction, n = m.groups(); n = int(n)
    wk = _weekend_msg(date, "(데이터 없음)")
    if wk: return wk
    
    tickers = (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )
    start = (pd.Timestamp(date) - pd.Timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    nxt   = _next_day(date)    # yfinance end 파라미터는 exclusive
    df = _download(tuple(tickers), start=start, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"

    pct_change: Dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if date not in sub.index:                  # 당일 데이터 없으면 skip
                continue
            if _is_zero_volume(sub):                   # 당일 거래량 0/NaN skip
                continue

            today_c = sub.loc[date, "Close"]
            if pd.isna(today_c) or today_c == 0:
                continue

            # ▼ “오늘 이전” 구간에서 마지막으로 유효한 종가 찾기
            prev_series = sub.loc[:date, "Close"].iloc[:-1].dropna()
            if prev_series.empty:
                continue
            prev_c = prev_series.iloc[-1]
            if prev_c == 0:
                continue

            pct_change[t] = (today_c - prev_c) / prev_c * 100.0
        except Exception:
            continue

    if not pct_change:
        return f"{date} 데이터 없음"

    sorted_tk = sorted(
        pct_change.items(), key=lambda x: x[1], reverse=(direction == "상승률")
    )[:n]
    names = [TICK2NAME.get(t, t) for t, _ in sorted_tk]
    return ", ".join(names)


# — Top price (가장 비싼 종목 TOP N) —

def _answer_top_price(m: re.Match) -> str:
    date   = m.group(1)              # 필수 ①
    market = m.group(2)              # 필수 ②
    n_str  = m.group(3)              # 선택 ③
    wk = _weekend_msg(date, "(데이터 없음)")
    if wk:
        return wk
    n = int(n_str) if n_str else 1
    
    tickers = (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )
    nxt = _next_day(date)
    df = _download(tuple(tickers), start=date, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"

    closes: Dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if _is_zero_volume(sub):
                continue
            if sub.empty or "Close" not in sub.columns:
                continue
            val = sub["Close"].iloc[0]
            if not pd.isna(val):
                closes[t] = val
        except KeyError:
            continue

    if not closes:
        return f"{date} 데이터 없음"

    top = sorted(closes.items(), key=lambda x: x[1], reverse=True)[:n]
    names = [TICK2NAME.get(t, t) for t, _ in top]
    return ", ".join(names)


# — KOSPI Index Close —

def _answer_kospi_index(m: re.Match) -> str:
    date = m.group(1)
    wk = _weekend_msg(date, "(데이터 없음)")
    if wk:
        return wk
    try:
        val = get_price_on_date("^KS11", date, "Close")
        return f"{val:,.2f}" if val is not None else f"{date} 데이터 없음"
    except Exception:
        return f"{date} 데이터 없음"
    
# — 전체 시장 거래대금 (합산) —

def _answer_trading_value(m: re.Match) -> str:
    date = m.group(1)
    wk = _weekend_msg(date, "(데이터 없음)")
    if wk:
        return wk
    
    tickers = GLOBAL_TICKERS
    nxt = _next_day(date)
    df = _download(tuple(tickers), start=date, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"

    total = 0
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if sub.empty or not {"Close", "Volume"}.issubset(sub.columns):
                continue
            price = sub["Close"].iloc[0]
            vol   = sub["Volume"].iloc[0]
            if pd.isna(price) or pd.isna(vol):
                continue
            total += price * vol
        except KeyError:
            continue

    if total == 0:
        return f"{date} 데이터 없음"
    return f"{int(total):,}원"

# ──────────────────────────────
# 패턴 & 핸들러 매핑
# ──────────────────────────────
_PATTERNS = [
    # 1) 가격·등락률 ── re.Match ➜ 질문 문자열로 전달
    (
        re.compile(r"(종가|시가|고가|저가|등락률)"),
        lambda m: _answer_price(m.string),
    ),

    # 2) 거래량 TOP N
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})\s*(?:에서)?\s*(KOSPI|KOSDAQ)?(?:\s*시장)?(?:에서)?"
            r".*?거래량.*?(?:상위|많[은이]?|TOP)?(?:\s*종목)?\s*(\d+)\s*개"
            r"(?:는?|은?|인가|입니까|요|냐)?",
            re.I,
        ),
        _answer_volume,
    ),
    # 2′) 숫자를 생략한 경우 ― 기본값 1
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})\s*(?:에서)?\s*(KOSPI|KOSDAQ)?(?:\s*시장)?(?:에서)?"
            r".*?거래량.*?(?:상위|많[은이]?|TOP)?(?:\s*종목)?"
            r"(?:는?|은?|인가|입니까|요|냐)?",
            re.I,
        ),
        _answer_volume,
    ),

    # 3) 상승·하락 종목 **수 / 몇 개**
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})(?:에|에서)?\s*"
            r"(KOSPI|KOSDAQ)?(?:\s*시장)?(?:에서)?\s*"
            r"(상승|하락)한\s*종목(?:은|는)?\s*"
            r"(?:수|몇\s*개)?"
            r"(?:\s*(?:는|은|인가|입니까|요|냐))?"
        ),
        _answer_updown_count,
    ),
    # 상승/하락 종목 수
    # (
    #     re.compile(
    #         r"(\d{4}-\d{2}-\d{2})[에에서]?\s*(KOSPI|KOSDAQ)?(?:\s*시장)?"
    #         r".*?(상승|하락)한\s*종목.*?몇\s*개",
    #     ),
    #     _answer_updown_count,
    # ),

    # 4) ‘거래된 종목 수’
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})\s*(KOSPI|KOSDAQ)\s*시장에\s*거래된\s*종목(?:은|는)?\s*수"
            r"(?:는?|는요|인가|입니까|요|냐)?",
        ),
        lambda m: _answer_traded_count_yf(m.group(1), m.group(2)),
    ),

    # 5) 상승률·하락률 TOP N
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})(?:\s*(?:에|에서))?\s*"          # 날짜 (+‘에서’ 선택)
            r"(KOSPI|KOSDAQ)\s*(?:시장)?\s*에서?\s*"        # KOSPI|KOSDAQ (+‘시장’·‘에서’ 선택)
            r"(상승률|하락률)\s*높은\s*종목\s*"              # 상승률·하락률 높은 종목
            r"(\d+)\s*개(?:는?|은?|인가|입니까|요|냐)?",      # N개
        ),
        _answer_top_mover,
    ),

    # 6) 최고가 TOP N
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})(?:\s*(?:에|에서))?\s*"          # 날짜
            r"(KOSPI|KOSDAQ)\s*(?:시장)?\s*에서?\s*"        # 시장
            r"가장\s*비싼\s*종목"                            # 가장 비싼 종목
            r"(?:\s*(\d+)\s*개)?(?:는?|은?|인가|입니까|요|냐)?",  # (N개) 선택
        ),
        _answer_top_price,
    ),

    # 7) KOSPI 지수
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})\s*KOSPI\s*지수(?:는?|은?|인가|입니까|요|냐)?"
        ),
        _answer_kospi_index,
    ),

    # 8) 전체 시장 거래대금
    (
        re.compile(
            r"(\d{4}-\d{2}-\d{2})\s*전체\s*시장\s*거래대금(?:은?|는?|인가|입니까|요|냐)?"
        ),
        _answer_trading_value,
    ),
]

# ————————————————————————————
# 메인 엔트리포인트
# ————————————————————————————

def _answer_traded_count_yf(date: str, market: str) -> str:
    tickers = (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )
    nxt = _next_day(date)
    df = _download(tuple(tickers), start=date, end=nxt, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"

    count = 0
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if sub.empty or "Volume" not in sub.columns:
                continue
            vol = sub["Volume"].iloc[0]
            if not pd.isna(vol) and vol > 0:
                count += 1
        except KeyError:
            continue
    return f"{count:,}개"


def handle(question: str) -> str:
    q = question.strip()
    for pattern, fn in _PATTERNS:
        m = pattern.search(q)
        if m:
            try:
                return fn(m) if m.groups() else fn(q)
            except Exception as e:
                return f"[ERROR] {e}"
    return "질문을 이해하지 못했습니다."