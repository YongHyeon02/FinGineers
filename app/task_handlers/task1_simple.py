# app/task_handlers/task1_simple.py
"""
Task 1 – 단순 조회
"""
from __future__ import annotations

import re, math, datetime as dt
from functools import lru_cache
from typing import List, Dict, Tuple, Iterable

import pandas as pd
import yfinance as yf
import numpy as np

from app.ticker_lookup import to_ticker, TickerInfo, disambiguate_ticker_hcx
from app.data_fetcher import get_price_on_date, get_volume_top, _download, _slice_single
from app.universe import (
    KOSPI_TICKERS, KOSDAQ_TICKERS, GLOBAL_TICKERS,
    NAME_BY_TICKER, KOSPI_MAP, KOSDAQ_MAP,
)
from app.utils import _is_zero_volume, _holiday_msg, _universe, _prev_bday, _next_day, _find_prev_close, _nth_prev_bday
from config import AmbiguousTickerError


# ──────────────────────────────
FIELD_MAP = {"종가": "Close", "시가": "Open", "고가": "High", "저가": "Low", "pct_change": "%Change", "거래량": "Volume"}
TICK2NAME: Dict[str, str] = {v: k for k, v in {**KOSPI_MAP, **KOSDAQ_MAP}.items()}

                   # 지난 7 일 안에서 직전 거래일 탐색


# ─────────────────────────── 1. 가격/등락률 ───────────────────────────
# ─────────────────────────── NEW: 범용 다중-조회 ───────────────────────────
_FIELD_KO = {"종가": "Close", "시가": "Open", "고가": "High",
             "저가": "Low",   "거래량": "Volume"}      # 등락률·변동성·베타는 계산식

def _fmt(val, kind):
    if val is None:
        return "데이터 없음"
    if kind == "거래량":
        return f"{int(val):,}주"
    if kind in {"변동성", "베타"}:
        return f"{val:.3f}" if kind == "변동성" else f"{val:.2f}"
    if kind == "pct_change":
        return f"{val:+.2f}%"
    return f"{val:,.0f}원"

def _answer_multi(params: dict, api_key: str) -> str:
    date     = params["date"]
    metrics  = params["metrics"]
    aliases  = params["tickers"]
    market   = params.get("market")

    results = []

    for alias in aliases:
        try:
            info = to_ticker(alias, with_name=True, api_key=api_key)  # 한글명 → 코드
        except AmbiguousTickerError as e:
            raise
        except Exception:                                    # 완전 미인식
            all_names = list(KOSPI_MAP.keys()) + list(KOSDAQ_MAP.keys())
            best, _ = disambiguate_ticker_hcx(alias, all_names, api_key)
            cands = [best] + [n for n in all_names if n != best][:5]
            raise AmbiguousTickerError(alias, cands)

        tic, name = info.ticker, info.name
        parts = []

        # ① 가격·거래량 류 ───────────────────────────
        for m in metrics:
            if m in _FIELD_KO:
                field = _FIELD_KO[m]
                try:
                    val = get_price_on_date(tic, date, field)
                    vol = get_price_on_date(tic, date, "Volume")
                    if field == "Volume":   # 거래량은 ‘0’ 차단 필요 없음
                        ok = val not in (None, 0)
                    else:                   # 가격·시가 등은 거래정지 체크
                        ok = (val not in (None, 0)) and (vol not in (None, 0))
                except Exception:
                    ok = False
                parts.append(f"{m} {_fmt(val if ok else None, m)}")

        # ② 등락률 ────────────────────────────
        if "pct_change" in metrics:
            try:
                p_today = get_price_on_date(tic, date, "Close")
                _, p_prev = _find_prev_close(tic, date)
                pct = (p_today - p_prev) / p_prev * 100 if p_prev else None
            except Exception:
                pct = None
            parts.append(f"등락률 {_fmt(pct, 'pct_change')}")

        # ③ 변동성 / 베타 ───────────────────────
        if "변동성" in metrics:
            v = _calc_volatility(tic, date)
            parts.append(f"변동성 {_fmt(v, '변동성')}")
        if "베타" in metrics:
            b = _calc_beta(tic, date, market)
            parts.append(f"베타 {_fmt(b, '베타')}")

        results.append(f"{name}: " + ", ".join(parts) if parts else f"{name}: 데이터 없음")
    
    # ── 출력 형식(기존 변동성·베타 함수와 동일) ─────────────────────────
    if len(results) == 1:
        line = results[0]
        if ":" in line:
            name, vals = map(str.strip, line.split(":", 1))
            return f"{date}에 {name}의 {vals} 입니다."
        return f"{date}에 {line}"
    bullet = "\n".join(f"- {r}" for r in results)
    return f"{date} 기준 종목별 지표는 다음과 같습니다.\n{bullet}"

