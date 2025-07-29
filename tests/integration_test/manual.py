# tests/manual.py
from app.router import route
from app.session import new_id

def run():
    # 1) 모든 필드가 완전한 질문
    cid1 = new_id()
    q1 = "2024-07-15 KOSPI 지수는?"
    print("Q1:", q1)
    print("A1:", route(q1, cid1, api_key="nv-7d2217209920476bac7b3691905e2462Q4VS"), end="\n\n")

    # 2) 날짜가 빠진 질문 → follow-up → 보강 → 최종 응답
    cid2 = new_id()
    q2 = "카카오 종가는?"
    print("Q2-1:", q2)
    follow = route(q2, cid2, api_key="nv-7d2217209920476bac7b3691905e2462Q4VS")          # 누락 필드 질의
    print("Bot:", follow)

    # 사용자가 날짜만 응답했다고 가정
    user_reply = "2024-12-01"
    print("Q2-2:", user_reply)
    final_ans = route(user_reply, cid2, api_key="nv-7d2217209920476bac7b3691905e2462Q4VS")
    print("A2:", final_ans)

# if __name__ == "__main__":
#     while True:
#         cid = new_id()
#         q = input("질문을 입력하세요: ").strip()
#         print(route(q, cid), end="\n\n")
#     # run()

def main():
    cid = new_id()                              # 한 세션 유지
    while True:
        q = input("질문 ▶ ").strip()
        if not q:
            print("테스트 종료.")
            break

        ans = route(q, cid, api_key="nv-7d2217209920476bac7b3691905e2462Q4VS")
        print("Bot:", ans)

        # “정확히 알려주세요” 류 follow-up 요구가 나오면 추가 입력 루프
        while "정확히" in ans and "알려주세요" in ans:
            follow = input("추가 입력 ▶ ").strip()
            if not follow:
                print("테스트 종료.")
                return
            ans = route(follow, cid, api_key="nv-7d2217209920476bac7b3691905e2462Q4VS")
            print("Bot:", ans)

if __name__ == "__main__":
    main()