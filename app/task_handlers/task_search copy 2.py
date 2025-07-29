from __future__ import annotations
from app.utils import _universe
from app.data_fetcher import _download, _next_day
from app.ticker_lookup import to_ticker
from app.universe import NAME_BY_TICKER
from app.search_utils import (
    search_by_pct_change_range,
    search_by_consecutive_change,
    search_cross_count_by_stock,
    search_cross_dates_by_condition,
    search_by_price_close,
    search_by_volume,
    search_by_pct_change,
    search_by_volume_pct,
    detect_rsi,
    detect_volume_spike,
    detect_ma_break,
    detect_bollinger_touch,
    three_pattern_tickers,
    three_pattern_counts,
    three_pattern_dates,
)
from app.ticker_lookup import to_ticker
import pandas as pd

def handle(_: str, p: dict) -> str:
    task = p.get("task")
    if task == "종목검색":
        return _handle_stock_search(p)
    elif task == "횟수검색":
        return _handle_count_search(p)
    elif task == "날짜검색":
        return _handle_date_search(p)
    else:
        return "[ERROR] 알 수 없는 task입니다."


# ───────────────────────────── 종목검색 ─────────────────────────────
def _handle_stock_search(p: dict) -> str:
    from app.universe import NAME_BY_TICKER, KOSPI_TICKERS, KOSDAQ_TICKERS
    from app.data_fetcher import _download
    from app.utils import _next_day
    from app.search_utils import (
        search_by_price_close, search_by_volume, search_by_pct_change, search_by_volume_pct,
        detect_rsi, detect_volume_spike, detect_ma_break, detect_bollinger_touch,
        search_by_pct_change_range, search_by_consecutive_change,
        search_cross_dates_by_condition, three_pattern_tickers,
    )

    cond = p.get("conditions", {})
    date = p.get("date")
    date_from = p.get("date_from")
    date_to = p.get("date_to")
    market = p.get("market")

    # ───────────────────── 단일일 조건 처리 ─────────────────────
    if date:
        def _need_history_depth(cond: dict) -> int:
            days = 0
            if "pct_change" in cond or "volume_pct" in cond:
                days = max(days, 2)
            if "RSI" in cond:
                days = max(days, cond["RSI"].get("window", 14))
            if "volume_spike" in cond:
                days = max(days, cond["volume_spike"].get("window", 20))
            if "moving_avg" in cond:
                days = max(days, cond["moving_avg"].get("window", 20))
            if "bollinger_touch" in cond:
                days = max(days, 20)
            return days * 2

        depth = _need_history_depth(cond)
        start = (pd.to_datetime(date) - pd.Timedelta(days=depth)).strftime("%Y-%m-%d")
        end = _next_day(date)

        tickers = tuple(_universe(market))

        df = _download(tickers, start=start, end=end, interval="1d")
        if df.empty:
            return f"{date}의 데이터를 불러올 수 없습니다."

        result = list(tickers)

        if "price_close" in cond:
            result = search_by_price_close(df, date, cond["price_close"], result)
        if "volume" in cond:
            result = search_by_volume(df, date, cond["volume"], result)
        if "pct_change" in cond:
            result = search_by_pct_change(df, date, cond["pct_change"], result)
        if "volume_pct" in cond:
            result = search_by_volume_pct(df, date, cond["volume_pct"], result)
        if "RSI" in cond:
            result = detect_rsi(df, date, cond["RSI"], result)
        if "volume_spike" in cond:
            result = detect_volume_spike(df, date, cond["volume_spike"], result)
        if "moving_avg" in cond:
            result = detect_ma_break(df, date, cond["moving_avg"], result)
        if "bollinger_touch" in cond:
            result = detect_bollinger_touch(df, date, cond["bollinger_touch"], result)

        if not result:
            return "조건에 맞는 종목이 없습니다."

        names = [NAME_BY_TICKER.get(t, t) for t in result]
        return f"종목은 다음과 같습니다.\n" + ", ".join(sorted(names))

    # ───────────────────── 기간 조건 처리 ─────────────────────
    elif date_from and date_to:
        tickers = list(_universe(market))
        df = _download(tuple(tickers), start=date_from, end=_next_day(date_to), interval="1d")
        if df.empty:
            return f"{date_from} ~ {date_to}의 데이터를 불러올 수 없습니다."

        result = tickers

        if "pct_change_range" in cond:
            result = search_by_pct_change_range(df, date_from, date_to, cond["pct_change_range"], result)

        if "consecutive_change" in cond:
            result = search_by_consecutive_change(df, date_from, date_to, cond["consecutive_change"], result)

        if "cross" in cond:
            result = search_cross_dates_by_condition(df, date_from, date_to, cond["cross"], result)

        if "three_pattern" in cond:
            result = three_pattern_tickers(df, cond["three_pattern"], date_from, date_to, result)

        if not result:
            return "조건에 맞는 종목이 없습니다."

        names = [NAME_BY_TICKER.get(t, t) for t in sorted(result)]
        return f"종목은 다음과 같습니다.\n" + ", ".join(names)

    # ───────────────────── 날짜 없음 ─────────────────────
    else:
        return "[ERROR] 날짜 정보가 없습니다."

# ───────────────────────────── 횟수검색 ─────────────────────────────
def _handle_count_search(p: dict) -> str:
    cond = p.get("conditions", {})
    date_from, date_to = p.get("date_from"), p.get("date_to")
    ticker_name = p.get("tickers", [None])[0]
    ticker = to_ticker(ticker_name)

    if "three_pattern" in cond:
        return three_pattern_counts(ticker, cond["three_pattern"], date_from, date_to)

    return search_cross_count_by_stock(ticker_name, date_from, date_to, cond["cross"])

# ───────────────────────────── 날짜검색 ─────────────────────────────
def _handle_date_search(p: dict) -> str:
    cond = p.get("conditions", {})
    date_from, date_to = p.get("date_from"), p.get("date_to")
    ticker_name = p.get("tickers", [None])[0]
    ticker = to_ticker(ticker_name)

    if "three_pattern" in cond:
        return three_pattern_dates(ticker, cond["three_pattern"], date_from, date_to)

    return "[ERROR] 지원하지 않는 날짜검색 조건입니다."
