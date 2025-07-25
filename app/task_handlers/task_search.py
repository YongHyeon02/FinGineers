from __future__ import annotations
from app.search_utils import (
    search_stock_by_conditions,
    search_stock_by_range_return,
    search_cross_count_by_stock,
    search_cross_dates_by_condition,
)
from app.signal_utils import (
    detect_rsi,
    detect_volume_spike,
    detect_ma_break,
    detect_bollinger_touch,
    three_pattern_tickers,
    three_pattern_counts,
    three_pattern_dates,
    to_ticker,
)

def handle(_: str, p: dict) -> str:
    task = p.get("task")
    # ────────────────────────── 종목검색 ──────────────────────────
    if task == "종목검색":
        cond = p.get("conditions", {})
        metrics = p.get("metrics", [])
        date_from, date_to = p.get("date_from"), p.get("date_to")
        date = p.get("date")

        # 기간 기반 조건
        if "pct_change_range" in cond or "consecutive_change" in cond:
            return search_stock_by_range_return(p)

        # 크로스 발생 종목 필터링
        elif cond.get("side") and date_from and date_to:
            return search_cross_dates_by_condition(p)

        # 시그널 기반 종목 필터링
        elif metrics:
            return _handle_signal_detection(p)

        # 단일일 조건검색
        elif cond and date:
            return search_stock_by_conditions(p)

        else:
            return "[ERROR] 지원하지 않는 종목검색 조건입니다."


    # ────────────────────────── 횟수검색 ──────────────────────────
    elif task == "횟수검색":
        tickers = p.get("tickers", [])
        date_from, date_to = p.get("date_from"), p.get("date_to")
        metrics = p.get("metrics", [])
        if any(m in {"적삼병", "흑삼병"} for m in metrics):
            pattern = metrics[0]
            name = tickers[0]
            ticker = to_ticker(name)
            return three_pattern_counts(ticker, pattern, date_from, date_to)
        else:
            return search_cross_count_by_stock(p)

    # ────────────────────────── 날짜검색 ──────────────────────────
    elif task == "날짜검색":
        metrics = p.get("metrics", [])
        date_from, date_to = p.get("date_from"), p.get("date_to")
        tickers = p.get("tickers", [])
        if any(m in {"적삼병", "흑삼병"} for m in metrics):
            pattern = metrics[0]
            name = tickers[0]
            ticker = to_ticker(name)
            return three_pattern_dates(ticker, pattern, date_from, date_to)
    else:
        return "[ERROR] 알 수 없는 task입니다."

# ────────────────────────── 시그널 감지 (종목검색용) ──────────────────────────
def _handle_signal_detection(p: dict) -> str:
    metrics = p.get("metrics", [])
    cond = p.get("conditions", {})
    date = p.get("date")
    date_from = p.get("date_from")
    date_to = p.get("date_to")
    market = p.get("market")

    if not metrics:
        return "[ERROR] 시그널 감지를 위한 metrics 또는 날짜가 누락되었습니다."

    signal_type = metrics[0]
    if signal_type == "RSI":
        return detect_rsi(date, cond)
    elif signal_type == "거래량평균":
        return detect_volume_spike(date, cond)
    elif signal_type == "이동평균돌파":
        return detect_ma_break(date, cond)
    elif signal_type == "볼린저터치":
        return detect_bollinger_touch(date, cond)
    elif any(m in {"적삼병", "흑삼병"} for m in metrics):
        pattern = metrics[0]
        return three_pattern_tickers(pattern, date_from, date_to, market)
    else:
        return f"[ERROR] 지원하지 않는 시그널 유형입니다: {signal_type}"
