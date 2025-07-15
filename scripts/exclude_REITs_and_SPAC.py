# 리츠 목록: https://www.kareit.or.kr/invest/page2.php

import pandas as pd

def filter_tickers(
    all_csv_path: str,
    reits_txt_path: str,
    output_csv_path: str
):
    # 1) 전체 종목 로드
    df = pd.read_csv(all_csv_path, encoding="utf-8-sig")
    # 종목명 공백 제거
    df["종목명"] = df["종목명"].astype(str).str.strip()

    # 2) REITs 제외 리스트 로드
    with open(reits_txt_path, encoding="utf-8") as f:
        reits = {line.strip() for line in f if line.strip()}

    # 3) 필터링
    mask_not_reit = ~df["종목명"].isin(reits)
    mask_not_spac = ~df["종목명"].str.contains("스팩", na=False)
    filtered = df[mask_not_reit & mask_not_spac].copy()

    # 4) 저장
    filtered.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
    print(f"[완료] {output_csv_path} · 종목 수: {len(filtered)}")


if __name__ == "__main__":
    # 처리할 시장 목록
    markets = ["kospi", "kosdaq"]
    base_dir = "."           # CSV 파일이 있는 디렉토리
    reits_file = "./data/REITs.txt"

    for m in markets:
        all_file = f"{base_dir}/{m}_tickers_all.csv"
        out_file = f"{base_dir}/{m}_tickers.csv"
        filter_tickers(all_file, reits_file, out_file)
