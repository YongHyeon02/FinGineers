# 시그널 감지 (이동평균 돌파 등)
# app/task_handlers/task3_signal.py
from __future__ import annotations

import re
from typing import Literal

from app.signal_utils import *

SignalType = Literal[
    "RSI_OVERBOUGHT", "RSI_OVERSOLD",
    "VOLUME_SPIKE",
    "MA5_BREAK", "MA20_BREAK", "MA60_BREAK",
    "BOLLINGER_UPPER", "BOLLINGER_LOWER",
    "GOLDEN_CROSS_COUNT", "DEAD_CROSS_COUNT",
    "GOLDEN_CROSS_LIST", "DEAD_CROSS_LIST",
]

def handle(question: str) -> str:
    parsed = parse_signal_question(question)
    if parsed is None:
        return "[ERROR] 파싱 실패: 시그널 질문이 아닙니다."
    try:
        return handle_signal_query(**parsed)
    except Exception as e:
        return f"[ERROR] 처리 중 오류: {e}"

def handle_signal_query(
    signal_type: SignalType,
    date: str | None = None,
    threshold: float | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    target_name: str | None = None,
    window: int | None = None,
) -> str:
    if signal_type.startswith("RSI"):
        return detect_rsi(signal_type, date, threshold)
    elif signal_type == "VOLUME_SPIKE":
        return detect_volume_spike(date, threshold, window)
    elif "MA" in signal_type:
        return detect_ma_break(signal_type, date, threshold)
    elif "BOLLINGER" in signal_type:
        return detect_bollinger_touch(signal_type, date)
    elif signal_type.endswith("CROSS_COUNT"):
        return count_crosses(signal_type, from_date, to_date, target_name)
    elif signal_type.endswith("CROSS_LIST"):
        return list_crossed_stocks(signal_type, from_date, to_date)
    elif signal_type == "CROSS_COUNT_BOTH":
        g = count_crosses("GOLDEN_CROSS_COUNT", from_date, to_date, target_name)
        d = count_crosses("DEAD_CROSS_COUNT", from_date, to_date, target_name)
        return f"데드크로스 {d}, 골든크로스 {g}"
    else:
        return "[ERROR] 알 수 없는 시그널 타입입니다."

def parse_signal_question(q: str) -> dict | None:
    q = q.strip()

    # RSI 과매수 / 과매도 (우선적으로 검사)
    if m := re.search(r"(.+?)에 RSI가 (\d+)[^\d\n]+과매수 종목", q):
        return dict(signal_type="RSI_OVERBOUGHT", date=m[1], threshold=float(m[2]))
    if m := re.search(r"(.+?)에 RSI가 (\d+)[^\d\n]+과매도 종목", q):
        return dict(signal_type="RSI_OVERSOLD", date=m[1], threshold=float(m[2]))

    # 거래량 급증
    if m := re.search(r"(.+?)에 거래량.+?(\d+)일 평균 대비 (\d+)% 이상", q):
        return dict(signal_type="VOLUME_SPIKE", date=m[1], window=int(m[2]), threshold=float(m[3])        )

    # MA 돌파
    if m := re.search(r"(.+?)에 종가가 (\d+)일 이동평균보다 ([\d.]+)% 이상", q):
        return dict(signal_type=f"MA{m[2]}_BREAK", date=m[1], threshold=float(m[3]))

    # 볼린저 밴드 상단/하단
    if m := re.search(r"(.+?)에 볼린저 밴드 (상단|하단)", q):
        signal_type = "BOLLINGER_UPPER" if m[2] == "상단" else "BOLLINGER_LOWER"
        return dict(signal_type=signal_type, date=m[1])

    # 골든/데드크로스 횟수
    if m := re.search(r"(.+?) ?(\d{4}-\d{2}-\d{2})부터 (\d{4}-\d{2}-\d{2})까지 (.+?)가 몇번 발생", q):
        both = "골든" in m[4] and "데드" in m[4]
        if both:
            return dict(signal_type="CROSS_COUNT_BOTH", target_name=m[1], from_date=m[2], to_date=m[3])
        cross_type = "GOLDEN_CROSS_COUNT" if "골든" in m[4] else "DEAD_CROSS_COUNT"
        return dict(signal_type=cross_type, target_name=m[1], from_date=m[2], to_date=m[3])

    # 골든/데드크로스 종목 리스트
    if m := re.search(r"(\d{4}-\d{2}-\d{2})부터 (\d{4}-\d{2}-\d{2})까지 (.+?)가 발생한 종목", q):
        cross_type = "GOLDEN_CROSS_LIST" if "골든" in m[3] else "DEAD_CROSS_LIST"
        return dict(signal_type=cross_type, from_date=m[1], to_date=m[2])

    return None

