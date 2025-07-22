from __future__ import annotations
from typing import Literal

from app.signal_utils import (
    detect_rsi,
    detect_volume_spike,
    detect_ma_break,
    detect_bollinger_touch,
    count_crosses,
    list_crossed_stocks,
    three_pattern_dates,
    three_pattern_tickers,
    three_pattern_counts,
)
from app.ticker_lookup import to_ticker

SignalType = Literal[
    "RSI", "거래량급증", "이동평균돌파", "볼린저터치", 
    "적삼병", "흑삼병"
]

def handle(_: str, p: dict) -> str:
    try:
        task = p["task"]
        cond = p.get("conditions", {})

        # ───────────────────────────────
        # Task 1: 시그널 감지 (종목 필터링)
        # ───────────────────────────────
        if task == "시그널감지":
            signal_type = _to_signal_type(p.get("metrics", []))
            if signal_type == "RSI":
                return detect_rsi(p["date"], cond)
            elif signal_type == "거래량급증":
                return detect_volume_spike(p["date"], cond)
            elif signal_type == "이동평균돌파":
                return detect_ma_break(p["date"], cond)
            elif signal_type == "볼린저터치":
                return detect_bollinger_touch(p["date"], cond)
            elif signal_type in ("적삼병", "흑삼병"):
                from_date, to_date = p["date_from"], p["date_to"]
                if p.get("tickers"):
                    tk = to_ticker(p["tickers"][0])
                    return three_pattern_dates(tk, signal_type, from_date, to_date)
                market = p.get("market")
                return three_pattern_tickers(signal_type, from_date, to_date, market)
                
            else:
                return f"[ERROR] 알 수 없는 시그널 유형입니다: {signal_type}"
            
        # ───────────────────────────────
        # Task 2: 시그널 횟수 (단일 종목)
        # ───────────────────────────────
        elif task == "시그널횟수":
            name = p["tickers"][0] if p["tickers"] else None
            if not name:
                return "[ERROR] 종목명이 필요합니다."
            from_date, to_date = p["date_from"], p["date_to"]
            signal_type = _to_signal_type(p.get("metrics", []))
            if signal_type in ("적삼병", "흑삼병"):
                tk = to_ticker(name)
                return three_pattern_counts(tk, signal_type, from_date, to_date)
            
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

        # ───────────────────────────────
        # Task 3: 시그널 종목 리스트
        # ───────────────────────────────
        elif task == "시그널종목":
            from_date, to_date = p["date_from"], p["date_to"]
            side = cond.get("side")
            market = p.get("market")
            signal_type = _to_signal_type(p.get("metrics", []))
            if signal_type in ("적삼병", "흑삼병"):
                return three_pattern_tickers(signal_type, from_date, to_date, market)

            tickers = list_crossed_stocks(from_date, to_date, cond)
            if not tickers:
                return "조건에 맞는 종목 없음"
            cross_txt = "골든크로스" if side == "golden" else "데드크로스"
            return f"{from_date}부터 {to_date}까지 {cross_txt}가 발생한 종목은 다음과 같습니다.\n{', '.join(tickers)}"

        else:
            return f"[ERROR] 알 수 없는 task: {task}"

    except Exception as e:
        return f"[ERROR] 처리 중 오류: {e}"


def _to_signal_type(metrics: list[str]) -> str:
    if not metrics:
        raise ValueError("metrics가 비어 있습니다.")
    return metrics[0]
