# config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"          # ⇦ CSV를 두는 폴더
CACHE_DIR = DATA_DIR / "yf_cache"
INFO_DIR = DATA_DIR / "info_cache"
KOSPI_CSV  = DATA_DIR / "kospi_tickers.csv"
KOSDAQ_CSV = DATA_DIR / "kosdaq_tickers.csv"
ALIAS_CSV = DATA_DIR / "alias_tickers.csv"

# ─────────────  티커 디스앰비규에이션  ─────────────
TOP_K_FUZZY       = 3          # fuzzy 로 뽑을 후보 수
TOP_K_EMBED       = 3          # 임베딩으로 뽑을 후보 수
HCX_CONF_THRESHOLD = 0.82      # hcx confidence ≥ 0.82 → 확정

# ─────────────  공용 예외  ─────────────
class AmbiguousTickerError(Exception):
    """티커 후보가 모호하여 사용자 재질문이 필요한 경우"""
    def __init__(self, alias: str, candidates: list[str]):
        self.alias = alias
        self.candidates = candidates
        super().__init__(f"Ambiguous ticker for {alias}: {candidates}")