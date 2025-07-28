import requests

cid = None
while True:
    q = input("질문 ▶ ").strip()
    if not q:
        break

    url = f"http://localhost:8000/agent?question={q}"
    if cid:
        url += f"&session_id={cid}"

    resp = requests.get(url).json()
    print("Bot:", resp["answer"])
    cid = resp.get("session_id", cid)