def _answer_price(params: dict, api_key: str) -> str:
    raw_name   = params["tickers"][0]
    date   = params["date"]
    field_ko = params["metrics"][0]          # 종가·시가·고가·저가·등락률 중 하나
    if (msg := _holiday_msg(date)):
        return msg
    info: TickerInfo = to_ticker(raw_name, with_name = True, api_key=api_key)
    ticker, off_name = info.ticker, info.name

    # 가격 데이터가 없는 주식(거래정지) → 0 처리
    if field_ko == "pct_change":
        try:
            p_today = get_price_on_date(ticker, date, "Close")
            _, p_prev = _find_prev_close(ticker, date)
            if not p_prev or not p_today:
                return f"{date}에 {off_name}의 등락률 데이터를 찾을 수 없습니다"
            pct = (p_today - p_prev) / p_prev * 100
            value = f"{pct:+.2f}%"
            return f"{date}에 {off_name}의 등락률은 {value} 입니다."
        except Exception:
            return f"{date}에 {off_name}의 등락률 데이터를 찾을 수 없습니다"

    field = FIELD_MAP[field_ko]
    try:
        price = get_price_on_date(ticker, date, field)
        vol   = get_price_on_date(ticker, date, "Volume")
    except Exception:
        price, vol = None, None
    if price in (None, 0):
        return f"{date}에 {off_name}의 {field_ko} 데이터를 찾을 수 없습니다"
    if vol in (None, 0) or price in (None, 0):
        return f"{date}에 {off_name}은(는) 거래되지 않았습니다."
    unit = "주" if field_ko == "거래량" else "원"
    value = f"{price:,.0f}{unit}"
    return f"{date}에 {off_name}의 {field_ko}은(는) {value} 입니다."

def _answer_index(date: str, market: str, ticker: str) -> str:
    msg = _holiday_msg(date)
    if msg:
        return msg
    try:
        val = get_price_on_date(ticker, date, "Close")
    except Exception:
        val = None
    if not val:
        return f"{date}에 {market} 지수 데이터가 없습니다."
    return f"{date}에 {market} 지수는 {val:,.2f} 입니다."

def _answer_kospi_index(date: str)  -> str: return _answer_index(date, "KOSPI",  "^KS11")
def _answer_kosdaq_index(date: str) -> str: return _answer_index(date, "KOSDAQ", "^KQ11")

# 거래대금
def _answer_total_trading_value(date: str, market: str | None) -> str:
    if msg := _holiday_msg(date):
        return msg
    tickers = _universe(market)
    market_txt = market if market else "전체 시장"
    df = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df.empty:
        return f"{date}에 {market_txt} 거래대금 데이터가 없습니다"
    total = 0
    for t in GLOBAL_TICKERS:
        try:
            sub = _slice_single(df, t)
            price, vol = sub["Close"].iloc[0], sub["Volume"].iloc[0]
            if not pd.isna(price) and not pd.isna(vol):
                total += price * vol
        except Exception:
            continue
    if not total:
        return f"{date}에 {market_txt} 거래대금 데이터가 없습니다"
    
    value = f"{int(total):,}원"
    return f"{date}에 {market_txt} 거래대금은 {value} 입니다."

# ─────────────────────────── 2. 상승/하락/거래 종목 수 ───────────────────────────
def _updown_count(date: str, market: str|None, direction: str) -> int | None:
    """direction ∈ {'상승','하락'}"""
    tickers = _universe(market)
    df = _download(tuple(tickers), start=date, end=date, interval="1d") # 당일만
    if df.empty:
        return None

    inc = 0
    for t in tickers:
        try:
            today_c =   _slice_single(df, t)["Close"].iloc[0]
            vol =       _slice_single(df, t)["Volume"].iloc[0]
            if pd.isna(today_c) or pd.isna(vol) or vol == 0:
                continue
            _, prev_c = _find_prev_close(t, date)
            if not prev_c:
                continue
            if (today_c > prev_c and direction == "상승") or (today_c < prev_c and direction == "하락"):
                inc += 1
        except KeyError:
            continue
    return inc

