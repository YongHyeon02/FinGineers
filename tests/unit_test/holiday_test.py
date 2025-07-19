from app.utils import _holiday_msg, _prev_bday, _next_day

import pandas as pd


def main():
    date_str = input("날짜를 YYYY-MM-DD 형식으로 입력하세요: ")
    # msg = _holiday_msg(date_str)
    msg = _prev_bday(date_str)
    if msg:
        print(msg)

if __name__ == "__main__":
    main()
