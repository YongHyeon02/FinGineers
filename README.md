# FinGineers – HyperCLOVA Fin Agent

## 1. 프로젝트 개요
HyperCLOVA API와 yfinance 실시간·과거 데이터를 결합하여 **금융 Q&A**를 수행하는 에이전트입니다.  
- **신뢰성 & 속도**: 실시간/배치 파이프라인 + 한국거래소 영업일 캘린더 적용  
- **모듈식 아키텍처**: 자연어 질문 → HCX-005 파라미터화 → Router → Task Handler

## 2. 팀 정보

| 구분   | 내용                    |
| ------ | ---------------------- |
| **팀명** | FinGineers            |
| **분야** | AI Tech |
| **팀원** | 조용현 · 박선홍       |

## 3. 핵심 특징

### 3-1. yfinance 데이터 캐싱
* `app/yf_cache.py`  
  * **프리패치**: `2024-01-01 ~ 2025-07-31` 구간은 Parquet 캐시만 사용 → 네트워크 호출 *0*  
  * 미캐시 구간은 즉시 호출 후 저장  
* `scripts/prefetch_yf.py` CLI로 대량 사전 수집 및 레이트-리밋 자동 처리

### 3-2. 영업일 계산 & 휴장일 메시지
* `pandas_market_calendars`의 `XKRX` 달력 사용  
* 비영업일 질의 시 `_holiday_msg()`가  
  `YYYY-MM-DD는 휴장일입니다. 데이터가 없습니다.` 반환

### 3-3. Ticker 디스앰비규에이션

| 단계 | 방법                     | 설명                                              |
| ---- | ------------------------ | ------------------------------------------------- |
| ①    | 정적 CSV                | KOSPI·KOSDAQ·Alias 매핑                           |
| ②    | **Fuzzy**               | `rapidfuzz` 편집거리 → 상위 `TOP_K_FUZZY = 3`         |
| ③    | **Sentence-BERT 임베딩**| 768-dim cosine sim → 상위 `TOP_K_EMBED = 3`           |
| ④    | **HCX Re-ranking**      | 후보를 HyperCLOVA가 최종 선택 (conf ≥ 0.82)       |

모호하면 `AmbiguousTickerError`를 발생시켜 **후속 재질문** 유도. Fuzzy와 Sentence-BERT 임베딩 상위 후보를 예시로 제시.

## 4. FastAPI 엔드포인트 & 세션 관리

### 4-1. `/agent` 엔드포인트
| Method | URL | Query Param | Header (선택) | 설명 |
| ------ | --- | ----------- | ------------- | ---- |
| **GET** | `/agent` | `question=<사용자 질문>` | `X-NCP-CLOVASTUDIO-REQUEST-ID=<UUID>` | 자연어 질문을 HCX-005 → 파라미터 추출 → Task Handler로 전달하여 답변 |

- **세션 식별자**  
  - 프론트엔드가 `X-NCP-CLOVASTUDIO-REQUEST-ID` 헤더를 보내면 해당 값으로 세션을 고정한다.  
  - 없으면 서버에서 임의 UUID를 발급하여 `session_id` 필드로 반환한다.

- **응답 JSON**
  ```json
  {
    "answer": "…자연어 답변…",
    "session_id": "3a17b8f7-…"
  }
  ```

### 4-2. 인-메모리 세션 캐시 `app/session.py`
- **키**: `cond_id` (session_id)
- **값**: 슬롯-필링 도중 완성되지 않은 params 딕셔너리
- 후속 질의가 오면 부족한 슬롯만 채워서 같은 Task 핸들러로 재시도 ➜ 문맥 유지
    ```
    U: 삼성전자, NAVER 종가는?
    A: 질문에 명확하게 대답하기 위해 날짜를 알려주세요
    
    U: 2025-07-29
    A: 70,600원
    ```

## 5. Task 별 구현

### 5-1. Task 1 — 단순 조회

| 기능(메서드)                         | 설명                                    |
|--------------------------------------|-----------------------------------------|
| `가격·등락률` `_answer_price()`       | 시가·종가·고가·저가·등락률 계산         |
| `거래량 Top N` `_answer_volume()`     | 특정 날짜·시장별 거래량 상위 N           |
| `상승/하락 종목 수` `_answer_updown_count()` | 하루 기준 상승·하락·보합 종목 개수      |
| `거래대금 합계` `_answer_trading_value()` | 시장별·날짜별 거래대금 총합             |
| `Top Mover/Price` `_answer_top_mover()` 등 | 등락률·가격 상위/하위 N                |
| **다중 Ticker/Metric**                | “삼성전자·카카오 종가·거래량” 같은 복합 질의 지원 |
| **Look-back 7일**                     | 매매정지·데이터 누락 시 `_LOOKBACK_DAYS = 7` 범위에서 대체 |
| **Volume 0 필터**                     | 거래량 0 종목은 모든 랭킹·통계에서 제외  |

