#!/usr/bin/env python3
"""
tests/test_simple_queries.py
CSV에 수록된 질문 → router.route() 호출 → expected_answer와 비교
성공하면 즉시 출력, 실패한 경우만 나중에 모아 보여준다.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# (프로젝트 루트 경로가 PYTHONPATH에 없다면) 동적 경로 추가
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.router import route  # 라우터가 각 Task 핸들러를 호출

# -------------------------------------------------------------
CSV_PATH  = ROOT / "tests/simple_queries.csv"  # CSV 경로
ENCODING  = "utf-8"                            # 파일 인코딩
MISMATCHES = []                                # 실패 목록

with CSV_PATH.open(encoding=ENCODING, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        q = row["question"].strip()
        expected = row["expected_answer"].strip()

        actual = route(q).strip()

        if actual == expected:
            print(f"✅ PASS: {q} → {actual}", flush=True)
        else:
            # 실패한 질문만 저장 (출력은 나중에)
            MISMATCHES.append((q, expected, actual))

# -------------------------------------------------------------
if not MISMATCHES:
    print("\n🎉 모든 질문이 예상 답과 일치합니다!")
    sys.exit(0)

print(f"\n❌ {len(MISMATCHES)}개 질문이 불일치:\n")
for i, (q, exp, act) in enumerate(MISMATCHES, 1):
    print(f"[{i}] 질문   : {q}")
    print(f"    예상   : {exp}")
    print(f"    실제   : {act}\n")

# 실패 상태 코드
sys.exit(1)
