#!/usr/bin/env python3
"""
tests/test_conditional_queries.py
조건검색 관련 CSV 테스트
route() 호출 → expected_answer와 비교 → 실패한 케이스만 출력
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.router import route

# -------------------------------------------------------------
CSV_PATH  = ROOT / "tests/test_csv/conditional_queries.csv"
ENCODING  = "utf-8"
MISMATCHES = []

with CSV_PATH.open(encoding=ENCODING, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row["question"]:
            continue

        q = row["question"].strip()
        expected = row["expected_answer"].strip()

        actual = route(q).strip()

        if actual == expected:
            print(f"✅ PASS: {q} → {actual}\n", flush=True)
        else:
            print(f"❌ FAIL: {q} \nexpected: {expected!r}\nactual: {actual!r}\n", flush=True)
            MISMATCHES.append((q, expected, actual))

# -------------------------------------------------------------
if not MISMATCHES:
    print("\n🎉 모든 조건검색 테스트가 통과했습니다!")
    sys.exit(0)

print(f"\n❌ {len(MISMATCHES)}개 질문이 실패했습니다:\n")
for i, (q, exp, act) in enumerate(MISMATCHES, 1):
    print(f"[{i}] 질문   : {q}")
    print(f"    예상   : {exp}")
    print(f"    실제   : {act}\n")

sys.exit(1)
