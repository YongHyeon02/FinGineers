TASK_REQUIRED = {
    "단순조회":    {"date", "metrics", "tickers"},      # metrics=1+, ticker=1
    "시장순위":    {"date", "metrics", "rank_n"},       # rank_n ≥1
    "상승종목수":  {"date"},
    "하락종목수":  {"date"},
    "거래종목수":  {"date"},
}