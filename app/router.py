# app/router.py
from __future__ import annotations
import logging
import datetime as dt
from typing import Callable, Optional, Dict, Any
from app import session                  # ↩︎ 간단한 in-mem 세션 캐시 (앞서 제안)
from app.utils import _holiday_msg, _prev_bday
from app.llm_bridge import extract_params, fill_missing
from app.task_handlers import (
    task_search,
    task1_simple,
    task4_ambiguous,
)
from config import AmbiguousTickerError

logger = logging.getLogger(__name__)
_FAIL = "질문을 이해하지 못했습니다."

# ─────────────────────────────────────────────────────
# 0. 보조 유틸  ← ★ 새로 추가
# ─────────────────────────────────────────────────────
def _most_recent_bday() -> str:
    """
    오늘이 영업일이면 오늘(YYYY-MM-DD),
    아니면 직전 영업일을 반환
    """
    today = dt.date.today().isoformat()
    return today if _holiday_msg(today) is None else _prev_bday(today)

_recent_kw = ("최근", "요즘", "근래", "요새", "이즈음")
_today_kw  = ("오늘", "금일", "당일", "오늘자")

def _auto_fill_relative_dates(question: str, params: dict) -> None:
    """
    • date 와 date_to 가 모두 None 인 상태에서
      - “최근*”류 키워드 → date = 최근 영업일
      - “오늘*”류 키워드 → date = 최근 영업일
    • date_from 값이 이미 있으면 date_to 에도 최근 영업일 세팅
    """
    if params.get("date") or params.get("date_to"):
        return  # 이미 값이 있으면 건너뜀

    q = question
    if any(k in q for k in _recent_kw + _today_kw):
        recent = _most_recent_bday()
        params["date"] = recent
        if params.get("date_from"):
            params["date_to"] = recent
# ─────────────────────────────────────────────────────

# ──────────────────────────────────────────────
# 1.  task 메타 정의  (추가 시 여기만 수정)
# ──────────────────────────────────────────────
HandlerFn = Callable[[str, dict], str]      # (question, params) -> answer

TASK_REGISTRY: Dict[str, dict] = {
    # task명        handler                 필수필드 집합
    "단순조회":    {"fn": task1_simple.handle,     "req": {"date","metrics","tickers"}},
    "상승종목수":  {"fn": task1_simple.handle,     "req": {"date"}},
    "하락종목수":  {"fn": task1_simple.handle,     "req": {"date"}},
    "거래종목수":  {"fn": task1_simple.handle,     "req": {"date"}},
    "시장순위":    {"fn": task1_simple.handle,     "req": {"date","metrics","rank_n"}},
    "종목검색":    {"fn": task_search.handle,      "req": {"conditions"}},
    "횟수검색":    {"fn": task_search.handle,      "req": {"date_from", "date_to", "tickers", "conditions"}},
    "날짜검색":    {"fn": task_search.handle,      "req": {"date_from", "date_to", "tickers", "conditions"}},
    }
THREE_PATTERN_METRICS = {"적삼병", "흑삼병"}

# ──────────────────────────────────────────────
def _safe_handle(fn: HandlerFn, question: str, params: dict) -> Optional[str]:
    try:
        out = fn(question, params)
        # print(out)
        return out if out else None
    except AmbiguousTickerError:
        raise
    except Exception as e:
        logger.exception("%s 실행 오류: %s", fn.__name__, e)
        return None

def _missing_fields(task: str, params: dict) -> set[str]:
    """
    task 별 필수 슬롯 누락 항목 계산
    (빈 리스트도 누락으로 간주)
    """
    req = TASK_REGISTRY.get(task, {}).get("req", set())
    miss = {k for k in req if not params.get(k)}
    
    # ── (1) metrics / tickers 빈 리스트 처리 ────────────────────
    if "metrics" in req and not params.get("metrics"):
        miss.add("metrics")
    if "tickers" in req and not params.get("tickers"):
        miss.add("tickers")

    # ── (2) 지수(인덱스) 조회 특례 ─────────────────────────────
    if task == "단순조회":
        metrics = params.get("metrics") or []
        is_index_query = len(metrics) == 1 and metrics[0] == "지수"
        is_transaction_amount_query  = len(metrics) == 1 and metrics[0] == "거래대금"

        if is_index_query:
            # ① tickers 는 필요 없음
            miss.discard("tickers")
            # ② 대신 market(KOSPI/KOSDAQ) 이 꼭 있어야 함
            if not params.get("market"):
                miss.add("market")

        if is_transaction_amount_query:
            miss.discard("tickers")

        cond = params.get("conditions") or {}

'''   for key, val in cond.items():
        if key == "volume_pct":
            if not isinstance(val, dict) or "min" not in val:
                miss.add("conditions:volume_pct:min")

        elif key in {"volume", "price_close", "pct_change", "pct_change_range"}:
            if not isinstance(val, dict) or not ("min" in val or "max" in val):
                miss.add(f"conditions:{key}:min_or_max")

        elif key == "moving_avg":
            if not isinstance(val, dict) or "window" not in val:
                miss.add("conditions:moving_avg:window")
            if not isinstance(val, dict) or "diff_pct" not in val:
                miss.add("conditions:moving_avg:diff_pct")

        elif key == "volume_spike":
            if not isinstance(val, dict) or "window" not in val:
                miss.add("conditions:volume_spike:window")
            if "volume_ratio" not in val or "min" not in val["volume_ratio"]:
                miss.add("conditions:volume_spike:volume_ratio_min")

        elif key == "bollinger_touch":
            if val not in {"upper", "lower"}:
                miss.add("conditions:bollinger_touch")

        elif key == "cross":
            if val not in {"dead", "golden", "both"}:
                miss.add("conditions:cross")

        elif key == "consecutive_change":
            if val not in {"up", "down"}:
                miss.add("conditions:consecutive_change")

        elif key == "three_pattern":
            if val not in {"적삼병", "흑삼병"}:
                miss.add("conditions:three_pattern")'''


