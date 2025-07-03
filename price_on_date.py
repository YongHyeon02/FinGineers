#!/usr/bin/env python3
"""
price_on_date.py
입력: 종목명(한글) 또는 티커, 날짜(YYYY-MM-DD)
출력: 종가
"""

import argparse
import datetime as dt
import re
from typing import Optional

import pandas as pd
import yfinance as yf

# ──────────────────────────────
# 1. 한글 종목명 ↔ 티커 매핑 (샘플)
#    필요 시 CSV / DB 로드로 확장 가능
NAME2TICKER = {
    "삼성전자": "005930.KS",
    "LG전자": "066570.KS",
    "카카오":   "035720.KS",
    "네이버":  "035420.KS",
    # 미국 예시
    "마이크로소프트": "MSFT",
    "애플": "AAPL",
}

# ──────────────────────────────
def to_ticker(identifier: str) -> str:
    """
    한글 이름이면 매핑 사전으로 변환,
    영문·숫자(티커)면 그대로 사용
    """
    identifier = identifier.strip()
    # 한글이 포함돼 있으면 이름으로 간주
    if re.search(r"[가-힣]", identifier):
        ticker = NAME2TICKER.get(identifier)
        if not ticker:
            raise ValueError(f"'{identifier}' → 티커 매핑이 없습니다.")
        return ticker
    return identifier.upper()


def get_close_price(ticker: str, date_str: str) -> float:
    """
    지정 날짜의 종가 반환.
    - ticker: '005930.KS', 'MSFT' 등
    - date_str: 'YYYY-MM-DD'
    """
    try:
        target = dt.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("날짜 형식이 잘못됐습니다. YYYY-MM-DD로 입력하세요.")

    start = target
    end   = target + dt.timedelta(days=1)  # 다음날 00:00까지 조회

    df: pd.DataFrame = yf.download(
        tickers=ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        progress=False,
    )

    if df.empty:
        raise ValueError(f"{date_str} 에 대한 데이터가 없습니다.")

    close_val = float(df.iloc[0]["Close"])
    return close_val


# ──────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="종가 조회")
    parser.add_argument("symbol", help="종목명(한글) 또는 야후 티커")
    parser.add_argument("date", help="YYYY-MM-DD")
    args = parser.parse_args()

    try:
        ticker = to_ticker(args.symbol)
        price  = get_close_price(ticker, args.date)
        print(f"{args.symbol}({ticker}) {args.date} 종가: {price:,.2f}")
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
