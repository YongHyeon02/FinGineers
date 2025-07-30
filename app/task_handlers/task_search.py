from __future__ import annotations
from app.utils import _universe, _holiday_msg, _prev_bday, _nth_prev_bday
from app.data_fetcher import _download, _next_day
from app.ticker_lookup import to_ticker
from app.universe import NAME_BY_TICKER, KOSPI_TICKERS, KOSDAQ_TICKERS
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
    detect_52w_high_break,
    detect_52w_low,
    detect_off_peak,
    search_by_gap_pct,
)
from app.ticker_lookup import to_ticker
import pandas as pd

def handle(_: str, p: dict, api_key: str) -> str:
    task = p.get("task")
    if task == "종목검색":
        return _handle_stock_search(p)
    elif task == "횟수검색":
        return _handle_count_search(p, api_key)
    elif task == "날짜검색":
        return _handle_date_search(p, api_key)
    else:
        return "[ERROR] 알 수 없는 task입니다."


# ───────────────────────────── 종목검색 ─────────────────────────────
def _handle_stock_search(p: dict) -> str:
    cond = p.get("conditions", {})
    date = p.get("date")
    date_from = p.get("date_from")
    date_to = p.get("date_to")
    market = p.get("market")

    # ───────────────────── 단일일 조건 처리 ─────────────────────
    if date:
        if msg := _holiday_msg(date):
            return msg
        def _need_history_depth(cond: dict) -> int:
            days = 0
            if "pct_change" in cond or "volume_pct" in cond:
                days = max(days, 1)
            if "RSI" in cond:
                days = max(days, cond["RSI"].get("window", 14))
            if "volume_spike" in cond:
                days = max(days, cond["volume_spike"].get("window", 20))
            if "moving_avg" in cond:
                days = max(days, cond["moving_avg"].get("window", 20))
            if "bollinger_touch" in cond:
                days = max(days, 20)
            if "peak_break" in cond or "peak_low" in cond or "off_peak" in cond:
                days = max(days, cond.get("peak_break", {}).get("period_days",
                                 cond.get("peak_low", {}).get("period_days",
                                 cond.get("off_peak", {}).get("period_days", 260))))
            if "gap_pct" in cond:
                days = max(days, 1)
            if "net_buy" in cond:
                days = max(days, 1)
            return days
        
        depth = _need_history_depth(cond)
        start = _nth_prev_bday(date, depth)
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
        if "peak_break" in cond:
            period = cond["peak_break"].get("period_days", 260)
            result = detect_52w_high_break(df, date, period, result)
        if "peak_low" in cond:
            period = cond["peak_low"].get("period_days", 260)
            result = detect_52w_low(df, date, period, result)   
        if "off_peak" in cond:
            period = cond["off_peak"].get("period_days", 260)
            drop  = cond["off_peak"].get("min", 30)
            result = detect_off_peak(df, date, period, drop, result)
        if "gap_pct" in cond:
            result = search_by_gap_pct(df, date, cond["gap_pct"], result)

        if not result:
            return "조건에 맞는 종목이 없습니다."

        names = [NAME_BY_TICKER.get(t, t) for t in result]
        desc = _describe_conditions(date, cond)
        return desc + "\n" + ", ".join(sorted(names))

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
        desc = _describe_range_conditions(date_from, date_to, cond)
        return desc + "\n" + ", ".join(names)


    # ───────────────────── 날짜 없음 ─────────────────────
    else:
        return "[ERROR] 날짜 정보가 없습니다."

# ───────────────────────────── 횟수검색 ─────────────────────────────
def _handle_count_search(p: dict, api_key: str) -> str:
    cond = p.get("conditions", {})
    date_from, date_to = p.get("date_from"), p.get("date_to")
    ticker_name = p.get("tickers", [None])[0]
    ticker = to_ticker(ticker_name, api_key = api_key)

    if "three_pattern" in cond:
        return three_pattern_counts(ticker, cond["three_pattern"], date_from, date_to)

    return search_cross_count_by_stock(ticker_name, date_from, date_to, cond["cross"], api_key)

# ───────────────────────────── 날짜검색 ─────────────────────────────
def _handle_date_search(p: dict, api_key: str) -> str:
    cond = p.get("conditions", {})
    date_from, date_to = p.get("date_from"), p.get("date_to")
    ticker_name = p.get("tickers", [None])[0]
    ticker = to_ticker(ticker_name, api_key = api_key)

    if "three_pattern" in cond:
        return three_pattern_dates(ticker, cond["three_pattern"], date_from, date_to)

    return "[ERROR] 지원하지 않는 날짜검색 조건입니다."

