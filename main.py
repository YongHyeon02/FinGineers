from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.router import route
from app.session import new_id

app = FastAPI()

SESSION_POOL = {}

@app.get("/agent")
async def handle_agent(request: Request):
    question = request.query_params.get("question", "").strip()
    session_id = request.query_params.get("session_id", "").strip()

    if not question:
        return JSONResponse(content={"answer": "질문이 비어 있습니다."}, status_code=400)

    if not session_id or session_id not in SESSION_POOL:
        cid = new_id()
        SESSION_POOL[cid] = True
    else:
        cid = session_id

    answer = route(question, cid)

    return JSONResponse(content={
        "answer": answer,
        "session_id": cid
    })