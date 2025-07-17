# -------------------------------------------------------
# app/indicators.py
"""
Technical indicator helpers
"""
from __future__ import annotations
import pandas as pd

def pct_change(close: pd.DataFrame) -> pd.Series:
    return (close.iloc[-1] / close.iloc[0] - 1) * 100

def max_drawdown(high: pd.DataFrame, low: pd.DataFrame) -> pd.Series:
    peak = high.cummax()
    draw = (low - peak) / peak * 100   # 음수 값
    return draw.min()
