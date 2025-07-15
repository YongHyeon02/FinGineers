# scripts/prefetch_yf.py
import argparse, pandas as pd
from app.universe import KOSPI_TICKERS, KOSDAQ_TICKERS
from app.yf_cache import assure

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end",   required=True)
    args = p.parse_args()

    tickers = tuple(KOSPI_TICKERS + KOSDAQ_TICKERS)
    remaining = assure(tickers, args.start, args.end)
    if remaining:
        print(f"[WARN] {len(remaining)} tickers still missing due to rate-limit.")
        # 필요하면 파일에 기록
        Path("remaining.txt").write_text("\n".join(remaining))
    else:
        print("[OK] all tickers fetched.")



# 예) 2025-07-01~07-14 선-저장
# python -m scripts.prefetch_yf --start 2025-07-01 --end 2025-07-14

# CLI 자동 반복 모드(선택)
# until python -m scripts.prefetch_yf --start 2025-07-01 --end 2025-07-14 | grep -q "\[OK\]"; do
#     sleep 10  # 잠시 쉬었다 재시도
# done