def _traded_count(date: str, market: str) -> str:
    tickers = _universe(market)
    df = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df.empty:
        return None
    cnt = 0
    for t in tickers:
        try:
            sub = _slice_single(df, t)          # df에 없으면 KeyError
        except KeyError:
            continue                            # 데이터 미존재 → 패스

        if "Volume" not in sub.columns:
            continue
        v = sub["Volume"].iloc[0]
        if pd.isna(v) or v == 0:
            continue
        cnt += 1

    return cnt

# ─────────────────────────── 3. 시장 순위 ───────────────────────────
def _answer_volume_top(date: str, market: str|None, n: int) -> str:
    tickers = _universe(market)
    top = get_volume_top(tickers, date, n)
    if not top.any():
        return f"{date} 데이터 없음"
    if n == 1:
        t, v = top.index[0], int(top.iloc[0])
        return f"{TICK2NAME.get(t, t)} ({v:,}주)"
    names = [TICK2NAME.get(t, t) for t in top.index[:n]]
    return ", ".join(names)

def _answer_top_mover(date: str, market: str|None, direction: str, n: int) -> str:
    tickers = _universe(market)
    df_today = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df_today.empty:
        return f"{date} 데이터 없음"

    pct: Dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df_today, t)
            today_c = sub["Close"].iloc[0]
            vol     = sub["Volume"].iloc[0]
            if pd.isna(today_c) or pd.isna(vol) or vol == 0:
                continue
            _, prev_c = _find_prev_close(t, date)
            if prev_c is None or pd.isna(prev_c) or prev_c == 0:
                continue
            change = (today_c - prev_c) / prev_c * 100
            if pd.isna(change) or math.isinf(change):
                continue
            pct[t] = change
        except Exception:
            continue
    if not pct:
        return f"{date} 데이터 없음"

    rank = sorted(pct.items(), key=lambda x: x[1], reverse=(direction == "상승률"))[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in rank)

def _answer_top_price(date: str, market: str|None, n: int) -> str:
    tickers = _universe(market)
    df = _download(tuple(tickers), start=date, end=date, interval="1d")
    if df.empty:
        return f"{date} 데이터 없음"
    closes: dict[str, float] = {}
    for t in tickers:
        try:
            sub = _slice_single(df, t)        # 티커 없으면 KeyError
        except KeyError:
            continue                           # 데이터 미존재 → 패스

        if sub.empty or _is_zero_volume(sub):
            continue
        close_val = sub["Close"].iloc[0] if "Close" in sub.columns else None
        if pd.isna(close_val):
            continue
        closes[t] = float(close_val)
    if not closes:
        return f"{date} 데이터 없음"
    top = sorted(closes.items(), key=lambda x: x[1], reverse=True)[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in top)

