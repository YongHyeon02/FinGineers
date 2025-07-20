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

import requests
from app.constants import TASK_REQUIRED
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


def _hcx_chat(messages: List[dict], *, max_tokens: int = 256, temperature: float = 0.5) -> Optional[str]:
    """
    messages = [{"role":"system","content":...}, {"role":"user","content":...}]
    → assistant content 문자열 (실패 시 None)
    """
    api_key = os.getenv("HYPERCLOVA_API_KEY")
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
    
# ────────────────────────── ① 최초 질문 파싱 ─────────────────────────
_JSON_EXPECT     = {"task","date","date_from","date_to","market","tickers","metrics","rank_n","conditions"}
_JSON_EXPECT_MIN = {"task"}
_DEF_DATE        = (dt.date.today() - dt.timedelta(days=1)).isoformat()
_DEF_TOPN        = 10

@functools.lru_cache(maxsize=256)
def extract_params(question: str) -> Dict[str, Any]:
    """
    규칙 파서(_regex_parse) → HCX JSON → 보정
    """
    
    # prim = _regex_parse(question)

    # if prim and _JSON_EXPECT.issubset(prim):
    #     return prim

    # HCX 호출
    hcx_ans = _hcx_chat(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user",   "content": question}]
    ) or ""
    data = _safe_json(hcx_ans) or {}

    if _JSON_EXPECT_MIN.issubset(data):
        # 규칙 파서 결과를 우선 보존
        # data.update({k: v for k, v in prim.items() if v})
        # 디폴트 보정
        data.setdefault("date",   _DEF_DATE)
        data.setdefault("date_from", _DEF_DATE)
        data.setdefault("date_to", _DEF_DATE)
        data.setdefault("market", None)
        data.setdefault("tickers", [])
        data.setdefault("metrics", [])
        data.setdefault("rank_n", _DEF_TOPN)
        data.setdefault("conditions", {})
        return data

    logger.warning("HCX 파싱 실패: %s", question)
    return {"task": "unknown"}            # 핸들러 쪽에서 _FAIL 처리

# ────────────────────────── ② 슬롯 전용 파서 ─────────────────────────
_FOLLOW_PROMPTS_PATH = Path(__file__).with_name("prompts") / "follow_prompt.json"
try:
    with open(_FOLLOW_PROMPTS_PATH, encoding="utf-8") as f:
        _FOLLOW_PROMPTS: dict[str, str] = json.load(f)
except json.JSONDecodeError as e:
    raise RuntimeError(f"follow_prompts.json 파싱 오류: {e}")   

def fill_missing(user_reply: str, slot: str) -> dict | None:
    """
    후속 답변에서 특정 slot 하나만 추출 → {slot: value}
    실패 시 None
    """
    prompt = _FOLLOW_PROMPTS[slot]
    hcx_ans = _hcx_chat(
        [{"role": "system", "content": prompt},
         {"role": "user",   "content": user_reply}],
        max_tokens=64, temperature=0.2,
    ) or ""
    data = _safe_json(hcx_ans)
    if isinstance(data, dict) and slot in data and data[slot]:
        return data
    logger.debug("fill_missing 실패(slot=%s): %s", slot, hcx_ans)
    return None

# ──────────────────── ③ 필수 필드 누락 체크 ────────────────────
def _check_missing(params: Dict[str, Any]) -> set[str]:
    """task 별 필수-필드 누락 항목 반환"""
    req = TASK_REQUIRED.get(params.get("task"), set())
    missing = {f for f in req if not params.get(f)}
    if "metrics" in req and not params.get("metrics"):
        missing.add("metrics")
    if "tickers" in req and not params.get("tickers"):
        missing.add("tickers")
    return missing

# ──────────────────── 티커 디스앰비규에이션 ─────────────────────
_DISAMBIG_SYS = """
당신은 한국 주식 종목명을 해석하는 AI입니다.
주어진 ‘사용자 별칭’을 가장 잘 설명하는 **하나의** ‘후보’ 종목명을 골라야 합니다.
반환 형식(JSON only):
{"best": "<후보 중 하나 그대로>", "confidence": 0~1}
"""

def disambiguate_ticker_hcx(alias: str, candidates: list[str]) -> tuple[str, float]:
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



# @functools.lru_cache(maxsize=128)
# def _call_hyperclova(question: str) -> str | None:
#     api_key = os.getenv("HYPERCLOVA_API_KEY")
#     if not api_key: # or os.getenv("DRY_RUN") == "1":
#         logger.info("HyperCLOVA 호출 건너뜀")
#         return None

