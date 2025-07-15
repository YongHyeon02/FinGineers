# app/yf_cache.py
import yfinance as yf
from pathlib import Path
import pandas as pd
import time, random
from typing import List, Tuple, Dict, Set
from config import CACHE_DIR
from yfinance import Ticker

try:                    # 0.2.28+  (공식 위치)
    from yfinance.exceptions import (
        YFRateLimitError, YFTzMissingError, YFPricesMissingError,
    )
except ImportError:     # 0.2.17 ~ 0.2.27
    try:
        from yfinance.shared import (
            YFRateLimitError, YFTzMissingError, YFPricesMissingError,
        )
    except ImportError: # 0.2.16 이하
        from yfinance.shared._utils import (
            YFRateLimitError, YFTzMissingError, YFPricesMissingError,
        )

# ────────────────────────────────────────────────────────────────
# 1) 기본 유틸
# ────────────────────────────────────────────────────────────────
def _path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker}.parquet"

def load(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    """start~end 영업일이 모두 들어 있으면 DataFrame, 아니면 None"""
    fp = _path(ticker)
    if not fp.exists():
        return None
    df = pd.read_parquet(fp).loc[start:end]
    need = pd.date_range(start, end, freq="B")
    if set(need).issubset(df.index):
        return df
    return None

def save_or_append(ticker: str, df_new: pd.DataFrame) -> None:
    """
    기존 데이터와 병합해 중복(날짜) 제거 후 저장.
    최신 값(새로 받은 값)을 남기고 정렬.
    """
    fp = _path(ticker)
    if fp.exists():
        df_old = pd.read_parquet(fp)
        combined = pd.concat([df_old, df_new])
    else:
        combined = df_new.copy()

    combined = combined[~combined.index.duplicated(keep="last")]
    combined.sort_index(inplace=True)
    combined.to_parquet(fp)

def assure(
    tickers: Tuple[str, ...] | List[str],
    start: str,
    end: str,
    *,
    max_retry: int = 3,
    chunk: int = 100,
    pause: float = 2.0,
) -> List[str]:
    """
    주어진 기간의 일별 OHLCV·볼륨 데이터를 캐싱한다.
    반환값은 *레이트-리밋 때문에 아직까지 못 받은* 티커 목록이다.
    """
    todo: List[str] = [t for t in tickers if load(t, start, end) is None]

    permanent_fail: List[str] = []   # 상장폐지·타임존 미지원 등
    error_log: Dict[str, str] = {}   # 티커 → 오류 메시지
    rate_limited: Set[str] = set()   # <-- ★ 핵심! 재시도 대상

    for attempt in range(1, max_retry + 1):
        next_round: List[str] = []

        for i in range(0, len(todo), chunk):
            batch = todo[i:i+chunk]

            # ① 1차 배치-다운로드 (keep_errors 없음)
            df = yf.download(
                batch, start=start, end=end,
                interval="1d", group_by="ticker",
                progress=False, threads=True, auto_adjust=False,
            )

            # ② DataFrame에 포함된 티커 집합
            if isinstance(df.columns, pd.MultiIndex):
                present = set(df.columns.get_level_values(0))
            else:  # batch에 1개만 있을 때
                present = set(batch) if not df.empty else set()

            missing = [t for t in batch if t not in present]

            # ③ 누락 티커를 단건으로 재확인
            for t in missing:
                try:
                    sub = Ticker(t).history(
                        start=start, end=end,
                        interval="1d", auto_adjust=False,
                        raise_errors=True,        # history()는 지원
                    )
                except YFRateLimitError as e:
                    rate_limited.add(t)
                    error_log[t] = str(e)
                    next_round.append(t)
                    continue
                except (YFPricesMissingError, YFTzMissingError) as e:
                    permanent_fail.append(t)
                    error_log[t] = str(e)
                    continue
                except Exception as e:
                    permanent_fail.append(t)
                    error_log[t] = f"Other error: {e}"
                    continue

                # 데이터가 정상으로 내려온 경우
                if sub.empty or sub.isna().all().all():
                    permanent_fail.append(t)
                    error_log[t] = "No data / all-NaN"
                    continue
                save_or_append(t, sub)

            # 이미 df에 있었던 티커는 그대로 저장
            if isinstance(df.columns, pd.MultiIndex):
                for t in present:
                    sub = df[t]
                    if not sub.empty:
                        save_or_append(t, sub)
            elif present:
                save_or_append(batch[0], df)

        # ── 루프 종료 조건 ───────────────────────────────
        if not next_round:
            break

        todo = next_round
        time.sleep(pause * (1.5 ** (attempt - 1)) + random.uniform(0, 1))

    # 외부 참조용 속성
    assure.permanent_fail = permanent_fail
    assure.error_log = error_log
    assure.rate_limited = list(rate_limited)

    return list(rate_limited)        # ★ 레이트-리밋 종목만 반환