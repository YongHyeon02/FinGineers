# app/llm_bridge.py
"""
HyperCLOVA API 래퍼
  1) 최초 질문           → extract_params()
  2) 후속(슬롯) 답변      → fill_missing()
"""
from __future__ import annotations

import json, os, uuid, logging, functools, re, datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional
import re
import requests
import time
# from app.constants import TASK_REQUIRED
from config import HCX_CONF_THRESHOLD
# from app.parsers import _regex_parse      # 순환 참조 방지

logger = logging.getLogger(__name__)

# ──────────────────────────── HCX 설정 ────────────────────────────
_API_URL = os.getenv(
    "HYPERCLOVA_API_URL",
    # "https://clovastudio.stream.ntruss.com/testapp/v3/chat-completions/HCX-005",
    "https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-005",
)

_TIMEOUT = 40
_SYS_PROMPT_PATH = Path(__file__).with_name("prompts") / "hcx_system_prompt.txt"
SYSTEM_PROMPT = _SYS_PROMPT_PATH.read_text(encoding="utf-8").strip()

# ──────────────────────────── 공통 유틸 ────────────────────────────
def _safe_json(text: str) -> Optional[dict]:
    """
    응답 문자열에서 첫 JSON 객체만 추출 → dict
    """
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _hcx_chat(messages: List[dict], *, api_key: str, max_tokens: int = 256, temperature: float = 0.5) -> Optional[str]:
    """
    messages = [{"role":"system","content":...}, {"role":"user","content":...}]
    → assistant content 문자열 (실패 시 None)
    """
    if not api_key:
        logger.info("HyperCLOVA 호출 건너뜀 (API Key 없음)")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    payload = {
        "messages": messages,
        "maxTokens": max_tokens,
        "temperature": temperature,
        "topP": 0.8,
        "topK": 0,
        "repetitionPenalty": 1.1,
        "includeAiFilters": False,
    }

    try:
        r = requests.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content")
            or data.get("result", {}).get("message", {}).get("content")
            or ""
        ).strip()
        logger.debug("HCX raw answer: %s", content)
        return content
    except Exception as e:
        logger.exception("HCX 요청 실패: %s", e)
        return None
    
_ALNUM_RE = re.compile(r'[^A-Za-z0-9-]+')

def _strip_alphanum(val: Any) -> Any:
    """
    단일 값에 대해 영문·숫자만 남긴다.
    숫자만 남으면 int 로, 그 외는 문자열 그대로.
    """
    if isinstance(val, str):
        cleaned = _ALNUM_RE.sub('', val)
        return int(cleaned) if cleaned.isdigit() else cleaned
    if isinstance(val, list):
        return [_strip_alphanum(x) for x in val]
    if isinstance(val, dict):
        return {k: _strip_alphanum(v) for k, v in val.items()}
    return val

_EXCEPT_KEYS = {"date", "date_from", "date_to",
                "metrics", "market", "tickers", "rank_n"}

def _clean_params(data: dict) -> dict:
    """
    파라미터 dict를 돌며, 예외 키를 제외한 모든 value에
    _strip_alphanum() 을 적용한다.
    """
    out = {}
    for k, v in data.items():
        out[k] = v if k in _EXCEPT_KEYS else _strip_alphanum(v)
    return out

# ────────────────────────── ① 최초 질문 파싱 ─────────────────────────
_JSON_EXPECT     = {"task","date","date_from","date_to","market","tickers","metrics","rank_n","conditions"}
_JSON_EXPECT_MIN = {"task"}
_DEF_DATE        = (dt.date.today() - dt.timedelta(days=1)).isoformat()
_DEF_TOPN        = 10

