import re

def extract_expected(line: str) -> set[str]:
    return {re.sub(r"\([^)]*\)", "", s).strip() for s in line.split(",") if s.strip()}

def extract_actual(line: str) -> set[str]:
    tokens = [s.strip() for s in line.split(",")]
    return {s for s in tokens if re.search(r"[가-힣]", s)}

def process_file(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()

    # 블록 단위 파싱을 위해 줄 정리
    blocks = []
    block = []

    for line in raw_lines:
        stripped = line.strip()
        if stripped == "" and block:
            blocks.append(block)
            block = []
        else:
            block.append(stripped)

    if block:
        blocks.append(block)

    for idx, block in enumerate(blocks):
        if len(block) < 5:
            print(f"[경고] 블록 {idx+1}의 줄 수가 부족합니다. 건너뜀.")
            continue

        meta     = block[0]
        question = block[1]
        expected = extract_expected(block[2].removeprefix("expected:").strip())
        actual   = extract_actual(block[4])

        both = expected & actual
        only_expected = expected - actual
        only_actual = actual - expected

        print("=" * 60)
        print(question)
        print("\n✅ 공통 종목:")
        print(", ".join(sorted(both)) or "(없음)")

        print("\n❌ expected에만 있는 종목:")
        print(", ".join(sorted(only_expected)) or "(없음)")

        print("\n⚠️ actual에만 있는 종목:")
        print(", ".join(sorted(only_actual)) or "(없음)")


# 실행
process_file("a.out")