def _build_follow_up(missing: set[str]) -> str:
    qmap = {
        "date":    "어느 날짜 기준인지",
        "metrics": "시가·종가·거래량 등 어떤 지표를 원하시는지",
        "tickers": "조회할 종목명이 무엇인지",
        "rank_n":  "상위 몇 개 종목을 원하시는지",
        "conditions": "검색 조건(등락률·거래량 조건 등)이 무엇인지",
        "market":  "KOSPI·KOSDAQ 중 어느 시장인지",
        "conditions:volume_pct:min": "거래량 변화율의 최소값이 무엇인지",
        "conditions:volume:min_or_max": "거래량의 최소 또는 최대값이 무엇인지",
        "conditions:price_close:min_or_max": "종가의 최소 또는 최대값이 무엇인지",
        "conditions:pct_change:min_or_max": "등락률의 최소 또는 최대값이 무엇인지",
        "conditions:pct_change_range:min_or_max": "기간 수익률의 최소 또는 최대값이 무엇인지",
        "conditions:moving_avg:window": "이동평균 비교 시 기준 기간이 무엇인지",
        "conditions:moving_avg:diff_pct": "이동평균과의 차이 비율(%)이 얼마나 되는지",
        "conditions:volume_spike:window": "이동평균 기간(일)이 얼마인지",
        "conditions:volume_spike:volume_ratio_min": "거래량 급등의 기준(%)이 무엇인지",
        "conditions:bollinger_touch": "볼린저 밴드의 상단 또는 하단 중 어느 쪽을 의미하는지",
        "conditions:cross": "크로스 종류(데드/골든/양쪽) 중 무엇인지",
        "conditions:consecutive_change": "연속 상승 또는 하락 중 어느 쪽을 의미하는지",
        "conditions:three_pattern": "적삼병 또는 흑삼병 중 어떤 패턴인지",
    }
    asks = [qmap[f] for f in missing if f in qmap]
    return "질문을 더 정확히 이해하기 위해 " + " / ".join(asks) + " 알려주세요."


# ────────────────────────────── 메인 ──────────────────────────────
def route(question: str, conv_id: str) -> str:
    """
    conv_id : 세션 ID (웹소켓 UUID, 슬랙 thread_ts 등)
    """
    try:
        question = question.strip()
        if not question:
            return _FAIL

        # ── 1) 미완성 params 가 세션에 저장돼 있나?
        pending = session.get(conv_id)
        if pending:
            follow = extract_params(question)
            for k, v in follow.items():
                if not v:
                    continue
                if k == "tickers":
                    orig = pending.get("tickers", [])
                    pending["tickers"] = list(dict.fromkeys(orig + v))
                else:
                    if pending.get(k) in (None, [], "", {}):
                        pending[k] = v

            filled: dict[str, Any] = {}
            # 사용자가 보낸 follow-up 문장으로 슬롯 채우기
            for slot in _missing_fields(pending["task"], pending):
                v = fill_missing(question, slot)
                # print(f"{slot}: {v}")
                if v:
                    filled.update(v)
                for key, val in filled.items():
                    if key == "tickers":
                        orig = pending.get("tickers",[])
                        pending["tickers"] = list(dict.fromkeys(orig + val))
                    else:
                        pending[key] = val
            print(f"updated: {pending}")
            _auto_fill_relative_dates(question, pending)
            still_missing = _missing_fields(pending["task"], pending)

            if still_missing:                               # 여전히 비어 있음
                session.set(conv_id, pending)
                return _build_follow_up(still_missing)

            hinfo = TASK_REGISTRY[pending["task"]]
            answer = _safe_handle(hinfo["fn"], question, pending) or _FAIL
            if answer != _FAIL:
                session.clear(conv_id)
            return answer

        # ── 2) 최초 질문 파싱
        params = extract_params(question)
        _auto_fill_relative_dates(question, params)
        print(params)
        task   = params.get("task")

        # # 모호(unknown) → 급등주 등 Task4 로
        # if task not in TASK_REGISTRY:
        #     return task4_ambiguous.handle(question)

        missing = _missing_fields(task, params)
        if missing:                             # 정보 더 필요
            session.set(conv_id, params)
            return _build_follow_up(missing)

        # ── 3) 즉시 실행
        hinfo = TASK_REGISTRY[task]
        return _safe_handle(hinfo["fn"], question, params) or _FAIL
    except AmbiguousTickerError as e:
        cur = session.get(conv_id)
        if cur:
            cur["tickers"] = [t for t in cur.get("tickers", []) if t != e.alias]
            session.set(conv_id, cur)
        elif 'params' in locals() and params:           # 첫 질문의 params
            pending = params.copy()
            keep = [t for t in pending.get("tickers", []) if t != e.alias]
            pending['tickers'] = keep                  # ← 후속 답변 채울 자리
            session.set(conv_id, pending)

        sugg = " · ".join(e.candidates)
        return (
            "질문을 더 정확히 이해하기 위해 조회할 종목명을 정확히 알려주세요.\n"
            f"예시: {sugg}"
        )

