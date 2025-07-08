# app/task_handlers/task1_simple.py
"""
Task 1 – 단순 조회:
  1) 가격 질문 (종가·시가·고가·저가)
  2) 거래량 Top N 질문
"""
from __future__ import annotations

import re
from typing import List

import pandas as pd

from app.ticker_lookup import to_ticker
from app.data_fetcher import get_price_on_date, get_volume_top
from app.universe import KOSPI_TICKERS, KOSDAQ_TICKERS, GLOBAL_TICKERS

# ──────────────────────────────
FIELD_MAP = {
    "종가": "Close",
    "시가": "Open",
    "고가": "High",
    "저가": "Low",
    "등락률": "%Change",  # (선택) Task 확대 시
}

# ──────────────────────────────
def _answer_price(match: re.Match) -> str:
    name, date, field_ko = match.groups()
    field = FIELD_MAP[field_ko]

    ticker = to_ticker(name)
    price = get_price_on_date(ticker, date, field=field)
    unit = "원" if ticker.endswith((".KS", ".KQ")) else "USD"

    return f"{name}({ticker})의 {date} {field_ko}: {price:,.0f}{unit}"


def _answer_volume(match: re.Match) -> str:
    date, market, n_str = match.groups()
    n = int(n_str) if n_str else 1

    if market == "KOSPI":
        universe = KOSPI_TICKERS
    elif market == "KOSDAQ":
        universe = KOSDAQ_TICKERS
    else:
        universe = GLOBAL_TICKERS

    top = get_volume_top(universe, date, top_n=n)
    if top.empty:
        return f"{date} 거래량 데이터가 없습니다."

    # 예: "LS네트웍스 (33,638,023주)" 형식
    lines: List[str] = []
    for t, vol in top.items():
        # yfinance fast_info 로 한글 이름 얻기 시도, 실패 시 티커
        try:
            name = yf.Ticker(t).info.get("shortName") or t
        except Exception:
            name = t
        lines.append(f"{name} ({vol:,}주)")

    if n == 1:
        return f"{date} {market or ''} 시장에서 거래량이 가장 많은 종목은? {lines[0]}"
    else:
        return f"{date} {market or ''} 시장에서 거래량 기준 상위 {n}개 종목은?\n" + ", ".join(lines)


# ──────────────────────────────
# 메인 엔트리포인트
def handle(question: str) -> str:
    """
    자연어 질문을 받아 가격·거래량 Top N을 판단해 답변 문자열 반환
    """
    q = question.strip()

    # 1) 가격 조회
    m = re.search(
        r"([\w가-힣]+)의?\s*(\d{4}-\d{2}-\d{2})\s*(종가|시가|고가|저가)", q
    )
    if m:
        return _answer_price(m)

    # 2) 거래량 Top N
    m = re.search(
        r"(\d{4}-\d{2}-\d{2})\s*(KOSPI|KOSDAQ)?(?:\s*시장)?(?:에서)?\s*"
        r"거래량[^0-9]*?(?:상위)?\s*(\d+)?개?\s*종목",  # n이 없으면 1개
        q,
    )
    if m:
        return _answer_volume(m)

    return "죄송합니다. 해당 질문을 이해하지 못했습니다."
