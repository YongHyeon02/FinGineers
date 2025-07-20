TASK_REQUIRED = {
    "단순조회":    {"date", "metrics", "tickers"},      # metrics=1+, ticker=1
    "시장순위":    {"date", "metrics", "rank_n"},       # rank_n ≥1
    "상승종목수":  {"date"},
    "하락종목수":  {"date"},
    "거래종목수":  {"date"},
    "조건검색":    {"date","conditions"},
    "기간검색":    {"date_from","date_to","conditions"},
    "시그널감지":  {"date","metrics","conditions"},
    "시그널종목":  {"date_from","date_to","conditions"},
    "시그널횟수":  {"date_from","date_to","tickers","conditions"},
}