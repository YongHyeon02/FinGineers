# tests/test_task4.py
"""
CLI one-shot tester for Task 4.
Usage:
    python -m tests.test_task4 "최근 많이 오른 주식 알려줘"
"""
import sys
import os
import logging
from app.task_handlers import task4_ambiguous as t4
# from app.task_handlers.task4_ambiguous import handle

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("yfinance").setLevel("WARNING")
logging.getLogger("peewee").setLevel("WARNING")
def main():
    if len(sys.argv) < 2:
        q = input("질문을 입력하세요: ").strip()
    else:
        q = sys.argv[1]
    print(t4.handle(q))

if __name__ == "__main__":
    main()
