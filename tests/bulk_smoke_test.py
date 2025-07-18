# tests/bulk_smoke_test.py
import re
import pandas as pd

from app.router import route
from app.session import new_id

CSV_PATH = "tests/simple_queries.csv"  # 필요시 경로 조정

def is_follow_up(resp: str) -> bool:
    """
    봇 응답이 '재질문' 인지 간단히 판별
    """
    if not isinstance(resp, str):
        return False
    resp = resp.strip()
    if resp.endswith("?"):
        return True
    follow_kw = ("날짜", "market", "시장", "종목", "알려", "어느", "확인")
    return any(k in resp for k in follow_kw)

def main() -> None:
    df = pd.read_csv(CSV_PATH)

    total = passes = fails = follow = 0

    for _, row in df.iterrows():
        cid  = new_id()
        q    = str(row["question"])
        exp  = str(row["expected_answer"]).strip()
        resp = route(q, cid).strip()

        if is_follow_up(resp):
            follow += 1
            print(f"🔄 FOLLOW_UP: {q}\n", flush=True)
        else:
            if resp == exp:
                passes += 1
                print(f"✅ PASS: {q} → {resp}\n", flush=True)
            else:
                fails += 1
                print(f"❌ FAIL: {q}\nexpected: '{exp}'\nactual:   '{resp}'\n", flush=True)

        total += 1

    # 요약
    print("\n── Summary ───────────────────────────")
    print(f"TOTAL: {total}  PASS: {passes}  FAIL: {fails}  FOLLOW_UP: {follow}")

if __name__ == "__main__":
    main()
