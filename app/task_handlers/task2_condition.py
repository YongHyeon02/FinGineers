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

# ────────────────────────── 2. 메인 필터 ──────────────────────────
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

    for t in df.columns.levels[0]:  # 티커 순회
        if (t, "Close") not in today or (t, "Volume") not in today:
            continue

        tc = today.get((t, "Close"), pd.NA)
        tv = today.get((t, "Volume"), pd.NA)

        if pd.isna(tc) or pd.isna(tv):
            continue

        # ── 오늘 종가 / 거래량 조건 ──
        if need["today_close"]:
            cmin = cond["price_close"].get("min")
            cmax = cond["price_close"].get("max")
            if (cmin is not None and tc < cmin) or (cmax is not None and tc > cmax):
                continue

        if need["today_volume"]:
            vmin = cond["volume"].get("min")
            if vmin is not None and tv < vmin:
                continue

        # ── 전일 데이터 필요 시 ──
        if not (need["pct_change"] or need["vol_chg_pct"]):
            out.append(t)
            continue

        if prev is None or (t, "Close") not in prev or (t, "Volume") not in prev:
            continue

        pc = prev.get((t, "Close"), pd.NA)
        pv = prev.get((t, "Volume"), pd.NA)

        if any(pd.isna(x) or x == 0 for x in (pc, pv, tc, tv)):
            continue

        # 등락률
        if need["pct_change"]:
            delta = (tc - pc) / pc * 100
            dmin  = cond["pct_change"].get("min")
            dmax  = cond["pct_change"].get("max")
            if (dmin is not None and delta < dmin) or (dmax is not None and delta > dmax):
                continue

        # 거래량 증감률
        if need["vol_chg_pct"]:
            v_pct = (tv - pv) / pv * 100
            vpmin = cond["volume_pct"].get("min")
            vpmax = cond["volume_pct"].get("max")
            if (vpmin is not None and v_pct < vpmin) or (vpmax is not None and v_pct > vpmax):
                continue

        out.append(t)

    return out

# ────────────────────────── 3. public entry ──────────────────────────
def handle(_: str, p: dict) -> str:
    date, market, cond = p["date"], p.get("market"), p.get("conditions", {})
    if msg := _holiday_msg(date):
        return msg

    need = _need_flags(cond)
    df   = _download_for(date, market, need)
    if df.empty:
        return f"{date}의 데이터가 없습니다."

    tickers = _filter(df, date, cond, need)
    if not tickers:
        return "조건에 맞는 종목이 없습니다"

    names = [NAME_BY_TICKER.get(t, t) for t in tickers]

    # 조건 설명 텍스트 구성
    cond_parts = []
    if "pct_change" in cond:
        min_ = cond["pct_change"].get("min")
        max_ = cond["pct_change"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"등락률이 {min_}% 이상 {max_}% 이하")
        elif min_ is not None:
            cond_parts.append(f"등락률이 {min_}% 이상")
        elif max_ is not None:
            cond_parts.append(f"등락률이 {max_}% 이하")
    if "volume_pct" in cond:
        min_ = cond["volume_pct"].get("min")
        max_ = cond["volume_pct"].get("max")
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
        min_ = cond["price_close"].get("min")
        max_ = cond["price_close"].get("max")
        if min_ is not None and max_ is not None:
            cond_parts.append(f"종가가 {min_:,}원 이상 {max_:,}원 이하")
        elif min_ is not None:
            cond_parts.append(f"종가가 {min_:,}원 이상")
        elif max_ is not None:
            cond_parts.append(f"종가가 {max_:,}원 이하")

    cond_text = " 및 ".join(cond_parts) if cond_parts else "조건에 맞는"
    market_txt = f"{market}에서 " if market else ""
    intro = f"{date}에 {market_txt}{cond_text}인 종목은 다음과 같습니다."
    
    return f"{intro}\n{', '.join(names)}"