def _describe_conditions(date: str, cond: dict) -> str:
    parts = []

    def pct(x): return f"{x}%" if isinstance(x, (int, float)) else str(x)

    if "price_close" in cond:
        sub = cond["price_close"]
        rng = []
        if "min" in sub: rng.append(f"{sub['min']}원 이상")
        if "max" in sub: rng.append(f"{sub['max']}원 이하")
        parts.append(f"종가가 {', '.join(rng)}인")

    if "volume" in cond:
        sub = cond["volume"]
        rng = []
        if "min" in sub: rng.append(f"{sub['min']}주 이상")
        if "max" in sub: rng.append(f"{sub['max']}주 이하")
        parts.append(f"거래량이 {', '.join(rng)}인")

    if "pct_change" in cond:
        sub = cond["pct_change"]
        rng = []
        if "min" in sub: rng.append(f"{pct(sub['min'])} 이상 상승")
        if "max" in sub: rng.append(f"{pct(sub['max'])} 이하 하락")
        parts.append(f"등락률이 {', '.join(rng)}인")

    if "volume_pct" in cond:
        sub = cond["volume_pct"]
        parts.append(f"전일 대비 거래량이 {pct(sub['min'])} 이상 증가한")

    if "RSI" in cond:
        sub = cond["RSI"]
        if "min" in sub:
            parts.append(f"RSI가 {sub['min']} 이상인")
        elif "max" in sub:
            parts.append(f"RSI가 {sub['max']} 이하인")
        else:
            parts.append("RSI 과매수/과매도 상태인")

    if "volume_spike" in cond:
        sub = cond["volume_spike"]
        window = sub.get("window", 20)
        ratio = sub.get("volume_ratio", {}).get("min", None)
        if ratio:
            parts.append(f"거래량이 {window}일 평균 대비 {pct(ratio)} 이상 급증한")

    if "moving_avg" in cond:
        sub = cond["moving_avg"]
        window = sub.get("window")
        threshold = sub.get("diff_pct", {}).get("min", 0)
        parts.append(f"종가가 {window}일 이동평균선보다 {pct(threshold)} 이상 높은")

    if "bollinger_touch" in cond:
        b = cond["bollinger_touch"]
        if b == "upper":
            parts.append("볼린저밴드 상단을 터치한")
        elif b == "lower":
            parts.append("볼린저밴드 하단을 터치한")

    if "peak_break" in cond:
        days = cond["peak_break"].get("period_days", 260)
        parts.append(f"{days}일 내 신고가를 돌파한")

    if "peak_low" in cond:
        days = cond["peak_low"].get("period_days", 260)
        parts.append(f"{days}일 내 신저가를 갱신한")

    if "off_peak" in cond:
        days = cond["off_peak"].get("period_days", 260)
        drop = cond["off_peak"].get("min", 30)
        parts.append(f"{days}일 고점 대비 {pct(drop)} 이상 하락한")

    if "gap_pct" in cond:
        sub = cond["gap_pct"]
        rng = []
        if "min" in sub: rng.append(f"갭상승 {pct(sub['min'])} 이상")
        if "max" in sub: rng.append(f"갭하락 {pct(sub['max'])} 이하")
        parts.append(", ".join(rng))

    if not parts:
        return f"{date} 기준 조건에 부합하는 종목은 다음과 같습니다."

    desc = f"{date}에 " + ", ".join(parts) + " 종목은 다음과 같습니다."
    return desc

def _describe_range_conditions(date_from: str, date_to: str, cond: dict) -> str:
    parts = []

    def pct(x): return f"{x}%" if isinstance(x, (int, float)) else str(x)

    if "pct_change_range" in cond:
        sub = cond["pct_change_range"]
        rng = []
        if "min" in sub: rng.append(f"{pct(sub['min'])} 이상 상승")
        if "max" in sub: rng.append(f"{pct(sub['max'])} 이하 하락")
        parts.append(f"주가가 {', '.join(rng)}한")

    if "consecutive_change" in cond:
        direction = cond["consecutive_change"]
        if direction == "up":
            parts.append(f"연속 상승한")
        elif direction == "down":
            parts.append(f"연속 하락한")

    if "cross" in cond:
        side = cond["cross"].get("side")
        if side == "golden":
            parts.append("골든크로스가 발생한")
        elif side == "dead":
            parts.append("데드크로스가 발생한")
        elif side == "both":
            parts.append("골든/데드크로스가 발생한")

    if "three_pattern" in cond:
        pattern = cond["three_pattern"]
        if pattern == "적삼병":
            parts.append("적삼병 패턴이 나타난")
        elif pattern == "흑삼병":
            parts.append("흑삼병 패턴이 나타난")

    if not parts:
        return f"{date_from}부터 {date_to}까지 조건에 부합하는 종목은 다음과 같습니다."

    desc = f"{date_from}부터 {date_to}까지 " + ", ".join(parts) + " 종목은 다음과 같습니다."
    return desc
