"""
Ambiguous query parser
"""
from __future__ import annotations

import re
from typing import Dict
# from app.llm_bridge import extract_ambiguous_params  # HCX fallback

# __all__ = ["parse_ambiguous", "AmbiguousQuery"]

# ───────────── 내부 정규식 파서 ─────────────
_DEF_DAYS, _DEF_TOP = 20, 10

def _regex_parse(q: str) -> Dict[str, int | str]:
    q = q.lower().replace("%", "퍼센트")

    # intent
    if re.search(r"(많이\s*오르[ㄴ다]?|상승|급등)", q):
        intent = "top_gainers"
    elif re.search(r"(떨어진|하락|고점 대비)", q):
        intent = "off_peak"
    else:
        return {}

    # 기간
    m_days = re.search(r"(\d+)\\s*일", q)
    period_days = int(m_days.group(1)) if m_days else _DEF_DAYS

    # top_n
    m_top = re.search(r"(\\d+)\\s*종목", q)
    top_n = int(m_top.group(1)) if m_top else _DEF_TOP

    # threshold
    m_pct = re.search(r"(\\d+)\\s*퍼센트", q)
    threshold_pct = int(m_pct.group(1)) if m_pct else 0

    return {
        "intent": intent,
        "period_days": period_days,
        "top_n": top_n,
        "threshold_pct": threshold_pct,
    }

# ───────────── Public API ─────────────
class AmbiguousQuery(dict):
    __getattr__ = dict.__getitem__  # dot-access

# def parse_ambiguous(question: str) -> AmbiguousQuery | None:
#     # 1차 정규식 → 실패 시 HCX(JSON) 파서
#     params = _regex_parse(question) or extract_ambiguous_params(question)
#     if not params:
#         return None
#     return AmbiguousQuery(params)
