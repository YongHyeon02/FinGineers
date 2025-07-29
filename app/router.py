# app/router.py
from __future__ import annotations
import logging
from typing import Callable, Optional, Dict, Any
from app import session                  # ↩︎ 간단한 in-mem 세션 캐시 (앞서 제안)
from app.llm_bridge import extract_params, fill_missing
from app.task_handlers import (
    task_search,
    task1_simple,
    task4_ambiguous,
)
from config import AmbiguousTickerError

logger = logging.getLogger(__name__)
_FAIL = "질문을 이해하지 못했습니다."



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

    for key, val in cond.items():
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
                miss.add("conditions:three_pattern")


def _build_follow_up(missing: set[str]) -> str:
    qmap = {
        "date":    "어느 날짜 기준인지",
        "metrics": "시가·종가·거래량 등 어떤 지표를 원하시는지",
        "tickers": "조회할 종목명이 무엇인지",
        "rank_n":  "상위 몇 개 종목을 원하시는지",
        "conditions": "검색 조건(등락률·거래량 조건 등)이 무엇인지",
        "market":  "KOSPI·KOSDAQ 중 어느 시장인지",                 # 지수 질문에 필요. 추후 확인 필요
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
                if v:
                    pending[k] = v

            filled: dict[str, Any] = {}
            # 사용자가 보낸 follow-up 문장으로 슬롯 채우기
            for slot in _missing_fields(pending["task"], pending):
                v = fill_missing(question, slot)
                # print(f"{slot}: {v}")
                if v:
                    filled.update(v)
                    
            pending.update(filled)
            print(f"updated: {pending}")
            still_missing = _missing_fields(pending["task"], pending)

            if still_missing:                               # 여전히 비어 있음
                session.set(conv_id, pending)
                return _build_follow_up(still_missing)

            # 모든 슬롯 충족 → 실행
            session.clear(conv_id)
            hinfo = TASK_REGISTRY[pending["task"]]
            return _safe_handle(hinfo["fn"], question, pending) or _FAIL

        # ── 2) 최초 질문 파싱
        params = extract_params(question)
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
        if 'params' in locals() and params:           # 첫 질문의 params
            pending = params.copy()
            pending['tickers'] = []                  # ← 후속 답변 채울 자리
            session.set(conv_id, pending)

        sugg = " · ".join(e.candidates)
        return (
            "질문을 더 정확히 이해하기 위해 조회할 종목명을 정확히 알려주세요.\n"
            f"예시: {sugg}"
        )


# def route(question: str, conv_id: str) -> str:
#     question = question.strip()
#     if not question:
#         return _FAIL
    
#     # 1️⃣ Task 1 – 단순 조회(가격·통계·순위 등)
#     # if (ans := _safe_handle(task1_simple.handle, question)):
#     #     return ans

#     # # 3️⃣ Task 2 – 조건검색
#     # if (ans := _safe_handle(task2_condition.handle, question)):
#     #     return ans

#     # # 4️⃣ Task 3 – 시그널 감지
#     # if (ans := _safe_handle(task3_signal.handle, question)):
#     #     return ans
    
#     # # 2️⃣ Task 4 – 모호 질의(최근 급등주, 고점 대비 낙폭 등)
#     # if parse_ambiguous(question):
#     #     return task4_ambiguous.handle(question)

#     # HCX → task 결정
    
#     # ────────────────── 1) 세션에 pending params 있는지 확인 ──────────────────
#     pending = session.get(conv_id)
#     if pending:
#         # 후속 답변으로 누락 부분 보완
#         follow_params = extract_params(question)
#         pending.update({k: v for k, v in follow_params.items() if v})
#         missing = _check_missing(pending)
#         if missing:                          # 여전히 부족 → 다시 질문
#             session.set(conv_id, pending)
#             return _build_follow_up(missing)
#         else:
#             session.clear(conv_id)           # 모두 채워졌으면 세션 종료
#             return _handle_task1(question, pending)  # ← 아래 함수
    
#     # ────────────────── 2) 최초 질문 처리 ──────────────────
#     params = extract_params(question)
#     missing = _check_missing(params)
#     if missing:
#         session.set(conv_id, params)         # 세션에 저장
#         return _build_follow_up(missing)

#     return _handle_task1(question, params)

#     if missing:
#         return _build_follow_up(missing)
    
#     task = params.get("task")
#     if task in ("단순조회","상승종목수","하락종목수","거래종목수","시장순위"):
#         if (ans := _safe_handle(task1_simple.handle, question)):
#             return ans
    
#     # elif task in ("conditional",):
#     #     if (ans := _safe_handle(task2_condition.handle, question)):
#     #         return ans
#     # elif task in ("signal",):
#     #     if (ans := _safe_handle(task3_signal.handle, question)):
#     #         return ans
    
#     return _FAIL