@functools.lru_cache(maxsize=256)
def extract_params(question: str, api_key: str) -> Dict[str, Any]:
    """
    HCX 호출 후 결과 파싱 + 기본 필드 보정
    """

    def _try_hcx_chat_with_retry(max_retries=3, initial_delay=1.0) -> dict:
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                hcx_ans = _hcx_chat(
                    [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": question}],
                    api_key=api_key
                ) or ""
                return _safe_json(hcx_ans) or {}

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning(f"429 Too Many Requests – {delay:.1f}s 후 재시도 ({attempt+1}/{max_retries})")
                    time.sleep(delay)
                    delay *= 2  # 지수 백오프
                else:
                    logger.exception("HCX API 오류")
                    break

            except Exception:
                logger.exception("HCX 파싱 도중 예외 발생")
                break

        return {}

    # HCX 호출 (최대 3회까지 재시도)
    data = _try_hcx_chat_with_retry()

    if _JSON_EXPECT_MIN.issubset(data):
        data.setdefault("date", _DEF_DATE)
        data.setdefault("date_from", _DEF_DATE)
        data.setdefault("date_to", _DEF_DATE)
        data.setdefault("market", None)
        data.setdefault("tickers", [])
        data.setdefault("metrics", [])
        data.setdefault("rank_n", _DEF_TOPN)
        data.setdefault("conditions", {})
        return data

    logger.warning("HCX 파싱 실패: %s", question)
    return {"task": "unknown"}


# ────────────────────────── ② 슬롯 전용 파서 ─────────────────────────
_FOLLOW_PROMPTS_PATH = Path(__file__).with_name("prompts") / "follow_prompt.json"
try:
    with open(_FOLLOW_PROMPTS_PATH, encoding="utf-8") as f:
        _FOLLOW_PROMPTS: dict[str, str] = json.load(f)
except json.JSONDecodeError as e:
    raise RuntimeError(f"follow_prompts.json 파싱 오류: {e}")   

def fill_missing(user_reply: str, slot: str, api_key: str) -> dict | None:
    """
    후속 답변에서 특정 slot 하나만 추출 → {slot: value}
    실패 시 None
    """
    prompt = _FOLLOW_PROMPTS[slot]
    hcx_ans = _hcx_chat(
        [{"role": "system", "content": prompt},
         {"role": "user",   "content": user_reply}],
        api_key=api_key,
        max_tokens=64, temperature=0.2,
    ) or ""
    data = _safe_json(hcx_ans)
    data = _clean_params(data)
    if isinstance(data, dict) and slot in data and data[slot]:
        return data
    logger.debug("fill_missing 실패(slot=%s): %s", slot, hcx_ans)
    return None

def fill_missing_multi(user_reply: str, slots: list[str], api_key: str) -> Optional[dict]:
    """
    사용자의 후속 답변에서 `slots` 에 해당하는 값만 추출 → {slot: value, …}
    실패 시 None
    """
    if not slots:
        return {}

    # ① 시스템 프롬프트 작성
    slot_line = ", ".join(slots)
    sample = "{" + ", ".join(f'"{s}": "<value>"' for s in slots) + "}"
    sys_prompt = (
        "당신은 한국 주식 질의용 AI이다.\n"
        f"사용자 답변에서 다음 필드({slot_line})의 값을 추출해 **JSON 한 줄**로만 응답하라.\n"
        f"** {sample} ** 형식을 반드시 준수하라.\n"
        "값이 없으면 <value> 자리에 null을 입력하라.\n"
        "{\"date\"에 대해서는 {\"date\":\"YYYY-MM-DD\"} 형태로 반환하라.\n"
        "{\"date_from\"에 대해서는 {\"date_from\":\"YYYY-MM-DD\"} 형태로 반환하라.\n"
        "{\"date_to\"에 대해서는 {\"date_to\":\"YYYY-MM-DD\"} 형태로 반환하라.\n"
        "{\"metrics\"에 대해서는 {\"metrics\":[\"종가\", \"거래량\"]} 형태로 반환하라. metrics ∈ {\"종가\",\"시가\",\"고가\",\"저가\",\"pct_change\",\"거래량\",\"지수\",\"거래대금\",\"상승률\",\"하락률\",\"가격\",\"변동성\",\"베타\"} 외의 값은 허용되지 않는다.\n"
        "{\"tickers\"에 대해서는 {\"tickers\":[\"삼성전자\"]} 형태로 종목명을 반환하라.\n"
        "\"코스피\"/\"KOSPI\"가 질문에 포함되면 \"market\":\"KOSPI\", \"코스닥\"/\"KOSDAQ\"이 포함되면 \"market\":\"KOSDAQ\", 없으면 null로 반환하라."
    )
    print(sys_prompt)

    # ② HCX 호출
    ans = _hcx_chat(
        [{"role": "system", "content": sys_prompt},
         {"role": "user",   "content": user_reply}],
        api_key=api_key,
        max_tokens=128,
        temperature=0.2,
    ) or ""
    print(ans)
    data = _safe_json(ans) or {}
    data = _clean_params(data)
    return {k: v for k, v in data.items() if k in slots and v not in (None, "", [])} or None

# ──────────────────── 티커 디스앰비규에이션 ─────────────────────
_DISAMBIG_SYS = """
당신은 한국 주식 종목명을 해석하는 AI입니다.
주어진 ‘사용자 별칭’을 가장 잘 설명하는 **하나의** ‘후보’ 종목명을 골라야 합니다.
반환 형식(JSON only):
{"best": "<후보 중 하나 그대로>", "confidence": 0~1}
"""

def disambiguate_ticker_hcx(alias: str, candidates: list[str], api_key: str) -> tuple[str, float]:
    """
    별칭(alias)과 후보 종목명 리스트를 HyperCLOVA-X에 넘겨
    가장 적합한 종목명과 confidence(0~1)를 받아온다.
    실패 시 (첫 후보, 0.0) 반환
    """
    cand_line = ", ".join(candidates)
    usr_prompt = (
        f"사용자 별칭: '{alias}'\n"
        f"후보: {cand_line}\n"
        f"가장 잘 맞는 하나를 골라 JSON 형식으로 답변하세요."
    )
    ans = _hcx_chat(
        [
            {"role": "system", "content": _DISAMBIG_SYS},
            {"role": "user",   "content": usr_prompt},
        ],
        api_key=api_key,
        max_tokens=128, temperature=0.0
    ) or ""
    # print(ans)      
    data = _safe_json(ans) or {}
    best = data.get("best")
    try:
        conf = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0

    # 유효성 체크: best 가 후보 안에 없으면 신뢰도 0 처리
    if best not in candidates:
        best, conf = candidates[0], 0.0
    return best, conf

# ─────────────────── confidence 외부 접근용 ────────────────────
def is_confident(conf: float) -> bool:
    """HCX confidence 가 임계치 이상인지 여부"""
    return conf >= HCX_CONF_THRESHOLD