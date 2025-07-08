# scripts/export_tickers.py

from pykrx import stock
import pandas as pd

def export_market_tickers(
    market: str,
    filename: str,
    date: str | None = None,
    encoding: str = "utf-8-sig"
) -> None:
    """
    특정 시장의 전체 종목(티커+종목명)을 CSV로 저장합니다.

    Args:
      market: "KOSPI" 또는 "KOSDAQ"
      filename: 저장할 CSV 파일 경로 (예: "kospi.csv")
      date: 조회일자(YYYYMMDD). None이면 오늘 기준.
      encoding: CSV 인코딩 (기본 "utf-8-sig")
    """
    # 1) 조회 날짜 결정
    if date is None:
        date = pd.Timestamp.today().strftime("%Y%m%d")

    # 2) 티커 리스트 가져오기
    tickers = stock.get_market_ticker_list(market=market, date=date)

    # 3) 종목명 쌍 생성
    data = [
        {"종목코드": t, "종목명": stock.get_market_ticker_name(t)}
        for t in tickers
    ]

    # 4) DataFrame 생성 및 CSV 저장
    df = pd.DataFrame(data)
    df = df.sort_values("종목코드").reset_index(drop=True)
    df.to_csv(filename, index=False, encoding=encoding)

    print(f"✅ {market} {date} 기준 {len(df)}개 종목을 '{filename}'로 저장했습니다.")


if __name__ == "__main__":
    export_market_tickers("KOSPI", "kospi_tickers.csv")
    export_market_tickers("KOSDAQ", "kosdaq_tickers.csv")
