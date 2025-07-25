# app/search_utils.py
from __future__ import annotations
from typing import Dict, List
import pandas as pd

from app.data_fetcher import _download
from app.universe import NAME_BY_TICKER
from app.utils import _holiday_msg, _prev_bday, _next_day, _universe
from app.ticker_lookup import to_ticker

# ────────────────────────── 1. 내부 헬퍼 ──────────────────────────
def _need_flags(cond: Dict) -> Dict[str, bool]:
    today_close   = "price_close" in cond
    today_volume  = "volume" in cond
    pct_change    = "pct_change" in cond
    vol_chg_pct   = "volume_pct" in cond
    return {
        "today_close":  today_close,
        "today_volume": today_volume,
        "pct_change":   pct_change,
        "vol_chg_pct":  vol_chg_pct,
        "prev_close":   pct_change,
        "prev_volume":  vol_chg_pct,
    }

def _download_for(date: str, market: str | None, need: Dict) -> pd.DataFrame:
    tickers = _universe(market)
    start   = _prev_bday(date) if (need["prev_close"] or need["prev_volume"]) else date
    end     = _next_day(date)
    return _download(tuple(tickers), start=start, end=end, interval="1d")

def _filter(df: pd.DataFrame, date: str, cond: Dict, need: Dict) -> List[str]:
    try:
        today = df.loc[pd.to_datetime(date)]
    except KeyError:
        return []

    try:
        prev = df.loc[pd.to_datetime(_prev_bday(date))] if (need["prev_close"] or need["prev_volume"]) else None
    except KeyError:
        prev = None

    out: List[str] = []


    for t in df.columns.levels[0]:    
        if (t, "Close") not in today or (t, "Volume") not in today:
            continue

        tc = today.get((t, "Close"), pd.NA)
        tv = today.get((t, "Volume"), pd.NA)

        if pd.isna(tc) or pd.isna(tv):
            continue

        if need["today_close"]:
            cmin = cond["price_close"].get("min")
            cmax = cond["price_close"].get("max")
            if (cmin is not None and tc < cmin) or (cmax is not None and tc > cmax):
                continue

        if need["today_volume"]:
            vmin = cond["volume"].get("min")
            if vmin is not None and tv < vmin:
                continue

        if not (need["pct_change"] or need["vol_chg_pct"]):
            out.append(t)
            continue

        if prev is None or (t, "Close") not in prev or (t, "Volume") not in prev:       
            continue

        pc = prev.get((t, "Close"), pd.NA)
        pv = prev.get((t, "Volume"), pd.NA)

        # 가격 변화 필요시: 전날 종가(pc), 오늘 종가(tc)
        if need["pct_change"]:
            if pd.isna(pc) or pd.isna(tc) or pc == 0:
                continue

        # 거래량 변화 필요시: 전날 거래량(pv), 오늘 거래량(tv)
        if need["vol_chg_pct"]:
            if pd.isna(pv) or pd.isna(tv) or pv == 0:
                continue

        if need["pct_change"]:
            delta = (tc - pc) / pc * 100
            dmin  = cond["pct_change"].get("min")
            dmax  = cond["pct_change"].get("max")
            if (dmin is not None and delta < dmin) or (dmax is not None and delta > dmax):
                continue

        if need["vol_chg_pct"]:
            v_pct = (tv - pv) / pv * 100
            vpmin = cond["volume_pct"].get("min")
            vpmax = cond["volume_pct"].get("max")  
            if (vpmin is not None and v_pct < vpmin) or (vpmax is not None and v_pct > vpmax):
                continue
        
        out.append(t)

    return out

def _filter_pct_range(df: pd.DataFrame, start: str, end: str, cond: Dict) -> List[str]:
    min_, max_ = cond["pct_change_range"].get("min"), cond["pct_change_range"].get("max")
    out = []

    for t in df.columns.levels[0]:
        try:
            p1 = df.loc[pd.to_datetime(start), (t, "Close")]
            p2 = df.loc[pd.to_datetime(end),   (t, "Close")]
        except KeyError:
            continue
        if any(pd.isna(x) or x == 0 for x in (p1, p2)):
            continue
        change = (p2 / p1 - 1) * 100
        if (min_ is not None and change < min_) or (max_ is not None and change > max_):
            continue
        out.append(t)
    return out

