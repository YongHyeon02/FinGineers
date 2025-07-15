# app/data_fetcher.py
"""
yfinance + 로컬 캐시 래퍼 (Task 1 전용)

동작 정책
────────
1. **프리패치 윈도우**  
   2025-06-01 ≤ date ≤ 2025-07-14
   * 사전에 `prefetch_yf.py`로 캐싱해 둔 **로컬 데이터만** 활용.
   * 캐시에 없는 종목/날짜는 *없다고 간주*하고 **yfinance 호출을 하지 않는다**.
2. **그 외 구간**  
   * 기존과 동일하게 `yfinance.download()` → 캐시에 저장 → 반환.
3. **API 변경**  
   * 다중 종목·시장 통계용 `get_volume_top()`은 프리패치 구간에서 *캐시에 존재하는 종목*만 집계.
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

# ──────────────────────────────────────────────────────────
#  캐시 유틸 (app/yf_cache.py)
# ──────────────────────────────────────────────────────────
from app.yf_cache import (
    load as _load_cache,            # (ticker, start, end) → DataFrame | None
    save_or_append as _save_cache,  # (ticker, df) → None
)

warnings.filterwarnings("ignore", category=UserWarning)   # empty slice 등

# ──────────────────────────────────────────────────────────
#  1. 프리패치 윈도우 판정
# ──────────────────────────────────────────────────────────
_PREFETCH_START = dt.date(2025, 6, 1)
_PREFETCH_END   = dt.date(2025, 7, 14)

def _within_prefetch_window(start: str, end: str) -> bool:
    s = dt.date.fromisoformat(start)
    e = dt.date.fromisoformat(end)
    return _PREFETCH_START <= s and e <= _PREFETCH_END

# ──────────────────────────────────────────────────────────
#  2. 헬퍼
# ──────────────────────────────────────────────────────────

def _slice_single(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """멀티인덱스 DataFrame에서 단일 티커 레벨만 추출"""
    if isinstance(df.columns, pd.MultiIndex):
        return df[ticker]
    return df  # 1-level 컬럼

# ──────────────────────────────────────────────────────────
#  3. 다운로드 래퍼 (LRU)
# ──────────────────────────────────────────────────────────
@lru_cache(maxsize=2_048)
def _download(
    tickers: Tuple[str, ...], start: str, end: str, interval: str = "1d"
) -> pd.DataFrame:
    """캐시 우선 다운로드.

    • 프리패치 구간 → *캐시만* 사용 (miss → drop).  
      반환 DF 는 yfinance 형태와 동일하게 2-level 컬럼(MultiIndex)로 통일.
    • 그밖의 기간 → yfinance 호출 후 캐시에 저장.
    """
    tickers = tuple(tickers)

    # ── 프리패치 구간 ─────────────────────────────────────────
    if _within_prefetch_window(start, end):
        frames: list[pd.DataFrame] = []
        for t in tickers:
            cdf = _load_cache(t, start, end)
            if cdf is None or cdf.empty:
                continue  # 캐시 미존재 ⇒ 건너뜀
            cdf = cdf.copy()
            # 1-level → 2-level(MultiIndex) 컬럼 변환
            cdf.columns = pd.MultiIndex.from_product([[t], cdf.columns])
            frames.append(cdf)
        if frames:
            return pd.concat(frames, axis=1)
        return pd.DataFrame()  # 모두 미존재 → 빈 DF

    # ── 일반 구간(yfinance) ───────────────────────────────────
    df = yf.download(
        list(tickers),
        start=start,
        end=end,
        interval=interval,
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=False,
    )

    # 캐시 저장
    for t in tickers:
        try:
            sub = _slice_single(df, t)
            if not sub.empty:
                _save_cache(t, sub)
        except KeyError:
            pass  # yfinance에 데이터 없을 때
    return df

# ──────────────────────────────────────────────────────────
#  4. 단일 값 조회
# ──────────────────────────────────────────────────────────

def _fetch_one(ticker: str, start: str, end: str, field: str) -> float | None:
    """_download() 기반 단일 값 추출"""
    if _within_prefetch_window(start, end):
        cdf = _load_cache(ticker, start, end)
        if cdf is None or cdf.empty or field not in cdf.columns:
            return None
        return float(cdf[field].iloc[0])

    # 윈도우 밖 → _download 호출
    df = _download((ticker,), start, end, interval="1d")
    if df.empty:
        return None
    sub = _slice_single(df, ticker)
    if sub.empty or field not in sub.columns:
        return None
    return float(sub.iloc[0][field])

# ──────────────────────────────────────────────────────────
#  5. Public API
# ──────────────────────────────────────────────────────────

def get_price_on_date(ticker: str, date: str, field: str = "Close") -> float:
    target = dt.datetime.strptime(date, "%Y-%m-%d")
    start = date
    end   = (target + dt.timedelta(days=1)).strftime("%Y-%m-%d")

    # (1) _fetch_one 3회 재시도
    for i in range(3):
        try:
            price = _fetch_one(ticker, start, end, field)
            if price is not None:
                return price
            break
        except YFRateLimitError:
            time.sleep(1 + i)

    # (2) history()는 프리패치 구간에선 호출하지 않음
    if not _within_prefetch_window(start, end):
        for i in range(3):
            try:
                hist = yf.Ticker(ticker).history(
                    start=start, end=end, interval="1d", auto_adjust=False
                )
                if not hist.empty and field in hist.columns:
                    return float(hist[field].iloc[0])
                break
            except YFRateLimitError:
                time.sleep(2 + i * 2)

    raise ValueError(f"{date} {ticker} {field} 데이터 없음")


def get_volume_top(
    tickers: List[str], date: str, top_n: int = 10
) -> pd.Series:
    """특정 날짜 거래량 상위 N개 (NaN·0 제외)"""
    target = dt.datetime.strptime(date, "%Y-%m-%d")
    df = _download(
        tuple(tickers),
        start=date,
        end=(target + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
    )

    if df.empty:
        raise ValueError(f"{date} 거래량 데이터 없음")

    # df.columns 가 2-level이라고 가정
    volumes: dict[str, int] = {}
    for t in df.columns.get_level_values(0).unique():
        try:
            sub = _slice_single(df, t)
        except KeyError:
            continue
        if sub.empty or "Volume" not in sub.columns:
            continue
        vol_val = sub["Volume"].iloc[0]
        if pd.isna(vol_val) or vol_val == 0:
            continue
        volumes[t] = int(vol_val)

    if not volumes:
        raise ValueError(f"{date} 유효한 거래량 데이터가 없습니다.")

    return (
        pd.Series(volumes)
        .sort_values(ascending=False)
        .head(top_n)
    )
