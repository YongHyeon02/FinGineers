# 조건검색 (전일 n% 이상)
# app/task_handlers/task2_condition.py

import re
import pandas as pd
from typing import Dict

from app.data_fetcher import _download, _slice_single
from app.universe import GLOBAL_TICKERS, KOSPI_TICKERS, KOSDAQ_TICKERS, NAME_BY_TICKER
from app.task_handlers.task1_simple import _prev_bday, _next_day

def handle(question: str) -> str:
    try:
        return _answer_condition_query(question.strip())
    except Exception as e:
        return f"[ERROR] {e}"

# ──────────────────────────────
# 처리 함수: 조건 검색
# ──────────────────────────────

def _answer_condition_query(q: str) -> str:
    cond = _parse_condition(q)
    df = _get_market_df(cond["date"], cond.get("market"))
    df = _attach_change_metrics(df)
    df = _apply_filters(df, cond)
    names = [NAME_BY_TICKER.get(t, t) for t in df.index]
    return ", ".join(names) if names else "조건에 맞는 종목 없음"


def _parse_condition(q: str) -> Dict:
    date = re.search(r"(\d{4}-\d{2}-\d{2})", q).group(1)
    cond = {"date": date}

    # 시장 구분
    if "KOSPI" in q:
        cond["market"] = "KOSPI"
    elif "KOSDAQ" in q:
        cond["market"] = "KOSDAQ"

    if "등락률이 +" in q:
        pct = float(re.search(r"등락률이 \+?(\d+)% 이상", q).group(1))
        cond["pct_change_min"] = pct
    if "등락률이 -" in q:
        pct = float(re.search(r"등락률이 -(\d+)% 이하", q).group(1))
        cond["pct_change_max"] = -pct

    if "거래량이 전날대비" in q:
        pct = float(re.search(r"거래량이 전날대비 (\d+)% 이상", q).group(1))
        cond["volume_change_pct_min"] = pct
    if "거래량이" in q and "만주 이상" in q:
        vol = int(re.search(r"거래량이 (\d+)만주 이상", q).group(1))
        cond["volume_min"] = vol * 10_000

    if "종가가" in q:
        m = re.search(r"종가가 (\d+)만원 이상 (\d+)만원 이하", q)
        if m:
            cond["price_min"] = int(m.group(1)) * 10_000
            cond["price_max"] = int(m.group(2)) * 10_000
        else:
            m = re.search(r"종가가 (\d+)만원 이상", q)
            if m:
                cond["price_min"] = int(m.group(1)) * 10_000

    return cond


def _get_market_df(date: str, market: str | None = None) -> pd.DataFrame:
    tickers = (
        KOSPI_TICKERS if market == "KOSPI" else
        KOSDAQ_TICKERS if market == "KOSDAQ" else
        GLOBAL_TICKERS
    )
    nxt = _next_day(date)
    return _download(tuple(tickers), start=_prev_bday(date), end=nxt, interval="1d")


def _attach_change_metrics(df: pd.DataFrame) -> pd.DataFrame:
    metrics = {}
    for t in df.columns.get_level_values(0).unique():
        try:
            sub = _slice_single(df, t)
            if len(sub) < 2 or not {"Close", "Volume"}.issubset(sub.columns):
                continue
            prev_c, today_c = sub["Close"].iloc[0], sub["Close"].iloc[1]
            prev_v, today_v = sub["Volume"].iloc[0], sub["Volume"].iloc[1]
            if pd.isna(prev_c) or pd.isna(today_c) or prev_c == 0:
                continue
            if pd.isna(prev_v) or pd.isna(today_v) or prev_v == 0:
                continue
            metrics[t] = {
                "Close": today_c,
                "pct_change": (today_c - prev_c) / prev_c * 100,
                "volume": today_v,
                "volume_change_pct": (today_v - prev_v) / prev_v * 100
            }
        except Exception:
            continue
    return pd.DataFrame.from_dict(metrics, orient="index")


def _apply_filters(df: pd.DataFrame, cond: Dict) -> pd.DataFrame:
    if "pct_change_min" in cond:
        df = df[df["pct_change"] >= cond["pct_change_min"]]
    if "pct_change_max" in cond:
        df = df[df["pct_change"] <= cond["pct_change_max"]]
    if "volume_change_pct_min" in cond:
        df = df[df["volume_change_pct"] >= cond["volume_change_pct_min"]]
    if "volume_min" in cond:
        df = df[df["volume"] >= cond["volume_min"]]
    if "price_min" in cond:
        df = df[df["Close"] >= cond["price_min"]]
    if "price_max" in cond:
        df = df[df["Close"] <= cond["price_max"]]
    return df
