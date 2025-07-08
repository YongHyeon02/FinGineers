# app/data_fetcher.py
"""
yfinance 래퍼 – Task 1 전용 최소 함수
"""
from __future__ import annotations

import datetime as dt
import warnings
from functools import lru_cache
from typing import List, Tuple

import pandas as pd
import yfinance as yf

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


def get_price_on_date(ticker: str, date: str, field: str = "Close") -> float:
    """
    지정 날짜 가격 반환 (시가·종가·고가·저가)
    """
    target = dt.datetime.strptime(date, "%Y-%m-%d")
    df = _download(
        (ticker,),
        start=date,
        end=(target + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
    )
    if df.empty:
        raise ValueError(f"{date} 데이터 없음")

    one = _slice_single(df, ticker)
    if field not in one.columns:
        raise KeyError(f"필드 '{field}' 가 DataFrame에 없습니다. 컬럼 = {one.columns.tolist()}")

    return float(one[field].iloc[0])


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