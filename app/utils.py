# app/utils.py
import datetime as dt
import pandas as pd
from pandas.tseries.offsets import BDay

def _is_zero_volume(sub_df: pd.DataFrame, idx: int = -1) -> bool:
    """
    주어진 sub‑dataframe(단일 티커)을 받아
    원하는 행(idx)의 Volume 이 0·NaN 이면 True.
    """
    return (
        "Volume" not in sub_df.columns
        or pd.isna(sub_df["Volume"].iloc[idx])
        or sub_df["Volume"].iloc[idx] == 0
    )


def trading_day_offset(ref: dt.date, n: int) -> dt.date:
    """영업일 기준 n 일 오프셋"""
    return (pd.Timestamp(ref) + BDay(n)).date()

def fmt_price(val: float, is_pct: bool = False) -> str:
    return f"{val:.2f}%" if is_pct else f"{val:,.0f}원"