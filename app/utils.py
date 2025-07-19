# app/utils.py
import datetime as dt
import pandas as pd
from typing import List, Dict, Tuple
from pandas import isna
from pandas.tseries.offsets import BDay
import pandas_market_calendars as mcal
from app.universe import (
    KOSPI_TICKERS, KOSDAQ_TICKERS, GLOBAL_TICKERS,
    NAME_BY_TICKER, KOSPI_MAP, KOSDAQ_MAP,
)
from app.data_fetcher import get_price_on_date

_LOOKBACK_DAYS = 7   

def _is_zero_volume(sub_df: pd.DataFrame, idx: int = -1) -> bool:
    # 요청한 행이 존재하지 않으면 “데이터 없음”으로 간주
    if idx >= len(sub_df) or idx < -len(sub_df):
        return True
    return (
        "Volume" not in sub_df.columns
        or pd.isna(sub_df["Volume"].iloc[idx])
        or sub_df["Volume"].iloc[idx] == 0
    )

def _universe(market: str|None) -> List[str]:
    return (
        KOSPI_TICKERS  if market == "KOSPI"  else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )

def _find_prev_close(
    ticker: str, date: str, *, max_back: int = _LOOKBACK_DAYS
) -> Tuple[str, float] | Tuple[None, None]:
    """
    date 직전 영업일부터 최대 max_back 일 전까지
    • 거래대금이 0이 아니고 • Close 값이 존재하는 날을 찾아
      (그날의 날짜, Close 가격) 을 반환.
    못 찾으면 (None, None)
    """
    cur = _prev_bday(date)
    for _ in range(max_back):
        try:
            close = get_price_on_date(ticker, cur, "Close")
            vol   = get_price_on_date(ticker, cur, "Volume")
            if (
                close is not None and not isna(close) and close != 0
                and vol   is not None and not isna(vol)   and vol   != 0
            ):
                return cur, close
        except Exception:
            pass
        cur = _prev_bday(cur)   # 하루 더 뒤로
    return None, None




# task4_ambiguous.py 에서 사용했는데 잘못된 함수임. 사용하면 안됨.
def trading_day_offset(ref: dt.date, n: int) -> dt.date:
    """영업일 기준 n 일 오프셋"""
    return (pd.Timestamp(ref) + BDay(n)).date()

def fmt_price(val: float, is_pct: bool = False) -> str:
    return f"{val:.2f}%" if is_pct else f"{val:,.0f}원"
# ────────────────────────────────────────────────




# ── 휴장일 캘린더 ────────────────────────────────────────────────
_XKRX_CAL = mcal.get_calendar("XKRX")     # 한국거래소(KRX) 영업일 달력
_BDAY = pd.tseries.offsets.CustomBusinessDay(calendar=_XKRX_CAL)

# 휴장일 메세지
def _holiday_msg(date: str) -> str | None:
    """
    * 한국거래소 영업일이 아니면 → "YYYY-MM-DD는 휴장일입니다. 데이터가 없습니다."
    * 영업일이면 None
    """
    ts = pd.Timestamp(date)
    if _XKRX_CAL.schedule(start_date=ts, end_date=ts).empty:
        return f"{date}는 휴장일입니다. 데이터가 없습니다."
    return None

# 이전 영업일 계산
def _prev_bday(date: str, lookback_days: int = 20) -> str:
    ts = pd.Timestamp(date)
    start = ts - pd.Timedelta(days=lookback_days)
    sched = _XKRX_CAL.schedule(start_date=start, end_date=ts)
    days = sched.index
    if days.empty:
        raise ValueError(f"No trading days found in window up to {date}")
    if ts in days:
        if len(days) < 2:
            raise ValueError(f"Not enough prior trading days before {date}")
        prev = days[-2]
    else:
        prev = days[-1]
    return prev.strftime("%Y-%m-%d")

# 다음날 계산
def _next_day(date: str) -> str:
    return (pd.Timestamp(date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")