import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.task_handlers import task1_simple as t1

while(1):
    user_input = input()
    print(t1.handle(user_input) + "\n")

# print(t1.handle("KOSDAQ에서 신라젠의 2024-08-20 종가는?"))
# print(t1.handle("KOSPI에서 NICE평가정보의 2024-07-19 종가는?"))