# run export_tickers.py -> run exclude_REITs_and_SPAC.py

import pandas as pd
import yfinance as yf
from tqdm import tqdm
from datetime import datetime
from pykrx import stock

# pykrx에서 쓰는 시장 코드 매핑
MARKETS = {
    "kospi": {"krx": "KOSPI",   "suffix": ".KS"},
    "kosdaq": {"krx": "KOSDAQ", "suffix": ".KQ"},
}

def fetch_krx_list(market: str) -> pd.DataFrame:
    """
    pykrx를 이용해 market("KOSPI"/"KOSDAQ")의
    모든 종목(보통주+우선주 등) 목록을 가져와
    종목코드(str), 종목명을 반환
    """
    # 오늘 날짜 기준 YYYYMMDD 포맷
    today = datetime.today().strftime("%Y%m%d")
    # 티커 리스트와 이름 리스트
    tickers = stock.get_market_ticker_list(today, market=market)
    names   = [stock.get_market_ticker_name(t) for t in tickers]

    df = pd.DataFrame({
        "종목코드": tickers,
        "종목명": names
    })
    return df

def optional_yahoo_check(df: pd.DataFrame, suffix:str, keep_only_tradable=True) -> pd.DataFrame:
    """
    yfinance에 실제 존재하는 .KS 티커만 남기려면 verify_on_yahoo=True 로 호출
    """
    if not keep_only_tradable:
        df["종목코드"] = df["종목코드"] + suffix
        return df

    valid = []
    for code, name in tqdm(df.itertuples(index=False), total=len(df), desc=f"확인 중 ({suffix} 쿼리)"):
        code_full = code + suffix
        try:
            yf.Ticker(code_full).info
            valid.append((code_full, name))
        except Exception:
            pass
    return pd.DataFrame(valid, columns=["종목코드", "종목명"])

def build_all_csvs(out_dir=".", verify_on_yahoo=False):
    """
    MARKETS에 정의된 각 시장별로 CSV 파일 생성
    → kospi_tickers.csv, kosdaq_tickers.csv
    """
    for name, info in MARKETS.items():
        df = fetch_krx_list(info["krx"])
        if verify_on_yahoo:
            df = optional_yahoo_check(df, suffix=info["suffix"], keep_only_tradable=True)
        else:
            df["종목코드"] = df["종목코드"] + info["suffix"]

        path = f"{out_dir}/{name}_tickers.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[완료] {path} · 종목 수: {len(df)}")

if __name__ == "__main__":
    # verify_on_yahoo=True 로 실행하면 Yahoo에 존재하는 종목만 필터링 -> 차이 없음.
    build_all_csvs(out_dir=".", verify_on_yahoo=False)
