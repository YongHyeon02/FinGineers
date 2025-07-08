# app/parsers.py
"""
자연어 의도 파싱 유틸 (Task4용)
현재는 '최근 많이 오른 주식', '고점 대비 하락' 등 모호 질문 감지만 수행
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class AmbiguousQuery:
    intent: str                  # "top_gainers" | "off_peak"
    period_days: int = 30        # 수익률 계산 기간
    top_n: int = 10              # 상위 N
    threshold_pct: float = 20.0  # 고점 대비 하락 %

# 의도 패턴(간단 버전). 필요 시 추가
_INTENT_PATTERNS = {
    "top_gainers": [
        r"(최근|요즘).*(\d+일)?\s*.*오른.*주식",
        r"(급등|상승).*주식",
    ],
    "off_peak": [
        r"고점.*떨어진.*주식",
        r"(낙폭|하락폭).*큰.*주식",
    ],
}


def parse_ambiguous(question: str) -> Optional[AmbiguousQuery]:
    """질문에서 모호 의도를 감지하고 파라미터 추출 (못 찾으면 None)"""
    q_no_space = question.replace(" ", "")
    for intent, patterns in _INTENT_PATTERNS.items():
        if any(re.search(p, q_no_space) for p in patterns):
            break
    else:
        return None  # 매칭 없음

    # 숫자 파라미터 샘플 추출
    days_m = re.search(r"최근\s*(\d+)\s*일", question)
    n_m    = re.search(r"(?:상위|top)\s*(\d+)", question, re.I)
    pct_m  = re.search(r"(\d+)\s*%", question)

    return AmbiguousQuery(
        intent=intent,
        period_days=int(days_m.group(1)) if days_m else 30,
        top_n=int(n_m.group(1)) if n_m else 10,
        threshold_pct=float(pct_m.group(1)) if pct_m else 20.0,
    )
