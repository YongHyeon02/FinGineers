# app/router.py
from __future__ import annotations

from app.task_handlers import (
    task1_simple,
    task2_condition,
    task3_signal,
    task4_ambiguous,
)
from app.parsers import parse_ambiguous

_FAIL = "질문을 이해하지 못했습니다."


def _safe_handle(handler, question: str) -> str | None:
    """
    핸들러 호출 → _FAIL이 아니면 성공으로 간주하여 바로 반환.
    예외 발생 시 None 반환.
    """
    try:
        out = handler(question)
        return out if out != _FAIL else None
    except Exception:
        return None


def route(question: str) -> str:
    question = question.strip()

    # 1️⃣ Task 1 – 단순 조회(가격·통계·순위 등)
    #if (ans := _safe_handle(task1_simple.handle, question)):
    #    return ans

    # # 3️⃣ Task 2 – 조건검색
    if (ans := _safe_handle(task2_condition.handle, question)):
       return ans

    # # 4️⃣ Task 3 – 시그널 감지
    # if (ans := _safe_handle(task3_signal.handle, question)):
    #     return ans
    
    # # 2️⃣ Task 4 – 모호 질의(최근 급등주, 고점 대비 낙폭 등)
    # if parse_ambiguous(question):
    #     if (ans := _safe_handle(task4_ambiguous.handle, question)):
    #         return ans

    # 모두 실패한 경우
    return _FAIL
