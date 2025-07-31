def compare_stock_lists(expected_text: str, actual_text: str):
    expected_set = set(map(str.strip, expected_text.split(',')))
    actual_set = set(map(str.strip, actual_text.split(',')))

    both = sorted(expected_set & actual_set)
    only_expected = sorted(expected_set - actual_set)
    only_actual = sorted(actual_set - expected_set)

    print("✅ 양쪽에 모두 있는 종목:", ", ".join(both) if both else "-")
    print("🟥 expected에만 있는 종목:", ", ".join(only_expected) if only_expected else "-")
    print("🟦 actual에만 있는 종목:", ", ".join(only_actual) if only_actual else "-")

# 예시 실행
expected_text = "KH 건설(RSI:100.0), KH 미래물산(RSI:100.0), 태영건설(RSI:99.9), 카프로(RSI:99.8), 태영건설우(RSI:99.6), 코다코(RSI:98.3), HD현대미포(RSI:85.4), 엔에스이엔엠(RSI:85.3), 헥토파이낸셜(RSI:82.8), 펩트론(RSI:82.7), 일신석재(RSI:82.3), 동양생명(RSI:82.1), 듀켐바이오(RSI:80.5), 신성통상(RSI:80.2), 오늘이엔엠(RSI:80.2), 압타바이오(RSI:80.2), DI동일(RSI:80.0), 인크레더블버즈(RSI:79.5), STX그린로지스(RSI:79.3), 윈팩(RSI:79.1), 비투엔(RSI:79.1), 솔루스첨단소재(RSI:78.8), DYP(RSI:77.8), 현대글로비스(RSI:77.2), 아바텍(RSI:77.0), 코리아에셋투자증권(RSI:76.4), HD한국조선해양(RSI:76.3), 성우전자(RSI:76.1), SNT모티브(RSI:75.9), 솔루스첨단소재1우(RSI:75.5), LS티라유텍(RSI:75.2)"
actual_text = "DB증권, DI동일, DYP, E8, GS글로벌, HB솔루션, HD한국조선해양, HD현대, HD현대마린엔진, HD현대미포, HD현대중공업, LG전자, LG전자우, LIG넥스원, LS티라유텍, LX하우시스우, SG글로벌, SNT모티브, STX그린로지스, 골프존홀딩스, 나이벡, 남양유업, 동양생명, 듀켐바이오, 디씨엠, 로체시스템즈, 롯데렌탈, 마이크로디지탈, 바이오플러스, 사조대림, 삼성전자, 삼성증권, 삼영엠텍, 성우전자, 세진중공업, 신성통상, 신원, 아바텍, 아이쓰리시스템, 압타바이오, 에이치엔에스하이텍, 에프엔에스테크, 엔에스이엔엠, 엘앤씨바이오, 오늘이엔엠, 오스코텍, 윈팩, 윈하이텍, 유안타증권우, 유한양행, 유한양행우, 이녹스첨단소재, 인크레더블버즈, 인화정공, 일신석재, 자이에스앤디, 제이앤티씨, 조광페인트, 조비, 진양폴리, 캐리, 코리아에셋투자증권, 코스메카코리아, 코웨이, 콜마비앤에이치, 펩트론, 풍산, 피엔에이치테크, 하나머티리얼즈, 하이텍팜, 한화엔진, 헥토파이낸셜, 현대글로비스, 현대모비스, 현대차2우B, 현대차3우B, 화승알앤에이, 화신, 효성ITX"
compare_stock_lists(expected_text, actual_text)
