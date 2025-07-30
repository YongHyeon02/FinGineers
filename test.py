import requests
import uuid

API_KEY = "nv-7d2217209920476bac7b3691905e2462Q4VS"  # HyperCLOVA API 키

q = "2025년 6월 11일"  # 예시 질문

url = "http://127.0.0.1:8000/agent"
params = {"question": q}

# 요청 고유 ID (각 요청마다 새로 생성)
request_id = "03a1fb9f-5212-43aa-8c2c-ec464bdd2cda"

# 헤더에 API 키와 요청 ID 포함
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "X-NCP-CLOVASTUDIO-REQUEST-ID": request_id
}

# GET 요청 전송
resp = requests.get(url, headers=headers, params=params, timeout=5).json()

# 응답 출력
print("Bot:", resp)
