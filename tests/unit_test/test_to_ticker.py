# scripts/test_to_ticker.py

from app.ticker_lookup import to_ticker
from app.universe import NAME_BY_TICKER

def main():
    print("종목명을 입력하면 to_ticker 결과를 출력합니다. (종료: 빈 줄 입력)")
    while True:
        name = input("종목명 입력 ▶ ").strip()
        if not name:
            print("테스트 종료.")
            break
        try:
            ticker = to_ticker(name)
            kor_name = NAME_BY_TICKER.get(ticker, None)
            if kor_name:
                print(f"→ {name!r}  mapped to  {ticker} ({kor_name})\n")
            else:
                print(f"→ {name!r}  mapped to  {ticker}\n")
        except Exception as e:
            print(f"[ERROR] to_ticker 처리 중 예외 발생: {e}\n")

if __name__ == "__main__":
    main()
