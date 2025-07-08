import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.task_handlers import task1_simple as t1

print(t1.handle("동부건설우의 2024-11-06 시가은?"))
print(t1.handle("2025-06-23에 상승한 종목은 몇 개인가?"))
print(t1.handle("금양그린파워의 2024-08-08 종가는?"))
print(t1.handle("2025-06-26 KOSPI 시장에 거래된 종목 수는?"))
print(t1.handle("2025-01-20에서 KOSPI에서 상승률 높은 종목 5개는?"))