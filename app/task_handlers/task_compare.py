from __future__ import annotations
import pandas as pd
from typing import Literal

from app.data_fetcher import _download, _next_day, get_index_level
from app.utils import _prev_bday, _universe
from app.universe import NAME_BY_TICKER, GLOBAL_TICKERS
from app.ticker_lookup import to_ticker

Metric = Literal["시가", "종가", "고가", "저가", "거래량", "등락률", "지수", "시가총액"]

METRIC_MAP = {
    "시가": ("Open", "{:,.2f}원"),
    "종가": ("Close", "{:,.2f}원"),
    "고가": ("High", "{:,.2f}원"),
    "저가": ("Low", "{:,.2f}원"),
    "거래량": ("Volume", "{:,}주"),
}

def handle(_: str, p: dict, api_key: str) -> str:
    date     = p.get("date")
    metrics  = p.get("metrics", [])
    metric   = metrics[0] if metrics else None
    names    = p.get("tickers", [])
    markets  = p.get("market") or []
    tickers  = [to_ticker(name, api_key=api_key) for name in names]

    if not date or not metric:
        return "비교를 위한 날짜와 지표가 필요합니다."

    # ────────────────────────────── 1. 지수 비교 (KOSPI vs KOSDAQ)
    if metric == "지수" and len(markets) == 2 and not tickers:
        try:
            val_a = get_index_level(markets[0], date)
            val_b = get_index_level(markets[1], date)
        except Exception:
            return f"{date}의 지수를 불러올 수 없습니다."

        winner = markets[0] if val_a > val_b else markets[1]
        return (
            f"{date} 기준 지수가 더 높은 시장은 {winner}입니다.\n"
            f"  - {markets[0]}: {val_a:,.2f}\n"
            f"  - {markets[1]}: {val_b:,.2f}"
        )

    # ────────────────────────────── 2. 종목 vs 시장 평균
    if len(tickers) == 1:
        market_set = set(p.get("conditions", {}).get("market") or [])
        allowed_markets = {"KOSPI", "KOSDAQ"}

        if market_set.issubset(allowed_markets) and metric in ("등락률", "pct_change"):
            ticker = tickers[0]
            name = NAME_BY_TICKER.get(ticker, ticker)

            # 종목 데이터
            df = _download((ticker,), start=_prev_bday(date), end=_next_day(date), interval="1d")
            if df.empty or (ticker, "Adj Close") not in df.columns:
                return f"{date} 기준 {name}의 데이터를 불러올 수 없습니다."

            try:
                close = df[ticker, "Adj Close"]
                val = (close.loc[date] - close.loc[_prev_bday(date)]) / close.loc[_prev_bday(date)] * 100
            except:
                return f"{date} 또는 전일 종가가 없습니다."

            # 시장 전체 티커
            if market_set == {"KOSPI"}:
                tickers_all = tuple(_universe("KOSPI"))
                market_name = "KOSPI"
            elif market_set == {"KOSDAQ"}:
                tickers_all = tuple(_universe("KOSDAQ"))
                market_name = "KOSDAQ"
            else:
                tickers_all = tuple(_universe(None))  # 전체
                market_name = "KOSPI + KOSDAQ"

            # 시장 데이터 다운로드
            df_all = _download(tickers_all, start=_prev_bday(date), end=_next_day(date), interval="1d")
            try:
                prev_close = df_all.xs("Adj Close", level=1, axis=1).loc[_prev_bday(date)]
                curr_close = df_all.xs("Adj Close", level=1, axis=1).loc[date]
                prev_vol = df_all.xs("Volume", level=1, axis=1).loc[_prev_bday(date)]
                curr_vol = df_all.xs("Volume", level=1, axis=1).loc[date]

                # 유효 종목: 종가 존재 + 거래량 > 0
                valid = (
                    prev_close.notna() & curr_close.notna() &
                    (prev_vol > 0) & (curr_vol > 0)
                )
                pct_changes = (curr_close[valid] - prev_close[valid]) / prev_close[valid] * 100
                avg = pct_changes.mean()
            except:
                return f"{date} {market_name} 시장 평균 등락률 계산에 실패했습니다."

            result = "높습니다" if val > avg else "낮습니다"
            return (
                f"{date} 기준 {name}의 등락률은 {market_name} 시장 평균보다 {result}.\n"
                f"  - {name}: {val:+.2f}%\n"
                f"  - 시장 평균: {avg:+.2f}%"
            )

    # ────────────────────────────── 3. 종목 vs 종목
    if len(tickers) == 2:
        a, b = tickers

        if metric in ("등락률", "pct_change"):
            df_now  = _download((a, b), start=date, end=_next_day(date), interval="1d")
            prev_day = _prev_bday(date)
            df_prev = _download((a, b), start=prev_day, end=_next_day(prev_day), interval="1d")

            try:
                close_now  = df_now.xs("Adj Close", level=1, axis=1).loc[date]
                close_prev = df_prev.xs("Adj Close", level=1, axis=1).loc[prev_day]
                val_a = (close_now[a] - close_prev[a]) / close_prev[a] * 100
                val_b = (close_now[b] - close_prev[b]) / close_prev[b] * 100
            except:
                return f"{date} 또는 전일의 종가 데이터를 찾을 수 없습니다."

            fmt = "{:+.2f}%"
        elif metric in METRIC_MAP:
            col, fmt = METRIC_MAP[metric]
            df = _download((a, b), start=date, end=_next_day(date), interval="1d")
            if df.empty or (a, col) not in df.columns or (b, col) not in df.columns:
                return f"{date}의 데이터를 불러올 수 없습니다."
            val_a = df[a, col].get(date)
            val_b = df[b, col].get(date)
        else:
            return f"지원하지 않는 비교 지표입니다."

        if pd.isna(val_a) or pd.isna(val_b):
            return f"{date}에 필요한 데이터를 찾을 수 없습니다."

        name_a = NAME_BY_TICKER.get(a, a)
        name_b = NAME_BY_TICKER.get(b, b)

        # 방향성 판단
        higher_is_better = metric not in ("저가",)  # 저가는 낮을수록 좋음
        if (val_a > val_b and higher_is_better) or (val_a < val_b and not higher_is_better):
            winner = name_a
        else:
            winner = name_b

        # 지표 설명 문구
        comp_word = "높은" if higher_is_better else "낮은"

        if metric == "pct_change":
            metric = "등락률"

        return (
            f"{date} 기준 {metric}이 더 {comp_word} 종목은 {winner}입니다.\n"
            f"  - {name_a}: {fmt.format(val_a)}\n"
            f"  - {name_b}: {fmt.format(val_b)}"
        )


    return "비교할 조건이 부족하거나 지원하지 않는 비교 유형입니다."
