from __future__ import annotations
from typing import Dict, List
import pandas as pd

from app.data_fetcher import _download
from app.universe import NAME_BY_TICKER
from app.utils import _holiday_msg, _prev_bday, _next_day, _universe

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

        if any(pd.isna(x) or x == 0 for x in (pc, pv, tc, tv)):
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

# ────────────────────────── 2. 기간 조건 필터 ──────────────────────────
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

# ────────────────────────── 3. 핸들러 ──────────────────────────
def handle(_: str, p: dict) -> str:
    task = p["task"]
    cond = p.get("conditions", {})
    market = p.get("market")

    # ─ Task: 조건검색 (단일 날짜)
    if task == "조건검색":
        date = p["date"]
        if msg := _holiday_msg(date):
            return msg
        need = _need_flags(cond)
        df = _download_for(date, market, need)
        if df.empty:
            return f"{date}의 데이터가 없습니다."
        tickers = _filter(df, date, cond, need)

        date_text = f"{date}에 "

    # ─ Task: 기간검색
    elif task == "기간검색":
        date_from, date_to = p["date_from"], p["date_to"]
        tickers = tuple(_universe(market))
        df = _download(tickers, start=date_from, end=_next_day(date_to), interval="1d")
        if df.empty:
            return f"{date_from}~{date_to}의 데이터가 없습니다."

        if "pct_change_range" in cond:
            tickers = _filter_pct_range(df, date_from, date_to, cond)
        elif "consecutive_change" in cond:
            tickers = _filter_consecutive(df, date_from, date_to, cond["consecutive_change"])
        else:
            return "지원하지 않는 조건입니다."

        date_text = f"{date_from}부터 {date_to}까지 "

    else:
        return "[ERROR] 알 수 없는 Task입니다."

    if not tickers:
        return "조건에 맞는 종목이 없습니다"

    names = [NAME_BY_TICKER.get(t, t) for t in tickers]

    # ─ 조건 설명 텍스트 ─
    cond_parts = []
    if "pct_change" in cond:
        min_, max_ = cond["pct_change"].get("min"), cond["pct_change"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"등락률이 {min_}% 이상 {max_}% 이하")
        elif min_ is not None:
            cond_parts.append(f"등락률이 {min_}% 이상")
        elif max_ is not None:
            cond_parts.append(f"등락률이 {max_}% 이하")

    if "pct_change_range" in cond:
        min_, max_ = cond["pct_change_range"].get("min"), cond["pct_change_range"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"누적 수익률이 {min_}% 이상 {max_}% 이하")
        elif min_ is not None:
            cond_parts.append(f"누적 수익률이 {min_}% 이상")
        elif max_ is not None:
            cond_parts.append(f"누적 수익률이 {max_}% 이하")

    if "consecutive_change" in cond:
        dir_ = cond["consecutive_change"]
        word = "연속 상승" if dir_ == "up" else "연속 하락"
        cond_parts.append(word)

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
    intro = f"{date_text}{market_txt}{cond_text}인 종목은 다음과 같습니다."

    return f"{intro}\n{', '.join(names)}"
