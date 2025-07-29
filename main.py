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
        request.headers.get("X-NCP-CLOVASTUDIO-REQUEST-ID")
        or request.query_params.get("session_id", "")
    ).strip()

    if not question:
        return JSONResponse(content={"answer": "질문이 비어 있습니다."}, status_code=400)
    
    cid = session_id or new_id()

    answer = route(question, cid)

    if not answer.startswith("질문을 더 정확히 이해"):
        clear(cid)

    return JSONResponse(content={
        "answer": answer,
        "session_id": cid
    })