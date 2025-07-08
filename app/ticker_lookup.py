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
_STATIC_MAP.update({           # 필요 시 수동 보강
    "마이크로소프트": "MSFT",
    "애플": "AAPL",
})

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
    1️⃣ 그대로 매핑 시도
    2️⃣ 실패하면 조사 1글자 제거 후 재시도
    3️⃣ 둘 다 실패 → ValueError
    """
    identifier = identifier.strip()

    # 한글 포함 여부 판단
    if re.search(r"[가-힣]", identifier):
        # (1) 원본 그대로
        ticker = _lookup_korean(identifier)
        if ticker:
            return ticker

        # (2) 조사 제거 버전
        stripped = _strip_particle(identifier)
        if stripped != identifier:
            ticker = _lookup_korean(stripped)
            if ticker:
                return ticker

        # (3) 최종 실패
        raise ValueError(f"'{identifier}' → 티커 매핑 실패")

    # 알파벳/숫자 혼합 → 그대로
    return identifier.upper()