#     headers = {
#         "Authorization": f"Bearer {api_key}",
#         "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
#         "Content-Type": "application/json; charset=utf-8",
#         "Accept": "application/json",
#     }

#     payload: Dict[str, Any] = {
#         "messages": [
#             {"role": "system", "content": SYSTEM_PROMPT}
#             {"role": "user", "content": question},
#         ],
#         "topP": 0.8,
#         "topK": 0,
#         "maxTokens": 256,
#         "temperature": 0.5,
#         "repetitionPenalty": 1.1,
#         "includeAiFilters": False,
#     }

#     try:
#         r = requests.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT)
#         r.raise_for_status()
#         data = r.json()
#         logger.debug("HCX full JSON: %s", json.dumps(data, ensure_ascii=False))
#         content = (
#             data.get("choices", [{}])[0].get("message", {}).get("content")
#             or data.get("result", {}).get("message", {}).get("content")
#             or ""
#         ).strip()
#         logger.debug("HCX raw answer: %s", content)
#         return content
#     except Exception as e:
#         logger.exception("HyperCLOVA 요청 실패: %s", e)
#         return None

# # ─────────────────── 파라미터 추출 ───────────────────
# _JSON_EXPECT = {
#     "task", "date", "market", "tickers",
#     "metrics", "rank_n", "conditions"
# }
# _JSON_EXPECT_MIN = {"task"}        # task 만 있으면 진행
# _DEF_DATE   = (dt.date.today() - dt.timedelta(days=1)).isoformat()
# _FALLBACK = {"task": "ambiguous"}

# _DEF_PERIOD, _DEF_TOPN = 20, 10

# # ──────────────────────────────────────────────────────────────
# # Ambiguous 전용 경량 파서
# #   – extract_params() 결과 중 task=="ambiguous" 일 때
# #   – Task 4 핸들러(app/task_handlers/task4_ambiguous.py)가
# #     기대하는 4개 필드(intent · period_days · top_n · threshold_pct)만
# #     추려서 반환
# # ----------------------------------------------------------------
# def extract_ambiguous_params(question: str) -> dict:
#     data = extract_params(question)          # 기존 범용 파서 재사용
#     if data.get("task") != "ambiguous":
#         return {}

#     # ① intent 결정
#     cond = (data.get("conditions") or {}).get("change_pct", {})
#     op   = cond.get("op")
#     intent = (
#         "top_gainers" if op in (">", ">=") else
#         "off_peak"   if op in ("<", "<=") else
#         "top_gainers"
#     )

#     # ② 나머지 파라미터
#     return {
#         "intent": intent,
#         "period_days": cond.get("period_days", _DEF_PERIOD),
#         "top_n": data.get("rank_n", _DEF_TOPN),
#         "threshold_pct": cond.get("value", 0),
#     }

# # ────────────── 최상위 파라미터 추출 진입점 ──────────────
# @functools.lru_cache(maxsize=256)
# def extract_params(question: str) -> Dict[str, Any]:
#     """
#     ① 규칙 파서 → ② HCX JSON → ③ 실패 시 'ambiguous'
#     """
#     from app.parsers import _regex_parse           # 순환참조 방지
#     prim = _regex_parse(question)
#     # 규칙 파서가 date·task 등 **모든** 필드를 채웠는지 확인
#     if prim and _JSON_EXPECT.issubset(prim):
#         return prim

#     raw = _call_hyperclova(question) or ""
#     data = _safe_json(raw) or {}
#     if _JSON_EXPECT_MIN.issubset(data):
#         # 날짜 등 일부 빠진 경우 prim → data 머지
#         data.setdefault("date",   _DEF_DATE)
#         data.setdefault("market", None)           # null 처리
#         data.setdefault("tickers", [])
#         data.setdefault("metrics", ["change_pct"])
#         data.setdefault("rank_n", _DEF_TOPN)
#         data.setdefault("conditions", {})
#         return data

#     logger.warning("HCX 파싱 실패·fallback → ambiguous")
#     return _FALLBACK

# def _check_missing(data: Dict[str, Any]) -> set[str]:
#     """필수값 누락 항목 반환"""
#     req = TASK_REQUIRED.get(data.get("task"), set())
#     missing = {f for f in req if not data.get(f)}
#     # metrics·tickers는 빈 리스트도 누락으로 간주
#     if "metrics" in req and not data.get("metrics"):
#         missing.add("metrics")
#     if "tickers" in req and not data.get("tickers"):
#         missing.add("tickers")
#     return missing
