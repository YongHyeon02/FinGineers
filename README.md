# FinGineers – HyperCLOVA Fin Agent

**Korean-language financial Q\&A agent** that parses natural-language questions (Korean) and answers with market data (KRX: KOSPI/KOSDAQ; SPAC/REITs excluded).
Built with **FastAPI + HyperCLOVA (HCX)** for slot‑filling and **yfinance** with a local Parquet cache for speed and reliability.

> **Language**: API answers are returned **in Korean** by design.
> Prefer Korean docs? See **[Korean README (README.ko.md)](./README.ko.md)**.

---

## Why this project (for recruiters)

* **Production‑minded**: stateless HTTP API, deterministic caching layer, graceful rate‑limit handling, and KRX business‑day calendar.
* **LLM for structure, not facts**: HyperCLOVA fills missing slots (date/ticker/metric) and asks follow‑ups; numerical outputs always come from data.
* **Robust ticker disambiguation**: fuzzy match + sentence embeddings + LLM re‑ranking; if still ambiguous, prompts user with top suggestions (in Korean).

---

## Quick start

### 1) Run the API

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Endpoint**

```
GET http://localhost:8000/agent?question=<your question in Korean>
```

**Headers**

* `Authorization: Bearer <YOUR_HYPERCLOVA_API_KEY>`
* `X-NCP-CLOVASTUDIO-REQUEST-ID: <session-id>` (optional for single-turn; required for multi-turn)

### 2) Minimal client example (Python)

```python
import requests

API_KEY = "nv-xxx..."                 # Your HyperCLOVA API key
SESSION_ID = "abcd-1234..."          # Optional on first turn if single-turn

resp = requests.get(
    "http://localhost:8000/agent",
    params={"question": "2025-06-17 삼성전자 종가는?"},
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": SESSION_ID
    },
    timeout=30
)
print(resp.json())
```

**Example response**

```json
{
  "answer": "2025-06-17에 삼성전자의 종가은(는) 58,100원 입니다.",
  "session_id": "abcd-1234..."
}
```

> **Multi‑turn**: if the agent asks a follow‑up (e.g., missing date/metric), send your next request **with the same `X-NCP-...` session ID**.

---

## Key features

* **LLM‑driven slot filling**
  Converts ambiguous Korean questions into structured params (`task`, `date`, `tickers`, `metrics`, `conditions`…), asking **Korean follow‑ups** when needed.
* **Speed & reliability**
  Local Parquet cache for a large historical window; off‑cache ranges fall back to yfinance, then get cached automatically.
  KRX business‑day calendar; **no data** message on holidays/weekends.
* **Ticker disambiguation**
  Fuzzy + SBERT + LLM re‑ranking; if still ambiguous, returns a concise Korean prompt with top suggestions.
* **Task coverage**
  **Simple lookups** (price/volume/index/turnover), **market counts**, **ranking** (top volume/return/price/volatility/beta),
  **condition scans** (RSI, volume spike, MA break, Bollinger touch, gap up/down, 52w high/low, off‑peak),
  **pattern search** (Three White Soldiers / Three Black Crows), and **cross counts/dates** (golden/dead).

---

## API at a glance

**Endpoint**

```
GET /agent?question=<Korean natural language>
```

**Headers**

* `Authorization: Bearer <API_KEY>` (required)
* `X-NCP-CLOVASTUDIO-REQUEST-ID: <session-id>` (optional single-turn; required multi-turn)

**Answer**
Returns a Korean sentence tailored to the user’s question.

**Examples** (Korean responses by design)

```text
User: 오늘 삼성전자 종가는?
Agent: 어떤 날짜의 삼성전자 종가를 알려 드릴까요?
User: 2025-07-07
Agent: 2025-07-07에 삼성전자의 종가은(는) 61,700원 입니다.
```

```text
User: 2025-06-17 삼성전자, 카카오, 네이버의 종가·거래량·등락률·변동성·베타는?
Agent: 2025-06-17 기준 종목별 지표는 다음과 같습니다.
  - 삼성전자: 종가 58,100원, 거래량 28,637,003주, 등락률 +1.57%, 변동성 0.320, 베타 7.67
  - 카카오: 종가 51,800원, 거래량 3,981,660주, 등락률 -2.63%, 변동성 0.551, 베타 22.30
  - 네이버: 종가 206,500원, 거래량 837,169주, 등락률 -1.43%, 변동성 0.317, 베타 26.87
```

```text
User: 2025-06-30에 시가가 전일 종가 대비 5% 이상 갭상승한 종목 알려줘
Agent: 2025-06-30에 갭상승 5% 이상 종목은 다음과 같습니다.
  SCL사이언스, SK이노베이션, ... (생략)
```

---

## Architecture

```
User (Korean NL)
   │
   ▼
Router ──► LLM (HCX-005)  → slot-filling → params JSON
   │
   ├─► Task 1: Simple lookup (price/volume/index/turnover)
   ├─► Task 2/3: Condition scan & signals (RSI, MA, Bollinger, gap, 52w…)
   ├─► Task 4: Ambiguity handling (follow-up prompts)
   └─► Task 5: Advanced patterns & comparisons
         │
         └─► Data fetcher → yfinance (+local Parquet cache) → business-day guards
```

**Tech**: FastAPI · Python · pandas · yfinance · sentence-transformers (for embeddings)
**Data**: KOSPI/KOSDAQ equities (SPAC/REITs excluded)
**Caching**: Local Parquet (prefetch + incremental fill)
**Calendar**: KRX business days (holiday-aware responses)

---

## Repository layout (high level)

* `main.py` – FastAPI `/agent` endpoint, session header handling
* `app/router.py` – Route question → task handler (with follow-ups)
* `app/task_handlers/` – Task implementations (simple lookup, search, patterns…)
* `app/search_utils.py` – RSI, volume spike, MA break, Bollinger touch, gap, 52w high/low, off-peak, cross, three-pattern
* `app/data_fetcher.py` & `app/yf_cache.py` – yfinance I/O and local Parquet cache
* `app/ticker_lookup.py` – name/alias → ticker, disambiguation pipeline
* `hcx_system_prompt.txt` / `follow_prompt.json` – HCX extraction prompts

---

## Notes & limitations

* Answers are **Korean‑only** in this version. You can internationalize by swapping prompt templates and message generators.
* yfinance data latency and symbol coverage follow yfinance constraints; delisted/illiquid names may be missing.

---

## License

TBD (choose one before publishing externally).

---

**Need the Korean guide? → [README.ko.md](./README.ko.md)**

---