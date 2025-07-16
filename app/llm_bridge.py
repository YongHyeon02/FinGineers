"""
HyperCLOVA API 래퍼 ― 모호 질의 파라미터 추출

extract_ambiguous_params(question: str) → dict
  • 1차: 로컬 정규식 파서(_regex_parse)
  • 실패 시 HyperCLOVA API 호출 → JSON 파싱
  • DRY_RUN=1 또는 API Key 미설정 시 LLM 호출 생략
"""
from __future__ import annotations

import json, os, uuid, logging, functools
from typing import Dict

import requests

logger = logging.getLogger(__name__)
_API_URL = "https://clovastudio.apigw.ntruss.com/testapp/v1/chat-completions"  # 예시 엔드포인트

# ─────────────────── HyperCLOVA REST 호출 ────────────────────────────
@functools.lru_cache(maxsize=128)
def _call_hyperclova(prompt: str) -> str | None:
    api_key = os.getenv("HYPERCLOVA_API_KEY")
    if not api_key or os.getenv("DRY_RUN") == "1":
        logger.info("HyperCLOVA 호출 건너뜀")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-NCP-CLOVASTUDIO-REQUEST-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    payload = {"question": prompt}

    try:
        r = requests.post(_API_URL, headers=headers, json=payload, timeout=10)
        r.raise_for_status()
        return r.json().get("answer", "")
    except Exception as e:
        logger.exception("HyperCLOVA 요청 실패: %s", e)
        return None

# ─────────────────── 파라미터 추출 ──────────────────────────────
_EXPECT = {"intent", "period_days", "top_n", "threshold_pct"}
_DEF_PERIOD, _DEF_TOPN = 20, 10

SYSTEM_MSG = (
    "너는 금융 데이터를 다루는 분석 어시스턴트야. "
    "사용자 문장을 JSON 형태로만 구조화해서 답해. "
    "필드: intent(top_gainers|off_peak), period_days(int), top_n(int), threshold_pct(int)"
)

@functools.lru_cache(maxsize=256)
def extract_ambiguous_params(question: str) -> Dict[str, int | str | None]:
    # 1) 로컬 정규식 파서 우선
    from app.parsers import _regex_parse  # 순환참조 방지
    parsed = _regex_parse(question)
    if parsed:
        return parsed

    # 2) HyperCLOVA 호출
    answer = _call_hyperclova(question)
    if not answer:
        return {}

    try:
        data = json.loads(answer)
        if not _EXPECT.issubset(data.keys()):
            raise ValueError("필수 키 누락")
        return {
            "intent": data.get("intent"),
            "period_days": int(data.get("period_days") or _DEF_PERIOD),
            "top_n": int(data.get("top_n") or _DEF_TOPN),
            "threshold_pct": int(data.get("threshold_pct") or 0),
        }
    except Exception as e:
        logger.error("HyperCLOVA 응답 파싱 실패: %s", e)
        return {}
