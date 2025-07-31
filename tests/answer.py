import requests
import uuid

API_KEY = "nv-7d2217209920476bac7b3691905e2462Q4VS"  # HyperCLOVA API 키
cid = None

while True:
    try:
        q = input("질문 ▶ ").strip()
        if not q:
            break

        url = "http://127.0.0.1:8000/agent"
        params = {"question": q}

        # 요청 고유 ID (각 요청마다 새로 생성)
        request_id = str(uuid.uuid4())

        # 헤더에 API 키와 요청 ID 포함
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "X-NCP-CLOVASTUDIO-REQUEST-ID": request_id
        }

        # 세션 ID는 query param으로 전달
        if cid:
            params["session_id"] = cid

        # GET 요청 전송
        resp = requests.get(url, headers=headers, params=params, timeout=5).json()

        # 응답 출력
        print("Bot:", resp["answer"], resp["session_id"])

        # 응답에 session_id가 있으면 유지
        cid = resp.get("session_id", cid)

    except Exception as e:
        print("⚠️ 오류 발생:", e)
