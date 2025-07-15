from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yfinance as yf

from app.universe import KOSPI_MAP, KOSDAQ_MAP

# 1️⃣ 메모리 사전 (CSV + 수동 보강)
_STATIC_MAP: Dict[str, str] = {}
_STATIC_MAP.update(KOSPI_MAP)
_STATIC_MAP.update(KOSDAQ_MAP)
# _STATIC_MAP.update({           # 필요 시 수동 보강
#     "마이크로소프트": "MSFT",
#     "애플": "AAPL",
# })

# --------------- 2) 헬퍼 ---------------
@lru_cache(maxsize=512)
def _fallback_lookup(name: str) -> Optional[str]:
    """yfinance.Lookup / Search 로 티커 추정 (주식만 반환)"""
    try:
        res = yf.Lookup(name)
        for item in res.stock:  # type: ignore[attr-defined]
            return item.symbol
    except Exception:
        pass

    try:
        res = yf.Search(name, max_results=5)
        for q in res.quotes:
            if q.quoteType == "EQUITY":
                return q.symbol
    except Exception:
        pass
    return None

_PARTICLE_REGEX = re.compile(r"[의은는이가를]\s*$")

def _strip_particle(text: str) -> str:
    """문자열 끝의 조사 하나만 제거 (없으면 원본 그대로 반환)"""
    return _PARTICLE_REGEX.sub("", text)


def _lookup_korean(name: str) -> Optional[str]:
    """KOSPI/KOSDAQ 사전 + yfinance Lookup 검색"""
    return (
        KOSPI_MAP.get(name)
        or KOSDAQ_MAP.get(name)
        or _fallback_lookup(name)
    )

def to_ticker(identifier: str) -> str:
    """
    1) _STATIC_MAP (KOSPI/KOSDAQ CSV + 수동 보강)에서 먼저 찾기
    2) 없으면 yfinance Lookup/Search 시도
    3) 그래도 없으면 그대로 대문자 반환
    """
    identifier = identifier.strip()

    # 1️⃣ 조사 제거 1차·2차 버전 모두 사전 검색
    for name_try in (identifier, _strip_particle(identifier)):
        ticker = _STATIC_MAP.get(name_try)
        if ticker:
            return ticker

    # 2️⃣ yfinance Lookup/Search (한글·영문 모두 시도)
    fallback = _fallback_lookup(identifier)
    if fallback:
        return fallback

    # 3️⃣ 마지막으로 그대로 사용
    return identifier.upper()