def _filter_consecutive(df: pd.DataFrame, start: str, end: str, direction: str) -> List[str]:
    out = []
    sliced = df.loc[pd.to_datetime(start):pd.to_datetime(end)]

    for t in df.columns.levels[0]:
        try:
            close = sliced[(t, "Close")]
        except KeyError:
            continue
        if close.isna().any() or len(close) < 2:
            continue
        diff = close.diff().iloc[1:]
        if direction == "up" and (diff > 0).all():
            out.append(t)
        elif direction == "down" and (diff < 0).all():
            out.append(t)
    return out

# ────────────────────────── 2. Stock Search Functions ──────────────────────────
def search_stock_by_conditions(p: dict) -> str:
    date = p["date"]
    cond = p.get("conditions", {})
    market = p.get("market")

    if msg := _holiday_msg(date):
        return msg

    need = _need_flags(cond)
    df = _download_for(date, market, need)
    if df.empty:
        return f"{date}의 데이터가 없습니다."

    tickers = _filter(df, date, cond, need)
    if not tickers:
        return "조건에 맞는 종목이 없습니다"

    # 거래량 0 종목 제외
    today = df.loc[pd.to_datetime(date)]
    tickers = [t for t in tickers if (t, "Volume") in today and today[(t, "Volume")] > 0]

    # 정렬: 우선순위는 거래량 → 등락률 → 종가
    sort_keys = []

    if "volume" in cond:
        sort_keys.append(("Volume", lambda t: today.get((t, "Volume"), 0)))

    if "volume_pct" in cond and need["prev_volume"]:
        prev = df.loc[pd.to_datetime(_prev_bday(date))]
        sort_keys.append(("Volume Change %", lambda t: abs((today[(t, "Volume")] - prev[(t, "Volume")]) / prev[(t, "Volume")] * 100) if (t, "Volume") in prev and prev[(t, "Volume")] else 0))

    if "pct_change" in cond and need["prev_close"]:
        prev = df.loc[pd.to_datetime(_prev_bday(date))]
        sort_keys.append(("Price Change %", lambda t: abs((today[(t, "Close")] - prev[(t, "Close")]) / prev[(t, "Close")] * 100) if (t, "Close") in prev and prev[(t, "Close")] else 0))

    if "price_close" in cond:
        sort_keys.append(("Close", lambda t: today.get((t, "Close"), 0)))

    # 하나라도 있으면 첫 번째 키 기준 정렬
    if sort_keys:
        tickers.sort(key=sort_keys[0][1], reverse=True)

    names = [NAME_BY_TICKER.get(t, t) for t in tickers]

    # ─ 조건 설명 텍스트 생성 ─
    cond_parts = []
    if "pct_change" in cond:
        min_, max_ = cond["pct_change"].get("min"), cond["pct_change"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"등락률이 {min_}% 이상 {max_}% 이하")
        elif min_ is not None:
            cond_parts.append(f"등락률이 {min_}% 이상")
        elif max_ is not None:
            cond_parts.append(f"등락률이 {max_}% 이하")

    if "volume_pct" in cond:
        min_, max_ = cond["volume_pct"].get("min"), cond["volume_pct"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"거래량이 전날대비 {min_}% 이상 {max_}% 이하")
        elif min_ is not None:
            cond_parts.append(f"거래량이 전날대비 {min_}% 이상")
        elif max_ is not None:
            cond_parts.append(f"거래량이 전날대비 {max_}% 이하")

    if "volume" in cond:
        min_ = cond["volume"].get("min")
        if min_ is not None:
            cond_parts.append(f"거래량이 {min_:,}주 이상")

    if "price_close" in cond:
        min_, max_ = cond["price_close"].get("min"), cond["price_close"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"종가가 {min_:,}원 이상 {max_:,}원 이하")
        elif min_ is not None:
            cond_parts.append(f"종가가 {min_:,}원 이상")
        elif max_ is not None:
            cond_parts.append(f"종가가 {max_:,}원 이하")

    cond_text = " 및 ".join(cond_parts) if cond_parts else "조건에 맞는"
    market_txt = f"{market}에서 " if market else ""
    date_text = f"{date}에 "

    return f"{date_text}{market_txt}{cond_text}인 종목은 다음과 같습니다.\n{', '.join(names)}"

