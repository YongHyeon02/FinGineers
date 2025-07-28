from __future__ import annotations
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
    cond = p.get("conditions", {})
    date = p.get("date")
    date_from, date_to = p.get("date_from"), p.get("date_to")
    market = p.get("market")

    if "pct_change_range" in cond:
        return search_by_pct_change_range(date_from, date_to, market, cond["pct_change_range"])

    if "consecutive_change" in cond:
        return search_by_consecutive_change(date_from, date_to, market, cond["consecutive_change"])

    if "side" in cond and date_from and date_to:
        return search_cross_dates_by_condition(date_from, date_to, cond["side"])

    if "RSI" in cond:
        return detect_rsi(date, cond["RSI"])

    if "volume_spike" in cond:
        return detect_volume_spike(date, cond["volume_spike"])

    if "moving_avg" in cond:
        return detect_ma_break(date, cond["moving_avg"])

    if "bollinger_touch" in cond:
        return detect_bollinger_touch(date, cond["bollinger_touch"])

    if "three_pattern" in cond:
        return three_pattern_tickers(cond["three_pattern"], date_from, date_to, market)

    if "price_close" in cond:
        return search_by_price_close(date, market, cond["price_close"])

    if "volume" in cond:
        return search_by_volume(date, market, cond["volume"])

    if "pct_change" in cond:
        return search_by_pct_change(date, market, cond["pct_change"])

    if "volume_pct" in cond:
        return search_by_volume_pct(date, market, cond["volume_pct"])

    return "[ERROR] 지원하지 않는 종목검색 조건입니다."

# ───────────────────────────── 횟수검색 ─────────────────────────────
def _handle_count_search(p: dict) -> str:
    cond = p.get("conditions", {})
    date_from, date_to = p.get("date_from"), p.get("date_to")
    ticker_name = p.get("tickers", [None])[0]
    ticker = to_ticker(ticker_name)

    if "three_pattern" in cond:
        return three_pattern_counts(ticker, cond["three_pattern"], date_from, date_to)

    return search_cross_count_by_stock(ticker_name, date_from, date_to, cond["side"])

# ───────────────────────────── 날짜검색 ─────────────────────────────
def _handle_date_search(p: dict) -> str:
    cond = p.get("conditions", {})
    date_from, date_to = p.get("date_from"), p.get("date_to")
    ticker_name = p.get("tickers", [None])[0]
    ticker = to_ticker(ticker_name)

    if "three_pattern" in cond:
        return three_pattern_dates(ticker, cond["three_pattern"], date_from, date_to)

    return "[ERROR] 지원하지 않는 날짜검색 조건입니다."
