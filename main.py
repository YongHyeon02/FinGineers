from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.router import route
from app.session import new_id, clear

app = FastAPI()

SESSION_POOL = {}

@app.get("/agent")
async def handle_agent(request: Request):
    question = request.query_params.get("question", "").strip()
    session_id = (
        request.headers.get("X-NCP-CLOVASTUDIO-REQUEST-ID") or
        request.query_params.get("session_id", "")
    ).strip()

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(content={"answer": "API 키가 필요합니다."}, status_code=401)

    api_key = auth_header.removeprefix("Bearer ").strip()

    if not question:
        return JSONResponse(content={"answer": "질문이 비어 있습니다."}, status_code=400)

    cid = session_id or new_id()

    answer = route(question, cid, api_key)

    if not answer.startswith("질문을 더 정확히 이해"):
        clear(cid)

    return JSONResponse(content={"answer": answer})
