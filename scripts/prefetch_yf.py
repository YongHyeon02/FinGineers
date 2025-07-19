# scripts/prefetch_yf.py
import argparse
from pathlib import Path
from app.universe import KOSPI_TICKERS, KOSDAQ_TICKERS, NAME_BY_TICKER, INDEX_TICKERS
from app.yf_cache import assure

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    args = p.parse_args()

    tickers = tuple(KOSPI_TICKERS + KOSDAQ_TICKERS + INDEX_TICKERS)
    rate_limited = assure(tickers, args.start, args.end, write_cache=True)

    # ── 영구 실패 목록 기록 ──────────────────────────
    permanent = getattr(assure, "permanent_fail", [])
    if permanent:
        Path("permanent_failures.txt").write_text("\n".join(permanent))

    # ── 레이트-리밋 종목 기록 (remaining.txt) ───────
    if rate_limited:
        err_map = getattr(assure, "error_log", {})
        lines = [
            f"{t}\t{NAME_BY_TICKER.get(t, '')}\t{err_map.get(t, 'YFRateLimitError')}"
            for t in rate_limited
        ]
        Path("remaining.txt").write_text("\n".join(lines))
        print(f"[WARN] {len(rate_limited)} tickers rate-limited → remaining.txt")
    else:
        print("[OK] Rate-limit 없이 모든 티커 수집 완료")


# 예) 2025-07-01~07-14 선-저장
# python3 -m scripts.prefetch_yf --start 2025-07-01 --end 2025-07-14

# CLI 자동 반복 모드(선택)
# until python -m scripts.prefetch_yf --start 2025-07-01 --end 2025-07-14 | grep -q "\[OK\]"; do
#     sleep 10  # 잠시 쉬었다 재시도
# done