---

### 5-2. Task 2 & Task 3 — 조건검색·시그널 감지

- `search_utils.py`에 핵심 로직 구현 완료  
- 핸들러 연결 시 △이동평균 골든크로스 △RSI △볼린저 밴드 등 다양한 신호 처리 가능하도록 설계  

---

### 5-3. Task 4 — 모호한 의미 해석

- “최근 많이 오른 주식 알려줘” 같은 추상 질의를 **HCX 프롬프트 예시**로 Task 1–3 JSON 구조로 재해석  
- **날짜 키워드 자동 보정**  
  - `오늘·금일·당일` → 질의 당일  
  - `최근·요즘` → 질의 당일 기준 가장 최근 영업일  
  - `YYYY` 생략 시 `2025년`으로 자동 매핑
  - 다양한 포맷 (`YYYY/MM/DD`, `YYYY년 MM월 DD일`) 지원  
- 필수 슬롯 누락 시 **후속 재질문을 한국어로 자연스럽게 생성**

- **대화 예시**
`U:`는 사용자(질문), `A:`는 Fin Agent(응답)입니다.
```text
U: 오늘 코스피 지수 알려줘 (질문일: 2025-07-29)
A: 2025-07-29에 KOSPI 지수는 3,230.57 입니다.
```
---

### 5-4. Task 5 — 고급 패턴·지표

| 카테고리               | 함수                         | 내용                                                          |
|------------------------|------------------------------|---------------------------------------------------------------|
| 캔들스틱 패턴          | `_scan_three_pattern()`      | 적삼병(Three White Soldiers), 흑삼병(Three Black Crows)       |
| 52주 신고가 돌파       | `detect_52w_high_break()`    | `period_days` 파라미터로 기간 가변                            |
| 52주 신저가            | `detect_52w_low()`           | —                                                             |
| 고점 대비 n % 하락     | `detect_off_peak()`          | 최고가 대비 하락률 필터                                       |
| 갭 상승·하락            | `search_by_gap_pct()`        | (Open_today − Close_prev) / Close_prev 기반                   |
| 급등·급락               | `search_by_pct_change()`     | 상·하한가, 근접, ±n % 등                                    |
| 변동률 (Volatility)     | `calculate_volatility()`     | 지정 기간(예: 20일) 동안 수익률의 표준편차(롤링 변동성) 계산  |
| 베타 (Beta)            | `calculate_beta()`           | 종목과 벤치마크(예: KOSPI) 간 상관계수로 산출된 베타 계수 계산 |

- **대화 예시**
`U:`는 사용자(질문), `A:`는 Fin Agent(응답)입니다.

```text
U: 2025-05-12 삼성전자, NAVER 변동성과 베타 알려줘
A: 2025-05-12 기준 종목별 지표는 다음과 같습니다.
   - 삼성전자: 변동성 0.330, 베타 12.97
   - NAVER: 변동성 0.348, 베타 129.59

U: 2025-06-17 KOSPI 변동성이 가장 높은 10개 종목은?
A: 2025-06-17에 KOSPI에서 변동성이 높은 상위 10개 종목입니다.
   DH오토넥스, 대성산업, 참엔지니어링, KC코트렐, 평화홀딩스, 흥국화재우, 윌비스, 티와이홀딩스우, KG모빌리티, 쌍방울

U: 최근 많이 오른 주식 알려줘
A: 2025-07-29(최근 영업일) 기준 상승률 TOP 10은 다음과 같습니다.
   시디즈, 에코프로머티... (이하 생략)
```

## 6. 설치 & 실행

```bash
# 1) 의존성 설치
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2) yfinance 캐싱 (선택. 테스트 서버에는 사전에 캐싱 완료)
python -m scripts.prefetch_yf --start 2025-07-01 --end 2025-07-31
```

**예시 요청**

```bash
curl -G 'http://localhost:8000/agent' \
     --data-urlencode "question=2025-07-15에 시가가 전일 종가 대비 5% 이상 갭상승한 종목 알려줘"
```

## 7. 디렉터리 구조 (발췌)

```text
├─ app/
│  ├─ router.py              # 요청 라우팅
│  ├─ llm_bridge.py          # HCX 연동·파라미터 추출
│  ├─ task_handlers/
│  │   ├─ task1_simple.py    # Task 1: 단순 조회
│  │   ├─ task_search.py     # Task 2·3: 조건검색·시그널 감지
│  │   └─ ...                # Task 4·5: 모호한 의미 해석·고급 패턴
│  ├─ search_utils.py        # 조건 검색·패턴 감지
│  ├─ utils.py               # 휴장일·공통 유틸
│  └─ yf_cache.py            # yfinance 캐시 래퍼
├─ data/                     # CSV & Parquet 캐시
└─ scripts/
   └─ prefetch_yf.py         # 대량 캐시 다운로드
```