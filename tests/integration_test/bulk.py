# tests/bulk.py
import json
import re
from pathlib import Path

from app.router import route
from app.session import new_id

JSON_PATH = Path("tests/test_json/simple_queries.json")  # 경로 필요 시 조정

def is_follow_up(resp: str) -> bool:
    """
    봇 응답이 '재질문'인지 판별
    """
    if not isinstance(resp, str):
        return False
    resp = resp.strip()
    return resp.startswith("질문을 더 정확히 이해하기 위해") and resp.endswith("알려주세요.")

def main() -> None:
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    total = passes = fails = follow = 0

    for item in data:
        cid  = new_id()
        q    = str(item["input_data"]["message"])
        exp  = str(item["expected_output"]).strip()
        resp = route(q, cid).strip()

        if is_follow_up(resp):
            follow += 1
            print(f"🔄 FOLLOW_UP: {q}\nfollow up q: {resp}", flush=True)
        else:
            if resp == exp:
                passes += 1
                print(f"✅ PASS: {q} → {resp}\n", flush=True)
            else:
                fails += 1
                print(f"❌ FAIL: {q}\nexpected: '{exp}'\nactual:   '{resp}'\n", flush=True)

        total += 1

    print("\n── Summary ───────────────────────────")
    print(f"TOTAL: {total}  PASS: {passes}  FAIL: {fails}  FOLLOW_UP: {follow}")

if __name__ == "__main__":
    main()
