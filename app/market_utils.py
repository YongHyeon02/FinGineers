# app/market_utils.py
import re
from functools import lru_cache
from app.universe import NAME_BY_TICKER

# ① 패턴: '...우', '...우A/B', 또는 '스팩', '리츠' (어디에 있든)
_EXCLUDE_PAT = re.compile(r"(스팩|리츠$)", re.UNICODE)

def is_common_share(ticker: str) -> bool:
    """
    True  → 보통주
    False → 우선주, 스팩, 리츠 등
    """
    name = NAME_BY_TICKER.get(ticker)
    if name is None:          # CSV에 없는 티커 (해외·OTC 등) → 보통주 취급
        return True
    return _EXCLUDE_PAT.search(name) is None
