# app/router.py (발췌)
import re

from app.task_handlers import task1_simple, task2_condition, task3_signal, task4_ambiguous
from app.parsers import parse_ambiguous

def route(question: str) -> str:
    if re.search(r"(종가|시가|고가|저가|거래량)", question):
        return task1_simple.handle(question)
    if parse_ambiguous(question):
        return task4_ambiguous.handle(question)
    # … Task2·3 규칙 …
    return "질문을 이해하지 못했습니다."