def _batch_ohlcv(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    return _download(tuple(tickers), start=start, end=end, interval="1d")

def _calc_volatility(ticker: str, date: str, lookback: int = 60) -> float | None:
    """
    • 60 거래일 일간 수익률 표준편차 × √252
    • 캐싱은 _download() ↔ yf_cache 로컬파일 단계에서 이미 수행
    """
    start = _nth_prev_bday(date, lookback + 10)
    df = _download((ticker,), start=start, end=date, interval="1d")
    if df.empty or (ticker, "Adj Close") not in df.columns:
        return None
    close = df[ticker, "Adj Close"].dropna()
    if date not in close.index or len(close) < lookback:
        return None
    window = close.loc[:date].iloc[-lookback:]
    return window.pct_change().dropna().std() * math.sqrt(252)

def _calc_beta(ticker: str,
               date: str,
               market_hint: str | None = None,
               lookback: int = 60) -> float | None:
    """
    • market_hint == "KOSPI"/"KOSDAQ" 이면 강제 사용  
    • None 이면 티커 접미사(.KS/.KQ)로 시장 판단  
    """
    if market_hint == "KOSPI" or (market_hint is None and ticker.endswith(".KS")):
        idx_tic = "^KS11"
    elif market_hint == "KOSDAQ" or (market_hint is None and ticker.endswith(".KQ")):
        idx_tic = "^KQ11"
    else:                         # 알 수 없으면 KOSPI 기준 fallback
        idx_tic = "^KS11"

    start = _nth_prev_bday(date, lookback + 10)
    df = _download((ticker, idx_tic), start=start, end=date, interval="1d")
    try:
        p  = df[ticker , "Adj Close"].dropna()
        m  = df[idx_tic, "Adj Close"].dropna()
    except KeyError:
        return None
    if date not in p.index or len(p) < lookback or len(m) < lookback:
        return None

    joined = pd.concat([p, m], axis=1, join="inner").iloc[-lookback:]
    if joined.shape[0] < lookback or joined.iloc[:, 1].var() == 0:
        return None
    cov  = np.cov(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1]
    beta = cov / joined.iloc[:, 1].var()
    return None if math.isinf(beta) or math.isnan(beta) else beta

# ② 벡터화 변동성
def _volatility_all(date: str, tickers: list[str], lookback=60) -> dict[str, float]:
    start = _nth_prev_bday(date, lookback + 10)
    df = _batch_ohlcv(tickers, start, date)
    if df.empty:
        return {}
    # Adj Close 열이 하나도 없을 수도 있으므로 예외 처리
    try:
        closes = df.xs("Adj Close", level=1, axis=1).dropna(how="all")
    except KeyError:
        return {}

    pct = closes.pct_change().dropna(how="all")
    if pct.empty or len(pct) < lookback:
        return {}

    std = pct.rolling(lookback).std()
    if std.empty:           # window 부족 → 변동성 계산 불가
        return {}

    vol = std.iloc[-1] * math.sqrt(252)
    return vol.dropna().to_dict()

def _beta_all(date: str,
              tickers: list[str],
              market_hint: str | None,
              lookback: int = 60) -> dict[str, float]:
    """
    • market_hint == "KOSPI"  → 전체 티커를 ^KS11 기준으로 계산  
    • market_hint == "KOSDAQ" → 전체 티커를 ^KQ11 기준으로 계산  
    • None → 각 티커 접미사(.KS/.KQ)에 따라 자동 매핑
    """
    idx_map = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    start   = _nth_prev_bday(date, lookback + 10)

    # ── 두 지수 + 모든 티커를 한 번에 다운로드
    df = _download(tuple(tickers) + ("^KS11", "^KQ11"), start=start, end=date, interval="1d")
    if df.empty:
        return {}

    try:
        closes = df.xs("Adj Close", level=1, axis=1).dropna(how="all")
    except KeyError:
        return {}
    rets = closes.pct_change().dropna(how="all")
    if rets.empty:
        return {}
    ks_ret = rets.get("^KS11")
    kq_ret = rets.get("^KQ11")
    betas: dict[str, float] = {}

    for t in tickers:
        if t not in rets.columns:
            continue
        tic_ret = rets[t].dropna()
        # ── 지수 선택
        if market_hint == "KOSPI":
            idx_ret = ks_ret
        elif market_hint == "KOSDAQ":
            idx_ret = kq_ret
        else:  # auto
            idx_ret = kq_ret if t.endswith(".KQ") else ks_ret

        if idx_ret is None:
            continue
        joined = pd.concat([tic_ret, idx_ret], axis=1, join="inner").iloc[-lookback:]
        if joined.shape[0] < lookback or joined.iloc[:, 1].var() == 0:
            continue
        cov  = np.cov(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1]
        beta = cov / joined.iloc[:, 1].var()
        if not math.isinf(beta) and not math.isnan(beta):
            betas[t] = beta

    return betas
    
def _answer_volatility_rank(date, market, n, order="low"):
    tk = _universe(market)
    vol = _volatility_all(date, tk)
    ranked = sorted(vol.items(), key=lambda x: x[1], reverse=(order=="high"))[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in ranked)

def _answer_beta_rank(date, market, n, order="low"):
    tk = _universe(market)
    bet = _beta_all(date, tk, market)
    ranked = sorted(bet.items(), key=lambda x: x[1], reverse=(order=="high"))[:n]
    return ", ".join(TICK2NAME.get(t, t) for t, _ in ranked)


def _answer_risk_single(date: str, tickers: Iterable[str], metrics: Iterable[str],
                        market: str | None, api_key: str) -> str:
    results = []
    for raw in tickers:
        try:
            info = to_ticker(raw, with_name=True, api_key=api_key)          # 한글명 → 코드
        except Exception:
            results.append(f"{raw}: 티커 인식 실패")
            continue

        tic, name = info.ticker, info.name
        parts: list[str] = []
        if "변동성" in metrics:
            v = _calc_volatility(tic, date)
            if v is not None:
                parts.append(f"변동성 {v:.3f}")
        if "베타" in metrics:
            b = _calc_beta(tic, date, market)
            if b is not None:
                parts.append(f"베타 {b:.2f}")

        results.append(
            f"{name}: " + ", ".join(parts) if parts else f"{name}: 데이터 없음"
        )

    # ── 문장 형식 맞추기 ─────────────────────────────
    if len(results) == 1:
        line = results[0]
        if ":" in line:
            name, vals = map(str.strip, line.split(":", 1))
            return f"{date}에 {name}의 {vals} 입니다."
        return f"{date}에 {line}"
    else:
        bullet = "\n".join(f"- {r}" for r in results)
        return f"{date} 기준 종목별 지표는 다음과 같습니다.\n{bullet}"

# ─────────────────────────── 메인 엔트리 ───────────────────────────
def handle(_: str, p: dict, api_key: str) -> str:
    """
    Router 로부터 (원본질문, params) 을 받는다.
    원본 질문은 로그·후행 질문 생성용으로만 사용하므로
    여기선 params 만 쓰면 된다.
    """
    task = p["task"]
    msg = _holiday_msg(p["date"])
    if msg:
        return msg
    # 1) 단순가격/지수/거래대금
    if task == "단순조회":
        metric = p["metrics"][0]
        metric_set = set(p["metrics"])
        if metric_set <= {"종가","시가","고가","저가","pct_change","거래량","변동성","베타"}:
            if len(p["tickers"]) > 1 or len(metric_set) > 1:
                return _answer_multi(p, api_key)
            if metric_set & {"변동성", "베타"}:
                return _answer_risk_single(p["date"], p["tickers"], p["metrics"], p.get("market"), api_key)
            if metric_set <= {"종가","시가","고가","저가","pct_change","거래량"}:
                return _answer_price(p, api_key)
        if metric == "지수":
            mkt = p.get("market")
            if mkt == "KOSPI":
                return _answer_kospi_index(p["date"])
            if mkt == "KOSDAQ":
                return _answer_kosdaq_index(p["date"])
            return "KOSPI와 KOSDAQ 중 시장을 지정해주세요."
        if metric == "거래대금" and not p.get("tickers"):
            return _answer_total_trading_value(p["date"],p.get("market"))
        return f"지원하지 않는 지표입니다."

    # 2) 종목 수
    if task in ("상승종목수", "하락종목수", "거래종목수"):
        market = p.get("market")
        market_txt = f"{market}에서 " if market else ""
        if task == "상승종목수":
            cnt = _updown_count(p["date"], market, "상승")
            return f"{p['date']}에 {market_txt}상승한 종목은 {cnt:,}개 입니다." if cnt is not None else f"{p['date']}의 데이터가 없습니다."
        if task == "하락종목수":
            cnt = _updown_count(p["date"], market, "하락")
            return f"{p['date']}에 {market_txt}하락한 종목은 {cnt:,}개 입니다." if cnt is not None else f"{p['date']}의 데이터가 없습니다."
        if task == "거래종목수":
            cnt = _traded_count(p["date"], market)
            return f"{p['date']}에 {market_txt}거래된 종목은 {cnt:,}개 입니다." if cnt is not None else f"{p['date']}의 데이터가 없습니다."

    # 3) 시장순위
    if task == "시장순위":
        metric = p["metrics"][0]            # 거래량·상승률·하락률·가격
        n      = p.get("rank_n") or 1
        market = p.get("market")
        market_txt = f"{market}에서 " if market else ""
        order  = (p.get("conditions") or {}).get("order", "low")
        order_txt = f" 높은 종목" if order == "high" else " 낮은 종목"

        if metric == "거래량":
            names = _answer_volume_top(p["date"], market, n)
        elif metric in ("상승률", "하락률"):
            names = _answer_top_mover(p["date"], market, metric, n)
        elif metric == "가격":
            names = _answer_top_price(p["date"], market, n)
        elif metric == "변동성":
            names = _answer_volatility_rank(p["date"], market, n, order)
        elif metric == "베타":
            names = _answer_beta_rank(p["date"], market, n, order)

        else:
            return f"지원하지 않는 지표입니다."

        if "데이터 없음" in names:
            return f"{p['date']}에 데이터가 없습니다."
        if n == 1:
            if metric in {"변동성", "베타"}:
                return f"{p['date']}에 {market_txt}{metric}이(가) 가장{order_txt}은 {names} 입니다."
            return f"{p['date']}에 {market_txt}{metric}이(가) 가장 높은 종목은 {names} 입니다."
        return (
            f"{p['date']}에 {market_txt}{metric} 상위 {n}개 종목은 다음과 같습니다.\n"
            f"{names}"
        )

    return "질문을 이해하지 못했습니다."