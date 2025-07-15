# app/data_fetcher.py
"""
yfinance 래퍼 – Task 1 전용 최소 함수
"""
from __future__ import annotations

import time
import datetime as dt
import warnings
from functools import lru_cache
from typing import List, Tuple

import pandas as pd
import yfinance as yf
from yfinance.base import YFRateLimitError

warnings.filterwarnings("ignore", category=UserWarning)  # empty slice 등


# ──────────────────────────────
@lru_cache(maxsize=2_048)
def _download(
    tickers: Tuple[str, ...], start: str, end: str, interval: str = "1d"
) -> pd.DataFrame:
    """yfinance.download 래핑 + LRU 캐시"""
    return yf.download(
        list(tickers),
        start=start,
        end=end,
        interval=interval,
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=False,      # ← 경고 근본 해결
    )

def _slice_single(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """
    멀티인덱스(DataFrame)에서 단일 티커 레벨만 슬라이스
    (단일 티커여도 group_by='ticker' 때문에 2-level 컬럼)
    """
    if isinstance(df.columns, pd.MultiIndex):
        return df[ticker]
    return df  # 이미 1-level (예외 케이스 대비)

def _fetch_one(ticker: str, start: str, end: str, field: str) -> float | None:
    """yf.download() 단일 호출 → 값 없으면 None"""
    df = yf.download(
        tickers=ticker,
        start=start,
        end=end,
        interval="1d",
        progress=False,
        group_by=None,      # 단일 티커면 굳이 multi-index 안 써도 됨
        threads=False,
        auto_adjust=False,
    )
    if df.empty or field not in df.columns:
        return None
    return float(df.iloc[0][field])


def get_price_on_date(ticker: str, date: str, field: str = "Close") -> float:
    """특정 날짜 가격을 최대 6회(3+3) 재시도하며 가져온다."""
    target = dt.datetime.strptime(date, "%Y-%m-%d")
    start  = date
    end    = (target + dt.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # ① download() 3회 백오프 재시도
    for i in range(3):            # 0,1,2
        try:
            price = _fetch_one(ticker, start, end, field)
            if price is not None:
                return price
            break                 # 컬럼 없으면 굳이 반복 안 함
        except YFRateLimitError:
            time.sleep(1 + i)     # 1s, 2s, 3s

    # ② Ticker.history() 3회 백오프 재시도
    for i in range(3):            # 0,1,2
        try:
            hist = yf.Ticker(ticker).history(
                start=start, end=end, interval="1d", auto_adjust=False
            )
            if not hist.empty and field in hist.columns:
                return float(hist[field].iloc[0])
            break
        except YFRateLimitError:
            time.sleep(2 + i * 2)  # 2s, 4s, 6s

    raise ValueError(f"{date} {ticker} {field} 데이터 없음")

def get_volume_top(
    tickers: List[str], date: str, top_n: int = 10
) -> pd.Series:
    """
    특정 날짜 거래량 상위 N개 반환
    NaN·0 거래량 종목은 자동 제외
    """
    target = dt.datetime.strptime(date, "%Y-%m-%d")
    df = _download(
        tuple(tickers),
        start=date,
        end=(target + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
    )
    if df.empty:
        raise ValueError(f"{date} 거래량 데이터 없음")

    volumes = {}
    for t in df.columns.get_level_values(0).unique():
        # 해당 티커 열이 없거나 비어 있으면 continue
        try:
            sub = _slice_single(df, t)
        except KeyError:
            continue
        if sub.empty or "Volume" not in sub.columns:
            continue

        vol_val = sub["Volume"].iloc[0]
        if pd.isna(vol_val) or vol_val == 0:
            continue  # NaN 또는 0 거래량 스킵

        volumes[t] = int(vol_val)

    if not volumes:
        raise ValueError(f"{date} 유효한 거래량 데이터가 없습니다.")

    return (
        pd.Series(volumes)
        .sort_values(ascending=False)
        .head(top_n)
    )