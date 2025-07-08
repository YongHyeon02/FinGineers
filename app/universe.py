# app/universe.py
from __future__ import annotations

import pandas as pd
from functools import lru_cache
from typing import Dict, List

from config import KOSPI_CSV, KOSDAQ_CSV


@lru_cache(maxsize=1)
def _load_csv(path) -> Dict[str, str]:
    """
    CSV → {종목명: '티커.확장자'} 사전
    (확장자는 KOSPI→.KS, KOSDAQ→.KQ 로 자동 부착)
    """
    df = pd.read_csv(path, sep=",", encoding="utf-8-sig")      # 헤더: 종목코드, 종목명
    ext = ".KS" if "KOSPI" in path.name.upper() else ".KQ"
    mapping: Dict[str, str] = {}

    for _, row in df.iterrows():
        code_raw = str(row["종목코드"]).strip()           # 예) '5930', '0037T0'
        code = code_raw.zfill(6) if code_raw.isdigit() else code_raw.upper()
        name = str(row["종목명"]).strip()

        # 중복 종목명 발생 시 뒤에 (코드) 붙여 구분
        if name in mapping:
            name = f"{name}({code})"
        mapping[name] = f"{code}{ext}"

    return mapping


# ----------- 공개 API -----------
KOSPI_MAP: Dict[str, str]  = _load_csv(KOSPI_CSV)
KOSDAQ_MAP: Dict[str, str] = _load_csv(KOSDAQ_CSV)

KOSPI_TICKERS:  List[str] = list(KOSPI_MAP.values())
KOSDAQ_TICKERS: List[str] = list(KOSDAQ_MAP.values())

# 전체 유니버스 (≒ Task1 거래량 Top N 등에서 사용)
GLOBAL_TICKERS: List[str] = KOSPI_TICKERS + KOSDAQ_TICKERS
