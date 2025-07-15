# config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"          # ⇦ CSV를 두는 폴더
CACHE_DIR = DATA_DIR / "yf_cache"
KOSPI_CSV  = DATA_DIR / "kospi_tickers.csv"
KOSDAQ_CSV = DATA_DIR / "kosdaq_tickers.csv"