def search_stock_by_range_return(p: dict) -> str:
    date_from, date_to = p["date_from"], p["date_to"]
    cond = p.get("conditions", {})
    market = p.get("market")

    tickers = tuple(_universe(market))
    df = _download(tickers, start=date_from, end=_next_day(date_to), interval="1d")
    if df.empty:
        return f"{date_from}~{date_to}의 데이터가 없습니다."

    # ─ 누적 수익률 조건
    if "pct_change_range" in cond:
        out = _filter_pct_range(df, date_from, date_to, cond)
        if not out:
            return "조건에 맞는 종목이 없습니다"
        out.sort(key=lambda t: abs((df.loc[last_day, (t, "Close")] / df.loc[pd.to_datetime(date_from), (t, "Close")] - 1) * 100), reverse=True)
        # 거래량 0 종목 제거
        last_day = pd.to_datetime(date_to)
        out = [t for t in out if (t, "Volume") in df.columns and df.loc[last_day, (t, "Volume")] > 0]
        names = [NAME_BY_TICKER.get(t, t) for t in out]

        min_, max_ = cond["pct_change_range"].get("min"), cond["pct_change_range"].get("max")
        if min_ is not None and max_ is not None:
            cond_text = f"누적 수익률이 {min_}% 이상 {max_}% 이하"
        elif min_ is not None:
            cond_text = f"누적 수익률이 {min_}% 이상"
        elif max_ is not None:
            cond_text = f"누적 수익률이 {max_}% 이하"
        else:
            cond_text = "조건에 맞는"

        market_txt = f"{market}에서 " if market else ""
        return f"{date_from}부터 {date_to}까지 {market_txt}{cond_text}인 종목은 다음과 같습니다.\n{', '.join(names)}"

    # ─ 연속 상승/하락 조건
    elif "consecutive_change" in cond:
        direction = cond["consecutive_change"]
        out = _filter_consecutive(df, date_from, date_to, direction)
        if not out:
            return "조건에 맞는 종목이 없습니다"
        # 거래량 0 종목 제거
        last_day = pd.to_datetime(date_to)
        out = [t for t in out if (t, "Volume") in df.columns and df.loc[last_day, (t, "Volume")] > 0]
        names = [NAME_BY_TICKER.get(t, t) for t in out]

        word = "연속 상승" if direction == "up" else "연속 하락"
        market_txt = f"{market}에서 " if market else ""
        return f"{date_from}부터 {date_to}까지 {market_txt}{word}한 종목은 다음과 같습니다.\n{', '.join(names)}"

    else:
        return "지원하지 않는 조건입니다."
    
# ────────────────────────── 3. Count/Date Search Functions ──────────────────────────
def search_cross_count_by_stock(p: dict) -> str:
    from app.signal_utils import count_crosses
    name = p["tickers"][0] if p["tickers"] else None
    cond = p.get("conditions", {})
    if not name:
        return "[ERROR] 종목명이 필요합니다."
    from_date, to_date = p["date_from"], p["date_to"]
    g, d = count_crosses(from_date, to_date, name)
    side = cond.get("side")
    if side == "golden":
        return f"{name}에서 {from_date}부터 {to_date}까지 골든크로스가 발생한 횟수는 {g}번입니다."
    elif side == "dead":
        return f"{name}에서 {from_date}부터 {to_date}까지 데드크로스가 발생한 횟수는 {d}번입니다."
    elif side == "both":
        return f"{name}에서 {from_date}부터 {to_date}까지 데드크로스는 {d}번, 골든크로스는 {g}번 발생했습니다."
    else:
        return f"{name}에서 {from_date}부터 {to_date}까지 골든크로스 {g}번, 데드크로스 {d}번 발생했습니다."

def search_cross_dates_by_condition(p: dict) -> str:
    from app.signal_utils import list_crossed_stocks
    from_date, to_date = p["date_from"], p["date_to"]
    cond = p.get("conditions", {})
    side = cond.get("side")
    tickers = list_crossed_stocks(from_date, to_date, cond)
    if not tickers:
        return "조건에 맞는 종목 없음"
    cross_txt = "골든크로스" if side == "golden" else "데드크로스"
    return f"{from_date}부터 {to_date}까지 {cross_txt}가 발생한 종목은 다음과 같습니다.\n{', '.join(tickers)}"
