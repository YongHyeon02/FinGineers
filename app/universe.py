# app/universe.py
from __future__ import annotations

import pandas as pd
from functools import lru_cache
from typing import Dict, List

from config import KOSPI_CSV, KOSDAQ_CSV, ALIAS_CSV

@lru_cache(maxsize=1)
def _load_csv(path) -> Dict[str, str]:
    """
    CSV → {종목명: '티커.확장자'} 사전  
    """
    df = pd.read_csv(path, sep=",", encoding="utf-8-sig")  # 헤더: 종목코드, 종목명
    mapping: Dict[str, str] = {}

    for _, row in df.iterrows():
        raw_ticker: str = str(row["종목코드"]).strip().upper()  # 예: '069730.KS'
        name: str = str(row["종목명"]).strip()

        # 종목명이 중복될 경우 뒤에 (티커 앞 6자리)로 구분
        if name in mapping:
            code_part = raw_ticker.split(".")[0]  # '069730'
            name = f"{name}({code_part})"

        mapping[name] = raw_ticker

    return mapping

@lru_cache(maxsize=1)
def _load_alias_csv(path=ALIAS_CSV) -> Dict[str, str]:
    """alias_tickers.csv → {별칭: '티커.확장자'}"""
    if not path.exists():
        return {}
    df = pd.read_csv(path, encoding="utf-8-sig")
    return {
        str(a).strip(): str(t).strip().upper()
        for a, t in zip(df["alias"], df["ticker"])
        if a and t
    }

# ----------- 공개 API -----------
KOSPI_MAP:  Dict[str, str] = _load_csv(KOSPI_CSV)
KOSDAQ_MAP: Dict[str, str] = _load_csv(KOSDAQ_CSV)

KOSPI_TICKERS:  List[str] = list(KOSPI_MAP.values())
KOSDAQ_TICKERS: List[str] = list(KOSDAQ_MAP.values())

GLOBAL_TICKERS: List[str] = KOSPI_TICKERS + KOSDAQ_TICKERS
NAME_BY_TICKER: Dict[str, str] = {v: k for k, v in {**KOSPI_MAP, **KOSDAQ_MAP}.items()}

INDEX_TICKERS = [
    "^KS11",   # KOSPI Composite
    "^KS200",  # KOSPI 200
    "^KQ11",   # KOSDAQ Composite
    "^KQ100",  # KOSDAQ 100
]

ALL_TICKERS = GLOBAL_TICKERS + INDEX_TICKERS